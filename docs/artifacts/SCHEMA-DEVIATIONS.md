# Schema and implementation deviations requiring merge review

The acceptance baseline is the reviewed design reference under `design/original-review2/`, schema 0.2.0. The engine's schema is an implementation artifact, not authority to revise the baseline.

| Area | Current implementation | Required disposition |
|---|---|---|
| Schema identity | First candidate used 0.3.0. The current candidate creates new documents as 0.3.1 and still reads/renders frozen 0.3.0 fixtures without rewriting them. | Review the whole 0.2.0-to-0.3.x model delta. Preserve original schema files; do not assume a version bump is approval. |
| Canonical numbers | Strict safe-range integers only; fractional/exponent JSON numbers are rejected. Numeric text may be represented as text only with an explicit domain contract. | **Not a deviation.** The original v0.1.0 contract explicitly limits the hashing profile to strings, booleans, null, arrays, objects and safe integers and requires floats to be rejected. Retain cross-language conformance vectors for that declared subset. |
| Standalone presentation | 0.3.1 permits an empty companion locator. Single-file exports omit unavailable companion links, retain normative identity and do not alter canonical sources. | This is the export defect correction. No implicit rewrite or reapproval of old documents. |
| Schema validation | Closed evaluator for its packaged vocabulary, not a general Draft 2020-12 implementation. | Review coverage of every keyword used and error behavior; do not advertise general compliance. |
| Native storage | Linux uses anchored `openat`; Windows and macOS use `os.Root` containment with native locks. Linux and Windows pass native recovery suites; macOS is compile/vet-only locally. | Require exact-host macOS CI before promotion. Do not claim physical-power-loss, remote-filesystem or mixed-runtime guarantees. |
| Workflow integration | On-demand pilot guidance and selected Python seams, not the complete entry-point/consumer rollout. | Complete the consumer inventory and real-host wiring before default activation. |
| Farm | HTML projection, immutable base binding, pre-canary verification, provider-only enrichment, exact-byte sealing and dispatcher enforcement are implemented. Ordinary HTML farm use remains disabled. | T-018/AC-018 is locally implemented; require real authority adapters, native packaged payloads, generated-host/CI proof and fresh frontier/low-tier qualification before promotion. The June 2026 run earns zero current evidence. |
| Authority and verification | Content-bound cooperative receipts; tests use synthetic review identities. Common runner names are recognized, not arbitrary wrapper semantics. | Integrate real host events, independent review and actual named outcome collectors; review input/environment closure. |
| Reference examples | Engine regenerates the original normative content as implementation-format draft examples; their planned test names remain planned. | Review against the originals, not the regenerated views. Do not treat sample plan status as completion evidence. |

The package intentionally contains no automatic migration from reviewed schema 0.2.0 to a live approved runtime store. Reference reproduction is not authority migration. Ordinary reads preserve existing 0.3.0 document bytes; ordinary edits retain the document version and stale approvals when normative content changes. New documents use 0.3.1. Unknown versions fail closed.

## T-023 readiness mismatch

The original plan reproduction preserves T-023's test command with an empty `required_tests` list. The corrected common-runner policy reports `NO_TESTS_DECLARED` and the sample remains a structurally valid, unapproved draft, not ready for execution. The sample generator records that diagnostic rather than fabricating a test set or aborting without explanation. The merging reviewer must resolve the required-outcome collector contract explicitly. The T-023 task definition has not been weakened.

New transaction journals use 0.2.0 for durable original result fields, with 0.1.0 read compatibility. Storage downgrade requires explicit reconciliation; copying an older binary over the new journal writer is not a supported rollback.

## T-018 reviewed path-set expansion

The original T-018 explicitly required T-001 to discover and add the actual runtime/canary entry
paths; documentation-only enforcement was forbidden. The repository's one shared side-effecting farm
backend is `plugins/ca/tools/farm.ts`, with `plugins/ca/tools/farm.js` its generated bundle and Pi
preview consumer. Those two paths are therefore added to T-018. The implementation also necessarily
touches the existing internal protocol/router, evidence snapshot and transaction/store plumbing, plus
CI impact registration. This is an implementation-path expansion required by T-018 step 4, not a
change to AC-018 or the reviewed design artifacts. No public command, agent, persistent tool,
top-level skill or eagerly loaded schema was added.
