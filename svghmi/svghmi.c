#include <pthread.h>
#include <errno.h>
#include <string.h>
#include <stdio.h>
#include "iec_types_all.h"
#include "accessor.h"
#include "beremiz.h"
#include "svghmi.h"

#define DEFAULT_REFRESH_PERIOD_MS 100

/* Defined in split (hot-swap) builds: the logic-side symbols (item array, buffers,
 * geometry, hash) are resolved from the logic .so at runtime via dlsym; otherwise
 * (single-binary SDK / ABI builds) they are referenced by direct linkage. */
%(late_bind)s

/*
 * Everything that depends on the HMI tree / user settings is instantiated on the
 * logic side (svghmi_data.c) and reached here through pointers, (re)resolved at
 * each logic load / hot-swap.  svghmi.c — compiled into the stable IOs .so — is
 * thus independent of HMI content.
 */
static hmi_tree_item_t *hmi_tree_items = NULL;
static const uint8_t *hmi_hash = NULL;

/* PLC reads from rbuf, writes to wbuf; sbuf is the worst-case send buffer. */
static char *rbuf = NULL;
static char *wbuf = NULL;
static char *sbuf = NULL;
static unsigned int sbufidx;

static unsigned int hmi_item_count = 0;
static unsigned int hmi_buffer_size = 0;
static unsigned int hmi_max_connections = 0;
static unsigned int hmi_sbuf_size = 0;
static unsigned int hmi_heartbeat_index = 0;

#define ticktime_ns %(PLC_ticktime)d
static uint16_t ticktime_ms = (ticktime_ns>1000000)?
                     ticktime_ns/1000000:
                     1;

static int global_write_dirty = 0;
static uint32_t hmitree_rlock = 0;
static uint32_t hmitree_wlock = 0;

/* subscription list tail / incoming-changes list tail (reset on each logic bind) */
static hmi_tree_item_t *subscriptions_tail = NULL;
static hmi_tree_item_t *incoming_tail = NULL;

/* Logic-side symbols (svghmi_data.c) gathered at resolve time. */
typedef struct {
    hmi_tree_item_t *items;
    char *rbuf;
    char *wbuf;
    char *sbuf;
    const uint8_t *hash;
    unsigned int item_count;
    unsigned int buffer_size;
    unsigned int max_connections;
    unsigned int sbuf_size;
    unsigned int heartbeat_index;
} svghmi_logic_t;

static svghmi_logic_t bound_logic;
static int bound_ok = 0;

#ifdef SVGHMI_LATE_BIND
#include <dlfcn.h>
/* Resolve logic-side symbols from the (just loaded / swapped-in) logic .so.
 * Runs on the main thread (load / hot-swap prepare) — dlsym only. */
static int svghmi_resolve_logic(void *handle, svghmi_logic_t *l)
{
    const unsigned int *item_count      = dlsym(handle, "svghmi_item_count");
    const unsigned int *buffer_size     = dlsym(handle, "svghmi_buffer_size");
    const unsigned int *max_connections = dlsym(handle, "svghmi_max_connections");
    const unsigned int *sbuf_size       = dlsym(handle, "svghmi_sbuf_size");
    const unsigned int *heartbeat_index = dlsym(handle, "svghmi_heartbeat_index");
    l->items = dlsym(handle, "svghmi_hmi_tree_items");
    l->rbuf  = dlsym(handle, "svghmi_rbuf");
    l->wbuf  = dlsym(handle, "svghmi_wbuf");
    l->sbuf  = dlsym(handle, "svghmi_sbuf");
    l->hash  = dlsym(handle, "svghmi_hmi_hash");
    if(!item_count || !buffer_size || !max_connections || !sbuf_size
       || !heartbeat_index || !l->items || !l->rbuf || !l->wbuf || !l->sbuf || !l->hash)
        return -1;
    l->item_count      = *item_count;
    l->buffer_size     = *buffer_size;
    l->max_connections = *max_connections;
    l->sbuf_size       = *sbuf_size;
    l->heartbeat_index = *heartbeat_index;
    return 0;
}
#else
/* Single-binary build: the logic-side symbols live in the same binary. */
extern hmi_tree_item_t svghmi_hmi_tree_items[];
extern char svghmi_rbuf[];
extern char svghmi_wbuf[];
extern char svghmi_sbuf[];
extern const uint8_t svghmi_hmi_hash[];
extern const unsigned int svghmi_item_count;
extern const unsigned int svghmi_buffer_size;
extern const unsigned int svghmi_max_connections;
extern const unsigned int svghmi_sbuf_size;
extern const unsigned int svghmi_heartbeat_index;
static int svghmi_resolve_logic(void *handle, svghmi_logic_t *l)
{
    (void)handle;
    l->items = svghmi_hmi_tree_items;
    l->rbuf  = svghmi_rbuf;
    l->wbuf  = svghmi_wbuf;
    l->sbuf  = svghmi_sbuf;
    l->hash  = svghmi_hmi_hash;
    l->item_count      = svghmi_item_count;
    l->buffer_size     = svghmi_buffer_size;
    l->max_connections = svghmi_max_connections;
    l->sbuf_size       = svghmi_sbuf_size;
    l->heartbeat_index = svghmi_heartbeat_index;
    return 0;
}
#endif

