# Typed HTML specifications and plans

Load inside the existing brainstorming, planning, TDD, execution or resume
workflow for an existing HTML pair or an explicitly requested typed-HTML pilot.
This leaf adds no slash command, agent, skill registration or persistent model
tool.

**Pilot authoring boundary:** default rollout remains disabled until the
required consumer and hosted qualification gaps are closed. New full feature
and sprint pairs therefore remain Markdown unless the user explicitly selects
the typed-HTML pilot. For that pilot, check the installed capability before
writing; a missing, invalid, mismatched or unqualified capability is a STOP and
the workflow must not fall back to Markdown or create any fallback artifact.
Report `CAPABILITY_MISSING` and direct the user to repair or reinstall the pinned
artifact payload before retrying. An existing `.md` exact pair remains Markdown
and continues on the legacy path without automatic conversion. The feature
small lane remains an inline mini-spec and creates no artifact. HTML `--farm`
dispatch remains disabled and outside this rollout.

## Internal execution contract

The normal qualified package's installation-owned `release.json` pins the native
executable bytes. The stdlib
`hooks/_artifactlib.py` bridge selects only that verified installed payload,
never PATH, an environment-selected binary or a path supplied by the project.
The existing host's governed execution mechanism and permissions remain
applicable. An absent payload or denied invocation is a capability gap to
surface, not permission to bypass the gate.

Use one operation with JSON on stdin:

```text
ca-artifact <operation> --root ${CLAUDE_PROJECT_DIR} --request -
```

Requests carry `protocol: codearbiter.artifact-api/0.1.0`. Query `schema` for the
needed operation or record fragment only; do not preload complete schemas. Return
stdout is a single bounded JSON envelope. Nonzero exits are failures except the
structured `validate` response explicitly reporting `valid: false` (also a gate
failure). Logs/stderr are not artifact content.

## Authoring and approval

Explicit-pilot specs and plans use `.codearbiter/specs/<slug>.html` and
`.codearbiter/plans/<slug>.html`. Create a draft, then use typed `apply` changes;
do not write or regex-edit HTML or its embedded JSON. `record.add` allocates a
stable ID when omitted. Keep criterion IDs from the spec in plan references;
never assign a second criterion ledger. Use `record.update` and explicit
retirement reasons. There is no generic status/approval update.

Drafts may be incomplete. `validate` with `gate: ready` is required before review.
It checks types, references, scope coverage, contracts and task definitions—not
semantic truth. Retain the existing negative-intent question, adversarial review,
ADR compatibility review, open-question handling, harvest and user/SMARTS gates.
One criterion may need multiple tests. Never invent a condition, oracle, source,
command, result, approval or reviewer to satisfy a required field.

The existing user, SMARTS, reviewer, or verification boundary must first persist
its actual policy-owned workflow event as canonical JSON in the reserved
content-addressed authority-source store. The artifact adapter does not expose an
event-authoring helper: it receives only that existing source's exact locator and
digest and passes those two fields to `capture`. Never call `capture` with
request-authored `authority_kind`, verdict, actor, or source-text labels, and
never create an authority source merely to satisfy an artifact transition.
`capture` does not change approval state. `approve` checks the resulting receipt
against current ready content. A missing or changed receipt, captured event, or
still-present policy source returns `AUTHORITY_UNVERIFIED`. Receipt format 0.1.0
remains readable for inspection after upgrade but is not authority-bearing; the
applicable policy boundary must produce a fresh 0.2.0 attestation before further
approval, dispatch, acceptance, commit proof, or finalization. This is the
repository's cooperative same-user attestation model, not cryptographic identity
proof or protection from an unrestricted same-user filesystem writer.

Create a plan as `draft_preview`, consume existing criterion IDs, then `plan-bind`
to the approved spec. Approve the plan through the applicable existing workflow.
A normative change invalidates its approval. Rebinding is explicit and preserves
history; it does not waive coverage or permit silent reinterpretation.

## Reading and dispatch

Use `index`, then `outline`, then symbol-scoped `read`. Exact reads are explicitly
context-incomplete. Execution uses contextual pages; follow every `next_cursor`
until `context_complete: true`, and retain the final context ticket. Cursors bind
both documents and contributing receipts/events. No partial record is silently
returned. A stale cursor/ticket requires a fresh read.

These cursors and tickets name engine-written, content-addressed cooperative
delivery receipts. They are not authentication secrets and do not claim
resistance to an unrestricted same-user filesystem writer. A digest without its
corresponding engine-written receipt is rejected.

`eligible` is authoritative for task selection on the HTML path.
`task-start` checks current spec/plan approval, binding, prerequisites, source
snapshot, dependency evidence and the complete context ticket. Within a checkpoint,
a predecessor in `REVIEW` can provisionally unblock its dependent after fresh
verification and spec review. Across checkpoints, dependencies require accepted
scope evidence. Provisional progress never counts as completion.

The orchestrator executes the declared verification through its existing governed
execution tool, captures actual named-test outcomes and output hashes, and obtains
a separate spec review. `task-review` records those receipts. After every task in
the scope reaches `REVIEW`, reverify against one current source snapshot, review
the combined scope, and use `accept-scope` once. Do not accept tasks individually.

`IN_PROGRESS` after interruption requires reconciliation, not automatic completion.
`REVIEW` requires fresh evidence. Source changes stale proof; state/branding updates
do not stale their own verification. `task-block` invalidates downstream provisional
states. `scope-reconcile` records a reviewed new baseline after plan edits.

## Mutation and recovery

Every artifact mutation supplies the revision AND model hash last read, plus a
unique operation ID. On conflict, reread and reconsider—never overwrite forcefully.
A response lost after replacement is not evidence that nothing changed. Retry the
same operation ID with identical input, or use `recover` on an uncertain transaction.
Replaying a completed operation returns its original completion fields and a
transaction marked as replayed; use `identity` for the current document identity.
An older journal may return `refresh_required: true` instead. A rolled-back
operation is not success. Keep journal-compatible tooling when restoring code.
A transaction that was rolled back returns `OPERATION_ROLLED_BACK`.

`repair-preview` identifies an inconsistent generated view. `repair-apply` requires
both original-byte and candidate hashes and retains original bytes; it never
infers semantic edits from human-modified HTML. Export writes a standalone copy
outside canonical directories. Rebranding accepts only validated local assets.

## Legacy transition and blocked capabilities

Legacy Markdown remains readable through the old workflow. Conversion is explicit:
`migration-preview` receives typed spec/plan models and a complete nonoverlapping
line-disposition map for each original file. Review the models and mappings, then
`migration-apply` binds to the exact preview digest and records the review. Both
new artifacts are drafts. Original approval/status prose is not transferred.
Cutover is recoverable as a pair; completed cutovers use `migration-rollback`, which
refuses any intervening candidate edit. Original bytes remain in transaction history.

**HTML farm dispatch remains disabled and out of scope.** The
engine can derive an immutable base-bound projection, verify it before canary,
permit only `meta.model`/`meta.apiBaseUrl` enrichment, and seal exact execution
bytes plus caller-supplied provider-selection assertions. Those assertions are
auditable correspondence, not authenticated provenance. The shared built dispatcher enforces the checks
before side effects. Keep the HTML `--farm` path disabled until real authority
adapters, native packaged payloads and the fresh frontier/low-tier qualification
matrix all pass; the June 2026 run earns no current credit. Existing legacy farm
behavior is unchanged. Enabling normal premium-path HTML authoring does not count
as farm qualification or authorize farm dispatch.
