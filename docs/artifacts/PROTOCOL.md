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

Errors are field/symbol-specific and bounded. The Python host bridge retains a bounded `field` on `ArtifactError` so callers can identify a damaged artifact or failed repository-relative target. Do not dispatch or mutate from a partial response. Unknown fields and operations fail; there is no `force` field and no permissive passthrough. Query `schema` for the current closed request shape rather than guessing flags.

Storage permission, device I/O, capacity, and closed-handle failures return
`IO_ERROR` with a repository-relative target in `field` and a bounded operation
and OS error class when available. Raw OS paths and file contents are not copied into the
envelope. `IO_ERROR`, `LOCK_FAILED`, `LOCK_TIMEOUT`, and `NO_LOCAL_STORE` use
exit 5; `CORRUPT_JOURNAL` and `ORPHAN_HISTORY` use recovery exit 7. The JSON
`code` remains the authoritative classification. Missing files and unsafe path
objects retain their separate error codes.

On Windows, `index` and shared read-only observations (including `identity` and
`eligible`) return `NO_LOCAL_STORE` when `.codearbiter/`, `.codearbiter/.artifacts/`,
or `store.lock` is missing. This identifies absent or incomplete local metadata,
including in a fresh clone or worktree; it does not report lock contention or an
empty artifact catalog. These reads create nothing and do not proceed without a
lock. Normal authorized mutations initialize lock metadata through the existing
writer path. Existing-store access failures remain `LOCK_FAILED`, contention
remains `LOCK_TIMEOUT`, and unsafe objects remain `UNSAFE_PATH`.

`init-store` initializes that metadata on purpose. It takes the ordinary writer
lock, which creates `.codearbiter/.artifacts/` and `store.lock` when they are
absent, and writes nothing else: no artifact, journal or receipt. Its request
carries only `protocol`. The result is `{"store": "created"}` when it created the
metadata and `{"store": "present"}` when the store already existed, in which case
nothing changes. Linux locks the repository directory itself, needs no lock
metadata, and always reports `{"store": "present"}`. It is not a journaled
mutation and is safe to repeat.

The packaged bridge (`ArtifactClient`) uses it for fresh checkouts. When a call
fails with NO_LOCAL_STORE, the client runs `init-store` once and then retries the
original request once. If initialization is refused, as in a read-only checkout,
the call raises `NO_LOCAL_STORE` naming the refused initialization; a retry that
still finds no store is not retried again. A client constructed with
`initialize_store=False` never initializes and surfaces `NO_LOCAL_STORE` directly.

Lock initialization does not restore receipts referenced by committed plans.
Missing local evidence remains missing; copying tracked artifacts into a fresh
worktree does not establish their referenced verification or approval history.

## Operation families

| Family | Operations |
|---|---|
| Discovery | `capabilities`, `schema`, `index`, `outline`, `identity`, `task-context` |
| Content | `create`, `apply`, `plan-bind`, `diff`, `read`, `read-batch`, `plan-verification`, `validate`, `rebrand`, `export` |
| Integrity/recovery | `repair-preview`, `repair-apply`, `recover`, `init-store` |
| Explicit attestation | `capture`, `approve`, `sprint-approval-context`, `sprint-approve`, `smarts-apply` |
| Execution ledger | `prerequisite`, `snapshot`, `eligible`, `verification-status`, `task-start`, `task-check`, `task-review`, `task-block`, `task-reconcile`, `scope-reconcile`, `accept-scope` |
| Derived farm | `farm-project`, `farm-seal`, `farm-verify` |
| Legacy transition | `migration-preview`, `migration-apply`, `migration-rollback` |
| Repository knowledge | `knowledge-context`, `knowledge-initialize`, `knowledge-cutover`, `knowledge-merge` |
| Local work (initial slice) | `work-create`, `work-get`, `work-list`, `work-origins`, `work-context`, `work-view`, `project-view`, `work-update` |

`knowledge-cutover` has a read-only, cursor-paged `sections` mode that returns
exact Markdown byte spans and source hashes. `preview` and `apply` require one checklist row
per section, mapping every meaningful section to active record or note
references in its matching knowledge document. `apply` also requires the
preview's input identities and commits the cutover in one journaled transaction.

`capture` **writes** immutable events and receipts even though it does not increment an artifact revision. Locks, journals and a contextual-pagination key are engine-managed metadata; “read operation” does not mean the filesystem can never acquire such metadata. Host permission classification must distinguish content writes and event writes from ordinary reads. No generic content mutation can set approval or task acceptance.

## Identity domains

`artifact_id` and record IDs are stable semantic addresses. Normative content has a separate hash from the full model and rendered file bytes. A document revision increments on state/presentation changes as well as content edits; identity plus hash is the concurrency token. Hashes do not identify a human approver.

