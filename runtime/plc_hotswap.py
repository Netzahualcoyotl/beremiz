#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This file is part of Beremiz runtime.
#
# Copyright (C) 2026: Edouard TISSERANT
#
# See COPYING.Runtime file for copyrights details.

"""
PLC logic hot-swap support: instance tree reconciliation and ctypes copy-ops.

Used by PLCObject._HotSwapPLCLogic() to build the list of variable state
copy operations that the PLC thread executes at the next cycle boundary.
"""

import ctypes
from collections import namedtuple
from threading import Thread, Event

from runtime.typemapping import IEC_types_enum

# Callback type matching __scan_callback_t / __recurse_cb_t in plc_debug.c
SCAN_CB_FUNC = ctypes.CFUNCTYPE(
    ctypes.c_int,    # return value (1=continue, 0=stop)
    ctypes.c_int,    # type (__IEC_types_enum)
    ctypes.c_void_p, # ptr to __IEC_xxx_t instance
    ctypes.c_uint,   # cumulated flat index
    ctypes.c_uint,   # local index within parent
    ctypes.c_uint,   # count (>1 → container, ==1 → leaf)
    ctypes.c_char_p, # name
    ctypes.c_void_p) # userdata


class CopyOp(ctypes.Structure):
    """Matches copy_op_t in plc_ios_main_head.c."""
    _fields_ = [
        ("type", ctypes.c_int),     # __IEC_types_enum value
        ("src",  ctypes.c_void_p),  # pointer into old instance memory
        ("dst",  ctypes.c_void_p),  # pointer into new instance memory
    ]


def scan_lib_instances(scan_fn, config_only=False):
    """Walk a logic library's instance tree via its ScanInstances function.

    scan_fn: ctypes function with signature ScanInstances(cb, userdata,
             config_only) — e.g. new_lib.ScanInstances (already typed as
             SCAN_CB_FUNC, c_void_p, c_int).
    config_only: restrict the walk to configuration domain globals.

    Yields tuples identical to PLCObject.PLCScan():
        (path, type_category, type_enum_value, ptr,
         cumulated, local, count, name, userdata)

    Uses the same thread+Event hand-shake pattern as PLCScan so that both
    generators can be consumed in parallel from the main thread without
    unrolling either tree.
    """
    item_ready = Event()
    item_consumed = Event()
    result = [None]
    done = [False]
    abort = [False]
    stack = []  # [[path_prefix, flat_count, type_category, done], ...]

    @SCAN_CB_FUNC
    def scan_callback(type_enum_value, ptr, cumulated, local, count, name, userdata):
        name_str = name.decode() if name else ""

        if stack and stack[-1][1] == (local + count):
            stack[-1][3] = True

        type_category = IEC_types_enum.Categorize(type_enum_value)
        path = name_str if not stack else (stack[-1][0] + (
            "[%d/%d]" % (local, stack[-1][1])
            if stack[-1][2] == IEC_types_enum.ARRAY else
            "." + name_str))

        if type_category in [IEC_types_enum.ARRAY, IEC_types_enum.STRUCT]:
            stack.append([path, count, type_category, False])
        else:
            while stack and stack[-1][3]:
                stack.pop()

        result[0] = (path, type_category, type_enum_value, ptr,
                     cumulated, local, count, name_str, userdata)
        item_ready.set()
        item_consumed.wait()
        item_consumed.clear()

        return 0 if abort[0] else 1

    def run_scan():
        scan_fn(scan_callback, None, 1 if config_only else 0)
        done[0] = True
        item_ready.set()

    t = Thread(target=run_scan, name="PLCNewLogicScan")
    t.start()

    try:
        while True:
            item_ready.wait()
            item_ready.clear()
            if done[0]:
                break
            yield result[0]
            item_consumed.set()
    finally:
        abort[0] = True
        item_consumed.set()
        t.join()