/* Point the runtime globals at the (fresh) logic-side arrays and reset the
 * subscription lists.  On a hot-swap this discards the previous generation's HMI
 * state — clients are forced to reconnect and re-subscribe. */
static void svghmi_apply_logic(void)
{
    if(!bound_ok) return;
    hmi_tree_items      = bound_logic.items;
    rbuf                = bound_logic.rbuf;
    wbuf                = bound_logic.wbuf;
    sbuf                = bound_logic.sbuf;
    hmi_hash            = bound_logic.hash;
    hmi_item_count      = bound_logic.item_count;
    hmi_buffer_size     = bound_logic.buffer_size;
    hmi_max_connections = bound_logic.max_connections;
    hmi_sbuf_size       = bound_logic.sbuf_size;
    hmi_heartbeat_index = bound_logic.heartbeat_index;
    subscriptions_tail  = NULL;
    incoming_tail       = NULL;
}

#ifdef SVGHMI_LATE_BIND
/*
 * Logic lifecycle hooks (see plc_ios_main_head.c).
 *  __logic_bound_svghmi : main thread, at load and hot-swap prepare — dlsym only.
 *  __logic_active_svghmi: at load, and at hot-swap commit on the PLC thread — no
 *                         dlsym; switches the pointers under the hmitree locks so
 *                         websocket threads never observe a half-updated view.
 */
void __logic_bound_svghmi(void *handle)
{
    bound_ok = (svghmi_resolve_logic(handle, &bound_logic) == 0);
}

void __logic_active_svghmi(void)
{
    while(AtomicCompareExchange(&hmitree_wlock, 0, 1)) nRT_reschedule();
    while(AtomicCompareExchange(&hmitree_rlock, 0, 1)) nRT_reschedule();
    svghmi_apply_logic();
    AtomicCompareExchange(&hmitree_rlock, 1, 0);
    AtomicCompareExchange(&hmitree_wlock, 1, 0);
}
#endif

#define __Unpack_desc_type hmi_tree_item_t

%(var_access_code)s

static int write_iterator(hmi_tree_item_t *dsc)
{
    uint32_t session_index = 0;
    int value_changed = 0;
    void *dest_p = NULL;
    void *value_p = NULL;
    size_t sz = 0;
    int do_sample = 0;
    while(session_index < hmi_max_connections) {
        if(dsc->wstate[session_index] == buf_set){
            /* if being subscribed */
            if(dsc->refresh_period_ms[session_index]){
                uint16_t new_age_ms = dsc->age_ms[session_index] + ticktime_ms;
                if(new_age_ms < dsc->refresh_period_ms[session_index]){
                    dsc->age_ms[session_index] = new_age_ms;
                }else{
                    dsc->wstate[session_index] = buf_tosend;
                    global_write_dirty = 1;
                }
            }
        }

        /* variable is sampled if just subscribed (initial value)
           or already subscribed and having value change */
        int sample_session = 0;
        int just_subscribed = dsc->wstate[session_index] == buf_new;
        if(just_subscribed){
            sample_session = 1;
        } else {
            int already_subscribed = dsc->refresh_period_ms[session_index] > 0;
            if(already_subscribed){
                /* compute value_changed once only */
                if(!value_p){
                    UnpackVar(dsc, &value_p, NULL, &sz);
                    if(__Is_a_string(dsc)){
                        sz = ((STRING*)value_p)->len + 1;
                    }
                    dest_p = &wbuf[dsc->buf_index];
                    value_changed = memcmp(dest_p, value_p, sz) != 0;
                }
                sample_session = value_changed;
            }
        }


        if(sample_session){
            if(dsc->wstate[session_index] != buf_set && dsc->wstate[session_index] != buf_tosend) {
                if(dsc->wstate[session_index] == buf_new \
                   || ticktime_ms > dsc->refresh_period_ms[session_index]){
                    dsc->wstate[session_index] = buf_tosend;
                    global_write_dirty = 1;
                } else {
                    dsc->wstate[session_index] = buf_set;
                }
                dsc->age_ms[session_index] = 0;
            }
            do_sample = 1;
        }

        session_index++;
    }

    /* copy value if one at least one session did sample */
    if(do_sample){
        if(!value_p){
            UnpackVar(dsc, &value_p, NULL, &sz);
            if(__Is_a_string(dsc)){
                sz = ((STRING*)value_p)->len + 1;
            }
            dest_p = &wbuf[dsc->buf_index];
        }
        memcpy(dest_p, value_p, sz);
    }
    return 0;
}