A plan's `spec_ref` binds the exact normative specification digest. The initial mode is `draft_preview`. Ordinary `plan-bind` selects the current structurally valid specification and validates references and coverage without requiring approval. If the selected source has a genuine current approval, its `approved_source` provenance is retained; otherwise the binding remains `draft_preview`. Binding does not mint an approval or reset unrelated task progress. Explicit legacy evidence claims still validate their own approvals. Initial combined sprint review is the explicit exception to the sequential order: both documents remain ready drafts until one source-bound `sprint-approve` transaction projects the approved binding and commits both approvals. It cannot replace already-started or previously approved work. Normative changes invalidate approval; history is preserved.

Each canonical HTML contains one authoritative embedded JSON model, inline presentation and generated record boundaries. Normal readers revalidate its structure, hashes and exact renderer correspondence. Human-only HTML edits produce `RENDER_DRIFT`; they are not silently interpreted as semantic edits. Catalog-backed reads scan active specs and plans before serving even an unrelated catalog-backed read. `knowledge-context` reads its own knowledge documents without a catalog scan and does not verify spec or plan integrity. The error's `field` identifies the damaged repository-relative HTML path. Public diagnostics truncate `field` after 256 bytes; if it is truncated, inspect the repository for the full path before passing that path to `repair-preview` and `repair-apply`. Repair is explicit. Direct saves and legacy pair migration refuse to cross the 1,024-artifact or 64 MiB catalog limits before writing, while scans still reject out-of-band additions.

The canonical JSON domain intentionally permits only safe-range integers, booleans, strings, null, arrays and objects. Duplicate keys, invalid UTF-8, unpaired surrogates, fractional/exponent numbers, excessive depth and trailing data are rejected. It is a restricted canonical subset, **not** a general arbitrary-number RFC 8785 implementation. The schema evaluator similarly supports only the declared vocabulary used by the packaged schemas; it is not a general-purpose Draft 2020-12 library. Unknown schema keywords fail initialization.

## Small default workflow; historical proof on demand

The canonical model-facing `core/surface/includes/artifacts.md` owns ordinary
authoring, structured retrieval, factual prerequisites, reported checks, and
safe progress. It is intentionally compact. The much larger strict historical
receipt, authority-producer, and legacy pending-request procedures are now in
`core/surface/includes/artifacts-attestation.md`, loaded only when an actual
claim, explicit human checkpoint, historical recovery, or independently
applicable host/publication control requires that specific protocol.

The split is a **presentation/context optimization**, not a new permission
mode or an engine semantics change. Every original section is retained;
the existing native evidence and recovery validators remain unchanged. The
new reference is regenerated into Claude/Codex/Pi alongside the default
include. Normal tasks do **not** need to consume legacy evidence machinery to
read a task, update a plan, run a relevant check, or record `DONE`. Genuine
user denials, sandbox policies, unsafe writes, and commit/release boundaries
remain independently enforceable.

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

Cursors and completion tickets are SHA-256 names for engine-written cooperative delivery receipts under `.codearbiter/.artifacts/context-tokens/`. They are not authentication secrets and do not claim resistance to an unrestricted same-user filesystem writer. A digest without its corresponding engine-written receipt is rejected. Contextual `read` needs a writable receipt store and an exclusive lock; on a read-only store it fails with an I/O diagnostic naming the receipt path. `read` with `mode: "exact"` remains available without a receipt and reports `context_complete: false`.

## Compact task-context retrieval

`task-context` is a read-only request with `artifact_id` (plan ID),
`task` (symbol ID), the exact current `model_sha256`, and optional
`budget` (4,096 to 65,536 bytes, 16,384 default). It returns a bounded
`assessment: advisory` packet: the task's implementation fields and
declared checks, criterion summaries actually referenced by that task,
current dependency states, scoped prerequisite observations, unknown
legacy-prerequisite applicability, and matching plan/source identities.

The packet intentionally has `context_complete: false`: unrelated
requirements, decisions, source files and complete verification results
were **not** fetched. Retrieve additional symbols only where relevant;
never treat omission as proof of absence. `binding_current: false` is
visible and needs source reconciliation. A changed plan hash returns
`STALE_CURSOR`; missing/retired tasks and dangling references fail
without fabricated content. A packet too large for its requested budget
fails `RECORD_TOO_LARGE` without partially returning a record.

No source snapshot, authority receipt, reviewer, context ticket, test
execution, workspace scan, or persisted cache is created by this read.
The engine's normal transaction/pending-record checks still apply before
informational reads. It is not a permission-granting or verified-acceptance
operation and does not claim model comprehension or independent test proof.

The packet also carries the repository knowledge relevant to the task
(`knowledge`, below): `knowledge`, `knowledge_omitted`, `knowledge_unreadable`,
`knowledge_unresolved_references` and `knowledge_unmatched_records`. They fill
whatever budget the task fields leave.

## Repository knowledge and decomposition

Two optional HTML kinds hold repository context as records: `knowledge`
(`.codearbiter/context/<slug>.html`, ID `CTX-<SLUG>`) for the five narrative
documents (`project`, `tech-stack`, `coding-standards`, `security-controls`,
`code-map`), and `decomposition` (`.codearbiter/decomposition/<slug>.html`, ID
`DECOMP-<SLUG>`) for greenfield interview answers, intended architecture, phases
and proposed work. The ID is derived from the slug, so a cross-document link
renders as `../context/<slug>.html#<record>` by identity rather than through one
companion path. Both reuse the ordinary model, renderer, journal and typed
`create`/`apply`/`read`/`outline` operations. Being optional kinds, they are never
scanned by spec or plan reads, so a damaged knowledge page cannot veto those.

