#!/bin/bash
#
# PLC logic hot-swap test.
#
# Flow:
#  1. Start a Beremiz runtime on a random port.
#  2. Build + transfer + run the python example (v1).
#  3. Wait for "Python extensions started" — confirms PLC is running.
#  4. Kill v1 CLI (frees eRPC server connection; PLC keeps running).
#  5. Copy the project, change a variable initial value (logic-only change).
#  6. Build v2 using the SAME build path as v1.
#     Because the IO extension sources are unchanged, toolchain_gcc reuses
#     the existing IOs .so (same MD5); only the logic .so gets a new MD5.
#  7. Transfer v2 + keep-alive (new CLI, same runtime).
#     Hot-swap fires: PLCObject sees same IOs MD5, new logic MD5.
#  8. Verify "Hot-swap: logic updated" appears in new CLI log — swap happened
#     without stopping the PLC.
#
# Detection strategy:
#  - "Python extensions started" in v1 CLI log → PLC is up with Python ext
#  - "Hot-swap:" in v2 CLI log               → _HotSwapPLCLogic completed
#  - Absence of "PLC stopped" in v2 CLI log   → PLC survived the swap
#
# Note: the eRPC Python simple_server handles one client at a time.
# Killing the v1 CLI before the v2 transfer ensures the server accepts
# the v2 connection cleanly.

set -euo pipefail

RUNTIME_PORT=$(( RANDOM % 1000 + 61131 ))
RUNTIME_TMPDIR=$(mktemp -d)
TEST_TMPDIR=$(mktemp -d)

rm -f ./PLC_OK ./PLC_CONNECTED

cleanup() {
    # Kill CLI coproc session if still alive
    pkill -9 -s "${CLI_PID:-0}" 2>/dev/null || true
    # Kill the runtime coproc session
    pkill "${RUNTIME_PID:-0}" 2>/dev/null || true
    # Kill background runtime-drain process
    kill "${DRAIN_PID:-0}" 2>/dev/null || true
    rm -rf "$RUNTIME_TMPDIR" "$TEST_TMPDIR"
}
trap cleanup EXIT

# --- Step 1: Start runtime on a random port ---
$BEREMIZPYTHONPATH $BEREMIZPATH/Beremiz_service.py -p "$RUNTIME_PORT" -i 127.0.0.1 -x 0 "$RUNTIME_TMPDIR" &> >(
    echo "Start PLC loop"
    while read line; do
        # Wait for server to print modified value
        echo "PLC>> $line"
        if [[ "$line" == *"$RUNTIME_TMPDIR"* ]]; then
            echo "PLC is connected"
            touch ./PLC_CONNECTED
        fi
        if [[ "$line" == *"Hot-swap works"* ]]; then
            echo "PLC was re-programmed"
            touch ./PLC_OK
        fi
    done
    echo "End PLC loop"
) &
RUNTIME_PID=$!

echo wait for runtime to come up
res=110  # default to ETIMEDOUT
c=30
while ((c--)); do
    if [[ -a ./PLC_CONNECTED ]]; then
        res=0  # OK success
        break
    else
        sleep 1
    fi
done

# --- Step 2: Prepare two project copies ---
BUILD_DIR="$TEST_TMPDIR/build"
cp -a "$BEREMIZPATH/exemples/python" "$TEST_TMPDIR/python_v1"
cp -a "$BEREMIZPATH/exemples/python" "$TEST_TMPDIR/python_v2"

# Logic-only change: update the python_eval print string in plc.xml.
# This changes POUS.c (logic .so) but nothing in the IO extension files
# (IOs .so).  The shared build dir means toolchain_gcc will reuse the IOs
# .so from v1 unmodified.
sed -i 's/Hello world/Hot-swap works/' "$TEST_TMPDIR/python_v2/plc.xml"

# --- Step 3: Build + transfer + run v1 ---
coproc CLI ( setsid "$BEREMIZPYTHONPATH" "$BEREMIZPATH/Beremiz_cli.py" -k \
        --uri "ERPC://127.0.0.1:$RUNTIME_PORT" \
        --project-home "$TEST_TMPDIR/python_v1" \
        --buildpath "$BUILD_DIR" \
        clean build transfer run )
# Named coproc: bash sets CLI_PID automatically.

# --- Step 4: Wait for "Python extensions started" (PLC up with Python ext) ---
plc_v1_up=0
while read -u "${CLI[0]}" -t 120 line; do
    echo "CLI: $line"
    if [[ "$line" == *"Python extensions started"* ]]; then
        plc_v1_up=1
        break
    fi
    if [[ "$line" == *"Problem installing"* ]] || [[ "$line" == *"can't load PLC"* ]]; then
        echo "FAILED: PLC v1 failed to install"
        exit 1
    fi
done
if [[ $plc_v1_up -eq 0 ]]; then
    echo "FAILED: PLC v1 did not start (no 'Python extensions started' in CLI output)"
    exit 1
fi
echo ">>> PLC v1 running."

# --- Step 5: Disconnect v1 CLI so the server accepts the v2 connection ---
# The eRPC server handles one client at a time.  Killing v1 CLI frees the
# server; the PLC thread continues running independently of the client.
pkill -9 -s "${CLI_PID}" 2>/dev/null || true
CLI_PID=0  # prevent double-kill in cleanup
sleep 1    # allow server to process the disconnect and call accept() again

echo ">>> Initiating hot-swap to v2..."

# --- Step 6: Build v2 + hot-swap transfer + verify (new CLI, same runtime) ---
# -k: keep-alive after transfer so the keep-alive loop can read the
# "Hot-swap:" log message written by PLCObject after the swap.
coproc CLI ( setsid "$BEREMIZPYTHONPATH" "$BEREMIZPATH/Beremiz_cli.py" -k \
        --uri "ERPC://127.0.0.1:$RUNTIME_PORT" \
        --project-home "$TEST_TMPDIR/python_v2" \
        --buildpath "$BUILD_DIR" \
        build transfer )

saw_hotswap=0
while read -u "${CLI[0]}" -t 120 line; do
    echo "CLI2: $line"
    if [[ "$line" == *"Hot-swap:"* ]]; then
        saw_hotswap=1
        break
    fi
    if [[ "$line" == *"PLC stopped"* ]]; then
        echo "FAILED: PLC was stopped during hot-swap"
        exit 1
    fi
    if [[ "$line" == *"Problem installing"* ]] || [[ "$line" == *"can't load PLC"* ]]; then
        echo "FAILED: v2 install failed (full reload instead of hot-swap)"
        exit 1
    fi
done
if [[ $saw_hotswap -eq 0 ]]; then
    echo "FAILED: no 'Hot-swap:' confirmation in CLI2 output after transfer"
    exit 1
fi

echo ">>> HOT-SWAP SUCCESS: PLC logic swapped without restart."

# --- Step 7: Verify the new logic runs — "Hot-swap works" must appear in runtime output ---
echo wait for runtime to come up
res=110  # default to ETIMEDOUT
c=30
while ((c--)); do
    if [[ -a ./PLC_OK ]]; then
        res=0  # OK success
        echo ">>> OUTPUT VERIFIED: new logic printed 'Hot-swap works'."
        break
    else
        sleep 1
    fi
done

exit $res
