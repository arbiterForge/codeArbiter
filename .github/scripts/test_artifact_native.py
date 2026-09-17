#!/usr/bin/env python3
"""Run and attest the required native storage/recovery behavior by test name."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
REQUIRED = {
    "TestTransactionalCAS",
    "TestReplaceRecovery",
    "TestRecoveryConflictPreservesExternalEdit",
    "TestPathEscapeAndSymlink",
    "TestWriterLock",
    "TestCreateRaceDoesNotOverwrite",
    "TestProcessDeathRecovery",
    "TestCapabilitiesReportActualStorageBackend",
}


def main() -> int:
    pattern = "^(" + "|".join(sorted(REQUIRED)) + ")$"
    command = ["go", "test", "-json", "-buildvcs=false",
               "./internal/store", "./internal/operations",
               "-run", pattern, "-count=1"]
    result = subprocess.run(command, cwd=REPO / "core/artifacts",
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True)
    passed, skipped = set(), set()
    for line in result.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = event.get("Test")
        if name in REQUIRED and event.get("Action") == "pass":
            passed.add(name)
        if name in REQUIRED and event.get("Action") == "skip":
            skipped.add(name)
    missing = REQUIRED - passed
    if result.returncode or missing or skipped:
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        print(f"native artifact contract failed; missing={sorted(missing)} skipped={sorted(skipped)}",
              file=sys.stderr)
        return 1
    print(f"native artifact contract: {len(passed)}/{len(REQUIRED)} named tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
