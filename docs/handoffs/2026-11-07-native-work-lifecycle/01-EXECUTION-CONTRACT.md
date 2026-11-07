# 01. Execution contract

## Intended outcome, not a replacement permission layer

The agent should be able to start from an existing codeArbiter project, learn what work exists, perform authorized feature/fix/sprint work, record honest local progress and checks, and resume after interruption. Deterministic code owns identity, source preservation, bounded reads, CAS, journal recovery and valid mutations. It does not independently authorize ordinary work or attest to a model's claims.

Preserve:
- Stable native project and work IDs; one authoritative writer for each selected state object.
- Immutable historical board bytes, line/block digests, traceable provenance, valid aliases and dated transitions.
- Actual host permissions, explicit stops/denials, hook security boundaries and change review.
- Separate implementation state, reported checks, assessed verification, PR delivery, GitHub sync and release publication.
- Installed adapter compatibility and generated-projection parity across Claude, Codex and public ca-pi.

Reject proposals to add a new daemon, permission broker, generic policy DSL, extra human approval for each task, destructive migration, or broad reviewer reruns for normal record bookkeeping.

## T0. Re-pin and triage (mandatory; read-only)

1. Inspect actual `main` and HEAD; record `arbiterForge/codeArbiter@<full_sha>`.
2. Re-read issues #1084/#1087/#1089 and current PRs touching adoption, task board, commit-gate and work records. Check whether any defects were already fixed since the baseline; do not duplicate work.
3. Run existing focused tests and create a disposable fixture that reproduces today's failing cases. Freeze baseline command, exit, source hash and expected behavior.
4. Read ADR-0043, ADR-0008, owner/compatibility docs, generated-host rules and the named files in the source map. Trace `work.py -> _workadopt.py -> Go work-adopt` and `work.py -> taskwrite -> _taskboardlib.classify_board_diff -> commit-gate`.
5. Inspect current task board **as data in a disposable copy**, not by trying a migration in the real checkout.

Stop/replan only if current implementation invalidates a central premise. Record a concrete source-based delta rather than silently following an obsolete task.

## T1. Make Python preview and native Go adoption agree (#1084 + #1087 together)

Current source derives work ID from legacy origin and assumes unique `origin`. Multiple historical rows share the same `(from ...)` provenance, so naïvely relaxing one Python check leaves Go refusing the cutover. Make the entire path coherent:

- Derive one unique stable **native** correlation identity and one distinct Work ID per distinct physical source row, retaining explicit valid Work IDs where present.
- Retain the original shared `(from ...)` value as **source provenance**. It is not a unique key in those historical boards. Keep the native correlation `origin` unique rather than silently breaking `workByOrigin`/`work-origins`. Decide whether the already-snapshotted `legacy_source` block pointer is sufficient provenance, or whether a minimal, compatible typed field is required. Prove original value remains inspectable.
- Keep stable IDs across preview, cutover, same-operation replay, restart, clone and equivalent source bytes. Do not rely on runtime iteration order, randomness or an untrusted input-provided ID.
- Preserve canonical historical block content and digests, aliases, existing explicit IDs and archive data. Distinct same-origin rows migrate separately. An actual duplicate row, a conflicting explicit ID and an ambiguous alias must still refuse.
- Make Unicode semantics consistent. Python `len(str)` and Go byte length are not equivalent; title/summary limits and truncation must preserve complete UTF-8 code points and match the JSON schema contract.
- Handle legacy titles longer than 240 characters without silently deleting text. Keep a valid bounded, human-useful title; keep full one-line text in a field or original source record that is directly retrievable. Respect the 4,000-character intent bound and preserve any existing description or rationale. A genuinely unrepresentable row must refuse with the board and line.
- Normalize dates, title, states, links and all generated fields identically in Python and Go. The native engine MUST independently recompute identities and check exact source blocks, not trust preview JSON.
- Retain strict 1 MiB active-board read, 8 MiB archive read, bounded adoption-row count, symlink refusal, UTF-8 validation, board SHA checks and root lock semantics unless an independently evidenced reason mandates change.

Do not solve #1084 only in Python or #1087 only in rendering. Use source-coupled fixtures that execute both and compare every normalized field.

## T2. Accept authorized selected-row lifecycle changes (#1089)

Current `classify_board_diff` handles a single marker-only flip or a new queued entry, but rejects selected row attachments and compound transitions. Rewrite or extend its analysis to reason about **one selected task block** rather than only one changed line.

Pass the sanctioned mutations actually emitted by the owner:
- `attach` a spec/plan to one existing selected task.
- `start` then `attach` on that same task.
- `create` then `start` in one staged board change.
- `start` then `complete` in one staged board change.
- Continue accepting previous clean create/start/complete single transitions.

Reject changed titles/boundaries/rationale unless separately authorized by the owning edit contract; reject unknown metadata keys, a second task, removed history, unrelated section edits and arbitrary extra text. Define exactly which work-item field keys and date/status transitions are admitted by this narrow exception.

Use actual `work.py`/`taskwrite.py` operations to produce fixtures. Execute classifier tests on the resulting diffs, then exercise the real commit-gate path. Do not globally loosen scope checking or suppress pre-commit hooks.

## T3. Reconcile progress without inventing evidence

Two current plan artifacts still contain progress states lagging merged implementation:
- `.codearbiter/plans/native-first-workflow.html`: all eight tasks were `PENDING` at the frozen baseline, even though native-first source work merged.
- `.codearbiter/plans/project-work-system.html`: mixed `IN_PROGRESS`/`REVIEW`/`PENDING` states and historical check reports.

Read exact merged PRs, current implemented code, current applicable tests and the plan's real native identity first. Record appropriate implemented/review/verified dispositions *through the sanctioned native writer*, not by editing rendered HTML, fabricating check receipts, or marking all tasks DONE from a merge alone. If a task still lacks evidence, retain that uncertainty. This reconciliation is a delivery requirement, not a new autonomous status-generation framework.

## T4. Full journey and host adapter closure

Build an isolated existing-project test that starts on the legacy owner, previews adoption, applies a cutover, reads stable work/context, attaches the correct spec/plan, starts and completes work (with check status independently unknown or reported), resumes after restart, and renders local work/project views. Confirm old legacy mutators refuse native-owned state.

Regenerate canonical host projections and test current Claude, Codex and Pi source/package contracts. Where installed-host canaries cannot be run, label the exact missing cell. Do not claim host qualification from Go/Python tests alone. Preserve Pi's product-specific preview status and current distribution boundaries.

Run focused Go/Python checks, source sync/build checks, relevant site tests and full exact-head CI in the repository's existing supported workflow. Do not loosen tests or use synthetic passes to meet a metric.

## T5. PR and final evidence

Open one focused PR with issue links and a table for each acceptance behavior: baseline fail, changed owner, new test, passing result, environment, source commit and limitations. Include an inventory/accounting receipt from the **disposable** copy of the codeArbiter historical board. Require independent review of migration integrity and bypass resistance. Wait for exact-head CI evidence; if blocked, retain the PR as draft with an accurate blocker.

**Do not**: merge to main, publish/tags/releases, mutate actual user project state or external tracker targets, change a brand/portfolio canon, or opportunistically implement #1088 in this PR. If #1088 blocks legitimate development, diagnose precisely and use a separately authorized sanctioned recovery rather than evasion.

## Completion statement

The milestone is complete when an existing repository's real-world historical board shape migrates losslessly under an explicit cutover; normal in-scope work changes can be committed without a false board scope-creep finding; all negative safety controls remain enforceable; and project records distinguish progress, verification and external delivery from actual evidence.
