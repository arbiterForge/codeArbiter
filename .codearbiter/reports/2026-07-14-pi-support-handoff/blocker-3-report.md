# Batch 2 remediation 3 report - fail-closed enforcement bootstrap

**Recorded:** 2026-07-15
**Branch:** `feat/pi-support`
**Status:** implemented and locally verified
**Commits:** none

## Root cause

The shipped parent registered its only `tool_call` enforcement handler from
`installEnforcement()` during enabled `session_start`. If that registration threw,
`installParent()` reported an unhealthy status and rethrew, but there was no earlier persistent
guard. Pi 0.80.6's installed `ExtensionRunner.emit()` catches ordinary lifecycle-handler errors,
reports them through its error callback, and continues. RPC serializes that report as
`extension_error`; the agent's later `beforeToolCall` path then dispatches through whatever
`tool_call` handlers remain. In the failing case there were none, so the native mutating tool ran.

The failure was therefore not the thrown error itself. The defect was the registration order: the
boundary that should survive a bootstrap failure was inside the fallible bootstrap operation.

## Fault-injection design

`.github/scripts/test_pi_package.py` now exercises the real installed Pi RPC/JSON process with an
isolated Pi home, installed repository package, deterministic local provider, and enabled temporary
project.

The test-only extension arms one exception during its `session_start` callback. It temporarily
intercepts the real handler-map registration, targets the first attempted `tool_call` handler
registration, restores the original operation before throwing, and cannot throw a second time. The
local provider then emits a real `write` tool call through Pi's agent and dispatcher. The regression
requires all of the following from one run:

- exactly one ca-pi `session_start` `extension_error` containing the `/ca-doctor` direction;
- a later `agent_settled`, proving the real host continued;
- a real `tool_execution_end` for `write` with `isError: true` and `/ca-doctor` in the refusal;
- no mutation sentinel while the temporary fixture root still exists.

This is test-only fault injection. No production switch, environment variable, command,
configuration surface, endpoint, dependency, or manifest was added.

## RED evidence

The first real-host run used the production bundle before the readiness remediation:

```powershell
python .github/scripts/test_pi_package.py PiPackageTests.test_real_rpc_enforcement_registration_failure_stays_fail_closed -v
```

Result: **RED**, 1 failing test. Pi emitted the expected `session_start` `extension_error`, continued
to `agent_settled`, and emitted `tool_execution_end` for `write` with `isError: false`. The native
executor reported a 39-byte write to the sentinel path. The test found zero structured refusal
events where it required one.

The focused unit REDs were also observed before production edits:

```powershell
npm test -- --run test/tool-guard.test.ts -t "bootstrap"
npm test -- --run test/activation.test.ts -t "enforcement failure"
```

Results: 3 bootstrap tests failed because `EnforcementInstaller.ensureBootstrap` did not exist; the
activation retry test failed because no readiness transition occurred.

## Implementation

`EnforcementInstaller` now owns an idempotently registered bootstrap `tool_call` handler and three
small lifecycle transitions:

- inactive: dormant repositories remain ungoverned and silent;
- bootstrapping: descriptor-declared reads retain their approved advisory direction, while every
  execution, write, edit, unknown, opaque, or missing tool name returns a structured block naming
  `/ca-doctor`;
- ready: the bootstrap handler yields to the existing final-source guard and wrapped builtin
  executors.

The parent bundle installs that bootstrap handler during extension initialization. It does no file,
process, interpreter, bridge, or project work while inactive. Enabled `session_start` moves it to
bootstrapping before bridge preparation and enforcement installation. Readiness is marked only
after `installEnforcement()` has completed the unknown-tool guard, result bridge, and all four
builtin wrapper registrations. A thrown or partial installation never reaches `markReady()`, so the
bootstrap handler remains fail-closed after Pi catches the lifecycle error. A later successful
retry resets bootstrap state, completes the remaining idempotent installation work, and only then
releases calls to normal wrapped execution. Dormant activation and session shutdown deactivate the
bootstrap state.

The existing package-loader registration-count assertion was increased by one to account for the
new always-installed handler. No final-argument, source-identity, bridge, or builtin-wrapper logic
was weakened.

## Files changed

- `.github/scripts/test_pi_package.py` - one-shot real-Pi registration fault fixture and RPC
  fail-closed regression.
- `plugins/ca-pi/tools/src/tool-guard.ts` - bootstrap readiness state and structured guard.
- `plugins/ca-pi/tools/src/extension.ts` - early guard installation and activation/retry/shutdown
  transitions.
