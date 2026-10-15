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
ca-artifact <operation> --root ${CLAUDE_PROJECT_DIR} --request -
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

## Explicit verification-input and attestation contracts

The following input/receipt protocols describe explicit historical evidence and
attestation operations, not ordinary authoring or work-progress prerequisites.
Read only the portion needed for an actual evidence consumer. Do not create an
approval, method grant, or reviewer event just to satisfy a status transition.
Independent host permissions and genuinely requested user checkpoints still apply.

`verification_inputs.roots` and `exclude_directories` use exact slash-separated
repository-relative paths. Exclusions are directory paths, not globs or basename
matches and not relative to an individual root. For root `site`, a generated
dependency exclusion is `site/node_modules`, not `node_modules`. Review each
excluded output directory explicitly: the plan's roots and exclusions narrow
the ship set. In a git work tree `.gitignore` already keeps untracked ignored
files out of it; outside git nothing is filtered, so exclude generated
directories explicitly.
An exclusion outside all selected roots is rejected as ineffective. Overlapping
roots cannot reinclude an excluded directory. Roots must exist before execution;
use an existing containing directory for a planned new file so its creation
changes the snapshot. An oversized included file is reported with its path and
the 32 MiB per-file limit; revise the explicit policy rather than increasing the
limit or excluding source/test/governance inputs needed for the task.

Snapshot input identity is ship-set membership. In a git work tree the members
are the git index entries present on disk, plus untracked non-ignored files
within the plan's roots, minus its excludes. The one fixed exemption is
`.codearbiter/gate-events.log`: it is never counted, whatever the plan says, and
stays tracked as the audit trail; every other `.codearbiter` path still counts.
Outside git, membership is read from the filesystem (`membership: filesystem`);
the root must be the top level of its work tree, so a subdirectory root counts as
outside git. A failed git probe fails closed with `INPUT_MEMBERSHIP_UNAVAILABLE`. An unmerged
git index (conflicted paths) makes a snapshot fail closed until it is resolved.
The manifest format is `codearbiter.verification-inputs/0.2.0`; receipts bound to
a 0.1.0 manifest read as stale. Each evidence object is validated at most once
per operation and scans are bounded; raw reads are reused only up to a 64 MiB
per-operation retained-byte budget, past which an object can be read again, but
validation is never skipped.

The existing user, SMARTS, reviewer, or verification boundary must first persist
its actual policy-owned workflow event as canonical JSON in the reserved
content-addressed authority-source store. Interactive prompt approval currently
has production host seams in Claude Code and Codex. Pi 1.0.0 exposes an `input`
event, but codeArbiter has no Pi-native authority adapter. Under Pi do not arm this
adapter; the workflow remains blocked until that adapter is
implemented. On Claude Code or Codex, arm the exact current artifact immediately
before asking the approval question:

```sh
python "${CLAUDE_PLUGIN_ROOT}/hooks/_approvallib.py" arm --root "${CLAUDE_PROJECT_DIR}" --artifact-id <artifact-id>
```

On Claude Code, when the result carries `ask_envelope`, pass it unchanged as the
entire AskUserQuestion input (no `answers`, `annotations` or other field): the
user approves by clicking its Approve option, and the host-observed selection is
applied with origin `claude:AskUserQuestion:<session>`. Otherwise, or if the
user prefers typing, present the returned `short_reply` (a four-character code
such as `approve K7MQ`); the full `reply` is also accepted, and you
require that exact reply: the hook tolerates surrounding whitespace, invisible characters, a code
fence or quotes and a closing period, but nothing else in the message, and it
reports a mismatch instead of staying silent. The `UserPromptSubmit` hook
rechecks the armed identity, records the full armed reply as the host-observed
policy-owned source, captures its receipt, and applies approval. An ordinary
`yes`, a changed artifact, a wrong or expired code, a reply inside other text, or
a model-authored event does not confer authority. On the next turn, verify `validate` at the `approved`
gate before continuing. If the user declines or the artifact changes, cancel the
exact pending request before arming another one:

```sh
python "${CLAUDE_PLUGIN_ROOT}/hooks/_approvallib.py" cancel --root "${CLAUDE_PROJECT_DIR}" --artifact-id <artifact-id>
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

When adversarial review revises a ready initial draft spec after its draft plan exists,
query both current identities. The installed engine's explicit `plan-bind` request with
`binding_mode: draft_preview` requires the plan's existing `expected` CAS and the spec's
`spec_expected` revision/model CAS. It rebinds only that same-ID, same-slug initial pair:
both artifacts must remain unapproved drafts, tasks pending and unevidenced, prerequisites
unsatisfied and unevidenced, and scopes empty. Optional typed plan corrections must leave
both drafts fully ready. The binding remains `draft_preview`; this operation grants no
approval, delegation, prerequisite satisfaction, execution or acceptance. Revalidate both
current drafts, repeat the affected review and arm the exact combined approval afterward.
Inspect the installed operation schema first. An engine without this explicit draft
request reports a capability gap; never edit HTML, recreate the pair, substitute sequential
approval or use ordinary approved-source `plan-bind` to repair it.

## Historical paired approval and delegated methods

`${CLAUDE_PLUGIN_ROOT}/includes/sprint-authority.md` retains the old paired/method
attestation adapter contract for inspecting or recovering those records. It is
not required to create drafts, bind a source, or maintain an in-scope method.
A historical grant is not permission to bypass a real user stop or host denial.

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

## Explicit verification and review receipts

This is the existing attested-evidence path for a consumer that actually needs
that claim. It is not a mandatory author/reviewer sequence for ordinary work.
Do not apply the following arming protocol to receipt-free progress operations.

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
python "${CLAUDE_PLUGIN_ROOT}/hooks/artifact-authority.py" arm --root "${CLAUDE_PROJECT_DIR}" --artifact-id <plan-id> --record-id <task-id> --activity verification --workspace "candidate worktree=<absolute-worktree>" --workspace "baseline-evidence worktree=<absolute-worktree>"
```

Use only the mappings actually named by that task; missing or extra labels fail
closed. Run the returned request through one plain governed exec invocation (no
compound shell expression), then publish only after the host's matching
`PostToolUse` has corroborated the wrapper's completed request-bound result:

```sh
python "${CLAUDE_PLUGIN_ROOT}/hooks/artifact-authority.py" verify --root "${CLAUDE_PROJECT_DIR}" --request-id <request-id>
python "${CLAUDE_PLUGIN_ROOT}/hooks/artifact-authority.py" publish --root "${CLAUDE_PROJECT_DIR}" --request-id <request-id>
```

The verifier launches exact engine-declared argv without a shell, supervises the
whole process tree, bounds output, requires exact named outcomes, and rejects
workspace or executable drift. If an attempt is interrupted, use the adapter's
`recover` operation to retain it as failed or abandoned; never rerun an uncertain
attempt under the same request.

Named Playwright commands require `test --reporter=json`; each required name must
equal a unique native `spec.title`. Named Vitest commands require
`run --reporter=verbose`; use the complete rendered `suite > case` identity after
the filename, not a leaf-name alias. Named unittest commands require `-v` or
`--verbose`. A passing row cannot conceal a duplicate, skip, failure or retry.
Plain exit checks cannot attest named tests.

Named npm commands support inspectable single-runner scripts, a contained
repository-relative `--prefix`, and arguments forwarded after `--`. A root script
may delegate once through `npm -w <name> run <script>` or
`npm --workspace <name> run <script>` when the name resolves uniquely in an array
of at most 32 explicit, contained workspace directories. The runner binds the root
manifest and every inspected workspace manifest. Globs, linked directories,
multiple workspace selectors and recursive npm delegation are unsupported.
Workspace delegation uses the declared cwd; a non-dot `--prefix` is unsupported
for this shape.
Preserve both npm argument boundaries when adding a reporter: for a root
`test:client` script containing `npm -w @example/client run test`, declare
`npm run test:client -- -- --reporter=verbose` to forward the reporter to Vitest.
The original root command still executes the full script. Compound
scripts and pre/post lifecycle scripts require separately declared direct-runner
commands; retain every check from the original suite when splitting commands.
On Windows, only the qualified standard `npm.cmd` layout is adapted: the runner
pins the wrapper, sibling `node.exe`, sibling `node_modules/npm/bin/npm-cli.js`,
and script manifest. It deliberately selects that sibling CLI rather than the
shim's optional global-prefix redirection. Unknown batch wrappers fail closed.
For workspace delegation, it also pins `npm-prefix.js` and checks that the nested
wrapper uses the same CLI, the default script shell, and no configured Node
options. Local executables shadowing nested npm are rejected.
Direct Node script entrypoints are also pinned. These launch-file bindings do
not establish transitive dependency closure for deliberately excluded inputs.

