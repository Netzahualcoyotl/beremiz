/*
 * DEBUGGER code
 * 
 * On "publish", when buffer is free, debugger stores arbitrary variables 
 * content into, and mark this buffer as filled
 * 
 * 
 * Buffer content is read asynchronously, (from non real time part), 
 * and then buffer marked free again.
 *  
 * 
 * */
#ifdef TARGET_DEBUG_AND_RETAIN_DISABLE

int __init_debug    (void){return 0;}
void __cleanup_debug (void){}
void __retrieve_debug(void){}
void __publish_debug (void){}

#else

/*for memcpy*/
#include <string.h>
#include <stdio.h>
#include <errno.h>

#include "beremiz.h"

#include "accessor.h"
#include "iec_std_lib.h"
#include "POUS.h"

#include "undef_macros.h"
#include "pous_flatcount_c.h"
#include "POUS.h"

#include "undef_macros.h"
#include "pous_recurse_c.h"
#include "POUS.h"

typedef unsigned int uint32_t;

#define BUFFER_EMPTY 0
#define BUFFER_FULL 1

typedef struct {
    void *ptr;
    __IEC_types_enum type;
} resolved_var_t;

#ifndef TARGET_ONLINE_DEBUG_DISABLE

#define TRACE_BUFFER_SIZE 4096
#define TRACE_LIST_SIZE 1024

/* Atomically accessed variable for buffer state */
static uint32_t trace_buffer_state = BUFFER_EMPTY;

typedef struct trace_item_s {
    resolved_var_t var;
} trace_item_t;

trace_item_t trace_list[TRACE_LIST_SIZE];
char trace_buffer[TRACE_BUFFER_SIZE];

/* Trace's cursor*/
static trace_item_t *trace_list_collect_cursor = trace_list;
static trace_item_t *trace_list_addvar_cursor = trace_list;
static const trace_item_t *trace_list_end = 
    &trace_list[TRACE_LIST_SIZE-1];
static char *trace_buffer_cursor = trace_buffer;
static const char *trace_buffer_end = trace_buffer + TRACE_BUFFER_SIZE;



#define FORCE_BUFFER_SIZE 1024
#define FORCE_LIST_SIZE 256

typedef struct force_item_s {
    resolved_var_t var;
    void *value_pointer_backup;
} force_item_t;

force_item_t force_list[FORCE_LIST_SIZE];
char force_buffer[FORCE_BUFFER_SIZE];

/* Force's cursor*/
static force_item_t *force_list_apply_cursor = force_list;
static force_item_t *force_list_addvar_cursor = force_list;
static const force_item_t *force_list_end = 
    &force_list[FORCE_LIST_SIZE-1];
static char *force_buffer_cursor = force_buffer;
static const char *force_buffer_end = force_buffer + FORCE_BUFFER_SIZE;


#endif

/* Retain list — built once at init, iterated at every publish */
#define RETAIN_LIST_SIZE 4096

typedef struct {
    void *value_ptr;
    size_t size;
} retain_item_t;

static retain_item_t retain_list[RETAIN_LIST_SIZE];
static unsigned int retain_list_count = 0;
static unsigned int retain_total_size = 0;

/***
 * Declare global variables from resources and conf 
 **/
%(extern_variables_declarations)s

#define __Unpack_desc_type resolved_var_t

%(var_access_code)s

/***
 * Retain list collection callbacks
 **/
typedef struct {
    retain_item_t *cursor;
    retain_item_t *end;
    unsigned int total_size;
} __retain_collect_ctx_t;

/* Compact form: collect ALL leaves unconditionally */
static int __retain_collect_all_cb(
    __IEC_types_enum type, void *ptr,
    unsigned int cumulated, unsigned int local,
    unsigned int count, const char *name, void *userdata)
{
    if (count > 1) return 1;  /* recurse deeper */
    __retain_collect_ctx_t *ctx = (__retain_collect_ctx_t *)userdata;
    void *value_p = NULL;
    size_t size = 0;
    resolved_var_t dsc = {ptr, type};
    UnpackVar(&dsc, &value_p, NULL, &size);
    if (ctx->cursor < ctx->end) {
        ctx->cursor->value_ptr = value_p;
        ctx->cursor->size = size;
        ctx->cursor++;
    }
    ctx->total_size += size;
    return 1;
}

