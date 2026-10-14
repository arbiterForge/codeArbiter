# Internal artifact protocol

Product `v0.1.0` candidate · protocol `codearbiter.artifact-api/0.1.0` · schema `0.3.2` · renderer `codearbiter-html/0.1.0`.

This is an internal subprocess contract, not a proposal for another public command. No operation executes code, shell snippets or verification commands stored in the documents.

## In-progress assistive overhaul

ADR-0043 changes the native scheduling/progress contract described below. This is
an implementation slice on the overhaul PR, not a released-host claim. The
remaining execution-caller, evidence-applicability, migration, and package compatibility
work remains tracked in [the implementation handoff](../plans/assistive-state-engine-overhaul.md)
and [its progress record](../plans/assistive-state-engine-progress.md). Do not
publish a partial engine/caller conversion.

## Invocation and envelopes

```text
ca-artifact OPERATION --root REPOSITORY --request FILE
ca-artifact OPERATION --root REPOSITORY --request -
```

Supply one UTF-8 JSON object carrying the exact `protocol` value. Standard output contains one JSON envelope with `protocol`, `operation`, `ok` and either `result` or `error`. Diagnostics on stderr are not artifact content. Stdout is capped at 64 KiB, including envelope; bounded reads accept a 4096–65536 byte budget. `validate` can return `ok: true, result.valid: false` with exit 2: this is a failed validation gate, not approval.

Errors are field/symbol-specific and bounded. Do not dispatch or mutate from a partial response. Unknown fields and operations fail; there is no `force` field and no permissive passthrough. Query `schema` for the current closed request shape rather than guessing flags.

## Operation families

| Family | Operations |
|---|---|
| Discovery | `capabilities`, `schema`, `index`, `outline`, `identity` |
| Content | `create`, `apply`, `plan-bind`, `diff`, `read`, `read-batch`, `plan-verification`, `validate`, `rebrand`, `export` |
| Integrity/recovery | `repair-preview`, `repair-apply`, `recover` |
| Explicit attestation | `capture`, `approve`, `sprint-approval-context`, `sprint-approve`, `smarts-apply` |
| Execution ledger | `prerequisite`, `snapshot`, `eligible`, `verification-status`, `task-start`, `task-review`, `task-block`, `task-reconcile`, `scope-reconcile`, `accept-scope` |
| Derived farm | `farm-project`, `farm-seal`, `farm-verify` |
| Legacy transition | `migration-preview`, `migration-apply`, `migration-rollback` |

`capture` **writes** immutable events and receipts even though it does not increment an artifact revision. Locks, journals and a contextual-pagination key are engine-managed metadata; “read operation” does not mean the filesystem can never acquire such metadata. Host permission classification must distinguish content writes and event writes from ordinary reads. No generic content mutation can set approval or task acceptance.

## Identity domains

`artifact_id` and record IDs are stable semantic addresses. Normative content has a separate hash from the full model and rendered file bytes. A document revision increments on state/presentation changes as well as content edits; identity plus hash is the concurrency token. Hashes do not identify a human approver.

A plan's `spec_ref` binds the exact normative specification digest. The initial mode is `draft_preview`. Ordinary `plan-bind` selects the current structurally valid specification and validates references and coverage without requiring approval. If the selected source has a genuine current approval, its `approved_source` provenance is retained; otherwise the binding remains `draft_preview`. Binding does not mint an approval or reset unrelated task progress. Explicit legacy evidence claims still validate their own approvals. Initial combined sprint review is the explicit exception to the sequential order: both documents remain ready drafts until one source-bound `sprint-approve` transaction projects the approved binding and commits both approvals. It cannot replace already-started or previously approved work. Normative changes invalidate approval; history is preserved.

Each canonical HTML contains one authoritative embedded JSON model, inline presentation and generated record boundaries. Normal readers revalidate its structure, hashes and exact renderer correspondence. Human-only HTML edits produce `RENDER_DRIFT`; they are not silently interpreted as semantic edits.