A record has `type`, `title`, `statement`, `basis` (`user-reported`,
`source-observed`, `inferred`, `proposed`, `unknown`), `scope.paths`,
`related_refs` and `source_refs`. Only a `source-observed` record must cite a
source. A `command` record carries `argv`, `cwd`, `purpose` and `run_state`
(`unrun` until a run is reported; a reported state is not verification). A
decomposition `question` carries `status` and `answer`; a `work_item` may carry
its stable `work_id` and origin in its `promotion` back-reference. Older
`board_id` back-references remain readable until their selected owner upgrades
them. `knowledge` documents also hold
`notes`: unclassified text with its source `origin` (path and byte offsets).
Nothing in a record is policy: CONTEXT.md frontmatter keeps activation and stage,
and the scope blocks in `security-controls.md` stay the operative configuration.
`CONTEXT.md` frontmatter line `context-format: html` selects this layout.

- `knowledge-context` (read; `paths`, optional `budget`) returns the records
  relevant to those paths: records whose `scope.paths` overlap them, unscoped
  `command`, `constraint`, `exclusion` and `convention` records, and one explicit
  hop of their `related_refs`. Each document is parsed on its own; a damaged one
  is listed in `knowledge_unreadable` and the rest are still returned. A whole
  record that does not fit is named in `knowledge_omitted`, never truncated.
  Unrelated records are only counted. The result carries no admission,
  permission or ticket field and writes nothing.
- `knowledge-initialize` (`operation_id`, `expected` CONTEXT.md digest) adds the
  `<!--INITIALIZED-->` marker once the five knowledge documents exist and parse
  and the task board is well formed. Unknown records and open questions do not
  prevent it; no provenance, receipt or completed interview is required.
- `knowledge-cutover` (`operation_id`, `mode: preview|apply`, `expected`) switches
  a prepared Markdown repository in one journaled transaction. `knowledge.py
  convert` first creates empty HTML documents and lists the Markdown sources
  with a fingerprint token; an agent reads them and adds records or notes by
  inference, omitting secret values. Preview refuses any nonempty Markdown
  document lacking records, writes nothing, and returns input digests. Apply
  requires those digests, rewrites `CONTEXT.md` to select HTML, reduces
  `security-controls.md` to its scope blocks, removes replaced Markdown and
  provenance (original bytes remain in journal before-images), and adds the
  no-conversion lines for artifact HTML to `.codearbiter/.gitattributes`.
  A retry replays; cutover over converted state fails `ALREADY_CONVERTED`.
  Reads and package updates never cut over.
- `knowledge-merge` (`operation_id`, `path`, `base`, `ours`, `theirs`,
  `expected_current_sha256`) resolves a Git conflict in one knowledge page by
  record ID. A record changed on one side takes that side; one changed
  differently on both sides is returned as a conflict and nothing is written.
  Two different records added under the same new ID keep ours and give theirs
  the next free ID, rewriting links in theirs' records and reporting the rename.

The host helper `hooks/knowledge.py` wraps these for skills; see
`core/surface/includes/knowledge.md`.

## Local work items (initial slice)

`work-create` mints an opaque `WORK-` identity and, for a new native project,
an opaque portable `PROJECT-` identity in `.codearbiter/work/project.json`.
The project identity and each work HTML file are canonical tracked state;
`.codearbiter/.artifacts` remains the local journal, not the only copy of the
backlog. A repository with a legacy `open-tasks.md` still uses that board as its
work owner. The local work.py facade routes create and selected reads to the
existing board writer. New rows store a random portable WORK- ID beside the
board's exact (from ...) origin. Older promoted rows with no stored work ID
use a deterministic origin-derived ID, never a title or dotted board ID. A
caller with no origin must provide an operation ID, which becomes the stable
correlation key. A retry finds the same item even after it moves to
done-tasks.md. Legacy create stores the operation ID with the row and refuses
its reuse for a different origin. It can record intent, type and initial
spec/plan IDs as board subfields; selected context reports its omissions.
Existing rows without an origin need selected adoption and are not assigned
a guessed ID. Legacy listing pages the origin-backed items and reports old
unkeyed rows separately. Start, completion and archive use an exact origin
selector and a hash of the selected board block checked inside the board
writer's lock. A stale retry refuses rather than overwriting a later edit;
legacy board updates do not claim the native journal's exact replay result.
For a legacy update whose response might be lost, save the selected
`board_sha256` from `work-get` before the first attempt and pass it as
`--expected-model-sha256` on both attempts. Without that option, the CLI reads
a fresh board hash for each invocation, so repeating the command after another
edit could act on the changed row. A repeat after a successful update with the
original hash refuses as stale; it does not return the original result.
Completion can record already-performed work without inventing a start date
and leaves its check unknown. Legacy rename, later attachment and reopen
remain unsupported through this facade. Native creation still refuses while
the legacy board owns the project.