static int send_iterator(uint32_t index, hmi_tree_item_t *dsc, uint32_t session_index)
{
    if(dsc->wstate[session_index] == buf_tosend)
    {
        uint32_t sz = __get_type_enum_size(dsc->type);
        if(sbufidx + sizeof(uint32_t) + sz <=  hmi_sbuf_size)
        {
            void *src_p = &wbuf[dsc->buf_index];
            void *dst_p = &sbuf[sbufidx];
            if(__Is_a_string(dsc)){
                sz = ((STRING*)src_p)->len + 1;
            }
            /* TODO : force into little endian */
            memcpy(dst_p, &index, sizeof(uint32_t));
            memcpy(dst_p + sizeof(uint32_t), src_p, sz);
            dsc->wstate[session_index] = buf_free;
            sbufidx += sizeof(uint32_t) /* index */ + sz;
        }
        else
        {
            printf("BUG!!! %%d + %%ld + %%d >  %%d \n", sbufidx, sizeof(uint32_t), sz,  hmi_sbuf_size);
            return EOVERFLOW;
        }
    }

    return 0;
}

static int read_iterator(hmi_tree_item_t *dsc)
{
    if(dsc->rstate == buf_set)
    {
        void *src_p = &rbuf[dsc->buf_index];
        void *value_p = NULL;
        size_t sz = 0;
        UnpackVar(dsc, &value_p, NULL, &sz);
        memcpy(value_p, src_p, sz);
        dsc->rstate = buf_free;
    }
    return 0;
}

void update_refresh_period(hmi_tree_item_t *dsc, uint32_t session_index, uint16_t refresh_period_ms)
{
    uint32_t other_session_index = 0;
    int previously_subscribed = 0;
    int session_only_subscriber = 0;
    int session_already_subscriber = 0;
    int needs_subscription_for_session = (refresh_period_ms != 0);

    while(other_session_index < session_index) {
        previously_subscribed |= (dsc->refresh_period_ms[other_session_index++] != 0);
    }
    session_already_subscriber = (dsc->refresh_period_ms[other_session_index++] != 0);
    while(other_session_index < hmi_max_connections) {
        previously_subscribed |= (dsc->refresh_period_ms[other_session_index++] != 0);
    }
    session_only_subscriber = session_already_subscriber && !previously_subscribed;
    previously_subscribed |= session_already_subscriber;

    if(needs_subscription_for_session) {
        if(!session_already_subscriber)
        {
            dsc->wstate[session_index] = buf_new;
        }
        /* item is appended to list only when no session was previously subscribed */
        if(!previously_subscribed){
            /* append subsciption to list */
            if(subscriptions_tail != NULL){ 
                /* if list wasn't empty, link with previous tail*/
                subscriptions_tail->subscriptions_next = dsc;
            }
            dsc->subscriptions_prev = subscriptions_tail;
            subscriptions_tail = dsc;
            dsc->subscriptions_next = NULL;
        }
    } else {
        dsc->wstate[session_index] = buf_free;
        /* item is removed from list only when session was the only one remaining */
        if (session_only_subscriber) {
            if(dsc->subscriptions_next == NULL){ /* remove tail  */
                /* re-link tail to previous */
                subscriptions_tail = dsc->subscriptions_prev;
                if(subscriptions_tail != NULL){
                    subscriptions_tail->subscriptions_next = NULL;
                }
            } else if(dsc->subscriptions_prev == NULL){ /* remove head  */
                dsc->subscriptions_next->subscriptions_prev = NULL;
            } else { /* remove entry in between other entries */
                /* re-link previous and next node */
                dsc->subscriptions_next->subscriptions_prev = dsc->subscriptions_prev;
                dsc->subscriptions_prev->subscriptions_next = dsc->subscriptions_next;
            }
            /* unnecessary
            dsc->subscriptions_next = NULL;
            dsc->subscriptions_prev = NULL;
            */
        }
    }
    dsc->refresh_period_ms[session_index] = refresh_period_ms;
}