The canonical JSON domain intentionally permits only safe-range integers, booleans, strings, null, arrays and objects. Duplicate keys, invalid UTF-8, unpaired surrogates, fractional/exponent numbers, excessive depth and trailing data are rejected. It is a restricted canonical subset, **not** a general arbitrary-number RFC 8785 implementation. The schema evaluator similarly supports only the declared vocabulary used by the packaged schemas; it is not a general-purpose Draft 2020-12 library. Unknown schema keywords fail initialization.

## Authoring is not an authority preflight

The installation-pinned bridge checks the actual native writer capability before
new HTML authoring. `_select_authoring_route` does not require the installed
approval/verifier/reviewer inventory. `_preflight_plan_authoring` resolves the
exact spec artifact, same-slug target, normative digest, current model identity,
and structural validity; it does not demand an approved or fully ready spec.
Drafts can therefore expose missing work without inventing answers to pass an
approval boundary. Namespace conflicts and a changed source remain actual errors.

The `draft_for_pair` keyword is accepted for compatibility and checked as a
boolean, but no longer grants a special authoring mode. An explicit historical
paired-approval operation still validates its own original attestation contract.
`workflow_preflight()` retains that explicit inventory for consumers that really
use it, including the separate context workflow; it does not decide whether the
native spec/plan writer may author a draft. Native Pi writer admission is not
proof of a complete live Pi workflow, farm support, or changed maturity.

The generated writing-plans skill uses this contract. It plans coherent units of
work rather than mandatory five-minute task slices, records real constraints and
criteria, treats ready diagnostics as guidance, and does not arm approval codes
or verify future runner support simply to draft a plan. Broader sprint/execution
caller conversion remains separate work on this PR, not a claim established by
the drafting skill alone.

## Draft authoring and typed modification

`create` accepts identity, kind, slug, title and summary; optionally a typed `normative` body. A plan additionally names `spec_id`. For a supplied plan body its binding must match that current spec and use `draft_preview`. Missing content can be saved as an honest draft, but `validate gate=ready` will not pass until the required contract fields and relationships exist.

`apply` contains `artifact_id`, unique `operation_id`, `expected: {revision, model_sha256}`, and a nonempty `changes` list. Supported changes:

```json
{
  "op": "record.update",
  "symbol": "AC-001",
  "fields": {"statement": "When both validated values are present, the resolver shall select the environment value."}
}
```

`record.add` selects a supported typed collection and a record; an omitted ID is allocated by the engine. `record.update` cannot change identity or record kind. `record.retire` requires a reason and optionally a replacement reference. Removing nested symbols requires explicit retirement rationale; retired IDs are never reused. `header.update` permits only its defined fields. All changes are validated as one candidate before the transaction begins.

For mutations, fetch `identity` immediately before preparing the request. A conflict is a reason to reread and reconcile, never overwrite. A repeated operation ID is valid only with the identical request. A committed replay returns the transaction outcome; a rolled-back operation returns `OPERATION_ROLLED_BACK` (exit 7), not success. Use a new operation ID only after inspecting the restored state. For a committed replay, retrieve current identity separately instead of assuming the initial response shape.

## Retrieval and bounded context

`index` pages a unique validated catalog. `outline` returns stable IDs and summaries, bound to a model identity. Exact `read` returns the requested whole record and `context_complete: false`.

`plan-verification` is an internal observation for approval preflight. Every page
request supplies `artifact_id`, `expected: {artifact_id, revision, model_sha256,
normative_sha256}`, `offset` and `budget`; the host uses a 16384-byte budget.
The expected identity quartet is required on the first page and every continuation.
A changed identity returns `STALE_CURSOR`, which the approval bridge reports as
`STALE_PLAN_PREFLIGHT`. Other native failures retain their codes.