Work titles are labels, never lookup keys. `work-get` reads a selected ID
directly, including archived work. `work-list` pages active and archived IDs,
reading only the selected page's work models, including each origin for
deduplication and completion date for an age-based archival preview. A fresh
native project lists zero work without creating a project identity; orphan
work files without that identity still refuse.
`work-origins` checks up to 32 exact source keys in one bounded directory pass,
including archived items, for harvest preview. Its read is not a frozen
content snapshot. `work-list`'s membership digest rejects a continuation
after a create; it is not a frozen content snapshot. `work-create` with a
bounded local `SOURCE#ITEM` origin (including `ARTIFACT#SYMBOL` and harvest
source keys) scans active
and archived items for that correlation key and returns the matching stable ID
on retry. A retry with the same title, intent and type can fill a missing spec
or plan attachment after an interrupted promotion, even when the item is
archived. The repair checks the exact pair and journals only the selected work
file; it returns `attachment_repaired: true` without changing progress or check
status. A conflicting existing attachment or changed intent returns the
current item with `input_differs: true` and does not overwrite it.
The `work.py create` facade requires a caller-stable `--operation-id` or
`--origin` so an uncertain response can be retried without minting a second
item. A changed request with the same origin receives a distinct operation ID
and reports the current item or the scoped attachment repair.
The facade also requires `--operation-id` for updates. An exact retry supplies
the same expected revision and model SHA-256; reusing the ID against later
state refuses a changed request instead of overwriting that state.
`work-update` uses revision plus model SHA-256 CAS and the ordinary journal for
rename, attachment, start, completion, reopen and archive. Exact spec and plan
IDs are checked when attached; the work HTML links to their canonical pages.
Completion records local progress and leaves `check_status: unknown`. This
slice has no operation to assert a passing check, merge, release or deployment.

Native `work-context` returns bounded selected work plus current attached
document identities and concise summaries. Its `assessment: advisory` and
`context_complete: false` fields prevent a summary from impersonating a full
source read. Optional `paths` and `knowledge_refs` select relevant stored
knowledge in the same bounded response. The response names requested inputs,
unreadable optional documents, unresolved refs and records omitted by the
budget; the caller supplies these refs because this first work model does not
persist code-path scope. `hooks/work.py context` accepts `--path` and
`--knowledge-ref`. Legacy `work-context` returns selected `work`,
`context_complete: false`, and `omitted`; it does not include `assessment` or
attached-document summaries. When optional knowledge selectors are supplied,
it reports them and explicitly says the legacy adapter cannot join knowledge.
Read those attachments by exact artifact ID when needed. The canonical native
work page joins intent, progress, check status and links to the separate spec
and plan. Native `work-view` reads the selected
work and its exact attachments through `work-context`, then returns an HTML
overview. Progress, checks, delivery and tracker sync remain separate; unknown
check or delivery state is never inferred from completion. The overview has no
canonical model container, is not stored by the engine and is rejected by
`render.Parse`. `hooks/work.py view <WORK-ID>` prints the HTML to stdout. The
response also provides `view_path: .codearbiter/views/work/<WORK-ID>.html`;
saving the HTML there makes its relative spec and plan links valid. This
derived location stays outside canonical artifact discovery. The command does
not write a second work owner or scan unrelated artifacts. Native
`project-view` renders one bounded `work-list` page as an inert project work
overview. It shows local progress and checks separately, labels delivery as
unobserved and directs tracker state to each work item, and links to the existing
canonical work pages.
Its `offset`, `limit` (at most 16), `membership_sha256`, `next_offset`,
`total`, and `content_snapshot: false` have the same membership-only
continuation semantics as `work-list`. It refuses an absent portable project
identity. `hooks/work.py project-view` prints HTML; the response's
`.codearbiter/views/project/<PROJECT-ID>-<offset>.html` path is derived and
optional. When another page exists, the HTML includes the next offset and
membership digest in a complete `work.py project-view` command. The engine
does not save the page or include it in artifact discovery.
Legacy projects continue to use their board; this native-only derived view
reports unsupported through the legacy facade. Architecture and cycle
overviews remain future work.

Native GitHub issue effects use a separate portable
`.codearbiter/work/provider.json` binding and an optional `provider_effect`
inside the canonical work model. `work-provider-configure` accepts a finite
GitHub repository, credential reference and `after_merge` or `immediate`
timing. It stores the reference, never the credential. `work-effect-stage`
records pending intent; `work-effect-claim` journals `outcome_unknown` before
any network send; `work-effect-record` stores the exact issue number and URL
after readback. The fixed `hooks/work.py sync <WORK-ID>` adapter checks Git
origin against the binding. For the default `after_merge` timing, pass
`--pull-number N`: the adapter reads the merged PR, checks its default-branch
base and local HEAD ancestry, and reads the pending canonical work model at
the merge commit before claiming the effect. The persisted claim records that
PR number and merge commit. A failed merge check leaves intent pending.
`immediate` needs no PR number. A lost create response stays
`outcome_unknown`; `hooks/work.py reconcile-issue <WORK-ID> --number N`
verifies an exact remote work-ID marker before recording the binding and never
posts another issue. A user-supplied raw native claim is structurally checked
but does not itself perform remote verification; use the adapter for the
verified send. The facade's raw JSON request route excludes claim and record;
the native protocol still trusts its cooperating caller for those fields.
GitHub Projects and remote issue updates are not yet supported.

