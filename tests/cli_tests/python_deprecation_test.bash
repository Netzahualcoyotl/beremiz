#!/bin/bash

# Back-compat regression test for the deprecated 'PLCBinary' runtime handle.
#
# Since PLC IOs and logic were split into two shared libraries, runtime
# extension code should reference PLCIOsBinary / PLCLogicBinary explicitly.
# The legacy 'PLCBinary' name is kept as a deprecation shim that resolves a
# symbol against both libraries and logs a one-shot deprecation notice.
#
# tests/projects/python_legacy_plcbinary is a frozen copy of exemples/python
# that still uses 'PLCBinary' on purpose. This test builds/runs it and checks:
#   1. the deprecation notice is emitted ("Deprecation: PLCBinary."), and
#   2. the PLC still runs (the shim resolved the symbol) — "Grumpf" marker.

coproc setsid $BEREMIZPYTHONPATH $BEREMIZPATH/Beremiz_cli.py -k --project-home $BEREMIZPATH/tests/projects/python_legacy_plcbinary clean build transfer run;

seen_deprecation=0

while read -u ${COPROC[0]} line; do
    echo "$line"
    if [[ "$line" == *"Deprecation: PLCBinary."* ]]; then
        seen_deprecation=1
    fi
    if [[ "$line" == *Grumpf* ]]; then
        pkill -9 -s $COPROC_PID
        if [[ $seen_deprecation -eq 1 ]]; then
            exit 0
        fi
        # PLC ran but the deprecation notice was never reported: shim regressed.
        echo "FAIL: 'PLCBinary' deprecation notice was not reported"
        exit 1
    fi
done

exit 42