def reconcile_instance_trees(old_gen, new_gen):
    """Two-pointer streaming merge of old and new instance trees.

    Both generators yield tuples with:
        [0] path (str)
        [1] type_category (IEC_types_enum.ARRAY / STRUCT / SIMPLE / ...)
        [2] type_enum_value (int, __IEC_types_enum)
        [3] ptr (int, ctypes pointer to __IEC_xxx_t instance)

    Yields (type_enum, old_ptr, new_ptr) for every matched leaf node whose
    type is unchanged.  Container nodes (ARRAY, STRUCT) are skipped — they
    have no state of their own; their sub-variables are matched individually.

    Memory is bounded by the divergence depth (add/remove/rename at any level),
    not by the total tree size.
    """
    CONTAINERS = {IEC_types_enum.ARRAY, IEC_types_enum.STRUCT}

    def leaf_filter(gen):
        for item in gen:
            if item[1] not in CONTAINERS:
                yield item

    old_it = leaf_filter(old_gen)
    old_pending = {}   # path → item, bounded by local divergence
    old_node = next(old_it, None)

    for new_node in new_gen:
        if new_node[1] in CONTAINERS:
            continue  # skip container nodes from new_gen too

        new_path = new_node[0]
        new_type = new_node[2]
        new_ptr  = new_node[3]

        # Fast path: both generators at the same position (common case)
        if old_node is not None and old_node[0] == new_path:
            if old_node[2] == new_type:
                yield (new_type, old_node[3], new_ptr)
            old_node = next(old_it, None)
            continue

        # Check the buffer of previously seen old nodes
        if new_path in old_pending:
            old_n = old_pending.pop(new_path)
            if old_n[2] == new_type:
                yield (new_type, old_n[3], new_ptr)
            continue

        # Advance old stream until we find the matching path (or exhaust it)
        while old_node is not None and old_node[0] != new_path:
            old_pending[old_node[0]] = old_node
            old_node = next(old_it, None)

        if old_node is not None and old_node[0] == new_path:
            if old_node[2] == new_type:
                yield (new_type, old_node[3], new_ptr)
            old_node = next(old_it, None)
        # else: new_node has no matching old node → left at config_init__() defaults


SnapshotOps = namedtuple("SnapshotOps", ["save", "restore", "count", "buffer"])


def build_copy_ops_array(ops_gen):
    """Build a ctypes CopyOp array from a generator of (type_enum, src, dst) triples.

    Returns (array_or_None, count).  The returned array must be kept alive
    (stored in an instance variable) until the PLC thread has consumed it.
    """
    ops = list(ops_gen)  # O(matched_vars) — acceptable; tree streaming already done
    count = len(ops)
    if count == 0:
        return None, 0
    arr = (CopyOp * count)()
    for i, (type_enum, src, dst) in enumerate(ops):
        arr[i].type = type_enum
        arr[i].src  = src
        arr[i].dst  = dst
    return arr, count


def build_snapshot_ops(scan_gen, type_size):
    """Build the ops that carry configuration globals across __init_PLCLogicState().

    Those globals are stored in the IOs .so and every logic .so reaches them
    through symbol interposition, so initializing the tree of a logic .so about
    to be swapped in resets the ones the running program still uses.  The PLC
    thread saves them into a scratch buffer and restores them right after, in one
    pass, so the reset is never observable.

    scan_gen is expected to be a configuration-domain-only scan: resource scoped
    instances live in the logic .so alone and are carried over by the copy ops
    instead, so snapshotting them would cost a scratch slot each for nothing.

    type_size maps an __IEC_types_enum value to the size of its wrapper, 0 for
    the ones execute_save_ops does not copy (located and output variables, whose
    .value is a pointer the reset legitimately re-fills).  A first pass lays the
    buffer out from those sizes, so it holds exactly what is snapshotted.

    Returns a SnapshotOps, whose arrays and buffer must be kept alive until the
    PLC thread has consumed them.
    """
    CONTAINERS = {IEC_types_enum.ARRAY, IEC_types_enum.STRUCT}

    # First pass: keep the leaves worth saving and lay out their slots.  Offsets
    # are 8 byte aligned, which satisfies the alignment of every IEC wrapper.
    sizes = {}
    slots = []
    total = 0
    for item in scan_gen:
        type_enum, ptr = item[2], item[3]
        if item[1] in CONTAINERS or not ptr:
            continue
        size = sizes.get(type_enum)
        if size is None:
            size = sizes[type_enum] = type_size(type_enum)
        if size == 0:
            continue
        slots.append((type_enum, ptr, total))
        total += (size + 7) & ~7

    count = len(slots)
    if count == 0:
        return SnapshotOps(None, None, 0, None)

    buffer = (ctypes.c_uint64 * (total // 8))()
    base = ctypes.addressof(buffer)

    save = (CopyOp * count)()
    restore = (CopyOp * count)()
    for i, (type_enum, addr, offset) in enumerate(slots):
        slot = base + offset
        save[i].type = restore[i].type = type_enum
        save[i].src,    save[i].dst    = addr, slot
        restore[i].src, restore[i].dst = slot, addr

    return SnapshotOps(save, restore, count, buffer)