The facade also accepts `--request -` with one UTF-8 JSON object of at most
64 KiB: `{"schema":"codearbiter.work-request/0.1.0","operation":"work-create","request":{...}}`.
The closed operation set is `work-create`, `work-get`, `work-list`, `work-origins`,
`work-context`, `work-view`, `project-view`, `work-update`, `work-provider-get`,
`work-provider-configure` and `work-effect-stage`. The selected owner validates the
operation-specific request and returns one JSON result; the ordinary CLI
`view` and `project-view` verbs print raw HTML for an explicit human-view action. Native
`work-update` requires `expected: {"revision": N, "model_sha256": "..."}`.
Legacy `work-update` accepts `operation_id`, `work_id`, `action` (start,
complete or archive), and `expected_board_sha256` instead of `expected`.
The legacy `work-context` request accepts `work_id` and optional `budget`,
`paths` and `knowledge_refs`, with the omissions described above. The stable
operation ID and owner-specific
CAS rules still apply to mutations, including an uncertain retry.

## Advisory scheduling and ordinary progress

`eligible` returns scheduling advice from the recorded task states and explicit
task dependencies. Its result is labeled `assessment: advisory` and
`evidence_assessed: false`. It returns `next_task`, per-task `waiting_on`, current
recorded reasons, binding currency, and compact prerequisite assessments.
Prerequisite rows retain IDs, scoped task references and recorded status, with
`details_omitted: true`; full titles, requirements and observations remain in
exact symbol reads. The response has `context_complete: false`, `tasks_total`,
`tasks_omitted`, `prerequisites_total` and `prerequisites_omitted`. Rows that
cannot fit within the CLI response limit are omitted without changing the
global `next_task` decision. Use `outline` for symbol IDs and `read` with
`mode: exact` for prerequisite details, task definitions and reported checks.
`task-context` provides task state and reason. These reads retain their own
response bounds: an indivisible oversized record or reason can still produce
`RECORD_TOO_LARGE`. No stored content is truncated.
Legacy prerequisites have `scope: unspecified`; they are neither silently
satisfied nor automatically treated as plan-wide permission gates. The caller
must assess their actual applicability. Checkpoint order alone does not require
reverification of earlier work. A task in `BLOCKED` or already `IN_PROGRESS` is
not proposed as a new start.

This query performs no source snapshot and validates no approval or review
receipt chain. It deliberately does not return `all_accepted_and_current` or a
verification-input digest. `verification-status` owns those explicit legacy
evidence-assessment fields and retains the real receipt/freshness checks.
Its per-task `current_evidence` describes receipt freshness separately from
`has_conflicting_check_reports` and `conflicting_check_reports`. A failed
declared command with matching task/criterion definitions remains a conflict
until a later matching caller-reported pass has unchanged declared source
inputs. Ad-hoc reports, skipped/unknown checks, obsolete definitions and
changed source inputs cannot erase a current failure. Unbound failures are
shown with `worktree_freshness: unassessed`. These reports remain
`caller_reported`, with incomplete source coverage; they never become receipts.
A failing unindexed report also conflicts with each current declared command
whose `argv` and `cwd` match exactly, under the same task/criterion and source
applicability checks. Its summary uses `matched_command_index` and
`command_match: exact_argv_cwd`; the original report stays unindexed. Unrelated
ad-hoc failures do not conflict, and unindexed passes do not acquire declared
success semantics.
Existing verification captures also record the hashes of up to 16 retained
task reports. A successful, currently applicable verification receipt can
supersede reports included in its captured boundary and older report history;
attaching a receipt later does not cover reports made after that capture.
Capture retains the issued report boundary while revalidating source and
normative identities; reports made after issuance neither replace that boundary
nor invalidate otherwise current evidence. Old pending contexts without a
boundary remain capturable without acquiring an ordering claim.
New reports include the engine-owned `recording_operation_id`, so repeated
identical outcomes remain distinct even within the same clock second.
Historical reports and evidence contexts remain readable; a context without
the optional boundary does not establish report ordering.
`check_reports_total`, `check_reports_ignored`, `check_reports_superseded`, `check_history_bounded` and
`check_history_unassessed` disclose retained history and its limits. If history
was trimmed and a declared command has no retained applicable pass/fail,
absence of contrary reports remains unassessed. `all_accepted_and_current`
requires fresh acceptance receipts, no unresolved conflicting reports and no
such history uncertainty. Recording a current recovery report can resolve a
conflict without changing progress, deleting receipts or repeating approvals
and reviews. Full report content remains available through exact task reads. Do
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

## Ordinary command-level check observations

