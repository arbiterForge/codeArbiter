#!/usr/bin/env python3
"""Embed core/workflow-recovery-contract.json into core/pysrc/_workflowrecoverylib.py.

Only core/pysrc/*.py is vendored into the host plugins (tools/sync-core.py), so
the runtime owner carries an exact generated copy of the closed contract. Run
without arguments to regenerate, or with --check to fail (exit 1) on drift.
Run tools/sync-core.py afterwards to refresh the plugin copies."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONTRACT = REPO / "core" / "workflow-recovery-contract.json"
TARGET = REPO / "core" / "pysrc" / "_workflowrecoverylib.py"
BEGIN = "# BEGIN GENERATED CONTRACT (tools/build-workflow-recovery-contract.py)\n"
END = "# END GENERATED CONTRACT\n"


def render(source_text):
    value = json.loads(source_text)
    body = json.dumps(value, indent=1, sort_keys=True, ensure_ascii=True)
    if "'''" in body or "\\" in body:
        raise SystemExit("contract text cannot be embedded in a raw triple-quoted literal")
    return BEGIN + "_CONTRACT_JSON = r'''" + body + "'''\n" + END


def main(argv):
    check = "--check" in argv
    current = TARGET.read_text(encoding="utf-8")
    start = current.index(BEGIN)
    stop = current.index(END, start) + len(END)
    expected = current[:start] + render(CONTRACT.read_text(encoding="utf-8")) + current[stop:]
    if expected == current:
        print("build-workflow-recovery-contract: current")
        return 0
    if check:
        print("build-workflow-recovery-contract --check: DRIFT in " + str(TARGET.relative_to(REPO)))
        return 1
    TARGET.write_text(expected, encoding="utf-8", newline="\n")
    print("build-workflow-recovery-contract: wrote " + str(TARGET.relative_to(REPO)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