New observations use the closed `declared-command/0.3.0` producer profile to
retain collector and launch-file identities plus an engine-produced normalized
completion closure. Raw workspace fingerprints must still match before and
after command execution. Historical `0.1.0` and `0.2.0` bindings retain their
original contracts and cannot be relabelled as newer evidence.

For `spec_review` or `quality_review`, arm the corresponding activity without
workspace mappings and dispatch the returned `launch_envelope` unchanged to one
fresh host subagent. The bounded prompt names the retained, content-addressed
evidence context instead of embedding its full input manifest. The reviewer
must read that context and inspect its subject, coverage and source inputs.
The adapter verifies the context's canonical bytes and digest before launch and
publication; a missing or changed context blocks authority. Never shorten or
rewrite the returned envelope yourself.
The host hooks bind the exact launch call, child start and
the child's first stop; a pasted or coordinator-authored decision is not review
authority.

When reviewing completed work that relies on a verification run, linked
worktrees or supporting evidence, explicitly select the completion path. Add
`--completion-receipt <exact-published-receipt>` once per task and
`--supporting-file <absolute-regular-file>` for each supporting document to the
review `arm` command. A task review selects one verification receipt; a scope
review selects the exact receipt for every member. Supporting files require a
receipt selection. The existing review-before-verification path remains
available; it does not satisfy an explicitly requested completion review.

The native engine validates the selected published verification chain and
derives the worktree mappings from its qualified observation. It retains the
selected identities, worktree closure and supporting bytes in the immutable
context. Supporting material is data for review, not authority. Selection is
explicit: no newest-receipt search, directory import or attachment execution.
At most 16 regular files are admitted, each at most 64 KiB and together at most
256 KiB; links, reparse indirection, duplicate paths and changed content fail
closed. Read canonical spec and plan artifacts through the native artifact API;
they cannot be imported as supporting files. The generated prompt directs the reviewer to assess performed work
against each criterion, step and `done_when` obligation, using selected evidence
and source references. A consistent plan or an empty diff is insufficient.

Use the returned `completion_sha256` in the native `task-review` or
`accept-scope` request. The completed review and its exact verification run must
agree; a definition-only review or a different successful run is rejected.
A task review retains the exact run it actually inspected; never relabel it as
having reviewed another run. A new scope review may select a separately validated
passing rerun without redispatching that task reviewer when the original task
review remains current, the reviewed workspaces match the new run's normalized
closure, and all supporting material is retained. The engine checks those facts;
a new receipt ID alone is not a reason to repeat the task review. Different
source, definitions, or supporting evidence still needs the affected assessment.
This does not infer equivalence from a caller-supplied label or a matching exit
code, and does not make a later failed run pass.

Creating a completion context for a `0.3.0` verification recomputes the normalized
worktree closure bound during that verification. Only validated native outputs
and execution bookkeeping are normalized; their publication must not invalidate
unchanged source. Historical `0.2.0` verification retains its initial exact raw
fingerprint comparison. Later freshness checks allow native task-status and
execution bookkeeping updates in validated canonical artifacts while retaining
their normative content hashes.
Changes to task definitions, other HTML or other governance files still affect
freshness under the normal snapshot policy. The closure covers
tracked working-tree bytes and non-ignored untracked files, not ignored
dependencies or outputs. The completion assessment is still an independent
reviewer's judgment; schema validation does not prove that every file was read
or every conclusion is correct. Preserve the unchanged launch envelope and
genuine host capture throughout this path.
On Claude Code, pass the envelope's four fields as the Agent tool's entire
input: no `run_in_background`, `isolation` or other option. It launches the
read-only `ca:authority-reviewer`; arming refuses while a project or user agent
could shadow that name. While the reviewer runs, send no SendMessage from this
session to any recipient: any message rejects the request. For verification,
`arm` returns `verify_command` with literal absolute paths; run it unchanged as
its own foreground Bash call, without disabling the sandbox. The hook refuses a
command that still contains `$` or another shell metacharacter. A rejected
request is never retried; arm a new one.
Publish the completed request through the same `publish` command. `task-review`
records the separate verification and spec-review receipts. After every task in
the scope reaches `REVIEW`, reverify against one current source snapshot, run the
combined quality review, and use `accept-scope` once. Do not accept tasks
individually.