`task-check` is a CAS/journaled plan mutation, separate from historical
`verification-status` acceptance proof. Supply current
`artifact_id`, `operation_id`, `expected` revision/model digest,
`task`, and a closed `check` object like:

```json
{
  "task": "T-001",
  "check": {
    "argv": ["go", "test", "./..."],
    "cwd": ".",
    "outcome": "fail",
    "exit_code": 1,
    "summary": "A relevant test assertion failed.",
    "source": "Current session: command tool result.",
    "origin": "tool_result"
  }
}
```

This is an example observation fragment, **not a command to execute or
a real test result**. Actual `outcome` is `pass`, `fail`, `skip`, or
`unknown`. `exit_code` is required for a reported pass; skipped/unrun
checks cannot invent a code. A provided `command_index` must name and
match an existing verification definition's exact `argv` and `cwd`;
a pass must use its declared successful exit code. An ad-hoc result omits
that index and **cannot** assert that named tests passed. Each result may
carry at most 1,024 characters of bounded, inert `output_excerpt`.

The engine never executes these arguments, runs a collector, dispatches
reviewers, or mints a verification receipt. It adds a native recording
timestamp, `provenance: caller_reported`, current spec normative digest,
task-subject digest (verification commands, paths, `shared_inputs` and
references) and the exact *referenced* normative criterion digest.
Historical records without the newer criterion digest retain their old
whole-spec applicability semantics; they are never silently narrowed.
Real permission checks remain host-owned.
The latest result is visible in model-facing `task-context`, exact/batch
symbol reads, and escaped human-readable HTML. The task packet shows only
the latest three notes and reports omitted counts. The document keeps
the latest sixteen, with earlier observations preserved in existing
transaction before-images. No second ledger or cache is created.

`definition_current` means only that the recorded check definition and
referenced normative criteria still match. A different spec summary or an
unrelated criterion change no longer restarts this task's assessment; a
changed referenced requirement does. A stale plan/spec binding is always
reported separately, never silently refreshed. Older observations preserve
their original whole-spec applicability rules. Without an external spec
(e.g. when rendering a standalone HTML artifact), criterion applicability
remains unknown rather than falsely current or stale.

`task-check` also attempts a **bounded, read-only, optional scoped-input
fingerprint** for the task's repository-relative `paths` and explicitly
declared `shared_inputs`. Known build-control files at the repository root
and the verification command's working directories (for example `go.mod`,
package manifests/lockfiles, `tsconfig.json` and `pyproject.toml`) are
included with both present and absent states. A directory task path hashes
its immediate/nested members, so additions, deletions and renames affect
the result. It does not run code or execute the declared test.

The scope is bounded to 256 visited entries, depth 12, 2 MiB per file,
and 12 MiB total. It refuses unsafe generated state paths, symlink/reparse
inputs and ambiguous or changing handles through the existing rooted
filesystem. If no declared task/shared source actually exists or a limit
is exceeded, recording **continues** with `scope_unassessed_reason`;
no fake digest is generated. The model-facing `task-context` read checks
the source subset again and reports `worktree_freshness` as:

- `scoped_unchanged`: only the selected bounded inputs match.
- `scoped_changed`: selected source/configuration bytes or membership changed;
  refresh the affected checks, not unrelated task reviewers.
- `unassessed`: missing historical fingerprint, empty/unsafe/unbounded
  source selection, or inability to make a safe observation.

**Every scope result has `scope_complete: false`.** This is not full
import/build dependency closure, named-test attestation or proof that an
external service is unchanged. Exact/batch symbol reads and HTML, which
lack the live rooted source/spec pair, continue displaying explicitly
unassessed status. An earlier pass never conceals the latest
failure/skipped/unknown report, and reported checks do not change
`PENDING`/`DONE` to `ACCEPTED`.

This optional execution-field addition is inside the **unpublished
schema 0.3.2 candidate**; it is never silently written to a 0.3.0/0.3.1
artifact without the native version upgrade. Mixed installed-package
rollback and complete subject/file impact analysis remain unqualified.

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

Snapshot input identity is ship-set membership (ADR-0042). In a git work tree the members are the git index entries present on disk, plus untracked non-ignored files within the plan's input roots, minus the plan's excludes. A deleted index entry is absent, a gitlink counts as its pointer only, and executable flags come from the index mode. One fixed exemption exists: `.codearbiter/gate-events.log` is never counted in any snapshot, whatever the plan says, and it stays tracked as the audit trail. Every other `.codearbiter` path still counts when it is a ship-set member. A gitignored, untracked `.codearbiter` file is not a member, so it does not change the identity; track it to make it an input. Outside a git work tree, membership is read from the filesystem (`membership: filesystem`). A root below the top level of a work tree, such as a monorepo package, uses that work tree's membership scoped to the root, so the enclosing `.gitignore` applies there too. If the enclosing work tree ignores the root itself, the snapshot fails closed. A git probe that fails inside a work tree fails closed with `INPUT_MEMBERSHIP_UNAVAILABLE` and never falls back to the filesystem. An unmerged git index (conflicted paths) also makes a snapshot fail closed until the conflict is resolved. Membership probes accept one piece of environment-injected Git configuration: the bridge's resolved `core.excludesFile`, passed as `GIT_CONFIG_COUNT=1` with an absolute value. `GIT_CONFIG_PARAMETERS`, `GIT_CONFIG` and any other `GIT_CONFIG_KEY_n`/`GIT_CONFIG_VALUE_n` pair are dropped. Configuration files selected by `GIT_CONFIG_GLOBAL`, `GIT_CONFIG_SYSTEM` and `GIT_CONFIG_NOSYSTEM` still apply. A root policy that needs more than 512 anchored directories, such as hundreds of roots under distinct parents, fails with `MAX_INPUTS`; consolidate the roots under fewer common parents. The manifest format is `codearbiter.verification-inputs/0.2.0`, which records membership; receipts bound to a 0.1.0 manifest read as stale. Within one operation each evidence object is validated at most once and scans are bounded. Raw reads are reused only up to a 64 MiB per-operation retained-byte budget, past which an object can be read again, but validation is never skipped.

