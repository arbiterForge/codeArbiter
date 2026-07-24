# Blocker 3 independent-review fix report

**Recorded:** 2026-07-15
**Branch:** `feat/pi-support`
**Status:** review findings fixed and locally verified
**Commits:** none

## Scope

This fix resolves every finding in `blocker-3-task-security-review.md` without changing a
dependency, manifest, lockfile, production configuration surface, public command, or endpoint.
It preserves the existing final-argument snapshot, source-identity, unknown-tool, dormant-command,
and read-advisory contracts.

## Root cause

`EnforcementInstaller.deactivate()` reset only the bootstrap flags. The already registered final
unknown-tool handler, result handler, and built-in wrapper definitions had no lifecycle predicate,
so they remained live after a partial installation followed by dormant activation or
`session_shutdown`. The wrappers also captured the first enabled cwd. Merely bypassing the bridge
while inactive would still have delegated to a native executor rooted at that stale cwd.

The bootstrap refusal separately interpolated the untrusted `event.toolName` directly into its
structured reason. Pi serializes that reason into RPC/tool failure output, so an opaque
secret-shaped or control-bearing name could cross the failure-text boundary unchanged.

The real-Pi fixture armed a one-shot fault, but its test only observed the outer lifecycle error and
fail-closed result. It did not independently attest that the intended registration fault was the
fault consumed by that run.

## RED evidence

The following focused command was run before the production fix:

```powershell
npm test -- --run test/tool-guard.test.ts -t "bootstrap refusal serialization|deactivation makes every partially"
```

Result: **RED**, 2/2 selected tests failed for the intended reasons.

- `bootstrap refusal serialization omits an opaque secret-shaped control-bearing tool name` found
  the injected secret-shaped text and serialized CR/LF/NUL escapes in the refusal.
- `deactivation makes every partially installed final stage dormant without stale cwd or bridge
  activity` received the retained final unknown-tool block after `deactivate()` instead of
  `undefined`. The same table-driven regression covers guard-only, result-handler, and each
  built-in wrapper installation stage.

During the stale-cwd trace, a further focused RED was recorded:

```powershell
npm test -- --run test/tool-guard.test.ts -t "reactivation cannot reuse"
```

Result: **RED**, 1/1 selected test failed. An allowed bootstrap read called the bridge with
`C:/first-enabled` after lifecycle activation had moved to `C:/second-enabled`.

## Implementation

### Lifecycle-complete final enforcement

The persistent final guard and tool-result handler now receive the installer's lifecycle-active
predicate and return immediately while inactive. This makes dormant activation and
`session_shutdown` silent and prevents result bridge activity after any partial stage.

Built-in wrappers now distinguish three states:

- inactive: delegate directly to a native definition rebuilt for the execution context's cwd; do
  not call the governance bridge;
- bootstrapping: allow `READ` through that same current-cwd native path with no bridge dependency,
  while directly refusing mutating calls as defense in depth;
- ready: use the existing canonical snapshot, bridge verdict, and final executor path.

The installer records the cwd bound to each registered wrapper. A later enabled activation with a
different cwd replaces the same extension-owned definition in place before readiness; a same-cwd
retry remains idempotent. Readiness is still impossible until every final component completes.

### Opaque-name serialization

The bootstrap reason is now a fixed diagnostic and does not include the untrusted tool name. The
descriptor still classifies the name, and unknown/opaque names still block, but no attacker/model
controlled name enters the structured refusal.

### Authentic real-Pi fault fixture

The test-only provider writes one consumed-fault marker using exclusive-create mode immediately
before throwing `CA_PI_TEST_ENFORCEMENT_REGISTRATION_FAILURE`. The Python test reads that marker
before temporary-directory cleanup and requires its exact fixed value in addition to the single
`session_start` extension error, later `agent_settled`, failed real `write`, `/ca-doctor` refusal,
and absent mutation sentinel. A second consumption cannot silently overwrite the marker. No
production test switch, environment variable, dependency, manifest, or configuration was added.

## Pi 0.80.5 dispatcher evidence

No install or network access was needed. The local npm cache contained the registry tarball key
for `@earendil-works/pi-coding-agent@0.80.5` with SRI SHA-512 digest:

`18f605b87c3504dfb79b91b3c351c61f8d567450f36e994b6ae4b4cd849fd593a480a15deb0b4401c8dc841fef9b3f58b5319b40ec0409bb158fa1b1671ba780`

`Get-FileHash -Algorithm SHA512` over the integrity-addressed cache content matched that digest
exactly. Reading `package/dist/core/extensions/runner.js` directly from the cached tarball showed
`emitToolCall()` iterating handlers and immediately `return result` when `result.block` is true.
Thus the bootstrap-handler short-circuit is source-proven for 0.80.5 as well as the installed
0.80.6 runtime. The real fault-injection execution remains on locally installed 0.80.6; the
0.80.5 conclusion is integrity-verified source evidence, not a second runtime execution.

## Files changed by this fix

- `plugins/ca-pi/tools/src/tool-guard.ts`
- `plugins/ca-pi/tools/test/tool-guard.test.ts`
- `plugins/ca-pi/tools/test/activation.test.ts`
- `.github/scripts/test_pi_package.py`
- `plugins/ca-pi/extensions/codearbiter.js` (deterministically regenerated)
- `.codearbiter/reports/2026-07-14-pi-support-handoff/blocker-3-fix-report.md`

The regenerated child bundle remained byte-identical.

## GREEN and verification evidence

### Focused lifecycle, serialization, stale-cwd, and shutdown coverage

```powershell
npm test -- --run test/tool-guard.test.ts -t "bootstrap refusal serialization|deactivation makes every partially"
npm test -- --run test/tool-guard.test.ts -t "reactivation cannot reuse"
npm test -- --run test/activation.test.ts -t "enforcement failure"
npm test -- --run test/tool-guard.test.ts test/activation.test.ts
```

Results: 2/2 selected; 1/1 selected; 1/1 selected; 33/33 combined.

### Real installed-Pi regression

```powershell
python .github/scripts/test_pi_package.py PiPackageTests.test_real_rpc_enforcement_registration_failure_stays_fail_closed -v
```

Result: 1/1 passed with the exact consumed-fault marker, one lifecycle error, continued host
settlement, a structured failed `write`, and no mutation sentinel.

### Full suites

```powershell
cd plugins/ca-pi/tools
npm run typecheck
npm test
cd ../../..
python .github/scripts/test_pi_package.py
python .github/scripts/test_pi_package.py --rpc-commands
python .github/scripts/test_pi_parity.py
python .github/scripts/test_pi_doctor.py
python .github/scripts/test_hooklib.py
```

Results:

- TypeScript typecheck: exit 0
- Pi suite: 8 files, 102/102 tests passed
- package suite: 16/16 passed
- isolated command/alias RPC: 1/1 passed
- parity: 18/18 passed
- doctor/backstop: 5/5 passed
- activation/shared-hook backstop: 69/69 passed

### Generation, surface, and repository checks

```powershell
python tools/sync-core.py --check
python tools/build-surface.py --check
python tools/build-host-packages.py --check
git diff --check
```

Results: 42 shared core files across all three plugins are byte-identical; Claude, Codex, and Pi
surfaces are in sync; root/Pi package metadata matches the descriptor; diff check exits 0.

### Deterministic bundles

`npm run build` was run twice from `plugins/ca-pi/tools`. Both runs exited 0 and produced identical
SHA-256 hashes:

| Artifact | First build | Second build |
|---|---|---|
| `plugins/ca-pi/extensions/codearbiter.js` | `78292AD6926F74FE959EE8D1957E596C97C35FB736A87E175BD273118F42AD6F` | `78292AD6926F74FE959EE8D1957E596C97C35FB736A87E175BD273118F42AD6F` |
| `plugins/ca-pi/extensions/codearbiter-child.js` | `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328` | `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328` |

## Self-review and residual concern

- Final handlers, result processing, and wrappers all honor inactive lifecycle state.
- Partial failure remains fail-closed because bootstrap stays active and not ready until a dormant
  activation or shutdown explicitly deactivates it.