static void *svghmi_handle;

void SVGHMI_SuspendFromPythonThread(void)
{
    wait_RT_to_nRT_signal(svghmi_handle);
}

void SVGHMI_WakeupFromRTThread(void)
{
    unblock_RT_to_nRT_signal(svghmi_handle);
}

int svghmi_continue_collect;

int __init_svghmi()
{
#ifndef SVGHMI_LATE_BIND
    /* Single-binary build: resolve the same-binary logic symbols and adopt them now
     * (split builds do this from the __logic_bound/__logic_active hooks instead). */
    bound_ok = (svghmi_resolve_logic(NULL, &bound_logic) == 0);
    svghmi_apply_logic();
#endif
    if(hmi_tree_items == NULL)
        return 1;

    /* rbuf/wbuf are zero-initialised static storage on the logic side */

    svghmi_continue_collect = 1;

    /* create svghmi_pipe */
    svghmi_handle = create_RT_to_nRT_signal("SVGHMI_pipe");

    if(!svghmi_handle)
        return 1;

    return 0;
}

void __cleanup_svghmi()
{
    svghmi_continue_collect = 0;
    SVGHMI_WakeupFromRTThread();
    delete_RT_to_nRT_signal(svghmi_handle);
}

void __retrieve_svghmi()
{
    if(AtomicCompareExchange(&hmitree_rlock, 0, 1) == 0) {
        hmi_tree_item_t *dsc = incoming_tail;
        /* iterate through read list (changes from HMI) */
        while(dsc){
            hmi_tree_item_t *_dsc = dsc->incoming_prev;
            read_iterator(dsc);
            /* unnecessary
            dsc->incoming_prev = NULL;
            */
            dsc = _dsc;
        }
        /* flush read list */
        incoming_tail = NULL;
        AtomicCompareExchange(&hmitree_rlock, 1, 0);
    }
}

void __publish_svghmi()
{
    global_write_dirty = 0;

    if(AtomicCompareExchange(&hmitree_wlock, 0, 1) == 0) {
        hmi_tree_item_t *dsc = subscriptions_tail;
        while(dsc){
            write_iterator(dsc);
            dsc = dsc->subscriptions_prev;
        }
        AtomicCompareExchange(&hmitree_wlock, 1, 0);
    }

    if(global_write_dirty) {
        SVGHMI_WakeupFromRTThread();
    }
}

/* PYTHON CALLS */
int svghmi_wait(void){

    SVGHMI_SuspendFromPythonThread();
}

int svghmi_send_collect(uint32_t session_index, uint32_t *size, char **ptr){


    if(svghmi_continue_collect) {
        int res;
        sbufidx = HMI_HASH_SIZE;

        while(AtomicCompareExchange(&hmitree_wlock, 0, 1)){
            nRT_reschedule();
        }

        hmi_tree_item_t *dsc = subscriptions_tail;
        while(dsc){
            uint32_t index = dsc - hmi_tree_items;
            res = send_iterator(index, dsc, session_index);
            if(res != 0){
                break;
            }
            dsc = dsc->subscriptions_prev;
        }
        if(res == 0)
        {
            if(sbufidx > HMI_HASH_SIZE){
                memcpy(&sbuf[0], &hmi_hash[0], HMI_HASH_SIZE);
                *ptr = &sbuf[0];
                *size = sbufidx;
                AtomicCompareExchange(&hmitree_wlock, 1, 0);
                return 0;
            }
            AtomicCompareExchange(&hmitree_wlock, 1, 0);
            return ENODATA;
        }
        AtomicCompareExchange(&hmitree_wlock, 1, 0);
        return res;
    }
    else
    {
        return EINTR;
    }
}

typedef enum {
    unset = -1,
    setval = 0,
    reset = 1,
    subscribe = 2
} cmd_from_JS;

int svghmi_reset(uint32_t session_index){
    hmi_tree_item_t *dsc = subscriptions_tail;
    while(AtomicCompareExchange(&hmitree_wlock, 0, 1)){
        nRT_reschedule();
    }
    while(dsc){
        hmi_tree_item_t *_dsc = dsc->subscriptions_prev;
        update_refresh_period(dsc, session_index, 0);
        dsc = _dsc;
    }
    AtomicCompareExchange(&hmitree_wlock, 1, 0);
    return 1;
}