For advisory scheduling, a predecessor recorded as `REVIEW` or `ACCEPTED` can make its explicit dependent available without treating either label as current verification. Explicit legacy scope-acceptance claims remain separate: after all member tasks reach `REVIEW`, their current evidence and the scope quality review are checked. `accept-scope` records the entire scope together. A later source change marks evidence stale without pretending earlier work never happened. Interrupted work needs inspection and a reasoned progress update, not another artifact approval. Changed legacy evidence baselines still have their explicit scope-reconciliation operation while the remaining overhaul is implemented.

The outer `/feature` human checkpoint and host scheduling policies are not replaced by this ledger. The current overlay does not complete all those entry-point integrations.

## Unanswered legacy prompt supersession (adapter; not a native permission)

The canonical Python approval helper also offers internal
`retire --root <repo> --artifact-id <plan> --reason <text>` for the
historical **0.2 paired approval** only. It uses the existing serialized
pair-cancellation handler and refuses a durable reply/submission.
The old observer publishes immutable source observations *before* writing
the submission record; retirement also scans at most 513 names in the
bounded observations directory and checks exact content hashes, frozen
pending contexts and prompt identity. A matching observed reply, corrupt
immutable record, or over-limit directory fails closed. This scan runs
**only on explicit legacy prompt retirement**, never on normal task
selection, context reads or work progress.
An old **0.1 single approval** cannot distinguish an unanswered prompt
from a lost committed response and deliberately fails with
`LEGACY_APPROVAL_RECOVERY_REQUIRED`. It must be inspected rather than
automatically deleted.

The canonical prerequisite helper offers
`retire --root <repo> --artifact-id <plan> --prerequisite-id <id>
--reason <text>` only for the validated **ARMED** state. Its existing
per-artifact cross-process lock rejects `CONFIRMED` and `CAPTURED`
states, which retain exact-source recovery. Both return a non-authorizing
superseded disposition, without a new native API operation or another
state store. They are *manual, narrow legacy recovery helpers*; normal
execution never needs a new artifact approval/prerequisite code.

The existing `artifact-reconcile.py` host helper has an explicit
`--supersede --reason <nonblank-text>` path for a previously armed,
**unanswered** task/scope reconciliation prompt. It takes only the repository
root and plan artifact ID; **no old user code or exact prompt string** is
required. It reads a validated bounded pending record under the existing
per-artifact transition lock, verifies its prompt-route binding, and refuses
any durable mutation attempt, ambiguous marker location or unsafe root.
It reports `disposition: unanswered_prompt_superseded`,
`mutation_attempted: false`, and `authority_granted: false`.

This operation cancels obsolete *question routing*, **not actual work** or
an accepted user decision. It does not mutate native artifacts, snapshots,
receipts or the durable transaction log. A possible prior mutation must be
replayed under the exact stored ID via `--recover`; the accepted
`REVISION_CONFLICT`/`OPERATION_ROLLED_BACK` noncommit results remain a
closed set. The preexisting exact-prompt `--cancel` operation remains
available for other historical consumers. A missing route, an already
submitted attempt, or a conflicted legacy/current marker is an error, not
proof of noncommit. The helper never launches a verifier or renews a
prerequisite. A normal resumed task uses identity + advisory state and
receipt-free progress instead.

This is a **partial T07 transition**: mixed installed-client compatibility,
approval/prerequisite pending-marker recovery, and package rollback after
new edits still require separate qualification. It is not a new public
command or an all-prompt cleanup service.

## Historical schema 0.3.1 to assistive 0.3.2: exact-byte upgrade/rollback

An old 0.3.0/0.3.1 HTML spec/plan is read without rewriting its source bytes.
The first journaled mutation that introduces 0.3.2-only observations,
`shared_inputs`, or `DONE` records writes the **same artifact ID**, preserved
task states, evidence history and new schema identity. An identical operation
ID replays the same committed operation; it never runs the work a second time.
The before-image is retained in the engine's existing transaction history.

