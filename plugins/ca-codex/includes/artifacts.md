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
artifact payload before retrying. The payload ships only through the release
channels: Claude Code `/plugin marketplace update codearbiter` then
`/plugin update ca@codearbiter`; Codex the `ca-codex-marketplace` ref; Pi
`pi install npm:@arbiterforge/ca-pi`. A main-branch checkout never carries it. An existing `.md` exact pair remains Markdown
and continues on the legacy path without automatic conversion. The feature
small lane remains an inline mini-spec and creates no artifact. HTML `--farm`
dispatch remains disabled and outside this rollout.

## Installed authoring capability

`_select_authoring_route` checks the actual installation-pinned native writer and
rechecks the selected namespace. `_preflight_plan_authoring` checks the exact
current source identity and structural validity before returning its same-slug
plan target. Neither operation requires artifact approval, a verifier/reviewer
producer, or a source snapshot merely to author a draft. This includes the native
Pi writer; it does not qualify a Pi host workflow or enable HTML farm dispatch.

`ArtifactClient.workflow_preflight()` retains the explicit historical authority
resource inventory used by its own consumers, including the separate context
workflow. It is not an admission check for ordinary spec/plan authoring. Its
result does not prove host trust, enabled hooks, or live verification. Missing
actual writer capability remains a failed write with a repair diagnostic; it is
not permission to create a competing canonical artifact or claim success.

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

## Authoring

New full-lane specs and plans use `.codearbiter/specs/<slug>.html` and
`.codearbiter/plans/<slug>.html`. Create a draft, then use typed `apply` changes;
do not write or regex-edit HTML or its embedded JSON. `record.add` allocates a
stable ID when omitted. Keep criterion IDs from the spec in plan references;
never assign a second criterion ledger. Use `record.update` and explicit
retirement reasons. There is no generic status/approval update.

Drafts may be incomplete. Use `validate` with `gate: ready` to discover missing
coverage, contracts, or task definitions. These are useful diagnostics, not an
artifact permission decision. Structural errors, unsafe paths, and write
conflicts still fail the operation. Never invent a condition, source, command,
result, approval, or reviewer to fill a field.

Use the same source's criterion IDs and `plan-bind` to select its current
structurally valid definition. A draft binding does not require a user code.
Maintain methods, checks, and task decomposition within the agreed outcome using
typed changes and a concise reason; do not erase requirements to claim completion.
The drafting skill does not call `_approvallib._preflight_plan_verification` or
arm approvals merely to maintain this working agreement. Existing authorization
and genuine unresolved product decisions belong to the conversation and host.

## Explicit attestation or old-work recovery (on demand)

**Do not load historical review/approval machinery for ordinary implementation.**
The default workflow is plan → useful work → appropriate checks → progress.
Task scheduling, source binding, bounded context reads and `DONE` do not require
an approval code, a context-delivery ticket, or a reviewer fleet.

Only if an actual user instruction or separately applicable host/release policy
requires **attested proof**, or old saved work contains an unresolved pending
request / migration, read just the relevant section of
[includes/artifacts-attestation.md](artifacts-attestation.md). It retains complete
historical verification-input, reviewer, approval, and recovery protocols for
that explicit case; it is not the default task-start/commit authorization.
An older installed package must still follow its own exact capabilities.

## Reading and ordinary progress

Use `index`, `outline`, then exact symbol-scoped `read` or `read-batch` for the
records needed now. Exact reads explicitly report incomplete broader context;
fetch relevant requirements, dependencies, and constraints when needed. Complete
contextual pages remain available for a deliberate full context request, but
their delivery ticket is not permission to start a task.

For low-token orientation after task selection, query read-only
`task-context` with the current plan `model_sha256`, task ID, and optional
response `budget`. It supplies the complete selected task definition,
referenced criterion summaries, dependency states, scoped prerequisite
observations, and a notice about omitted broader context. A stale plan ID
refuses rather than combining revisions; a stale bound specification is
reported, not silently rebound. It never takes a source snapshot or creates
a ticket, reviewer, or authority. Its `context_complete: false` flag means
fetch specific additional symbols before making a decision that requires them.
A missing operation on an older installed package uses existing exact/batched
symbol reads rather than an invented result.

