# Migrating and recovering a spec/plan pair

Migration is an explicit, reviewed pair operation. It is not performed by
opening a file, starting codeArbiter, installing or upgrading the capability,
or reading a legacy repository. There is no mass-conversion step. Making the
capability available never reinterprets an existing Markdown pair; an explicit
reviewed migration remains required.

## Before conversion

Select one matching legacy specification and implementation plan. Preserve both
files' exact bytes and hashes. A plan-shaped Markdown file with the same basename
is not sufficient proof that the pair is related or that its specification was
approved.

Build candidate typed models plus a complete, nonoverlapping line-disposition
map for each source file. Every source line must map to a new record/field or be
identified as retained provenance, intentionally omitted information, or an
unresolved ambiguity. Preserve old acceptance-criterion numbers, status text and
source locations as provenance. Do not manufacture fields from prose, infer
approval from words such as `APPROVED`, or convert checked boxes into current
task evidence.

## Preview, review and apply

1. `migration-preview` validates the legacy source hashes, both candidate models
   and both line maps. It produces a digest-bound review report without changing
   the repository.
2. The existing external coordinator owns the human-review requirement for the
   candidate pair and every loss/ambiguity disposition.
3. `migration-apply` supplies the exact preview digest and records a
   caller-supplied, preview-digest-bound mapping-review attestation. That record
   does not authenticate the actor and is neither spec nor implementation
   approval. If either source changed after preview, the operation stops as
   stale.
4. Cutover writes and validates both HTML artifacts under one recovery-aware
   transaction before removing the two Markdown authorities. It never leaves
   one live legacy member beside one live HTML member as successful execution
   state.

The new pair is `DRAFT`, and `authority_verified` remains false until the normal
workflow separately obtains and binds current approvals. Old approvals and task
statuses are not transferred. Legacy reading remains available for repositories
that have not been explicitly converted.

## Recovery model

Ordinary existing-artifact mutations use a unique operation ID, the last-read
revision and model hash, a bounded writer lock, same-filesystem staging and an
intent/recovery record containing exact old/new identities. Pair migration uses
different explicit identities: apply binds the preview digest to exact legacy
bytes, candidate models and line mappings; rollback binds the cutover journal
and unchanged candidate bytes. Ordinary reads never perform hidden recovery
writes.

If a response is lost, retry the same operation ID with identical input or run
`recover`. Do not create a new operation, steal a lock based only on its age,
downgrade the binary, hand-edit the HTML or delete one side of the pair.
Completed replay returns the original outcome; an older journal can require a
refresh. A rolled-back operation reports `OPERATION_ROLLED_BACK`, not success.
`RECOVERY_REQUIRED` and `COMMIT_OUTCOME_UNKNOWN` stop execution until the
transaction is reconciled.

## Rollback

Stop dispatch first. Before any new-format mutation, `migration-rollback` may
restore both captured Markdown files and remove both HTML authorities through a
guarded, journal-bound inverse transaction. It refuses rollback if either
candidate changed since cutover, preventing unrelated work from being clobbered.

After new-format work exists, simple rollback is intentionally unavailable.
Produce a loss report and perform a reviewed reverse export or reconciliation;
retain the HTML artifacts, transaction records and repository history as
evidence. Never treat deleting HTML or installing an older binary as recovery.

## Selected production-repository pilot

The current pilot copies the exact bytes of codeArbiter's real
`reaudit-ra03-read-only-review-aggregation` spec/plan pair into a disposable,
isolated repository root. It does not mutate the authoritative pair. The test
binds the recorded source hashes, so a change to either production file makes
the evidence stale instead of silently exercising different bytes.

The fresh native-Windows candidate proved that making the installed capability
available leaves the Markdown pair byte-identical and does not create HTML.
Explicit preview and apply then produced a draft HTML pair with no transferred
authority. A selected-pair fault injection then recreated the durable prepared
state after the spec switch but before the plan switch. Exact-format discovery
rejected the mixed pair, engine reads returned `RECOVERY_REQUIRED`, and dispatch
eligibility was never reached. Explicit complete recovery restored the HTML
pair, after which the same operation ID and request replayed the durable result.
A downgraded client with no payload failed
`CAPABILITY_MISSING`; exact-format routing remained HTML and no Markdown shadow
was recreated. Journal-bound rollback restored both original SHA-256 byte
streams, removed both HTML authorities, and retained exact cutover and rollback
journal identity, source/candidate hashes and before-image evidence.

The complete result, candidate identity, executable and release-manifest
digests, source hashes, test locators and limitations are retained in
`docs/artifacts/DEFAULT-ROLLOUT-PILOT.json`. The mapping deliberately classifies
all lines as a fixture-only historical disposition: `semantic_mapping_verified`
is false. The pilot proves transition safety, not semantic adoption, production
authority, or approval of that real pair. `T024-PILOT-EVIDENCE.json` is retained
as historical evidence and is not current qualification.

## Unsupported and unqualified cells

The current evidence does not cover:

- hosted exact-head Windows, Linux and macOS results for the committed pilot revision;
- actual Claude, Codex and Pi release-channel installation and provenance;
- production SMARTS/reviewer/verification authority-adapter captures or full real-host feature/sprint traces;
- physical power interruption or remote/network filesystem guarantees; or
- native multi-browser and full accessibility qualification; or
- current frontier/low-tier HTML farm performance.

Local Windows and native WSL Linux process-death, lock and replacement suites
are green. The semantic migration/rollback suite and selected production-byte
pilot ran locally on native Windows. Cross-compilation is not native-host proof.
Promotion of the default typed-HTML rollout still requires the committed
revision's required hosted checks; the HTML farm remains independently
disabled. Existing Markdown pairs remain exact-format authorities until an
explicit migration.
