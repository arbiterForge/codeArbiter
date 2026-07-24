# Pi support Batch 2 trust/config residual fix report

Date: 2026-07-15
Branch: `feat/pi-support`
Source brief: `batch-2-trust-config-fix-brief.md`
Source finding: `batch-2-combined-security-review.md` security rereview HIGH

## Result

The residual trust/config HIGH is implemented and verified. Global Pi extension loading is now
discovery, not authorization. After the canonical activation marker is detected, `ca-pi` requires
`context.isProjectTrusted?.() === true` before Python or Git resolution, concrete bridge work,
enforcement installation, persona/shared startup, managed-hook discovery or installation,
repository Git reads, or fetch.

An enabled session with a missing, false, or failing trust result stays in the activation-check
fail-closed generation. Mutators remain blocked, retained native reads resolve fresh untrusted
settings, one fixed trust status/notification is published, and doctor reports the intentionally
withheld boundary without a bridge probe or wrapper self-test. Dormant sessions remain inactive and
silent. A false-to-true retry in the same process clears cached executable/bridge identities and
performs a normal fresh activation.

No Cyber Guard action blocked this run. No implementation or evidence was lost. Tasks 6-14 were not
started or modified by this residual pass. No staging, commit, push, publish, branch switch, stash,
reset, or clean was performed.

## RED evidence

The correction was driven by failing regressions before production edits:

- Focused unit RED:
  - command: `npm test -- --run test/activation.test.ts test/doctor.test.ts test/status.test.ts test/tool-guard.test.ts`
  - result: 4 intended failures and 77 passes;
  - missing and false trust both executed bridge preparation, enforcement installation, and persona
    loading;
  - the first leg of false-to-true same-process retry did the same unauthorized work;
  - enabled-untrusted doctor incorrectly reported the global trust boundary as healthy.
- Authentic supported-Pi/package RED:
  - command: `python .github/scripts/test_pi_package.py PiPackageTests.test_real_rpc_enabled_untrusted_global_session_stays_before_repository_boundary -v`
  - result before the production fix and bundle rebuild: `FAIL` because untrusted global startup
    installed a managed `.git/hooks/pre-commit` hook.
  - the canary also records pre-push, hook-discovery cache, shared session-start marker, and
    `.git/FETCH_HEAD` state using only temporary repositories and inert filesystem sentinels.

## Implementation

### Parent activation and lifecycle

- `plugins/ca-pi/tools/src/extension.ts`
  - every `session_start` deactivates the prior lifecycle, begins a new activation-check blocked
    generation, clears concrete bridge/Python/Git caches, and resets prior session state before
    asynchronous activation work;
  - canonical marker detection remains filesystem-only and precedes the trust decision;
  - dormant detection fully deactivates without status or notification;
  - enabled missing/false/failing trust publishes the fixed redacted direction and returns without
    bridge preparation, enforcement, persona loading, or shared `session_start`;
  - only affirmative trust begins bootstrap and repository-aware work;
  - enforcement factories use the already-authorized trust result without re-reading a mutable host
    signal mid-bootstrap;
  - repeated `session_start` supports false-to-true same-process activation with refreshed executable,
    bridge, wrapper, and settings identities.

### Fail-closed retained tools

- The existing generation-aware enforcement boundary remains active while trust is absent:
  - retained/bootstrap mutators return the activation fail-closed block and never reach native
    mutation or the bridge;
  - retained reads delegate through a fresh native factory at the execution cwd with
    `projectTrusted: false` and no bridge call;
  - trusted definitions cannot become active again after lifecycle invalidation.

### Truthful side-effect-free doctor

- `plugins/ca-pi/tools/src/doctor.ts`
  - trust is required when the canonical enabled marker is present, independent of global or local
    package scope;
  - missing, false, or throwing trust signals are non-affirmative;
  - Python resolution, bridge health, final-wrapper verification, and wrapper self-test are reported
    as intentionally withheld/degraded until trust rather than falsely unhealthy or healthy;
  - the trust row is unhealthy with one fixed remediation directing the operator to `/trust`, project
    inspection, explicit approval, and a new session;
  - no bridge probe or stored-wrapper live fire runs while enabled and untrusted.

## Test evidence

- `plugins/ca-pi/tools/test/activation.test.ts`
  - missing trust API and explicit false both produce zero bridge preparation, enforcement, persona,
    or bridge calls and exactly one fixed trust direction;
  - false-to-true retry stays blocked first, then completes normal governed startup with refreshed
    definitions in the same process;
  - shutdown and dormant status behavior remain exact.
