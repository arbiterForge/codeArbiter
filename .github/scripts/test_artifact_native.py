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
    "TestContextRecoveryAndPaths",
    "TestContextMutationAdmission",
}
RECOVERY_SUBTESTS = {
    "interruptions_before_and_after_each_replacement",
    "lost_response_replay_and_duplicate_operation_ids",
    "divergent_human_edits_preserve_pending_transaction",
    "symlink_target_fails_before_context_mutation",
    "case_alias_preserves_human_file",
    "case_colliding_transaction_paths_rejected_before_journal",
    "unsupported_journal_blocks_context_write_without_replacement",
}
EXPECTED = REQUIRED | {f"TestContextRecoveryAndPaths/{name}"
                       for name in RECOVERY_SUBTESTS} | {
    "TestContextMutationAdmission/approved_field_update_preserves_human_neighbors",
    "TestContextMutationAdmission/stale_document_and_provenance_pair_do_not_mutate",
    "TestContextMutationAdmission/unowned_or_unsupported_provenance_is_preserved",
}


def main() -> int:
    pattern = "^(" + "|".join(sorted(REQUIRED)) + ")$"
    command = ["go", "test", "-json", "-buildvcs=false",
               "./internal/store", "./internal/operations", "./internal/contextdocument",
               "-run", pattern, "-count=1"]
    result = subprocess.run(command, cwd=REPO / "core/artifacts",
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True)
    passed, skipped = {}, set()
    for line in result.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = event.get("Test")
        if name in EXPECTED and event.get("Action") == "pass":
            passed[name] = passed.get(name, 0) + 1
        if name in EXPECTED and event.get("Action") == "skip":
            skipped.add(name)
    missing = EXPECTED - passed.keys()
    duplicate = {name for name, count in passed.items() if count != 1}
    if result.returncode or missing or duplicate or skipped:
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        print(f"native artifact contract failed; missing={sorted(missing)} "
              f"duplicate={sorted(duplicate)} skipped={sorted(skipped)}",
              file=sys.stderr)
        return 1
    print(f"native artifact contract: {len(passed)}/{len(EXPECTED)} named tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