The result carries the same identity quartet, `context_complete: false`, `offset`,
the stable nonnegative active-task `total`, `tasks` and `next_offset`. Each task
contains exactly `id` and its complete `verification` array. Active task IDs are
strictly ascending and unique across pages; retired tasks and unrelated task prose
are excluded. Offsets, totals and revisions are integers, never booleans. A
continuation equals the current offset plus the number of whole tasks delivered;
the final page has `next_offset: null` and reaches the exact total. An empty
selection returns an empty final page at offset zero. A whole verification array
that cannot fit the requested budget returns `RECORD_TOO_LARGE`, without truncation.
The native projection preserves empty verification arrays; host preflight refuses
an active task with no definitions.

The bridge checks every projected command with the existing Python cwd and
command-definition validator, then collects the source-input snapshot, then
rechecks the full plan identity. Command diagnostics and snapshot diagnostics are
aggregated; a snapshot diagnostic still requires the final identity check. This
path executes no declared command, imports no declared test and performs no test
discovery. A valid single-page preflight uses projection, snapshot and identity
(three native calls); ordinary approval arming adds its existing ready identity
and validation (five calls). Malformed, incomplete or stale delivery refuses
before any pending approval is written.

This operation joins only the existing shared-observation allowlist under the
unchanged two-second lock timeout. It creates no context ticket, authority source,
receipt or artifact, and retains writer exclusion and existing admission checks.

Contextual `read` includes the selected record, applicable dependencies and governing context from the contributing documents. Follow every `next_cursor` until `context_complete: true`. Cursor identity includes contributing model and receipt/event bytes, not just the requested plan. A record is never silently cut in half; an oversized indivisible record fails with a specific diagnostic. The final context ticket describes that delivery and becomes stale when its contributing context changes. `task-start` no longer requires or validates the ticket; the optional field is accepted only for caller compatibility and grants no authority. Delivery of context is not proof the model understood it.

Cursors and completion tickets are SHA-256 names for engine-written cooperative delivery receipts under `.codearbiter/.artifacts/context-tokens/`. They are not authentication secrets and do not claim resistance to an unrestricted same-user filesystem writer. A digest without its corresponding engine-written receipt is rejected.

## Advisory scheduling and ordinary progress

`eligible` returns scheduling advice from the recorded task states and explicit
task dependencies. Its result is labeled `assessment: advisory` and
`evidence_assessed: false`. It returns `next_task`, per-task `waiting_on`, current
recorded reasons, binding currency, and the recorded prerequisite requirements.
Legacy prerequisites have `scope: unspecified`; they are neither silently
satisfied nor automatically treated as plan-wide permission gates. The caller
must assess their actual applicability. Checkpoint order alone does not require
reverification of earlier work. A task in `BLOCKED` or already `IN_PROGRESS` is
not proposed as a new start.

This query performs no source snapshot and validates no approval or review
receipt chain. It deliberately does not return `all_accepted_and_current` or a
verification-input digest. `verification-status` owns those explicit legacy
evidence-assessment fields and retains the real receipt/freshness checks. Do
not substitute its result back into ordinary task selection. The Python
acceptance-proof helper uses that evidence query, retaining its legacy result
key `eligible` only for existing proof consumers pending the caller overhaul.

`task-start` uses ordinary CAS and journaled writes to record a `PENDING` task as
`IN_PROGRESS`. It does not require approvals, a context ticket, or a source
snapshot. A new start of running/stopped work is refused to avoid duplicate
dispatch or silently clearing a stop; an identical operation ID safely replays.

`task-review` without receipts records implementation reported ready for review
as `REVIEW`, with an explicit reason that verification and review were not
assessed. It does not create a test result or review receipt. Supplying receipts
instead makes an explicit evidence claim: both verification and review receipts
are required together and must pass their existing validators. A completion hash
without both receipts is invalid. The first receipted review initializes a
scope's evidence baseline; that baseline is not represented as a pre-work source
snapshot. `task-reconcile` may update progress with a reason without a receipt;
an explicitly supplied receipt is still checked. Callers must inspect actual
work and honor user stop/deny instructions before reconciling or redispatching.