/* Check retain flag on each leaf, add if retained */
static int __retain_check_flags_cb(
    __IEC_types_enum type, void *ptr,
    unsigned int cumulated, unsigned int local,
    unsigned int count, const char *name, void *userdata)
{
    if (count > 1) return 1;  /* recurse into sub-FBs/complex */
    __retain_collect_ctx_t *ctx = (__retain_collect_ctx_t *)userdata;
    void *value_p = NULL;
    char flags = 0;
    size_t size = 0;
    resolved_var_t dsc = {ptr, type};
    UnpackVar(&dsc, &value_p, &flags, &size);
    if (flags & __IEC_RETAIN_FLAG) {
        if (ctx->cursor < ctx->end) {
            ctx->cursor->value_ptr = value_p;
            ctx->cursor->size = size;
            ctx->cursor++;
        }
        ctx->total_size += size;
    }
    return 1;
}

/***
 * Resolve a flat variable index to pointer and type
 * using __recurse accessors from POUS_accessors.h
 **/
typedef struct {
    unsigned int target_local;
    void *found_ptr;
    __IEC_types_enum found_type;
} __resolve_ctx_t;

static int __resolve_cb(
    __IEC_types_enum type, void *ptr,
    unsigned int cumulated, unsigned int local,
    unsigned int count, const char *name, void *userdata)
{
    __resolve_ctx_t *ctx = (__resolve_ctx_t *)userdata;
    if (count > 1) {
        if (ctx->target_local >= cumulated &&
            ctx->target_local < cumulated + count)
            return 1;   /* target is within subtree, recurse */
        /* target is not in this subtree — skip it.
         * Return -1 to hit the else { *cumulated += count; } branch
         * in both struct and array __recurse functions.
         * (Must not return count+1: array __recurse interprets
         *  ret > 1 as "skip ret-1 array elements", not flat count.) */
        return -1;
    }
    /* leaf */
    if (cumulated == ctx->target_local) {
        ctx->found_ptr = ptr;
        ctx->found_type = type;
        return 0;       /* stop */
    }
    return 1;           /* continue */
}

%(resolve_function)s

%(build_retain_list)s

/***
 * Instance tree scan — call a Python callback for every node
 * using __recurse accessors from POUS_accessors.h
 **/
typedef int (*__scan_callback_t)(
    __IEC_types_enum type, void *ptr,
    unsigned int cumulated, unsigned int local,
    unsigned int count, const char *name, void *userdata);

typedef struct {
    __scan_callback_t callback;
    void *userdata;
} __scan_ctx_t;

static int __scan_cb(
    __IEC_types_enum type, void *ptr,
    unsigned int cumulated, unsigned int local,
    unsigned int count, const char *name, void *userdata)
{
    __scan_ctx_t *ctx = (__scan_ctx_t *)userdata;
    return ctx->callback(type, ptr, cumulated, local, count,
                         name ? name : "", ctx->userdata);
}

%(scan_instances)s

void Remind(unsigned int offset, unsigned int count, void * p);

extern int CheckRetainBuffer(void);
extern int InitRetain(size_t);

int __init_debug(void)
{
    /* init local static vars */
#ifndef TARGET_ONLINE_DEBUG_DISABLE
    trace_buffer_cursor = trace_buffer;
    trace_list_addvar_cursor = trace_list;
    trace_list_collect_cursor = trace_list;
    trace_buffer_state = BUFFER_EMPTY;

    force_buffer_cursor = force_buffer;
    force_list_addvar_cursor = force_list;
    force_list_apply_cursor = force_list;
#endif

    __build_retain_list();

    int res = InitRetain(retain_total_size);
    if (res != 0) {
        char mstr[] = "RETAIN memory cannot be allocated";
        LogMessage(LOG_WARNING, mstr, sizeof(mstr));
        return res;
    }
    if (CheckRetainBuffer()) {
        unsigned int offset = 0;
        unsigned int i;
        for (i = 0; i < retain_list_count; i++) {
            Remind(offset, retain_list[i].size, retain_list[i].value_ptr);
            offset += retain_list[i].size;
        }
    } else {
        char mstr[] = "RETAIN memory invalid - defaults used";
        LogMessage(LOG_WARNING, mstr, sizeof(mstr));
    }
    return 0;
}

