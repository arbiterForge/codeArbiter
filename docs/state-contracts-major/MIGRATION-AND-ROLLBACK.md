# Compatibility, migration and rollback

## Preserve by default

Preserve stable IDs, canonical serialization, schema/wire vocabulary, command aliases, request finality, operation-id replay, journal/before-image history, scope/host/session bindings, platform-specific locking and approved remote-effect timing. Parent delegation is not permission to remove deterministic guards. Ordinary assistive progress remains ordinary; optional evidence and harvest do not become prerequisite ceremonies.

## Migration record

For each durable format change, record old/new schema versions and readers/writers; exact affected file classes; before-images and checksum; preflight/refusal conditions; atomic/CAS boundary; lost-response readback; repeated execution; mixed-version behavior; and what makes rollback no longer safe. A filename migration with no tested readers is incomplete.

If the existing closed schema rejects additive fields, do not casually add retry/delegation metadata to it. Use a supported existing representation or a deliberately versioned owner contract, with all consumers and generated schemas updated together. Register every new durable output class with its real writer and strict reader before enabling writes. Do not solve output recognition by ignoring arbitrary directories.

## Required upgrade fixtures

- Last relevant published artifact to the new candidate, with actual installed metadata and exact archive identity.
- Empty state; existing ordinary progress; strict historical evidence; retained task checks; retired records; scope baselines.
- Pending, partially committed, lost-response and corrupt transaction fixtures, preserving refusal/recovery semantics.
- Existing user settings changed after install; uninstall must preserve current ownership boundaries.
- Interrupted terminal obligations and duplicated/replayed recovery attempts.
- Parent/child session switch, revoked grant, stale generation and effect committed before result/audit settlement.

## Rollback boundary

Before new durable writes, a code rollback may suffice if readers still accept old state. After a new format or committed side effect, rollback must use the owner’s verified before-image/CAS path only when current state still matches the expected post-image. Subsequent user edits require forward reconciliation. Never delete checks/history to make a retirement operation pass.

After a release, registry publication, merge or remote effect, do not claim a local rollback undid it. Preserve immutable tags and published versions; observe and recover forward. A report/receipt failure does not authorize rerunning completed author work.

## Evidence invalidation

Classify changes by actual dependency: source bytes, schema, producer/consumer, host runtime, platform, build chain, authority bindings or remote publication identity. Invalidate only evidence depending on the changed inputs. Keep historical evidence with its original scope; do not rewrite it to look fresh. Do not wipe progress merely to express stale evidence unless B explicitly selects that semantic rule in the SMARTS decision.

## Performance and ordinary-work continuity

Bound startup/reentry scans and background recovery. Optional harvest backlog, unavailable telemetry or missing optional attestation must not stall independent authorized work. Report the local debt and next action. If an authority-bearing audit or shared-store integrity condition is necessary before a particular mutation, block that dependent mutation and continue safe independent work.