Historical evidence and unrelated progress are preserved. `REVIEW` alone means
neither tests passed nor an independent review occurred. Subject-scoped evidence applicability and active host instruction conversion
remain subsequent work in this same PR. The next section describes the implemented
prerequisite and implementation-completion operations, not installed-host qualification.

## Scoped prerequisite observations and implementation completion

Artifact schema **0.3.2** adds optional `kind: fact | decision` and `task_refs`
to prerequisite definitions. `task_refs` names the active tasks that actually need
that prerequisite. Omitted legacy scope remains `unspecified`, never an inferred
plan-wide permission gate. Classify a legacy requirement using an ordinary typed
`apply` before recording its result. Task references must resolve; do not narrow
a prerequisite's scope merely to hide a real dependency.

The existing `prerequisite` operation accepts a closed `observation` request as an
alternative to its historical receipt form. Supply the ordinary `protocol`,
`artifact_id`, `operation_id`, current `expected` revision/model digest, and
`prerequisite` ID, followed by:

```json
{
  "observation": {
    "outcome": "satisfied",
    "summary": "The service probe returned its expected healthy response.",
    "source": "Current session: the actual service-probe result.",
    "origin": "tool_result"
  }
}
```

This is the observation fragment, not a complete command or an executed result.
Use the actual result, never copy the example as evidence. Outcomes are
`satisfied`, `unsatisfied`, or `unknown`; origins are `tool_result`,
`user_statement`, or `agent_report`. The native engine assigns the recording time,
`provenance: caller_reported`, and a definition digest. It does not authenticate
a conversation, execute the source string, produce authority receipts, or invoke
reviewers. A resolved `decision` needs a reported `user_statement`; an agent's
opinion or an automated check cannot be mislabeled as the user's choice. Actual
host permissions and explicit user stops remain outside this bookkeeping.

Recording an observation changes no legacy authority flag. A newer negative or
unknown observation cannot fall back to an older positive receipt. The explicit
legacy proof query rejects substituting reported information for authority;
ordinary scheduling uses the recorded facts without invoking that proof query.
Prior observations remain in transaction before-images, and the latest observation
is retained when its prerequisite is retired.

Applicability is specific to the prerequisite definition: changing its kind,
requirement, task scope, or source references marks the observation as applying to
an older definition. Changing its title or an unrelated task method does not.
`definition_current` means the definition still matches, **not** that an external
service is live or the result was independently verified. The timestamp, source,
and reported origin remain visible so the agent can decide whether a new check
is useful. Only explicitly affected tasks get `waiting_prerequisites` advice;
independent work remains available. Advice is not a new permission barrier.

Exact and batch symbol reads include `prerequisite_assessment`, with the existing
whole-record response budget and explicit context-incomplete label. They neither
parse presentation HTML nor load authority chains. The same assessment is
available in a collapsed, escaped HTML section on new-schema artifacts.

`accept-scope` with `scope` and a nonblank `reason`, **without a receipt**, records
an implementation batch as `DONE`. Members must have recorded implementation in
progress, ready for review, or complete; a pending/stopped member is not silently
marked done. `DONE` explicitly means implementation complete, checks not assessed.
It makes recorded dependencies available without inventing acceptance or test
results. Existing evidence and genuinely accepted members are retained. The
historical receipt form remains an explicit proof operation; callers cannot mix
its receipt/completion fields with the ordinary progress form.

Old 0.3.0/0.3.1 artifacts remain readable without rewriting their bytes. Introducing
new fields or `DONE` writes schema 0.3.2 through the existing CAS/journal path.
New semantics cannot be stored under an old schema label, and an old engine does
not silently accept the new version. Full mixed-installed-client upgrade and
obsolete-prompt recovery remain T07; this source compatibility is not that claim.

## Reruns and retained task reviews

