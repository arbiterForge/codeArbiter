# Migrating and recovering a spec/plan pair

Migration is an explicit, reviewed pair operation. It is not performed by
opening a file, starting codeArbiter, installing or upgrading the capability,
or reading a legacy repository. There is no mass-conversion step. Making the
capability available never reinterprets an existing Markdown pair; an explicit
reviewed migration remains required.

## Before conversion

Select one matching legacy specification and implementation plan. Preserve both
files' exact bytes and hashes. A plan-shaped Markdown file with the same basename
is not sufficient proof that the pair is related or that any recorded decision
was actually authorized.

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

The new pair is `DRAFT`, and `authority_verified` remains false. Already-authorized
work can continue through ordinary task progress without obtaining artifact
approvals. Old approval labels and task statuses are preserved as historical
provenance, not transferred into current verified evidence. Legacy reading
remains available for repositories that have not been explicitly converted.

## Schema upgrades and mixed history

The current writer uses schema `0.3.2` and reads historical `0.3.0`/`0.3.1`
documents without relabeling them. Before a selected upgrade, preserve the whole
`.codearbiter/` store, including journals, provenance, observations and historical
receipts, along with the relevant worktree changes. A copy of only the visible
spec and plan is not a complete recovery point.

Use a matching installation-pinned runtime and inspect exact artifact identities.
An old client must refuse newer state it cannot interpret. If newer edits exist,
keep them and use forward recovery; restoring an old snapshot over them would
discard work. Historical approvals remain historical, and neither a package
upgrade nor a successful replay creates new authority or verification.

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

## Repository-context source upgrade and recovery

The repository-context writer keeps canonical human-readable Markdown and a
source-bound version 2 provenance record for each selected content document.
Ordinary authorized refresh uses `context-preview` and `context-apply` with the
returned `preview_ref` and `preview_sha256`; no approval receipt, scout profile
or actor ticket is required. Initial finalization uses `context-finalize-preview`
and the same apply path. An initialized refresh never repeats finalization.

Use `create` for a genuinely absent document, explicit `adopt` for supported
missing/v1 provenance, and `update` for a managed v2 pair. Bind current document
and provenance byte identities, the selected content and current source evidence.
The preview is inert; inspect its proposed change before applying. The writer
rechecks those identities under its lock, retains a historical provenance
preimage on adoption and writes the selected document/provenance pair together.
A selected whole-document replacement must preserve the user-owned content that
was not authorized for replacement. Unsupported shapes or stale identities
refuse without raw-edit fallback. Task, question, audit, release and ADR history
remain with their own writers. Hash equality does not certify semantic truth;
ordinary provenance remains unreviewed unless actual review evidence exists.

An interrupted context write leaves a journal for explicit `recover`. Retry
with the same operation ID and input after a lost response. Completing or
rolling back a pending transaction requires the recorded before/after bytes;
if a human changed either target, recovery reports a conflict and retains the
edit and pending journal for reconciliation. An unsupported journal version
blocks another context write rather than being deleted or interpreted by an
older engine. A stale expected document or provenance identity likewise
refuses replacement.

Version 1 provenance remains readable as legacy coverage while selected
records upgrade. Mixed version 1/version 2 coverage is incomplete, and even
a current version 2 identity does not establish semantic verification on its
own. A version 1 writer refuses to replace a version 2 or unsupported record;
an older host cannot claim verified-context reliance by silently skipping a
newer record. Canonical Markdown stays available for reading and authorized
task-time evidence use. An unavailable or invalid installation-pinned writer stops that mutation. It
does not prohibit safe source inspection, and a successful preview never grants
host permissions or certifies the installed host. Older receipt-based context
operations remain compatibility paths for their recorded history, not the
ordinary refresh prerequisite.

Native guidance publication and removal are conditional P1 work. No native
guidance rollback is claimed until that path is selected, implemented and
qualified; the context-document recovery contract above does not create it.

## Rollback

Stop dispatch first. Before any new-format mutation, `migration-rollback` may
restore both captured Markdown files and remove both HTML authorities through a
guarded, journal-bound inverse transaction. It refuses rollback if either
candidate changed since cutover, preventing unrelated work from being clobbered.

After new-format work exists, forward recovery takes precedence over restoring
an old backup. Simple rollback is intentionally unavailable.
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