Current Codex native V1 completion reviews retain the full frozen context in
its immutable, content-addressed file and keep only its closed reference in
mutable request state. Loading validates the exact context locator, hash,
canonical bytes and review kind. The native context budget remains 8 MiB;
mutable request state remains bounded at 1 MiB. Before dispatch, the adapter
reserves the exact fixed result identities, six times the 64 KiB decision
budget for canonical JSON escaping, and 32 bounded 256-byte lifecycle slots.
A request without that capacity is refused before child launch. Historical
inline requests retain their existing limits and abandonment-only recovery.

An ARMED review that never launched can be abandoned through the adapter:

```sh
python "${CLAUDE_PLUGIN_ROOT}/hooks/artifact-authority.py" recover --root "${CLAUDE_PROJECT_DIR}" --request-id <request-id> --disposition abandoned
```

The adapter requires no attempt, launch, observation, receipt or prior recovery.
It retains the request and its evidence, creates no receipt, and prohibits
dispatching that request again. This also covers bounded legacy requests whose
inline manifests made them too large for normal dispatch. Launched or captured
requests remain subject to their existing recovery rules. Arm a new request
only after the retained request is terminal.

## Assistive recovery of an unanswered legacy reconciliation prompt

After a session restart, **inspect the active task and any workers first**.
Ordinary `task-reconcile` records a reasoned progress update through the
native engine without a prompt token; it never clears an explicit user stop.
The following repair applies **only** when an older installed adapter has left
an *unanswered* reconciliation prompt that should no longer be re-armed:

```sh
python "${CLAUDE_PLUGIN_ROOT}/hooks/artifact-reconcile.py" --root "${CLAUDE_PROJECT_DIR}" --artifact-id <plan-id> --supersede --reason "Old unanswered artifact prompt; the actual task was inspected and no user decision is being overridden."
```

This calls the existing host adapter's locked, read-validated pending-state
handler. It requires the original prompt-route binding to match the pending
record, rejects ambiguous legacy/current markers, and **refuses any durable
mutation attempt**. It removes only an unanswered prompt/route, does not edit
spec/plan state, report tests passed, cancel a user stop, or fabricate an
approval. No existing receipt or evidence history is rewritten. If it fails
because a mutation may have started, use the exact `--recover` path below;
**never** reissue the work under a different operation ID. After superseding,
read `identity` and `eligible`, then reconcile only what actual observed
work requires. A cancelled question is not an accomplished task.

An **unanswered** old paired-sprint approval can be retired through the
existing approval adapter. The paired format persists any observed human
reply as a separate exact submission before attempting the native write.
The transition lock rechecks the current pair and **refuses a submitted
approval**, which must use the existing `resume-sprint` recovery path:

```sh
python "${CLAUDE_PLUGIN_ROOT}/hooks/_approvallib.py" retire --root "${CLAUDE_PROJECT_DIR}" --artifact-id <plan-id> --reason "The old paired approval was never answered; the current authorized work does not require that question."
```

Old **single-artifact** approval format 0.1 cannot prove that a submitted
reply was never captured or committed. Its no-code retirement therefore
**fails closed** as `LEGACY_APPROVAL_RECOVERY_REQUIRED`; inspect the
current artifact, actual authority history and journal instead of deleting
the marker. A historical approval, refusal, or genuine user stop is not a
routine progress permission and must not be silently inverted.

An unanswered old prerequisite can use the same existing prerequisite
helper when its validated state is exactly `ARMED`:

```sh
python "${CLAUDE_PLUGIN_ROOT}/hooks/_prerequisitelib.py" retire --root "${CLAUDE_PROJECT_DIR}" --artifact-id <plan-id> --prerequisite-id <prerequisite-id> --reason "No human reply was observed; use the real factual observation path if this condition still matters."
```

Its per-plan transition lock rejects `CONFIRMED` or `CAPTURED` requests:
preserve the source and recover the actual submission instead. Either
retirement reports `unanswered_prompt_superseded`,
`authority_granted: false`, and `mutation_attempted: false`.
Neither is an automatic prompt sweep or a native permission operation.
No canonical task state, receipt history, or explicit user denial changes.
**Inspect workers and actual state first**; do not invoke these commands
for an actively handled request. Other older interrupted decisions use
their specific recovery contract. Do not bulk-delete markers, receipts,
or Git-admin attempt state. Actual host permissions remain final.

## Historical pending-request recovery

Ordinary progress uses the receipt-free reconciliation path above. The following
legacy adapter operations describe retained armed requests, not a requirement to
create new approval prompts after every interruption. Do not delete an uncertain
mutation or relabel its history. Full upgrade retirement of obsolete prompts is
separate from ordinary task progress.

For an explicit historical authority-backed reconciliation, arm
the installed reconciliation adapter for the exact task or scope, present its
returned `short_reply` (`reconcile <STATE> <code>` for a task, `reconcile <code>`
for a scope; the full `reply` also works), and let `UserPromptSubmit` capture and apply the observed
user decision across repositories:

```sh
python "${CLAUDE_PLUGIN_ROOT}/hooks/artifact-reconcile.py" --root "${CLAUDE_PROJECT_DIR}" --artifact-id <plan-id> --target-id <task-id> --operation task-reconcile --target-state PENDING --reason "<reviewed reason>" --assessment "<reviewed assessment>"
python "${CLAUDE_PLUGIN_ROOT}/hooks/artifact-reconcile.py" --root "${CLAUDE_PROJECT_DIR}" --artifact-id <plan-id> --target-id <checkpoint-id> --operation scope-reconcile --assessment "<reviewed assessment>"
```

Ambiguous armed requests, changed identities, stale inputs, wrong replies, or a
foreign Git repository all fail closed. Re-run `eligible` after reconciliation;
the prompt reply itself is not proof that the lifecycle mutation committed.
If a mutation response is lost, submit the same exact reply again: the adapter
replays its durable operation ID and receipt without recapturing authority. A
request that has not reached mutation can be cancelled with:

```sh
python "${CLAUDE_PLUGIN_ROOT}/hooks/artifact-reconcile.py" --root "${CLAUDE_PROJECT_DIR}" --artifact-id <plan-id> --cancel --prompt "<exact returned reply>"
```

If a crash left a complete pending request before its prompt route was
registered, use this command instead. It refuses an active route or any
in-flight mutation:

```sh
python "${CLAUDE_PLUGIN_ROOT}/hooks/artifact-reconcile.py" --root "${CLAUDE_PROJECT_DIR}" --artifact-id <plan-id> --cancel-orphan
```

If a durable mutation attempt exists, neither cancellation path can clear it.
Replay the exact stored operation and receipt under the reconciliation lock:

```sh
python "${CLAUDE_PLUGIN_ROOT}/hooks/artifact-reconcile.py" --root "${CLAUDE_PROJECT_DIR}" --artifact-id <plan-id> --recover
```

Recovery clears the request only on a committed replay or a closed-set engine
result proving no commit (`REVISION_CONFLICT` or `OPERATION_ROLLED_BACK`). Other
errors retain it for investigation. Re-arm only after cancellation or recovery
succeeds; a committed recovery is not permission to repeat the mutation.

An `IN_PROGRESS` task after interruption requires inspecting the current
worktree, outstanding tools and actual task results, **not a new approval code**.
Use receipt-free `task-reconcile` only after establishing its real state; do
not assume completion or duplicate dispatch. `REVIEW` is implementation-ready,
not passing verification. Source changes affect applicable proof; presentation
and routine bookkeeping do not by themselves justify reviewer cascades.
The legacy `scope-reconcile` proof form remains an explicitly attested claim,
not the default method of resuming independent tasks.

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