An explicit completed task review retains the exact verification run it actually
inspected. Do not rewrite that old receipt or pretend it reviewed a newer run.
When a new scope review selects a fresh passing rerun, the native engine now
checks whether the prior task review still covers the current subject, whether
the selected rerun matches its own recorded workspace, whether its normalized
workspace closure matches the still-reviewed work, and whether all supporting
material is retained. When those checks hold, a different run/receipt identity
alone does not require another task review.

The new scope review records the newly selected run and makes its own assessment.
The old task review and original run stay unchanged. Changed source, requirements,
selected support, wrong workspace, or a corrupt run-owned closure do not qualify
for reuse. A failing selected verification is not accepted merely because an
older run passed. This is not a general claim that all checks outside a task's
path list are independent: broader source-scoped applicability remains T04 work.
Nor does it remove the initial per-task review requirement from this explicit
legacy proof path; normal orchestration is being converted separately in T05.

## Cooperative approval and evidence

`capture` persists a **host-supplied actual workflow event**, naming the artifact ID, normative digest, record subject, actor, origin, source text, authority kind, verdict and kind-specific payload. It creates a content-addressed receipt and does not approve the artifact. `approve` separately checks the matching receipt and readiness.

The test suite's synthetic user/reviewer events are test fixtures only. Production callers must not construct invented reviewer identities or successful results just to clear these gates. The existing codeArbiter cooperative-attestation threat model remains explicit; unrestricted same-user tampering is outside the claimed boundary.

A verification payload names the input digest, specification digest, task digest and actual outcomes for every declared command. Outcomes include the command-definition digest, exit, named test statuses and stdout/stderr digests. Missing, failing, duplicate or skipped required tests fail verification. A separate spec-review receipt is required. The binary verifies receipt structure and binding; the orchestrator—not this binary—runs commands and performs review.

`snapshot` derives an input identity from file bytes, executable flags, directory membership, normative documents and declared platform/toolchain identity. Engine-generated outputs are excluded only when their output contracts validate. Whole `.codearbiter` is never excluded. Two matching scans reject ordinary concurrent changes. Default input roots cover the repository except Git metadata; large repositories need a reviewed explicit policy. External compiler/environment dependencies and existing host-generated outputs require a complete policy/adapter inventory before production rollout.

Snapshot input identity is ship-set membership (ADR-0042). In a git work tree the members are the git index entries present on disk, plus untracked non-ignored files within the plan's input roots, minus the plan's excludes. A deleted index entry is absent, a gitlink counts as its pointer only, and executable flags come from the index mode. One fixed exemption exists: `.codearbiter/gate-events.log` is never counted in any snapshot, whatever the plan says, and it stays tracked as the audit trail. Every other `.codearbiter` path still counts. Outside a git work tree, membership is read from the filesystem (`membership: filesystem`). The root must be the top level of its work tree: a root that is a subdirectory of one has no `.git` of its own and counts as outside git; a git probe that fails inside a work tree fails closed with `INPUT_MEMBERSHIP_UNAVAILABLE` and never falls back to the filesystem. An unmerged git index (conflicted paths) also makes a snapshot fail closed until the conflict is resolved. The manifest format is `codearbiter.verification-inputs/0.2.0`, which records membership; receipts bound to a 0.1.0 manifest read as stale. Within one operation each evidence object is validated at most once and scans are bounded. Raw reads are reused only up to a 64 MiB per-operation retained-byte budget, past which an object can be read again, but validation is never skipped.

For advisory scheduling, a predecessor recorded as `REVIEW` or `ACCEPTED` can make its explicit dependent available without treating either label as current verification. Explicit legacy scope-acceptance claims remain separate: after all member tasks reach `REVIEW`, their current evidence and the scope quality review are checked. `accept-scope` records the entire scope together. A later source change marks evidence stale without pretending earlier work never happened. Interrupted work needs inspection and a reasoned progress update, not another artifact approval. Changed legacy evidence baselines still have their explicit scope-reconciliation operation while the remaining overhaul is implemented.

The outer `/feature` human checkpoint and host scheduling policies are not replaced by this ledger. The current overlay does not complete all those entry-point integrations.