- `plugins/ca-pi/tools/test/tool-guard.test.ts` - dormant, bootstrapping, unknown-tool, readiness,
  retry, and deactivation coverage.
- `plugins/ca-pi/tools/test/activation.test.ts` - readiness remains incomplete after failure and
  becomes ready only after a successful retry.
- `plugins/ca-pi/tools/test/package.test.ts` - exact real-loader registration-count contract.
- `plugins/ca-pi/extensions/codearbiter.js` - deterministic regenerated parent bundle.
- `.codearbiter/reports/2026-07-14-pi-support-handoff/blocker-3-report.md` - this report.

The child bundle was regenerated by the deterministic build but remained byte-identical.

## GREEN and verification evidence

### Focused remediation and preserved enforcement behavior

```powershell
python .github/scripts/test_pi_package.py PiPackageTests.test_real_rpc_enforcement_registration_failure_stays_fail_closed -v
npm test -- --run test/tool-guard.test.ts -t "bootstrap"
npm test -- --run test/activation.test.ts -t "enforcement failure"
npm test -- --run test/tool-guard.test.ts -t "installation|final args|unknown active tool"
npm test -- --run test/activation.test.ts
```

Results: real Pi 1/1; bootstrap 3/3; activation retry 1/1; existing installation retry,
final-argument, and unknown-tool tests 4/4; full activation 10/10.

### Full Pi TypeScript boundary

```powershell
npm run typecheck
npm test
```

Results: typecheck exit 0; 8 files and 99/99 tests passed. The first full-suite run correctly found
the stale package registration-count expectation; after changing `commandCount + 5` to
`commandCount + 6`, the fresh full run passed.

### Deterministic bundles

`npm run build` was run twice from `plugins/ca-pi/tools`. Both runs exited 0 and produced identical
SHA-256 hashes:

| Artifact | First build | Second build |
|---|---|---|
| `plugins/ca-pi/extensions/codearbiter.js` | `CEC089B6864FFA9025F89FF4E36F9DB766D2A036301FB10C835171D05F81AD89` | `CEC089B6864FFA9025F89FF4E36F9DB766D2A036301FB10C835171D05F81AD89` |
| `plugins/ca-pi/extensions/codearbiter-child.js` | `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328` | `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328` |

The child hash matches the preserved handoff hash.

### Package, RPC, parity, doctor, and backstops

```powershell
python .github/scripts/test_pi_package.py
python .github/scripts/test_pi_package.py --rpc-commands
python .github/scripts/test_pi_parity.py
python .github/scripts/test_pi_doctor.py
python .github/scripts/test_hooklib.py
```

Results: package 16/16; isolated command/alias RPC 1/1; parity 18/18; doctor/backstop 5/5;
activation/shared-hook backstop 69/69.

### Generation and repository checks

```powershell
python tools/sync-core.py --check
python tools/build-surface.py --check
python tools/build-host-packages.py --check
git diff --check
```

Results: 42 shared core files across all three generated plugins are byte-identical; Claude, Codex,
and Pi surfaces are in sync; root/Pi package metadata matches the descriptor; diff check exits 0.

## Self-review

- The persistent handler is registered before the one-shot real-Pi failure point and remains
  present when Pi catches the lifecycle error.
- Inactive state performs no interpreter resolution, bridge call, package operation, status write,
  or governance decision, preserving remediation 1 and dormant behavior.
- Enabled state becomes not-ready before any fallible bridge/enforcement work.
- Only explicit `READ` classifications pass during bootstrap. Unknown and opaque tools retain the
  required potentially-mutating classification.
- Partial wrapper registration cannot mark readiness; the transition occurs after the entire
  installation callback returns.
- Successful retry is covered both at activation lifecycle level and by the existing idempotent
  installation tests; ready state yields to the unchanged final-source guard/wrapper path.
- The test observes the mutation sentinel before fixture cleanup, so deletion of the temporary root
  cannot create a false green.
- No raw secret, production fault hook, dependency, manifest, lockfile, process, endpoint, command,
  or configuration surface was introduced.
- UTF-8/LF and deterministic parent generation are preserved; remediation 2's canonical activation
  path remains green.
- No audit log, task board, unrelated file, or later Task 6-9 surface was intentionally changed.

## Concerns

The fault fixture deliberately targets Pi's supported 0.80.x handler-map implementation so it can
raise at the exact registration boundary without a production switch. The real-host canary must be
kept when the supported Pi set changes because a future lifecycle implementation may require a new
test-only injection seam. No unresolved local blocker remains for remediation 3.