`eligible` supplies advisory scheduling from recorded dependencies and explicit
prerequisite task scope. It does not scan source inputs or claim current test or
review evidence. Inspect its waiting reasons; work on independent tasks while a
real prerequisite remains unresolved. A legacy unscoped prerequisite needs an
applicability assessment, not automatic plan-wide blocking or silent satisfaction.

For an observable prerequisite, run the appropriate check through the ordinary
authorized host tool and call `prerequisite` with its actual bounded `observation`.
Use `fact` or `decision` and relevant `task_refs` in the definition. Results are
caller-reported, with a native recording time and definition identity, not host
attestations. A tool result cannot stand in for a resolved user choice. Ask a clear
normal-language question for a genuinely missing decision; no certification code.

Ordinary verification output belongs in a typed **reported command check**, not
an invented review receipt. After an authorized host tool runs a relevant
command, call `task-check` with the observed `argv`, repository-relative
`cwd`, `outcome` (`pass`, `fail`, `skip`, `unknown`), factual `summary`,
the result's `source`, and `origin: tool_result` or `agent_report`.
Include `exit_code` only when the command actually ran; a reported pass
requires its code. Specify `command_index` only if the invocation exactly
matches that plan verification entry. An ad-hoc check omits the index and
never silently fulfills a named-test requirement. Never execute a command
stored in an artifact merely to record it.

The engine records a bounded `caller_reported` note and digest of the
declared check and **directly referenced criteria**, not a second approval.
Historical observations retain their original broad-spec semantics. The
latest failure/unknown is never hidden by an older pass. `task-context`
uses a safe, bounded read of the task's declared paths and explicit
`shared_inputs`, plus common build manifests/lockfiles, to report only
`scoped_unchanged`, `scoped_changed` or `unassessed`. This is **partial
source applicability**, not independent test evidence: `scope_complete`
remains false even when hashes match. The task's source binding remains
separately visible. Newly added/removed files beneath declared source
directories, and known build configuration, change the scoped identity.
Undeclared shared dependencies and custom build inputs still require
explicit investigation and optional `shared_inputs`, never an inferred
verification guarantee. On unsafe paths, symlinks, missing/oversize scopes or
uncertain reads, record a useful unassessed result rather than blocking
ordinary authorized work.

Exact/batch reads and rendered HTML do not inspect the filesystem, so they
do not report source freshness. A method-only task edit, presentation change
or fresh receipt identity by itself does not restart reviewers. A changed
command, task scope, referenced criterion or bounded tracked input makes the
affected check inapplicable or stale. Assess the changed work; do not
redispatch unrelated reviews. Real host denials and actual negative tests
remain independent.

Use `task-start` for pending work. Use `task-review` without receipts to record
implementation ready for review, or `accept-scope` with a reason and no receipt to
record a finished implementation batch as `DONE`. Neither operation asserts a
passing check or an independent review. Retain the actual check results and report
outstanding failures, uncertainty, and unrun checks separately. The explicit
`verification-status` proof query is not a scheduling prerequisite.

On resume, inspect current work and active workers before `task-reconcile` with a
reason. Do not clear a user stop or duplicate running work. A process restart does
not by itself require a new approval or reviewer. Preserve CAS and operation IDs;
handle an uncertain write through the transaction recovery contract below.

## Before using an older installed engine on a modern plan

Old 0.3.0/0.3.1 plans remain byte-for-byte readable by the 0.3.2
engine until the first journaled edit introducing the newer observation
or task status. Once any canonical plan member uses 0.3.2, an older
installed engine must refuse reads and writes rather than rewriting,
downgrading or silently losing it. **Use a matching installed
engine/bridge/host-resource cohort**; do not use another host's
outdated executable on the same project. Existing IDs, stopped tasks,
history and already recorded real receipts remain owned by the project.

To recover uncertain work, first inspect whether the prior worker or
native mutation already committed. Replay **exactly** the same operation
ID/input when needed; do not manufacture a replacement start. For
manual backup, use the compatible engine's standalone `export` without
replacing canonical HTML. Before any downgrade, keep the complete
transaction history and a verified backup, and only restore old files
when no later modifications would be lost. If new work occurred,
**forward recovery is required**. `migration-rollback` is limited to
the originally reviewed Markdown cutover and cannot be used as a
schema downgrade. Consult `docs/artifacts/PROTOCOL.md` for bounded
mixed-version checks and exact recovery boundaries.

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
