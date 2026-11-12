# Program checkpoint — live

Resume protocol: read current Git state first (`git fetch; git log major/state-contracts`), then `execution/progress.json`, then this file. Intake PLANNED/NOT_RUN labels are history, not status.

- **Repository:** arbiterForge/codeArbiter (origin verified)
- **Integration branch:** `major/state-contracts`
- **Active writer:** Claude Code session (2026-11-12). Codex: check `progress.json.active_writer` before writing.
- **Current head and inspected main base:** head = the commit carrying this file; base = `33abc347` (main at branch creation). Audit baseline `fd7eb34b`; 15 commits between. Drift worklist: `execution/source-drift-33abc347.json`.
- **Candidate versions and tag availability observation:** integration candidates (provisional, `.github/integration-candidate.json`): ca 4.0.0, ca-codex 0.30.0, ca-pi 0.30.0, ca-sandbox 0.2.0 - all untagged 2026-11-12; re-select at freeze. Current published: v3.8.7, ca-codex-v0.26.7, ca-pi-v0.27.7, ca-sandbox-v0.1.10. ca-pi-v0.27.4/0.27.5 still draft.
- **Completed task IDs with evidence links:** none.
- **Implemented but unqualified task IDs:** P-00 (committed-blob hashes verified 104/105; evidence zip awaits override ack; disposable-clone exercise remaining). P-01 (integration candidate rule + workflow admission; local suites green; hosted run observation pending).
- **Next runnable task IDs and owners:** P-01 (release-and-integration), P-02 (integration-architect).
- **Scoped decisions still needed from B:** none blocking tasks. Decided 2026-11-12: D-PROGRESS=B, D-HIGH=maintenance→MEDIUM, D-GOV-PRETAG=required (see progress.json later_decisions). Pending: own-words ack for the evidence-zip H-09b override; delete_branch_on_merge handling before Q-03.
- **Actual commands/tests executed:** `tools/validate_packet.py --repo . --initial` → PASSED (structure only), Windows 11 / Python 3.14.
- **Source/artifact digests tested:** intake MANIFEST.json 105 sha256 entries match imported bytes.
- **Pending transaction, authority, cleanup, publication or receipt outcomes:** none.
- **Safe recovery action for each unknown outcome:** n/a.
- **Current rollback boundary:** whole branch is additive; nothing merged to main, no tags/releases/Pages/marketplace effects.
- **Exact next action:** observe the first integration push CI/docs runs for P-01 (read job-selection logs), then P-02.

## Environment notes

- `tools/validate_packet.py` on Windows: run with `python -X utf8` (it reads text with the locale codec) and normalize relative path separators (its manifest population check compares `str(Path)` to `/`-separated names). A shim outside the corpus did this without editing the validator. On Linux it runs unmodified.
- Repo `delete_branch_on_merge=true`: the final promotion PR merge would delete this branch unless handled (see progress.json pending decisions).