## Filesystem and recovery

Repository operations use anchored directory descriptors on Linux and `os.Root` containment on Windows
and macOS, with bounded regular-file reads, an OS writer lock, staged replacement, durable
before-images and an operation journal. Linux and Windows have fresh native recovery evidence; macOS
support remains provisional until its exact-host CI cell passes. Unsupported platforms return
unsupported rather than receiving an untested rename-based guarantee.

Ordinary validation or stale-CAS rejection leaves canonical artifacts unchanged. Once a journaled replacement may have happened, the result can be `COMMIT_OUTCOME_UNKNOWN` with an operation ID. Retry identical input or use `recover` with `complete`/`rollback`. A pending pair transaction blocks canonical reads. Recovery rejects third-party endpoint edits instead of overwriting them.

Process-death tests exercise actual subprocess exits at stage/journal/replacement boundaries. They are not physical power-loss tests and do not certify every filesystem or network mount. Historical transaction records are retained; automatic garbage collection is not implemented.

`repair-preview` identifies a model-valid but view-inconsistent file. `repair-apply` is explicit, bound to source-byte/candidate hashes, and preserves original bytes. The candidate offers digest-based repair preview, not an interactive visual semantic merge.

`export` writes an explicitly noncanonical standalone HTML copy under `.codearbiter/exports/`. It removes companion browsing because the companion is not part of a single-file export. Qualified references remain visible as text. The original canonical pair is not modified, and the export retains the normative digest but has its own model/file identities. There is no independently editable JSON sidecar.

## Legacy conversion

Legacy Markdown remains with the original workflow until explicit conversion. `migration-preview` takes reviewed typed normative content plus a complete nonoverlapping line mapping for each source. Every line is mapped, historical or explicitly out of scope; a disposition requires its reason and target. It does not ask a model to infer omitted obligations.

`migration-apply` requires the exact preview identity and a recorded review. The new documents start as drafts. Old approval and acceptance prose is not transferred as authority. A pair cutover journals HTML creation and Markdown retirement together. Original bytes remain in history. `recover` handles an uncertain cutover; `migration-rollback` inverses a completed cutover only while canonical endpoints still match it. Intervening edits block rollback.

## Derived farm projection

`farm-project` accepts only a current eligible checkpoint slice from an approved HTML pair. It checks
the minimal closed runtime projection against canonical task IDs, paths, dependency order and
verification argv, then requires a cooperative `farm_authorization` receipt binding the current
spec/plan/input identities, scope, slice, base bytes and fresh failing-test results. Projection and
content-addressed binding are committed in one recoverable transaction. Commands are represented for
the existing farm runtime but are never executed by the artifact engine.

`farm-verify phase=canary` requires the exact un-enriched canonical projection bytes and a current
source binding. After canary/model selection, callers may add only `meta.model` and
`meta.apiBaseUrl`; `farm-seal` records the exact full bytes and the caller's provider-selection
assertions. `farm-verify
phase=dispatch` requires that seal to match the effective provider. The shared built dispatcher calls
these checks before creating reports/worktrees or making a network request. Derived receipts are
correspondence records under the cooperative same-user threat model, not editable planning authority
or cryptographic approver authentication. `selection_source` and `origin` are auditable caller
statements, not independently authenticated provenance; the enforced fact is correspondence between
the current source binding, exact execution bytes and effective model/base URL.

## Known unsupported integrations

Typed-HTML farm projection and runtime guards are locally implemented, but the HTML farm path remains
disabled until real authority adapters, installed host payloads, exact-head generated-host/CI proof
and a fresh frontier/low-tier qualification matrix pass. The June 2026 run earns zero current
qualification credit. Existing legacy farm JSON/runtime behavior remains unchanged. Linux and Windows
native candidates have local storage/recovery and bridge evidence. Linux has a descriptor-relative
cold-install proof. The reviewed release-only builder pins all staging roots, rejects false native
architecture and unsupported identity, and requires qualification receipts bound to exact commit,
protected workflow run, platform, digest and named native tests. A separately required job assembles
all three exact-host candidates into the canonical package roots; Linux and Windows cold execution
pass from every staged root without Go or PATH fallback, while a production dependency/source guard
rejects network-capable packages and direct network syscalls. The ordinary Windows developer installer
deliberately remains fail-closed. No actual release channel yet applies the staged payload, and there
is no hosted exact-head or release/promotion evidence.