extern void InitiateDebugTransfer(int tick);
extern void CleanupRetain(void);

void __cleanup_debug(void)
{
#ifndef TARGET_ONLINE_DEBUG_DISABLE
    trace_buffer_cursor = trace_buffer;
    InitiateDebugTransfer(__tick);
#endif

    CleanupRetain();
}

void __retrieve_debug(void)
{
}

void Retain(unsigned int offset, unsigned int count, void * p);

/* Return size of all retain variables */
unsigned int GetRetainSize(void)
{
    return retain_total_size;
}


extern int TryEnterDebugSection(void);
extern uint32_t AtomicCompareExchange(uint32_t*, uint32_t, uint32_t);
extern void LeaveDebugSection(void);
extern void ValidateRetainBuffer(void);
extern void InValidateRetainBuffer(void);

#ifndef TARGET_ONLINE_DEBUG_DISABLE

#define __ReForceOutput_case_p(TYPENAME)                                                            \
        case TYPENAME##_P_ENUM :                                                                    \
        case TYPENAME##_O_ENUM :                                                                    \
            {                                                                                       \
                char *next_cursor = force_buffer_cursor + sizeof(TYPENAME);                         \
                if(next_cursor <= force_buffer_end ){                                               \
                    /* outputs real value must be systematically forced */                          \
                    if(vartype == TYPENAME##_O_ENUM)                                                \
                        /* overwrite value pointed by backup */                                     \
                        *((TYPENAME *)force_list_apply_cursor->value_pointer_backup) =              \
                            *((TYPENAME *)force_buffer_cursor);                                     \
                    /* inc force_buffer cursor */                                                   \
                    force_buffer_cursor = next_cursor;                                              \
                }else{                                                                              \
                    stop = 1;                                                                       \
                }                                                                                   \
            }                                                                                       \
            break;

#endif

void __publish_debug(void)
{
    InValidateRetainBuffer();

#ifndef TARGET_ONLINE_DEBUG_DISABLE
    /* Check there is no running debugger re-configuration */
    if(TryEnterDebugSection()){
        /* Lock buffer */
        uint32_t latest_state = AtomicCompareExchange(
            &trace_buffer_state,
            BUFFER_EMPTY,
            BUFFER_FULL);

        /* If buffer was free */
        if(latest_state == BUFFER_EMPTY)
        {
            int stop = 0;

            /* Reset force buffer cursor */
            force_buffer_cursor = force_buffer;
            /* Reset force list cursor */
            force_list_apply_cursor = force_list;

            /* iterate over force list */
            while(!stop && force_list_apply_cursor < force_list_addvar_cursor){
                __IEC_types_enum vartype = force_list_apply_cursor->var.type;
                switch(vartype){
                    __ANY(__ReForceOutput_case_p)
                    __ReForceOutput_case_p(ENUM)
                default:
                    break;
                }
                force_list_apply_cursor++;
            }

            /* Reset buffer cursor */
            trace_buffer_cursor = trace_buffer;
            /* Reset trace list cursor */
            trace_list_collect_cursor = trace_list;

            /* iterate over trace list */
            while(trace_list_collect_cursor < trace_list_addvar_cursor){
                void *value_p = NULL;
                size_t size = 0;
                char* next_cursor;

                resolved_var_t *dsc = &trace_list_collect_cursor->var;

                UnpackVar(dsc, &value_p, NULL, &size);

                /* copy visible variable to buffer */;
                if(__Is_a_string(dsc)){
                    /* optimization for strings */
                    /* assume NULL terminated strings */
                    size = ((STRING*)value_p)->len + 1;
                }

                /* compute next cursor positon.*/
                next_cursor = trace_buffer_cursor + size;
                /* check for buffer overflow */
                if(next_cursor < trace_buffer_end)
                    /* copy data to the buffer */
                    memcpy(trace_buffer_cursor, value_p, size);
                else
                    /* stop looping in case of overflow */
                    break;
                /* increment cursor according size*/
                trace_buffer_cursor = next_cursor;
                trace_list_collect_cursor++;
            }

            /* Leave debug section,
             * Trigger asynchronous transmission
             * (returns immediately) */
            if (trace_list_collect_cursor != trace_list)
            {
                InitiateDebugTransfer(__tick); /* size */
            }
        }
        LeaveDebugSection();
    }
#endif
    /* Save retain variables */
    {
        unsigned int offset = 0;
        unsigned int i;
        for (i = 0; i < retain_list_count; i++) {
            Retain(offset, retain_list[i].size, retain_list[i].value_ptr);
            offset += retain_list[i].size;
        }
    }
    ValidateRetainBuffer();
}

#ifndef TARGET_ONLINE_DEBUG_DISABLE

#define TRACE_LIST_OVERFLOW    1
#define FORCE_LIST_OVERFLOW    2
#define FORCE_BUFFER_OVERFLOW  3
#define FORCE_INVALID  4

#define __ForceVariable_checksize(TYPENAME)                                             \
    if(sizeof(TYPENAME) != force_size) {                                                \
        error_code = FORCE_BUFFER_OVERFLOW;                                             \
        goto error_cleanup;                                                             \
    }

/*
 * Force setup macros — no size check, caller guarantees type match.
 * Used by ForceVariable(); RegisterDebugVariable() validates size first.
 **/
#define __Force_case_t(TYPENAME)                                                        \
        case TYPENAME##_ENUM: {                                                         \
            force_list_addvar_cursor->var = resolved;                                   \
            ((__IEC_##TYPENAME##_t *)varp)->flags |= __IEC_FORCE_FLAG;                  \
            ((__IEC_##TYPENAME##_t *)varp)->value = *((TYPENAME *)force_value);         \
            break; }

#define __Force_case_p(TYPENAME)                                                        \
        case TYPENAME##_P_ENUM:                                                         \
        case TYPENAME##_O_ENUM: {                                                       \
            char *next_cursor = force_buffer_cursor + sizeof(TYPENAME);                 \
            if(next_cursor > force_buffer_end)                                          \
                return FORCE_BUFFER_OVERFLOW;                                           \
            force_list_addvar_cursor->var = resolved;                                   \
            /* outputs real value must be systematically forced */                      \
            if(vartype == TYPENAME##_O_ENUM)                                            \
                *(((__IEC_##TYPENAME##_p *)varp)->value) = *((TYPENAME *)force_value);  \
            /* save pointer to backup */                                                \
            force_list_addvar_cursor->value_pointer_backup =                            \
                ((__IEC_##TYPENAME##_p *)varp)->value;                                  \
            /* store forced value in force_buffer */                                    \
            *((TYPENAME *)force_buffer_cursor) = *((TYPENAME *)force_value);            \
            /* replace pointer with pointer to force_buffer */                          \
            ((__IEC_##TYPENAME##_p *)varp)->value = (TYPENAME *)force_buffer_cursor;    \
            /* mark variable as forced */                                               \
            ((__IEC_##TYPENAME##_p *)varp)->flags |= __IEC_FORCE_FLAG;                  \
            /* inc force_buffer cursor */                                               \
            force_buffer_cursor = next_cursor;                                          \
            break; }

/*
 * ForceVariable — set up force_list entry and apply force to a variable.
 *
 * Called by RegisterDebugVariable (after size check) and by execute_copy_ops
 * (via plc_force_var_fn function pointer) to reconstruct forces across a hot-swap.
 * force_value must point to a value of the correct size for type.
 **/
int ForceVariable(void *ptr, __IEC_types_enum type, void *force_value)
{
    if(force_list_addvar_cursor > force_list_end)
        return FORCE_LIST_OVERFLOW;

    void *varp = ptr;
    __IEC_types_enum vartype = type;
    resolved_var_t resolved = {ptr, type};

    /* GCC false-positive: __IEC_STRING_t.flags is at offset 127;
     * GCC sees small objects and warns. STRING_ENUM only resolves to __IEC_STRING_t. */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wstringop-overflow"
    switch(type){
        __ANY(__Force_case_t)
        __ANY(__Force_case_p)
        __Force_case_t(ENUM)
        __Force_case_p(ENUM)
        default: return 0;
    }
#pragma GCC diagnostic pop
    force_list_addvar_cursor++;
    return 0;
}

/* Size-check-only case macros for RegisterDebugVariable.
 * Validate Python-provided force_size before delegating to ForceVariable. */
#define __ForceVariable_checksize_t(TYPENAME)                                           \
        case TYPENAME##_ENUM:                                                           \
            __ForceVariable_checksize(TYPENAME) break;

#define __ForceVariable_checksize_p(TYPENAME)                                           \
        case TYPENAME##_P_ENUM:                                                         \
        case TYPENAME##_O_ENUM:                                                         \
            __ForceVariable_checksize(TYPENAME) break;

void ResetDebugVariables(void);

int RegisterDebugVariable(uint32_t idx, void* force, size_t force_size)
{
    int error_code = 0;
    resolved_var_t resolved;
    if(resolve_instance(idx, &resolved) == 0){
        /* add to trace_list */
        if(trace_list_addvar_cursor <= trace_list_end){
            trace_list_addvar_cursor->var = resolved;
            trace_list_addvar_cursor++;
        } else {
            error_code = TRACE_LIST_OVERFLOW;
            goto error_cleanup;
        }
        if(force){
            /* Validate size of Python-provided force data before applying */
            __IEC_types_enum vartype = resolved.type;
            switch(vartype){
                __ANY(__ForceVariable_checksize_t)
                __ANY(__ForceVariable_checksize_p)
                __ForceVariable_checksize_t(ENUM)
                __ForceVariable_checksize_p(ENUM)
                default: break;
            }
            error_code = ForceVariable(resolved.ptr, resolved.type, force);
            if(error_code)
                goto error_cleanup;
        }
    }
    return 0;

error_cleanup:
    ResetDebugVariables();
    return error_code;

}

#define ResetForcedVariable_case_t(TYPENAME)                                            \
        case TYPENAME##_ENUM :                                                          \
            ((__IEC_##TYPENAME##_t *)varp)->flags &= ~__IEC_FORCE_FLAG;                 \
            break;

#define ResetForcedVariable_case_p(TYPENAME)                                            \
        case TYPENAME##_O_ENUM :                                                        \
        case TYPENAME##_P_ENUM :                                                        \
            ((__IEC_##TYPENAME##_p *)varp)->flags &= ~__IEC_FORCE_FLAG;                 \
            /* restore backup to pointer */                                             \
            ((__IEC_##TYPENAME##_p *)varp)->value =                                     \
                force_list_apply_cursor->value_pointer_backup;                          \
            break;

void ResetDebugVariables(void)
{
    /* Reset trace list */
    trace_list_addvar_cursor = trace_list;

    force_list_apply_cursor = force_list;
    /* Restore forced variables */
    while(force_list_apply_cursor < force_list_addvar_cursor){
        void *varp = force_list_apply_cursor->var.ptr;
        switch(force_list_apply_cursor->var.type){
            __ANY(ResetForcedVariable_case_t)
            __ANY(ResetForcedVariable_case_p)
            ResetForcedVariable_case_t(ENUM)
            ResetForcedVariable_case_p(ENUM)
        default:
            break;
        }
        /* inc force_list cursor */
        force_list_apply_cursor++;
    }

    /* Reset force list */
    force_list_addvar_cursor = force_list;
    /* Reset force buffer */
    force_buffer_cursor = force_buffer;

    trace_buffer_state = BUFFER_EMPTY;
}

void FreeDebugData(void)
{
    /* atomically mark buffer as free */
    AtomicCompareExchange(
        &trace_buffer_state,
        BUFFER_FULL,
        BUFFER_EMPTY);
}
int WaitDebugData(unsigned int *tick);
/* Wait until debug data ready and return pointer to it */
int GetDebugData(unsigned int *tick, unsigned int *size, void **buffer){
    int wait_error = WaitDebugData(tick);
    if(!wait_error){
        *size = trace_buffer_cursor - trace_buffer;
        *buffer = trace_buffer;
    }
    return wait_error;
}
#endif
#endif
