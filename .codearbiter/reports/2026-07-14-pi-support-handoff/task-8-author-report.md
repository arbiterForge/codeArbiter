# Task 8 author report - host-neutral prune policy and Pi-native compaction

Status: implementation complete; focused gates green.

## Test-first evidence

- RED: `.github/scripts/test_prune_policy_parity.py` initially failed because `_prunepolicy` did not
  exist.
- RED: `plugins/ca-pi/tools/test/compaction.test.ts` initially failed because `compaction.ts` did not
  exist.
- RED: `.github/scripts/test_pi_compaction_surface.py` initially failed on the absent internal charter
  and Claude-specific Pi prune prose.
- RED: runner seam tests proved the role-only runner rejected zero-tool internal compaction.
- RED: lifecycle integration tests failed until the bridge-backed runner and native event installer
  existed.
- GREEN: the completed compaction suite passes 11/11, including exact no-tool launch, empty-tool child
  attestation, lifecycle/trust gating, confirmed-only audit, redaction/bounds, cancellation, invalid
  plans, no-op plans, and persisted-plan idempotency.

## Implemented slice

- Added stdlib-only `_prunepolicy.py` with `SemanticEntry`, `PrunePolicy`, `PrunePlan`, deterministic
  protected-tail selection, tier ordering, marker/idempotency policy, metrics, audit codes, and plan
  fingerprints.
- Routed Claude's protected boundary, strategy selection, metrics, audit outcomes, and condensation
  markers through the shared policy without changing its JSONL parse/mutation/write/backup codec.
- Added a bounded `prune_plan` request to the Pi Python bridge. It receives content-free semantic
  entries and returns a schema-shaped plan through the existing bounded response envelope.
- Added `compaction.ts`: Pi semantic codec, bridge-backed policy runner, policy-selected native result,
  exact provider/model and zero-tool summarizer, redaction and UTF-8 byte caps, lifecycle/trust-gated
  native events, active-session non-mutation, confirmed-compaction audit, and idempotency.
- Extended the hardened two-argument child runner with one discriminated `internal-compaction` launch.
  It admits only the exact packaged internal charter with zero tools and zero skills; ordinary roles
  retain catalog-exact non-empty allowlists and all fd3/attestation/environment/process-tree controls.
- Allowed the enforcement-only child to attest an empty active-tool set for that private launch while
  still rejecting unknown/duplicate tools and leaving ordinary role validation unchanged.
- Added generated `includes/compaction-charter.md`. It is an internal include, not an agent charter;
  generated `roles.json` remains exactly 28 public roles.
- Replaced Claude-specific Pi prune guidance with host-neutral serialization wording and explicit
  Pi-native active-session compaction safety.

## Verification

- `npm --prefix plugins/ca-pi/tools exec -- vitest run test/compaction.test.ts`: 11/11 pass.
- Focused compaction/status/dispatch/runner integration: 78/78 pass.
- `npm --prefix plugins/ca-pi/tools run typecheck`: pass.
- `npm --prefix plugins/ca-pi/tools run build`: pass; parent and child bundles regenerated.
- `.github/scripts/test_prune_policy_parity.py`: 3/3 pass.
- `.github/scripts/test_pi_compaction_surface.py`: 2/2 pass.
- `.github/scripts/test_prune_nudge.py`: 42/42 pass.
- `unittest discover -p "test_prune*.py"`: 68/68 pass.
- `tools/sync-core.py --check`: 44 shared files x 3 hosts byte-identical.
- `tools/build-surface.py --check`: Claude, Codex, and Pi renders synchronized.
- `.github/scripts/test_pi_package.py`: 21/21 pass.
- `.github/scripts/test_pi_child_live.py`: 7/7 pass plus supported-version live contract PASS.

The first full Pi Vitest run exposed one stale registration-count assertion (47 actual vs. 45
expected) because native compaction adds two event handlers. The assertion is updated to the explicit
five parent lifecycle + two enforcement + two compaction registrations; its isolated real-loader
rerun passed. A later combined rerun reached the same test in 5.245 seconds and tripped its fixed
5-second timeout before the assertion, so the unrelated timing flake is recorded rather than hidden.
