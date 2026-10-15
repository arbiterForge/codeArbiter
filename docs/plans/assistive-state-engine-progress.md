# Assistive state engine — current implementation status

**PR:** [arbiterForge/codeArbiter #983](https://github.com/arbiterForge/codeArbiter/pull/983)
**Branch:** `overhaul/assistive-state-engine` — **draft, unmerged, unreleased**.
**Implementation evidence commit:** `b7681d9857b954d60cee91e28ba5590e984ebbf0`.
**Direction:** [ADR-0043](../../.codearbiter/decisions/0043-assistive-state-engine.md).
**Scope:** [single-PR task contract](assistive-state-engine-overhaul.md).

## Target

The agent reads the agreed outcome and bounded task context, implements useful
work, records actual checks and progress, and continues without artifact-origin
permission questions. True user stops, host security, journal/CAS integrity,
commits and publication permissions are **not** bypassed.

## Task tracker

| Task | Source state | Remaining |
|---|---|---|
| T01 | Approved direction and owning-callers inventory | None for design approval |
| T02 | Advisory scheduling; receipt-free task and batch progress | Complete affected host-caller conversion |
| T03 | Scoped factual prerequisites and real user-decision records | Preserve unknown scope on old records |
| T04 | Reported checks and bounded selected/shared-source applicability | Unmodeled/transitive dependencies and real host-result attestation |
| T05 | Normal feature, sprint, TDD, planning and execution instructions adapted for Claude, Codex and Pi | Model-backed host exercise |
| T06 | `task-context` with exact criteria, dependencies, bounded readback and explicit omissions | Measure end-to-end model/tool-call cost |
| T07 | Safe exact replay; protected user stops; older-engine fail-closed; multiple unanswered-prompt recovery cases; newer edits preserved in forward export | Unknown historical formats, full backup/restore and mixed-client qualification |
| T08 | Three generated host adapters; default artifact instructions minimized; strict explicit proof loaded on demand | Exact released website, Academy and package derivatives |
| T09 | Native/fixture and cold installed-candidate checks pass on Windows for three adapters | Hosted exact-head matrix, genuine host/model canaries and distributed package readback |

## Verified candidate checks

- **Offline installed-candidate ordinary workflow:** Claude, Codex and Pi
  each complete draft → task-context → start → reported UNKNOWN check →
  `DONE` → fresh-process readback. No additional approval, receipt, or
  Markdown shadow is created. The separate explicit historical proof path
  also passed in each host fixture. Candidate native Windows/amd64 SHA-256:
  `2236f2e7ad6cd991596b33988ed89af86a6ea8d2a84cba66bf461ae230efb68d`.
  This is **not** model-backed behavior or a distributed artifact.
- **Real two-binary T07 probe:** source-built 0.3.1 engine refuses new-schema
  writes; 0.3.2 preserves later journaled edits when replaying earlier
  operations; exported view contains newer work. No automatic downgrade.
- **TDD/caller correction:** 43 debug tests, five focused authoring tests and
  eight UX obligation groups passed locally.
- **Current instruction projection:** `build-surface.py --check` and
  `sync-core.py --check` passed against all three generated hosts.
- **Latest source-head check:** CI and Docs must be revalidated after the
  source-bound atlas update; neither a local test nor an older successful
  workflow establishes a new released or deployed artifact.

## Next executable work

1. Complete exact-head CI and correct proven failures without replacing source
   checks with looser assertions or adding new approval machinery.
2. Verify the ordinary workflow in actual supported installed hosts using an
   authorized model session; distinguish real tests from reported/synthetic
   observations and inspect the exact candidate bytes.
3. Address only demonstrated T04/T07 gaps that can lose real work or cause
   unnecessary repeated verification. Keep unknown dependency coverage
   `unassessed`; never invent a universal freshness guarantee.
4. Reconcile owning public/Academy/install claims after the actual package is
   qualified. Do not describe this PR as a release.

The Git repository retains earlier slice evidence and prior versions of this
status file. The active instructions and this tracker intentionally contain
only current operational facts.
