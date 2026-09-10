/**
 * Head of code for the IOs shared object.
 *
 * Contains: extension dispatch, PLC cycle entry, and hot-swap mechanism.
 * The PLC logic (config_run__, ScanInstances, etc.) lives in a separate
 * shared object loaded via loadPLCLogic() / preparePLCLogicSwap().
 **/

#include "beremiz.h"
#include "iec_types_all.h"
#include <stdatomic.h>
#include <dlfcn.h>
#include <string.h>

/*
 * Prototypes of functions provided by generated target C code
 **/

// Retain buffer handling
int CheckRetainBuffer(void);
void ValidateRetainBuffer(void);
void InValidateRetainBuffer(void);
void Retain(unsigned int offset, unsigned int count, void *p);
void Remind(unsigned int offset, unsigned int count, void *p);
void CleanupRetain(void);
int InitRetain(size_t buffer_size);

// Debug
#ifndef PLC_NO_DEBUG
int TryEnterDebugSection(void);
void InitiateDebugTransfer(int tick);
#endif

// Logging
#ifndef PLC_USES_ABI /* not on PLC side if using ABI */
#ifndef PLC_NO_LOGGING
void __init_logging(void);
#endif
#endif

/*
 * Per-extension logic lifecycle hooks (optional, weakly linked).
 * Emitted per IO-extension location; an extension implements them only if it
 * keeps state tied to the logic .so (e.g. pointers into logic-side memory that
 * must be re-resolved across hot-swaps, or eval queues to re-enable):
 *   void __logic_bound_<loc>(void *handle); // main thread: new logic .so bound
 *   void __logic_active_<loc>(void);        // logic .so became active / swapped in
 * NULL (skipped) for extensions that provide neither.
 */
%(logic_hook_prototypes)s

/*
 *  Variables used by generated C softPLC and plugins
 **/
IEC_TIME __CURRENT_TIME = {0, 0};
unsigned int __tick = 0;
char *PLC_ID = 0;
char *PLC_SERVICE_NAME = 0;

/*
 * Local copies of PLC timing constants.
 * Defined here so plc_Linux_main.c (GetCommonTickTime) can access them.
 * Updated from logic .so values by loadPLCLogic().
 **/
unsigned long long common_ticktime__ = 1000000; /* 1ms default */
unsigned long greatest_tick_count__ = 0;

/* Help to quit cleanly when init fail at a certain level */
static int init_level = 0;

/*
 * Prototypes of functions exported by IO extensions
 **/
%(calls_prototypes)s

/*
 * Function pointer types for PLC logic .so interface
 **/
typedef void (*plc_logic_cycle_fn_t)(unsigned int tick);
typedef void (*plc_scan_fn_t)(void *cb, void *userdata, int config_only);
/* config_init__ wrapper, see __init_PLCLogicState in plc_logic_main.c */
typedef void (*plc_logic_state_init_fn_t)(void);

/* Currently active logic cycle and scan functions */
static volatile plc_logic_cycle_fn_t plc_logic_run_fn = NULL;
static volatile plc_scan_fn_t plc_logic_scan_fn = NULL;

/*
 * GetRetainSize wrapper.
 *
 * plc_${target}_main_retain.c declares GetRetainSize() as extern and calls it
 * at InitRetain() time (after both .so files are loaded).  The real
 * implementation is in plc_debug.c (logic .so), so we provide a thin wrapper
 * here that calls through a function pointer set by loadPLCLogic().
 **/
typedef int (*get_retain_size_fn_t)(void);
static get_retain_size_fn_t _plc_GetRetainSize = NULL;

/*
 * ForceVariable proxy — delegates to the currently active logic .so.
 * Called from execute_copy_ops to reconstruct the force list after hot-swap.
 **/
typedef int (*force_var_fn_t)(void *, __IEC_types_enum, void *);
static volatile force_var_fn_t plc_force_var_fn = NULL;

/* plc_${target}_main_retain.c declares this as 'int GetRetainSize(void)' */
int GetRetainSize(void)
{
    return _plc_GetRetainSize ? _plc_GetRetainSize() : 0;
}

/*
 * Hot-swap pending state.
 * Set by Python main thread via preparePLCLogicSwap().
 * Consumed by PLC thread at the next cycle boundary (best-effort).
 **/
typedef struct {
    int type;    /* __IEC_types_enum value */
    void *src;   /* pointer into old instance memory */
    void *dst;   /* pointer into new instance memory */
} copy_op_t;