**Do not run two engine generations against one repository concurrently.**
An older 0.3.1 client fails closed with `UNSUPPORTED_VERSION` once it
encounters a new-format member of the canonical pair; it cannot continue
writing other artifacts in that repository. This is intentional, not missing
data or a reason to downgrade the HTML schema label. Update the installed
cohort to the compatible engine/bridge and active caller resources first.
No automatic Markdown conversion or reapproval is part of this cutover.

For a rollback *before subsequent changes*, preserve the candidate's
journal and exact pre-upgrade files. Restore old files only after checking
there have been **no newer edits** and no uncertain mutation to recover.
Never simply copy an old backup over a changed plan. The native
`migration-rollback` API applies only to an explicitly reviewed,
completed **Markdown-to-HTML** cutover; it refuses an edited candidate and
is **not** a general schema-downgrade method.

After any 0.3.2 write or change to task/source evidence, prefer forward
recovery with the compatible engine. Use `identity`, `task-context`,
exact/batch symbol reads, and a standalone `export` to
`.codearbiter/exports/<name>.html` before considering any manual
migration. The export records its source hash and cannot replace the
canonical pair. Retain all receipts/history and make an explicit new
reviewed forward migration if older tooling must be restored. A previous
binary's refusal is safer than silently discarding modern state.

A reproducible disposable compatibility probe is
`python tools/test-artifact-mixed-schema.py --old <0.3.1-binary>
--candidate <0.3.2-binary>`. The binaries must be exact trusted versions;
the probe creates no project-wide state. It checks old reads preserving
bytes, a retained user stop, one journaled new observation and idempotent
replay, older-client rejection, source ID/history, and unchanged canonical
bytes after an export. The probe is fixture evidence, **not** live host,
security or distribution qualification.

This compatibility rule does not silently retire submitted approval or
prerequisite markers. A historical answered or in-flight request must use
its owner-specific exact-operation recovery; only *unanswered* legacy
reconciliation questions can use the separately documented code-free
supersession. Never fabricate user consent or delete unknown state.

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

Legacy Markdown remains with the original workflow until explicit conversion. `migration-preview` requires both spec and plan mappings for the same slug in one request, with reviewed typed normative content and a complete nonoverlapping line mapping for each source. Every line is mapped, historical or explicitly out of scope; a disposition requires its reason and target. It does not ask a model to infer omitted obligations.

`migration-apply` requires the same pair, the exact preview identity, and a recorded review. The new documents start as drafts. Old approval and acceptance prose is not transferred as authority. A pair cutover journals HTML creation and Markdown retirement together. Original bytes remain in history. `recover` handles an uncertain cutover; `migration-rollback` also accepts historical completed two-edit cutovers while canonical endpoints still match them. Intervening edits block rollback.

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

Completion workspace probes require Git 2.45 or newer, which supports
`--no-lazy-fetch`. An older Git that rejects this option returns
`UNSUPPORTED_VERSION` (exit 6); the engine does not retry without the no-fetch
guard. This requirement is separate from the ADR lifecycle verifier's Git
requirement.

## Durable replay results

Journal 0.2.0 records the bounded original completion result. Identical retries preserve that result even after later artifact edits. Journal 0.1.0 remains readable and explicitly requests a fresh identity where original metadata is absent. Rolled-back operations return `OPERATION_ROLLED_BACK`, never a successful mutation result. Export responses use `companion_links` for the disposition of companion links.

## Obstructed transaction stores

`Pending()` and `Infrastructure()` name the offending repository-relative
transaction or history entry in `field`. An unexpected transaction entry blocks
new writes; an unreadable, oversized or malformed final journal blocks both new
writes and recovery of that operation. Orphaned or missing history blocks
`Infrastructure()` snapshots but does not by itself block committed replay or
new writes. Preserve the entire store and inspect the named entry before
changing it. Stop all artifact operations that can access this store, including
other `ca-artifact` processes, for the full manual reconciliation. For a foreign
entry, retain its bytes and metadata outside the store, establish that no valid
journal references it, and reconcile the entry before resuming operations. A
final `.json`
may describe already changed targets even when no
`.new` stage remains, so stage-file absence is not evidence that it is safe to
remove the journal. Restore readability or the exact retained journal bytes,
then use the normal `recover` operation under the writer lock. If the journal
cannot be recovered, reconcile each target against trusted before and after
evidence; the engine must not guess a transaction outcome.

A missing before-image blocks snapshots, while valid committed journals still
support `Pending()` and exact-ID replay. A new write does not reconstruct the
missing history. Restore the before-image only from a trusted copy
whose SHA-256 matches the `before_sha256` in its valid journal entry, then rerun
the snapshot. A mismatch remains a corruption error. The engine treats
`.codearbiter/.artifacts` as local operational metadata: a fresh clone or
worktree can initialize without inherited journals, and Git tracking is not
required for normal operation. This repository tracks no files there and does
not ignore the directory. Git history is therefore not a backup for these
before-images. Preserve the whole local store when exact-ID replay, rollback,
or audit history must survive a worktree move or cleanup. Do not prune or
quarantine history without a separate policy for recovery, replay and audit.


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
