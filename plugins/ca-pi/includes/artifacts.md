# Typed HTML specifications and plans

Load inside the existing brainstorming, planning, TDD, execution or resume
workflow for new full-lane work or an existing HTML pair.
This leaf adds no slash command, agent, skill registration or persistent model
tool.

**Default authoring boundary:** new full feature and sprint spec/plan pairs
default to canonical `.html`. Check the installed capability before writing; a
missing, invalid, mismatched or unqualified capability is a STOP and
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
ca-artifact <operation> --root <project-root> --request -
```

Requests carry `protocol: codearbiter.artifact-api/0.1.0`. Query `schema` for the
needed operation or record fragment only; do not preload complete schemas. Return
stdout is a single bounded JSON envelope. Nonzero exits are failures except the
structured `validate` response explicitly reporting `valid: false` (also a gate
failure). Logs/stderr are not artifact content.

## Authoring and approval

New full-lane specs and plans use `.codearbiter/specs/<slug>.html` and
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
content-addressed authority-source store. Interactive prompt approval currently
has production host seams in Claude Code and Codex. Pi 0.84.1 exposes no
pre-model event carrying the user's exact prompt, so under Pi do not arm this
adapter; the workflow remains blocked until a Pi-native authority adapter is
implemented. On Claude Code or Codex, arm the exact current artifact immediately
before asking the approval question:

```sh
python "<plugin-root>/hooks/_approvallib.py" arm --root "<project-root>" --artifact-id <artifact-id>
```

Present the returned `reply` value verbatim and require that exact reply. The
`UserPromptSubmit` hook rechecks the armed identity, records the host-observed
prompt as the policy-owned source, captures its receipt, and applies approval.
An ordinary `yes`, a changed artifact, a wrong token, or a model-authored event
does not confer authority. On the next turn, verify `validate` at the `approved`
gate before continuing. If the user declines or the artifact changes, cancel the
exact pending request before arming another one:

```sh
python "<plugin-root>/hooks/_approvallib.py" cancel --root "<project-root>" --artifact-id <artifact-id>
```

Cancellation records no authority. Other workflow authorities must use their
corresponding host-owned adapters. Legacy `capture` events remain readable for
inventory but are inspection-only: the engine refuses to wrap them in a current
receipt. Current authority requires `capture-observation` over a closed producer
profile and engine-issued evidence context; never create an authority source
merely to satisfy an artifact transition. `approve` checks the resulting receipt
against current ready content. A missing or changed receipt, captured event, or
still-present policy source returns `AUTHORITY_UNVERIFIED`. Receipt format 0.1.0
remains readable for inspection after upgrade but is not authority-bearing; the
applicable policy boundary must produce a fresh 0.2.0 attestation before further
approval, dispatch, acceptance, commit proof, or finalization. This is the
repository's cooperative same-user attestation model, not cryptographic identity
proof or protection from an unrestricted same-user filesystem writer.

For ordinary sequential planning, create a plan as `draft_preview`, consume existing criterion IDs,
then `plan-bind` to the approved spec and approve the plan through its existing workflow. Initial
combined HTML sprint review uses the explicit paired path below instead of separate approvals.
A normative change invalidates its approval. Rebinding is explicit and preserves
history; it does not waive coverage or permit silent reinterpretation.

## Initial sprint pair and delegated methods

Only when preparing initial combined approval, replaying an observed reply, or revising a task's
method under its existing grant, load `<plugin-root>/includes/sprint-authority.md`. That private
card owns the `arm-sprint` / `resume-sprint` / `smarts` bridge and the native pair/method operations.
Do not bulk-load it for ordinary task reads. Scoring is not consent; the initial observed user reply,
protected scope, real producer, current evidence and existing security/permission gates remain required.

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

Before task selection, inspect the plan's exact prerequisite records. If one is
unsatisfied, collect and present the facts needed to judge its requirement; a
verification runner may supply facts but cannot confer prerequisite authority.
On Claude Code or Codex, arm a genuine user-workflow decision for the exact
current approved plan and prerequisite:

```sh
python "<plugin-root>/hooks/_prerequisitelib.py" arm --root "<project-root>" --artifact-id <artifact-id> --prerequisite-id <prerequisite-id>
```

Show the returned title, requirement, and review-packet digest, then require the
returned `satisfy-prerequisite ...` reply verbatim. The `UserPromptSubmit` hook
durably records that observed decision before publishing its authority source,
captures a prerequisite receipt, and applies the existing prerequisite CAS
operation. Its final nonce is non-secret freshness/correlation data, not a
credential: possession alone confers no authority, and only the exact prompt
observed at the trusted host boundary while the reviewed plan remains current
can satisfy the prerequisite. Wrong nonces or records, stale plan content or
approval, and expired requests confer no authority. A retry after confirmation reuses the same event,
receipt, operation ID, and mutation request; it never reconstructs a decision.
Only an unconfirmed request can be cancelled:

```sh
python "<plugin-root>/hooks/_prerequisitelib.py" cancel --root "<project-root>" --artifact-id <artifact-id> --prerequisite-id <prerequisite-id>
```

If the plan changes after confirmation, recover the obsolete request instead of
deleting its marker. `supersede` first proves the current identity differs. For
a captured request it also retries the exact operation ID: a committed replay is
accepted, while only an engine `REVISION_CONFLICT` proves the obsolete mutation
did not commit and permits the marker to clear. Published source and receipt
files remain as evidence:

```sh
python "<plugin-root>/hooks/_prerequisitelib.py" supersede --root "<project-root>" --artifact-id <artifact-id> --prerequisite-id <prerequisite-id>
```

The adapter fixes `authority_kind: user_workflow` and `verdict: satisfied`;
there is no caller-selected authority or bulk-satisfaction path. SMARTS prerequisite satisfaction remains unsupported; the plan-method producer below does not
grant prerequisite, security, backend or publication authority. Pi has no
qualified pre-model prompt seam and must remain blocked. Do not infer eligibility from one satisfied prerequisite:
rerun `eligible`, and resolve each remaining record independently against the
new current plan identity.

`eligible` is authoritative for task selection on the HTML path.
`task-start` checks current spec/plan approval, binding, prerequisites, source
snapshot, dependency evidence and the complete context ticket. Within a checkpoint,
a predecessor in `REVIEW` can provisionally unblock its dependent after fresh
verification and spec review. Across checkpoints, dependencies require accepted
scope evidence. Provisional progress never counts as completion.

The orchestrator executes the declared verification through its existing governed
execution tool through the installed production authority adapter; it never
constructs a successful workflow event itself. Arm an exact task request first.
Verification and review authority below is supported on Codex and Claude Code.
On Pi, stop at this boundary rather than treating model-authored results as
authority; its installed prompt approval seam does not imply verification or
review support.
Every distinct `cwd` label in the engine context must be mapped once to an exact
linked Git worktree root. Mapped worktrees must share the artifact repository's
Git common directory, and the adapter freezes their filesystem identity, HEAD,
status digest, effective argv, and executable bytes:

```sh
python "<plugin-root>/hooks/artifact-authority.py" arm --root "<project-root>" --artifact-id <plan-id> --record-id <task-id> --activity verification --workspace "candidate worktree=<absolute-worktree>" --workspace "baseline-evidence worktree=<absolute-worktree>"
```

Use only the mappings actually named by that task; missing or extra labels fail
closed. Run the returned request through one plain governed exec invocation (no
compound shell expression), then publish only after the host's matching
`PostToolUse` has corroborated the wrapper's completed request-bound result:

```sh
python "<plugin-root>/hooks/artifact-authority.py" verify --root "<project-root>" --request-id <request-id>
python "<plugin-root>/hooks/artifact-authority.py" publish --root "<project-root>" --request-id <request-id>
```

The verifier launches exact engine-declared argv without a shell, supervises the
whole process tree, bounds output, requires exact named outcomes, and rejects
workspace or executable drift. If an attempt is interrupted, use the adapter's
`recover` operation to retain it as failed or abandoned; never rerun an uncertain
attempt under the same request.

For `spec_review` or `quality_review`, arm the corresponding activity without
workspace mappings and dispatch the returned `launch_envelope` unchanged to one
fresh host subagent. The host hooks bind the exact launch call, child start and
the child's first stop; a pasted or coordinator-authored decision is not review
authority.
Publish the completed request through the same `publish` command. `task-review`
records the separate verification and spec-review receipts. After every task in
the scope reaches `REVIEW`, reverify against one current source snapshot, run the
combined quality review, and use `accept-scope` once. Do not accept tasks
individually.

An interrupted or `BLOCKED` HTML task never resumes by editing its status. Arm
the installed reconciliation adapter for the exact task or scope, present its
returned reply verbatim, and let `UserPromptSubmit` capture and apply the observed
user decision across repositories:

```sh
python "<plugin-root>/hooks/artifact-reconcile.py" --root "<project-root>" --artifact-id <plan-id> --target-id <task-id> --operation task-reconcile --target-state PENDING --reason "<reviewed reason>" --assessment "<reviewed assessment>"
python "<plugin-root>/hooks/artifact-reconcile.py" --root "<project-root>" --artifact-id <plan-id> --target-id <checkpoint-id> --operation scope-reconcile --assessment "<reviewed assessment>"
```

Ambiguous armed requests, changed identities, stale inputs, wrong replies, or a
foreign Git repository all fail closed. Re-run `eligible` after reconciliation;
the prompt reply itself is not proof that the lifecycle mutation committed.
If a mutation response is lost, submit the same exact reply again: the adapter
replays its durable operation ID and receipt without recapturing authority. A
request that has not reached mutation can be cancelled with:

```sh
python "<plugin-root>/hooks/artifact-reconcile.py" --root "<project-root>" --artifact-id <plan-id> --cancel --prompt "<exact returned reply>"
```

If a crash left a complete pending request before its prompt route was
registered, use this command instead. It refuses an active route or any
in-flight mutation:

```sh
python "<plugin-root>/hooks/artifact-reconcile.py" --root "<project-root>" --artifact-id <plan-id> --cancel-orphan
```

If a durable mutation attempt exists, neither cancellation path can clear it.
Replay the exact stored operation and receipt under the reconciliation lock:

```sh
python "<plugin-root>/hooks/artifact-reconcile.py" --root "<project-root>" --artifact-id <plan-id> --recover
```

Recovery clears the request only on a committed replay or a closed-set engine
result proving no commit (`REVISION_CONFLICT` or `OPERATION_ROLLED_BACK`). Other
errors retain it for investigation. Re-arm only after cancellation or recovery
succeeds; a committed recovery is not permission to repeat the mutation.

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