// Returns :
//   0 is OK, <0 is error, 1 is heartbeat
int svghmi_recv_dispatch(uint32_t session_index, uint32_t size, const uint8_t *ptr){
    const uint8_t* cursor = ptr + HMI_HASH_SIZE;
    const uint8_t* end = ptr + size;

    int was_hearbeat = 0;

    /* match hmitree fingerprint */
    if(size <= HMI_HASH_SIZE || memcmp(ptr, hmi_hash, HMI_HASH_SIZE) != 0)
    {
        printf("svghmi_recv_dispatch MISMATCH !!\n");
        return -EINVAL;
    }

    int ret;
    int got_wlock = 0;
    int got_rlock = 0;
    cmd_from_JS cmd_old = unset;
    cmd_from_JS cmd = unset;

    while(cursor < end)
    {
        uint32_t progress;

        cmd_old = cmd;
        cmd = *(cursor++);


        if(cmd_old != cmd){
            if(got_wlock){
                AtomicCompareExchange(&hmitree_wlock, 1, 0);
                got_wlock = 0;
            }
            if(got_rlock){
                AtomicCompareExchange(&hmitree_rlock, 1, 0);
                got_rlock = 0;
            }
        }
        switch(cmd)
        {
            case setval:
            {
                uint32_t index; //  = *(uint32_t*)(cursor);
                uint8_t const *valptr = cursor + sizeof(uint32_t);

                // unaligned access forces memcpy instead of cast
                memcpy(&index, cursor, sizeof(uint32_t));

                if(index == hmi_heartbeat_index)
                    was_hearbeat = 1;

                if(index < hmi_item_count)
                {
                    hmi_tree_item_t *dsc = &hmi_tree_items[index];
                    size_t sz = 0;
                    void *dst_p = &rbuf[dsc->buf_index];

                    if(__Is_a_string(dsc)){
                        sz = ((STRING*)valptr)->len + 1;
                    } else {
                        UnpackVar(dsc, NULL, NULL, &sz);
                    }

                    if((valptr + sz) <= end)
                    {
                        // rescheduling spinlock until free
                        if(!got_rlock){
                            while(AtomicCompareExchange(&hmitree_rlock, 0, 1)){
                                nRT_reschedule();
                            }
                            got_rlock=1;
                        }

                        memcpy(dst_p, valptr, sz);

                        /* check that rstate is not already buf_set */
                        if(dsc->rstate != buf_set){
                            dsc->rstate = buf_set;
                            /* append entry to read list (changes from HMI) */
                            dsc->incoming_prev = incoming_tail;
                            incoming_tail = dsc;
                        }

                        progress = sz + sizeof(uint32_t) /* index */;
                    }
                    else
                    {
                        ret = -EINVAL;
                        goto exit_free;
                    }
                }
                else
                {
                    ret = -EINVAL;
                    goto exit_free;
                }
            }
            break;

            case reset:
            {
                progress = 0;
                if(!got_wlock){
                    while(AtomicCompareExchange(&hmitree_wlock, 0, 1)){
                        nRT_reschedule();
                    }
                    got_wlock = 1;
                }
                {
                    hmi_tree_item_t *dsc = subscriptions_tail;
                    while(dsc){
                        hmi_tree_item_t *_dsc = dsc->subscriptions_prev;
                        update_refresh_period(dsc, session_index, 0);
                        dsc = _dsc;
                    }
                }
            }
            break;

            case subscribe:
            {
                uint32_t index; // = *(uint32_t*)(cursor);
                uint16_t refresh_period_ms; // = *(uint32_t*)(cursor + sizeof(uint32_t));

                // unaligned access forces memcpy instead of cast
                memcpy(&index, cursor, sizeof(uint32_t));
                memcpy(&refresh_period_ms, cursor+sizeof(uint32_t), sizeof(uint16_t));

                if(index < hmi_item_count)
                {
                    if(!got_wlock){
                        while(AtomicCompareExchange(&hmitree_wlock, 0, 1)){
                            nRT_reschedule();
                        }
                        got_wlock = 1;
                    }
                    hmi_tree_item_t *dsc = &hmi_tree_items[index];
                    update_refresh_period(dsc, session_index, refresh_period_ms);
                }
                else
                {
                    ret = -EINVAL;
                    goto exit_free;
                }

                progress = sizeof(uint32_t) /* index */ +
                           sizeof(uint16_t) /* refresh period */;
            }
            break;
            default:
                printf("svghmi_recv_dispatch unknown %%d\n",cmd);

        }
        cursor += progress;
    }
    ret = was_hearbeat;

exit_free:
    if(got_wlock){
        AtomicCompareExchange(&hmitree_wlock, 1, 0);
        got_wlock = 0;
    }
    if(got_rlock){
        AtomicCompareExchange(&hmitree_rlock, 1, 0);
        got_rlock = 0;
    }
    return ret;
}