- Dormant wrapper execution uses the real execution context cwd and never the captured enabled cwd.
- Bootstrap reads cannot use a prior cwd or depend on the governance bridge; mutating direct wrapper
  calls remain blocked even if a host regresses its handler short-circuit.
- Ready wrappers retain the original canonical snapshot and final-argument bridge authority.
- Unknown/opaque tools remain potentially mutating and blocked by default.
- The new refusal contains no untrusted name, secret-shaped input, or control-bearing input.
- The fixture is test-only and independently attests its exact one-shot fault.
- No unrelated or user-owned state was intentionally modified.

Residual concern: the real failure canary is executed locally against Pi 0.80.6. Pi 0.80.5's
short-circuit is proven from an SRI-verified cached release tarball, and the CI version matrix remains
the runtime backstop for both supported versions. A future supported Pi version still requires
retaining the real-host canary and rechecking the handler-map injection seam.

## Second fix pass - ready-state opaque-name serialization (2026-07-15)

The independent rereview in `blocker-3-task-security-rereview.md` confirmed the bootstrap boundary
was fixed but found the same raw opaque-name interpolation in ready-state `guardUnknownTools()`.
The unknown branch classified `event.toolName` as `OTHER`, then copied that attacker/model-controlled
value into the structured block reason serialized by Pi.

### RED

A ready/final guard regression was added with a secret-shaped name carrying CR, LF, and NUL plus a
distinct control payload:

```powershell
npm test -- --run test/tool-guard.test.ts -t "ready-state unknown refusal serialization"
```

Result: **RED**, 1/1 selected test failed for the intended reason. `JSON.stringify()` of the
structured refusal contained the injected secret-shaped text and control payload.

### Fix

The ready-state `OTHER` branch now emits a fixed diagnostic:

`An unknown Pi tool is potentially mutating and is blocked; classify it in the generated descriptor or run /ca-doctor.`

It continues to return `block: true`, retains classification guidance and `/ca-doctor`, and no
opaque name enters failure/RPC text. The separate source-drift reason still names descriptor-known
governed tools only; those names are selected by exact lookup from the trusted generated descriptor,
not accepted as opaque input. Known-tool source identity, final-argument snapshots, and default
unknown blocking are unchanged.

### Focused GREEN

```powershell
npm test -- --run test/tool-guard.test.ts -t "ready-state unknown refusal serialization|blocks an unknown active tool|competing definition|judges final args"
```

Result: 4/4 selected tests passed. This covers adversarial serialization, default unknown blocking,
known-tool source drift, and final-argument enforcement.

### Full verification after regeneration

```powershell
cd plugins/ca-pi/tools
npm run build
npm run typecheck
npm test
cd ../../..
python .github/scripts/test_pi_package.py
python .github/scripts/test_pi_package.py --rpc-commands
python .github/scripts/test_pi_parity.py
python .github/scripts/test_pi_doctor.py
python .github/scripts/test_hooklib.py
python tools/sync-core.py --check
python tools/build-surface.py --check
python tools/build-host-packages.py --check
git diff --check
```

Results:

- TypeScript typecheck: exit 0
- Pi suite: 8 files, 103/103 tests passed
- package suite, including real-Pi fault canary: 16/16 passed
- isolated command/alias RPC: 1/1 passed
- parity: 18/18 passed
- doctor/backstop: 5/5 passed
- activation/shared-hook backstop: 69/69 passed
- shared core: 42 files across all three plugins byte-identical
- Claude/Codex/Pi generated surfaces: in sync
- root/Pi package metadata: matches descriptor
- diff check: exit 0

`npm run build` was then run twice. Both runs produced identical SHA-256 hashes:

| Artifact | First build | Second build |
|---|---|---|
| `plugins/ca-pi/extensions/codearbiter.js` | `E5FC3166D2AA3608C97A8D7973B0B1D769254666DF79B90F997121D7B77749AF` | `E5FC3166D2AA3608C97A8D7973B0B1D769254666DF79B90F997121D7B77749AF` |
| `plugins/ca-pi/extensions/codearbiter-child.js` | `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328` | `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328` |

No commit, staging, push, branch switch, stash, reset, clean, dependency install, or network action
was performed in this second fix pass.