## Review-3 schema compatibility and limits

New artifacts advertise schema **0.3.1**. This patch permits an empty companion locator for truly standalone exports. The engine also accepts existing schema-0.3.0 artifacts, and byte-preservation tests use frozen prior-version fixtures. Reads and ordinary edits do not silently relabel those documents or renew their approvals. Unknown versions still fail closed. Both versions use the same bounded integer-only content domain.

The reviewed design originally used schema 0.2.0. It is retained as a re-rendered review reference under `design/original-review2/` for merge acceptance. The implementation's 0.3.x schema changes are **implementation deviations requiring explicit review**, not amendments to that original contract. The safe-integer-only canonical domain is not one of those deviations; it is the original v0.1.0 contract.

Readiness now requires every declared task path to fall within its verification-input roots and outside explicit exclusions. This proves declared-path coverage only, not transitive build dependencies. Explicitly excluded symlinks are not followed or inspected; an included symlink still blocks a snapshot. Known test-runner spellings (including absolute Go paths, Python module invocation, Node and npm) require named tests. Custom wrappers still need reviewer-declared `required_tests`; the engine does not claim universal command intent detection.

## Completion workspace Git probes

Completion evidence checks use the bridge-selected absolute Git executable for a
closed set of read-only identity, status and index probes. Their arguments are
compiled into the engine; artifact text cannot supply a command or Git option.
The probes disable lazy fetching and filesystem-monitor commands, retain bounded
output and a timeout, and do not invoke a shell. The package guard permits this
reviewed boundary while continuing to reject other process launches, network
packages and direct network syscalls.

## Durable replay results

Journal 0.2.0 records the bounded original completion result. Identical retries preserve that result even after later artifact edits. Journal 0.1.0 remains readable and explicitly requests a fresh identity where original metadata is absent. Rolled-back operations return `OPERATION_ROLLED_BACK`, never a successful mutation result. Export responses use `companion_links` for the disposition of companion links.


## Initial paired approval and delegated SMARTS methods

The private workflow card `core/surface/includes/sprint-authority.md` owns the installed invocation
and consent wording. `sprint-approval-context` freezes both full model/revision identities, projected
plan binding, protected plan scope and optional method delegation. `sprint-approve` consumes two
bound observations from the same actual host reply and persists both approvals in one existing
journal transaction. Generic capture and single-document approval cannot consume its pair sources.
Arming is not approval; interrupted observed submissions replay the same transaction. Changed or
rolled-back definitions require a new actual approval rather than a fabricated retry event.

`smarts-apply` is a closed production producer, not a generic model-verdict ingestion endpoint. Its
original paired user grant must explicitly permit method changes. It changes only an existing task's
steps and retains every other normative plan field. Qualitative comparisons allow a single evidenced
option and in-scope ties; recorded reasoning is not independently verified semantic truth. The
producer refuses affected running writers, retains recorded BLOCKED states/reasons, invalidates
impacted checkpoint/dependency proof, emits
a source-bound `smarts_workflow` receipt and approves only the revised plan definition, never its
work. Original execution, verification, review and security/permission gates still apply.

This extension adds no public skill, command or tool registration. It does not grant prerequisite,
specification, provider, spending, commit or publication authority; enable HTML farm; qualify Pi's
missing pre-model prompt seam; or establish a sandbox against arbitrary same-user filesystem writes.
Native/installed-engine tests use explicitly synthetic host observations. Authenticated host/model
qualification and exact released-artifact claims remain separate.