static _Atomic int swap_pending = 0;  /* 0=idle 1=ops ready 2=done */
static copy_op_t *swap_ops = NULL;
static size_t swap_ops_count = 0;
static plc_logic_cycle_fn_t swap_run_fn = NULL;
static plc_scan_fn_t swap_scan_fn = NULL;
static get_retain_size_fn_t swap_get_retain_size = NULL;
static force_var_fn_t swap_force_var_fn = NULL;

/*
 * Instance tree init of a logic .so about to be swapped in, first half of the
 * hot-swap.  Config level globals live in the IOs .so and every logic .so
 * reaches them through symbol interposition, so __init_PLCLogicState() resets
 * the ones the running program is still using.  Snapshotting them either side
 * of that reset in a single PLC thread pass is what keeps it unobservable.
 * The snapshot covers the whole old instance tree rather than just the shared
 * globals: telling them apart needs the new tree's addresses, which only exist
 * once this has run.  Restoring a variable the reset never touched is a no-op.
 **/
static _Atomic int init_pending = 0;  /* 0=idle 1=ops ready 2=done */
static copy_op_t *init_save_ops = NULL;
static size_t init_save_ops_count = 0;
static copy_op_t *init_restore_ops = NULL;
static size_t init_restore_ops_count = 0;
static plc_logic_state_init_fn_t init_state_fn = NULL;

/*
 * Execute instance state copy ops — called from PLC thread during hot-swap.
 * Uses the same __ANY-based switch pattern as var_access.c UnpackVar().
 *
 * For each variable that had __IEC_FORCE_FLAG set in the old instance,
 * plc_force_var_fn (→ ForceVariable in the new logic .so) is called to
 * reconstruct the force_list entry so forced variables remain forced.
 * plc_force_var_fn is updated to the new logic before execute_copy_ops runs.
 **/
#define __Copy_case_t(TYPENAME) \
    case TYPENAME##_ENUM: { \
        __IEC_##TYPENAME##_t *s = ((__IEC_##TYPENAME##_t *)op->src); \
        __IEC_##TYPENAME##_t *d = ((__IEC_##TYPENAME##_t *)op->dst); \
        d->value = s->value; \
        d->flags = (s->flags & __IEC_FORCE_FLAG) \
                 | (d->flags & __IEC_RETAIN_FLAG); \
        if ((s->flags & __IEC_FORCE_FLAG) && plc_force_var_fn) \
            plc_force_var_fn(op->dst, (__IEC_types_enum)op->type, &s->value); \
        break; }

/* Located/output vars: .value pointer is re-set by config_init__() in the new logic.
 * If the variable was forced, reconstruct the force_list entry via plc_force_var_fn;
 * s->value still points into the old force_buffer (old .so remains mapped until
 * _PendingOldLogicHandle is closed on the next NewPLC call). */
#define __Copy_case_p(TYPENAME) \
    case TYPENAME##_P_ENUM: \
    case TYPENAME##_O_ENUM: { \
        __IEC_##TYPENAME##_p *s = ((__IEC_##TYPENAME##_p *)op->src); \
        if ((s->flags & __IEC_FORCE_FLAG) && plc_force_var_fn) \
            plc_force_var_fn(op->dst, (__IEC_types_enum)op->type, s->value); \
        break; }

static void execute_copy_ops(copy_op_t *ops, size_t count)
{
    for (size_t i = 0; i < count; i++) {
        copy_op_t *op = &ops[i];
        switch ((__IEC_types_enum)op->type) {
            __ANY(__Copy_case_t)
            __ANY(__Copy_case_p)
            __Copy_case_t(ENUM)
            __Copy_case_p(ENUM)
            default: break;
        }
    }
}

/*
 * Size of one __IEC_*_t wrapper, so that Python can lay the save buffer out to
 * fit exactly what it snapshots.  0 for anything not copied by
 * execute_save_ops, which lets the caller skip it altogether.
 **/
#define __Size_case_t(TYPENAME) \
    case TYPENAME##_ENUM: return sizeof(__IEC_##TYPENAME##_t);

size_t plcIECTypeSize(int type)
{
    switch ((__IEC_types_enum)type) {
        __ANY(__Size_case_t)
        __Size_case_t(ENUM)
        default: return 0;
    }
}

/*
 * Snapshot ops — plain wrapper copy, used both ways around __init_PLCLogicState.
 * Deliberately not execute_copy_ops: that reconstructs force_list entries for
 * forced variables, which would register the scratch buffer as a forced
 * variable's address on the way out, and register the running logic's forces a
 * second time on the way back.  Copying the wrapper whole carries the flags
 * over as they were, which is all a snapshot round trip needs.
 **/