- `plugins/ca-pi/tools/test/tool-guard.test.ts`
  - retained mutators block in the activation-check generation;
  - retained reads use current fresh untrusted settings with zero bridge calls.
- `plugins/ca-pi/tools/test/doctor.test.ts`
  - enabled-untrusted doctor makes zero bridge and wrapper calls and reports the withheld checks
    truthfully.
- `.github/scripts/test_pi_package.py`
  - the authentic real RPC canary now proves an enabled untrusted global-extension session creates no
    managed hook, hook-discovery cache, shared startup marker, or fetch state;
  - exact trust status and side-effect-free doctor output are observed through Pi's real RPC stream;
  - the existing trusted Windows absolute-executable and managed-hook canary remains green.

Authentic canary GREEN after rebuild:

```text
python .github/scripts/test_pi_package.py PiPackageTests.test_real_rpc_enabled_untrusted_global_session_stays_before_repository_boundary -v
Ran 1 test in 1.999s
OK
```

## Documentation reconciliation

The following governing artifacts now use one non-contradictory invariant: global load is discovery;
affirmative current project trust authorizes repository-aware adapter startup.

- `.codearbiter/specs/pi-support.md`
- `.codearbiter/specs/pi-support-review.md`
- `.codearbiter/plans/pi-support.md`
- `.codearbiter/security-controls.md`

They also record the dormant, enabled-untrusted, doctor, false-to-true retry, trusted Git-backstop,
and project-local load-time trust behavior.

## Final verification

All commands ran from `C:\Users\brenn\projects\codeArbiter` unless a working directory is shown.

| Command | Result |
|---|---|
| focused activation/doctor/status/tool-guard Vitest (`plugins/ca-pi/tools`) | GREEN, 81/81 |
| `npm test -- --run` (`plugins/ca-pi/tools`) | GREEN, 138/138 |
| `npm run typecheck` (`plugins/ca-pi/tools`) | GREEN |
| `npm run build` (`plugins/ca-pi/tools`), repeated with before/after SHA-256 | GREEN, byte-deterministic |
| authentic enabled-untrusted global real-RPC canary | GREEN, 1/1 |
| `python .github/scripts/test_pi_package.py` | GREEN, 20/20 |
| `python .github/scripts/test_pi_package.py --rpc-commands` | GREEN, 1/1 |
| trusted Windows executable-identity and managed-hook canary within package suite | GREEN, 1/1 |
| `python .github/scripts/test_pi_parity.py` | GREEN, 19/19 |
| `python .github/scripts/test_pi_doctor.py` | GREEN, 7/7 |
| `python plugins/ca/hooks/tests/test_git_hooks.py` | GREEN, 34/34 |
| `python -m unittest discover -s plugins/ca/hooks/tests -p "test_*.py"` | GREEN, 932/932 |
| `python .github/scripts/test_sync_core.py` | GREEN, 12 passed; 1 expected Windows permission skip |
| `python tools/sync-core.py --check` | GREEN, 43 canonical files x 3 plugins byte-identical |
| `python tools/build-host-packages.py --check` | GREEN |
| `python .github/scripts/test_host_descriptors.py` | GREEN, 13/13 |
| `python .github/scripts/test_build_surface.py` | GREEN, 34/34 |
| `git diff --check` | GREEN |

## Deterministic hashes

The same hashes were observed before and after the final repeat build:

```text
FE70C2B22E5925D4A5E6A7CC3026930E5E87EA36822F632C5BFBB611A31C9973  plugins/ca-pi/extensions/codearbiter.js
E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328  plugins/ca-pi/extensions/codearbiter-child.js
9D3FE616FFBC306BC77B25F2C1CFEA3A4A2A41354F9C170CE102A101C1871CC2  plugins/ca-pi/tools/package-lock.json
```

## Workspace integrity and handoff

- Branch: `feat/pi-support`.
- Staged paths: none (`git diff --cached --name-only` returned no output).
- Existing user-owned dirty and untracked files were preserved.
- Active dispatch remains honestly `DEGRADED`; PI-AC-28 and Task 5 remain `BLOCKED` pending the
  supported-version promotion evidence already assigned later in the plan.
- The Batch 2 checkpoint remains blocked until fresh integration and security rereviews accept this
  residual correction.

Ready for the same integration and security reviewers to rereview the cumulative Batch 2 diff
against `batch-2-trust-config-fix-brief.md` and this report.
