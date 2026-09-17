# Internal artifact protocol

Product `v0.1.0` candidate · protocol `codearbiter.artifact-api/0.1.0` · schema `0.3.1` · renderer `codearbiter-html/0.1.0`.

This is an internal subprocess contract, not a proposal for another public command. No operation executes code, shell snippets or verification commands stored in the documents.

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
| Content | `create`, `apply`, `diff`, `read`, `validate`, `rebrand`, `export` |
| Integrity/recovery | `repair-preview`, `repair-apply`, `recover` |
| Authority | `capture`, `approve`, `plan-bind`, `prerequisite` |
| Execution ledger | `snapshot`, `eligible`, `task-start`, `task-review`, `task-block`, `task-reconcile`, `scope-reconcile`, `accept-scope` |
| Derived farm | `farm-project`, `farm-seal`, `farm-verify` |
| Legacy transition | `migration-preview`, `migration-apply`, `migration-rollback` |

`capture` **writes** immutable events and receipts even though it does not increment an artifact revision. Locks, journals and a contextual-pagination key are engine-managed metadata; “read operation” does not mean the filesystem can never acquire such metadata. Host permission classification must distinguish content writes and event writes from ordinary reads. No generic content mutation can set approval or task acceptance.

## Identity domains

`artifact_id` and record IDs are stable semantic addresses. Normative content has a separate hash from the full model and rendered file bytes. A document revision increments on state/presentation changes as well as content edits; identity plus hash is the concurrency token. Hashes do not identify a human approver.

A plan's `spec_ref` binds the exact normative specification digest. The initial mode is `draft_preview`. `plan-bind` requires the approved current spec and validates coverage. The newly bound plan must receive its own applicable approval. Normative changes invalidate approval; history is preserved.

Each canonical HTML contains one authoritative embedded JSON model, inline presentation and generated record boundaries. Normal readers revalidate its structure, hashes and exact renderer correspondence. Human-only HTML edits produce `RENDER_DRIFT`; they are not silently interpreted as semantic edits.

The canonical JSON domain intentionally permits only safe-range integers, booleans, strings, null, arrays and objects. Duplicate keys, invalid UTF-8, unpaired surrogates, fractional/exponent numbers, excessive depth and trailing data are rejected. It is a restricted canonical subset, **not** a general arbitrary-number RFC 8785 implementation. The schema evaluator similarly supports only the declared vocabulary used by the packaged schemas; it is not a general-purpose Draft 2020-12 library. Unknown schema keywords fail initialization.

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

Contextual `read` includes the selected record, applicable dependencies and governing context from the contributing documents. Follow every `next_cursor` until `context_complete: true`. Cursor identity includes contributing model and receipt/event bytes, not just the requested plan. A record is never silently cut in half; an oversized indivisible record fails with a specific diagnostic. The final context ticket is required by `task-start` and becomes stale when its contributing context changes. Delivery of context is not proof the model understood it.

Cursors and completion tickets are SHA-256 names for engine-written cooperative delivery receipts under `.codearbiter/.artifacts/context-tokens/`. They are not authentication secrets and do not claim resistance to an unrestricted same-user filesystem writer. A digest without its corresponding engine-written receipt is rejected.

## Cooperative approval and evidence

`capture` persists a **host-supplied actual workflow event**, naming the artifact ID, normative digest, record subject, actor, origin, source text, authority kind, verdict and kind-specific payload. It creates a content-addressed receipt and does not approve the artifact. `approve` separately checks the matching receipt and readiness.

The test suite's synthetic user/reviewer events are test fixtures only. Production callers must not construct invented reviewer identities or successful results just to clear these gates. The existing codeArbiter cooperative-attestation threat model remains explicit; unrestricted same-user tampering is outside the claimed boundary.

A verification payload names the input digest, specification digest, task digest and actual outcomes for every declared command. Outcomes include the command-definition digest, exit, named test statuses and stdout/stderr digests. Missing, failing, duplicate or skipped required tests fail verification. A separate spec-review receipt is required. The binary verifies receipt structure and binding; the orchestrator—not this binary—runs commands and performs review.

`snapshot` derives an input identity from file bytes, executable flags, directory membership, normative documents and declared platform/toolchain identity. Engine-generated outputs are excluded only when their output contracts validate. Whole `.codearbiter` is never excluded. Two matching scans reject ordinary concurrent changes. Default input roots cover the repository except Git metadata; large repositories need a reviewed explicit policy. External compiler/environment dependencies and existing host-generated outputs require a complete policy/adapter inventory before production rollout.

Within one checkpoint, a predecessor in `REVIEW` can unblock a dependent after current verification and spec review. Across checkpoint scopes, dependencies need current accepted-scope evidence. After all tasks reach `REVIEW`, reverify against the current combined input state and perform the scope quality review. `accept-scope` records the entire scope together. A later source change marks evidence stale without pretending earlier work never happened. Interrupted `IN_PROGRESS` tasks and changed scope baselines require explicit reconciliation.

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

## Durable replay results

Journal 0.2.0 records the bounded original completion result. Identical retries preserve that result even after later artifact edits. Journal 0.1.0 remains readable and explicitly requests a fresh identity where original metadata is absent. Rolled-back operations return `OPERATION_ROLLED_BACK`, never a successful mutation result. Export responses use `companion_links` for the disposition of companion links.
