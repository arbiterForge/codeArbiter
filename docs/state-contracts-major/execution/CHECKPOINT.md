# Program checkpoint — live

Resume protocol: read current Git state first (`git fetch; git log major/state-contracts`), then `execution/progress.json`, then this file. Intake PLANNED/NOT_RUN labels are history, not status.

- **Repository:** arbiterForge/codeArbiter (origin verified)
- **Integration branch:** `major/state-contracts`
- **Active writer:** Claude Code session (2026-11-12). Codex: check `progress.json.active_writer` before writing.
- **Current head and inspected main base:** head = the commit carrying this file; base = `33abc347` (main at branch creation). Audit baseline `fd7eb34b`; 15 commits between. Drift worklist: `execution/source-drift-33abc347.json`.
- **Candidate versions and tag availability observation:** proposed ca 4.0.0 (unused). ca-codex/ca-pi/ca-sandbox candidates not yet chosen (P-01). Current published: v3.8.7, ca-codex-v0.26.7, ca-pi-v0.27.7, ca-sandbox-v0.1.10. ca-pi-v0.27.4/0.27.5 still draft.
- **Completed task IDs with evidence links:** none.
- **Implemented but unqualified task IDs:** P-00 (in progress — bootstrap imported; committed-blob hash check and disposable-clone exercise remaining).
- **Next runnable task IDs and owners:** P-01 (release-and-integration), P-02 (integration-architect).
- **Scoped decisions still needed from B:** D-PROGRESS (blocks NT-09), D-HIGH (blocks HW-09/HW-20), D-GOV-PRETAG (blocks R-03), delete_branch_on_merge handling (needed before Q-03 only).
- **Actual commands/tests executed:** `tools/validate_packet.py --repo . --initial` → PASSED (structure only), Windows 11 / Python 3.14.
- **Source/artifact digests tested:** intake MANIFEST.json 105 sha256 entries match imported bytes.
- **Pending transaction, authority, cleanup, publication or receipt outcomes:** none.
- **Safe recovery action for each unknown outcome:** n/a.
- **Current rollback boundary:** whole branch is additive; nothing merged to main, no tags/releases/Pages/marketplace effects.
- **Exact next action:** P-01 — extend `.github/workflows/ci.yml` admission to `major/state-contracts` and implement the integration candidate-version rule in both version-gate owners.

## Environment notes

- `tools/validate_packet.py` on Windows: run with `python -X utf8` (it reads text with the locale codec) and normalize relative path separators (its manifest population check compares `str(Path)` to `/`-separated names). A shim outside the corpus did this without editing the validator. On Linux it runs unmodified.
- Repo `delete_branch_on_merge=true`: the final promotion PR merge would delete this branch unless handled (see progress.json pending decisions).