#define __Save_case_t(TYPENAME) \
    case TYPENAME##_ENUM: \
        *((__IEC_##TYPENAME##_t *)op->dst) = *((__IEC_##TYPENAME##_t *)op->src); \
        break;

static void execute_save_ops(copy_op_t *ops, size_t count)
{
    for (size_t i = 0; i < count; i++) {
        copy_op_t *op = &ops[i];
        switch ((__IEC_types_enum)op->type) {
            __ANY(__Save_case_t)
            __Save_case_t(ENUM)
            default: break;   /* located/output vars: .value is a pointer that
                               * __init_PLCLogicState() legitimately re-sets */
        }
    }
}

/*
 * Resolve the three logic-side symbols shared by both load and swap paths.
 * Returns 0 on success, -1 if either mandatory function is missing.
 * GetRetainSize is optional (NULL if absent).
 **/
static int _resolve_logic_fns(void *handle,
                               plc_logic_cycle_fn_t *run,
                               plc_scan_fn_t        *scan,
                               get_retain_size_fn_t *get_retain,
                               force_var_fn_t       *force_var)
{
    *run  = (plc_logic_cycle_fn_t)dlsym(handle, "plc_logic_cycle");
    *scan = (plc_scan_fn_t)       dlsym(handle, "ScanInstances");
    /* Resolve via specific handle so we get the logic .so's own implementation,
     * not the global-namespace wrapper defined in this file. */
    *get_retain = (get_retain_size_fn_t)dlsym(handle, "GetRetainSize");
    *force_var  = (force_var_fn_t)      dlsym(handle, "ForceVariable");
    return (*run && *scan) ? 0 : -1;
}

/*
 * Load new PLC logic at startup or after full reload.
 * Called from Python main thread (not PLC thread) — dlsym is safe here.
 * Also reads common_ticktime__ and greatest_tick_count__ from the logic .so:
 * those constants are guaranteed stable across hot-swaps (a change would
 * produce a different IOs .so MD5, preventing hot-swap).
 **/
int loadPLCLogic(void *handle)
{
    plc_logic_cycle_fn_t run;
    plc_scan_fn_t scan;
    get_retain_size_fn_t get_retain;
    force_var_fn_t force_var;

    if (_resolve_logic_fns(handle, &run, &scan, &get_retain, &force_var) != 0)
        return -1;

    unsigned long long *ctt =
        (unsigned long long *)dlsym(handle, "common_ticktime__");
    unsigned long *gtc =
        (unsigned long *)dlsym(handle, "greatest_tick_count__");

    if (ctt) common_ticktime__ = *ctt;
    if (gtc) greatest_tick_count__ = *gtc;

    _plc_GetRetainSize = get_retain;
    plc_force_var_fn   = force_var;
    plc_logic_scan_fn  = scan;
    plc_logic_run_fn   = run;

    /* Notify extensions: new logic .so bound, then active (main thread, PLC idle). */
    %(logic_bound_calls)s
    %(logic_active_calls)s
    return 0;
}

/*
 * Prepare a hot-swap.
 * Resolves logic symbols from the new handle (Python main thread — safe).
 * Sets swap_pending=1; PLC thread applies the swap on its next cycle.
 * Timing constants (common_ticktime__, greatest_tick_count__) are not
 * updated: a change there requires a new IOs .so (different MD5) and
 * therefore a full reload, not a hot-swap.
 **/
int preparePLCLogicSwap(void *handle, copy_op_t *ops, size_t count)
{
    plc_logic_cycle_fn_t run;
    plc_scan_fn_t scan;
    get_retain_size_fn_t get_retain;
    force_var_fn_t force_var;

    if (_resolve_logic_fns(handle, &run, &scan, &get_retain, &force_var) != 0)
        return -1;

    swap_run_fn          = run;
    swap_scan_fn         = scan;
    swap_get_retain_size = get_retain;
    swap_force_var_fn    = force_var;
    swap_ops             = ops;
    swap_ops_count       = count;

    /* Let extensions resolve against the new logic .so here (main thread — dlsym safe);
     * activation is deferred to the swap commit in PLC_run. */
    %(logic_bound_calls)s

    atomic_store(&swap_pending, 1);
    return 0;
}

/*
 * Prepare the init half of a hot-swap.
 * Resolves __init_PLCLogicState from the new handle (Python main thread — safe)
 * and hands over the snapshot ops.  The PLC thread runs the three of them back
 * to back on its next cycle, so the config level globals shared with the
 * running logic are never observable at their initial values.
 **/
int preparePLCLogicInit(void *handle,
                        copy_op_t *save_ops, size_t save_count,
                        copy_op_t *restore_ops, size_t restore_count)
{
    plc_logic_state_init_fn_t state_init =
        (plc_logic_state_init_fn_t)dlsym(handle, "__init_PLCLogicState");

    if (!state_init)
        return -1;

    init_state_fn          = state_init;
    init_save_ops          = save_ops;
    init_save_ops_count    = save_count;
    init_restore_ops       = restore_ops;
    init_restore_ops_count = restore_count;

    atomic_store(&init_pending, 1);
    return 0;
}

int getPLCLogicInitState(void)
{
    return atomic_load(&init_pending);
}

int cancelPLCLogicInit(void)
{
    int expected = 1;
    return atomic_compare_exchange_strong(&init_pending, &expected, 0) ? 1 : 0;
}

/*
 * Hot-swap barrier for Python: 1 while the swap is still pending, 2 once the
 * PLC thread committed it.  PLCObject waits for it to leave 1 before building
 * the new logic's retain list, which needs the flags __init_PLCLogicState() set.
 **/
int getPLCLogicSwapState(void)
{
    return atomic_load(&swap_pending);
}

/*
 * Withdraw a swap the PLC thread has not picked up yet.
 * Returns 1 if the swap was cancelled, 0 if it had already been committed.
 **/
int cancelPLCLogicSwap(void)
{
    int expected = 1;
    return atomic_compare_exchange_strong(&swap_pending, &expected, 0) ? 1 : 0;
}

/*
 * ScanInstances proxy — delegates to the currently active logic .so.
 * Called by PLCObject Python code for debug variable inspection.
 **/
void ScanInstances(void *cb, void *userdata, int config_only)
{
    plc_scan_fn_t fn = plc_logic_scan_fn;
    if (fn) fn(cb, userdata, config_only);
}

/*
 * PLC_run: retrieve IO inputs, run PLC logic cycle, publish IO outputs.
 * Also checks for a pending hot-swap at the top of each cycle.
 **/
unsigned int PLC_run(unsigned int periods_passed)
{
    PLC_GetTime(&__CURRENT_TIME);

    __tick += periods_passed;

    if (greatest_tick_count__)
        __tick %%= greatest_tick_count__;

    /* Hot-swap, first half: initialize the instance tree of the logic .so about
     * to be swapped in, snapshotting the globals it shares with the running one
     * around that reset.  Plain wrapper copies both ways, so a forced variable
     * keeps its flags without its force_list entry being registered twice. */
    if (atomic_load(&init_pending) == 1) {
        execute_save_ops(init_save_ops, init_save_ops_count);
        init_state_fn();
        execute_save_ops(init_restore_ops, init_restore_ops_count);
        atomic_store(&init_pending, 2);  /* signal Python: tree initialized */
    }

    /* Best-effort hot-swap: check flag set by Python main thread */
    if (atomic_load(&swap_pending) == 1) {
        /* Update ForceVariable pointer BEFORE execute_copy_ops so that
         * force_list entries are reconstructed in the new logic .so. */
        plc_force_var_fn   = swap_force_var_fn;
        execute_copy_ops(swap_ops, swap_ops_count);
        /* Switch remaining logic symbols */
        plc_logic_run_fn   = swap_run_fn;
        plc_logic_scan_fn  = swap_scan_fn;
        _plc_GetRetainSize = swap_get_retain_size;

        /* Activate the swapped-in logic for extensions, atomically with the run fn
         * (PLC thread: hooks must not dlsym here — resolve was done in prepare). */
        %(logic_active_calls)s

        atomic_store(&swap_pending, 2);  /* signal Python: swap done */
    }

    %(retrieve_calls)s

    if (plc_logic_run_fn)
        plc_logic_run_fn(__tick);

    %(publish_calls)s

    return __tick;
}

/*
 * PLC_init: initialize IO extensions only.
 * PLC logic initialization is done separately via loadPLCLogic().
 **/

#ifdef PLC_USES_ABI
extern beremiz_plc_ABI *beremiz_plc_interface_ptr;
#define EXT_INIT_ARGS(index) beremiz_plc_interface_ptr->argcs[index],beremiz_plc_interface_ptr->argvs[index]
#else
#define EXT_INIT_ARGS(index) 0,NULL
#endif

int PLC_init(int argc, char **argv)
{
    int res = 0;
    init_level = 0;

    if (!common_ticktime__)
        common_ticktime__ = 1000000;

#ifndef PLC_USES_ABI /* not on PLC side if using ABI */
#ifndef PLC_NO_LOGGING
    __init_logging();
#endif
#endif

    %(init_calls)s
    return res;
}

/*
 * PLC_cleanup: cleanup IO extensions.
 **/
void PLC_cleanup(void)
{
    %(cleanup_calls)s
}

/*
 * Extensions requirements
 **/
#define EXTENSIONS_REQUIREMENTS \
%(extensions_requirements)s

/*
 * plc_${target_name}_main.c is concatenated verbatim after this
 **/
