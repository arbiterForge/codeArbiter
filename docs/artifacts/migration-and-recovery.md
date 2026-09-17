# Migrating and recovering a spec/plan pair

Migration is an explicit, reviewed pair operation. It is not performed by
opening a file, starting codeArbiter, installing the capability or reading a
legacy repository. There is no mass-conversion step, and the default rollout
remains disabled.

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

## Selected pilot result

A native-Windows pilot built from clean commit
`12ab0ef2d720420b90265f35675fb961375a439b` exercised one legacy pair through the
installed subprocess protocol independently of the pre-existing automated
migration fixtures:

- preview completed with SHA-256
  `e9e1d9670e57b1f3896944664260ef51ad5c432be666192074871631746e7b13`;
- apply with a fixture-supplied mapping-review attestation bound to the preview
  digest produced a draft pair with `authority_verified: false` and no
  transferred approvals;
- both Markdown authorities were absent only after the pair cutover committed;
- rollback restored both original files byte-for-byte and removed both HTML
  authorities; and
- the inverse transaction committed with `refresh_required: true`.

The same exact candidate created a new spec/plan fixture, exercised the
approval/binding boundary with synthetic receipts, started execution, recreated
the process, observed the task still `IN_PROGRESS`, explicitly reconciled it to
`PENDING`, acquired a fresh context ticket, redispatched it, then reviewed and
accepted the scope. That complements the legacy rollback drill; it does not
prove a real host's authority adapter or a human-authentication boundary.

The exact observed fields, clean source commit, toolchain identity,
release-manifest/executable digests, canonical receipt and workflow-event
objects with their locators, transaction identities and limitations are retained
in `docs/artifacts/T024-PILOT-EVIDENCE.json`. It is a direct local protocol
observation, not an independently signed CI receipt or a production authority
trace.

## Unsupported and unqualified cells

The current evidence does not cover:

- hosted exact-head macOS native write/recovery and package execution;
- hosted exact-head Linux results for the current revision;
- actual Claude, Codex and Pi release-channel installation and provenance;
- production authority-adapter captures or full real-host feature/sprint traces;
- physical power interruption or remote/network filesystem guarantees; or
- native multi-browser and full accessibility qualification; or
- current frontier/low-tier HTML farm performance.

Local Windows and native WSL Linux process-death, lock and replacement suites
are green. The semantic migration/rollback suite and selected pilot ran natively
on Linux and Windows respectively; Windows has not run the complete semantic
migration test suite, while the selected pair pilot did run there. Cross-
compilation is not native-host proof. The default typed-HTML rollout and HTML
farm therefore remain disabled, while legacy Markdown behavior remains
unchanged.
