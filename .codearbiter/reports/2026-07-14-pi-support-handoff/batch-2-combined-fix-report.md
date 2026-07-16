# Pi support Batch 2 cumulative review fix report

Date: 2026-07-15
Branch: `feat/pi-support`
Source brief: `batch-2-combined-fix-brief.md`
Source reviews: `batch-2-combined-integration-review.md`, `batch-2-combined-security-review.md`

## Result

All four cumulative Batch 2 findings are implemented and verified. The controller's follow-up lifecycle-overlap observation is also closed: a new `session_start` invalidates the prior enforcement generation before awaiting activation detection, enters a fail-closed activation-check generation, settles dormant only after a false activation result, and begins bootstrap only after an enabled result.

No Cyber Guard action blocked this fix run. The authentic Windows poison canary executed in both its expected RED and final GREEN forms. No implementation or evidence was lost.

Active dispatch remains honestly `DEGRADED`; PI-AC-28 and Task 5 remain `BLOCKED`. Tasks 6-9 were not started.

## RED evidence

The changes were driven by failing regressions before production edits:

- Focused Vitest RED: 10 intended failures, 63 passes across activation, status, bridge, and tool-guard tests.
  - final doctor envelopes reached 96,106 UTF-8 bytes for all-escape/C1 input and 32,106 bytes for quote, backslash, and multibyte input;
  - failed-start shutdown retained the unhealthy keyed status;
  - dormant reads retained the prior trusted settings manager;
  - the bridge child ran from the governed project cwd.
- Authentic Windows poison RED:
  - command: `python .github/scripts/test_pi_package.py PiPackageTests.test_real_rpc_enabled_start_never_executes_project_git_and_installs_absolute_hook_identities -v`
  - result before the fix/bundle rebuild: `FAIL`, `poison_observed=True`; enabled `session_start` selected/executed the project-local `git.exe` control.
- Full package RED after status hardening exposed one compatibility edge: a never-published bare lifecycle emitted a redundant shutdown clear. Shutdown now clears whenever codeArbiter actually published a keyed status, regardless of `enabled`, while a wholly silent dormant lifecycle stays silent.
- Controller overlap RED: immediately after plain deactivation, a retained mutator still delegated native. The completed transition now enters an activation-check blocked generation before the `isEnabled` await; the regression proves retained writes block and retained reads use current untrusted-native settings during that interval.

## Finding 1 - project-cwd executable search

### Implementation

- `plugins/ca-pi/tools/src/bridge.ts`
  - manually resolves canonical absolute Python and Git identities from absolute PATH entries only;
  - ignores empty, relative, missing, and project-contained search entries;
  - validates both identities again inside `BridgeClient` and rejects either identity when it is the request project or a descendant, including a project-local plugin/package layout;
  - runs bridge Python from the canonical installed package root rather than the governed repository;
  - sends the repository only in the validated request and lets shared Python use explicit cwd/`git -C` arguments;
  - supplies an explicit absolute-only child PATH made from the trusted executable directories and Windows System32, plus `CODEARBITER_GIT_EXECUTABLE` and `CODEARBITER_PYTHON_EXECUTABLE`;
  - resolves and validates absolute Windows `taskkill.exe`; no bare helper lookup remains in process-tree termination.
- `core/pysrc/_gitexec.py` and generated host copies
  - validate the optional absolute executable identity channel;
  - preserve Claude/Codex's historical bare-Git fallback only when the Pi identity channel is absent.
- Every shared Python Git subprocess reachable from Pi now calls `_gitexec.git_executable()`:
  - `_githooks.py`, `_gitlib.py`, `_metricslib.py`, `_previewlib.py`, `_provenancelib.py`, `doctor.py`, `git-enforce.py`, `hostapi.py`, `init-codearbiter.py`, `migration-pass.py`, `pre-bash.py`, `security-pass.py`, and `session-start.py`.
- `_githooks.py`
  - managed Pi hook shims embed shell-quoted absolute `PY` and `G` identities;
  - export both identities to the later hook process;
  - execute the absolute Python identity directly;
  - retain the exact legacy Claude/Codex shim when neither identity is present;
  - reject an incomplete one-sided identity channel.
- `tools/sync-core.py` propagated the canonical shared changes byte-identically to Claude, Codex, and Pi.
- `npm --prefix plugins/ca-pi/tools run build` rebuilt the parent extension deterministically.

### Evidence

- `plugins/ca-pi/tools/test/bridge.test.ts`
  - direct resolver test ignores project-local, empty, and relative PATH entries;
  - child observes the trusted package cwd, absolute Git/Python identities, and an absolute-only sanitized PATH;
  - direct `BridgeClient` construction rejects Git or Python located inside the request project, including when the installed package is itself project-local.
- `.github/scripts/test_pi_package.py`
  - authentic Windows canary installs the real package first, then places a copied Python control at project-local `git.exe`;
  - final real RPC enabled startup does not execute/select the control;
  - the installed managed pre-commit hook is then actually executed with PATH restricted to the poisoned project;
  - the hook succeeds, the poison sentinel remains absent, and parsed `PY`/`G` identities are absolute existing files outside the project;
  - the hook contains no legacy `if python3 -c` search branch.
- `plugins/ca/hooks/tests/test_git_hooks.py`
  - managed identities are embedded and legacy output remains byte-for-byte unchanged when the channel is absent.
- Structural bare-executable audit:
  - `PiPackageTests.test_shared_python_contains_no_direct_bare_git_subprocess` scans canonical shared Python and rejects direct `subprocess.run/Popen/check_call/check_output(["git", ...])` forms;
  - result: GREEN, no offenders.

Identity hashes:

```text
1350E81C95D7168504D0187096CC75E818BDFAEFD20385AC2EDAC3FDF82E0C85  core/pysrc/_gitexec.py
1350E81C95D7168504D0187096CC75E818BDFAEFD20385AC2EDAC3FDF82E0C85  plugins/ca/hooks/_gitexec.py
1350E81C95D7168504D0187096CC75E818BDFAEFD20385AC2EDAC3FDF82E0C85  plugins/ca-codex/hooks/_gitexec.py
1350E81C95D7168504D0187096CC75E818BDFAEFD20385AC2EDAC3FDF82E0C85  plugins/ca-pi/hooks/_gitexec.py
```

Deterministic generated-bundle hashes before and after a second rebuild:

```text
51C3861E74DC79F143D8CDE22DC7E11E78F06B27859833AEAA77555121C7B0E8  plugins/ca-pi/extensions/codearbiter.js
E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328  plugins/ca-pi/extensions/codearbiter-child.js
```

## Finding 2 - stale native-tool settings and lifecycle overlap

### Implementation

- `plugins/ca-pi/tools/src/extension.ts`
  - settings factories create a `SettingsManager` for each execution root rather than capturing the activation-time instance;
  - active factories honor only the current activation's trust result;
  - native dormant/bootstrap/stale factories force `projectTrusted: false` while preserving permitted current user-level settings;
  - every enabled activation refreshes the concrete bridge and same-cwd builtin definitions.
- `plugins/ca-pi/tools/src/tool-guard.ts`
  - definitions bind to an opaque lifecycle generation;
  - old handles cannot become active again after same-cwd reactivation;
  - stale/bootstrap reads delegate through a newly resolved native factory at the current execution cwd with no bridge call;
  - stale/bootstrap mutators fail closed;
  - a distinct activation-check generation protects the interval before activation detection resolves;
  - same-generation bridge failures retain their existing propagation semantics; late results from old generations remain suppressed.
- `session_start` ordering is now:
  1. deactivate/invalidate the prior generation;
  2. enter activation-check blocking;
  3. clear stale status/session state;
  4. await activation detection;
  5. settle fully inactive on dormant, or begin enabled bootstrap on true.

### Evidence

`plugins/ca-pi/tools/test/tool-guard.test.ts` covers:

- cross-cwd dormant delegation with the execution cwd;
- same-cwd reactivation after settings/trust changes;
- retained old read and write handles;
- fresh untrusted-native settings during the activation-check await;
- retained mutator block during that same interval with zero bridge/native mutation execution;
- partial installation/deactivation at guard, result, and every builtin-factory stage;
- old approvals and rejected/cancelled results across deactivate/reactivate;
- same-generation/live failure behavior unchanged;
- fallback session identity rotation only with lifecycle generation.

`plugins/ca-pi/tools/test/activation.test.ts` proves `deactivate` is the first readiness action synchronously, before activation I/O resolves, `beginBootstrap` occurs only after enabled detection, and retry remains operational.

## Finding 3 - final doctor-envelope byte bound

### Implementation

`renderPiDoctorReportBlock` now:

- applies shared secret/control redaction before sizing;
- encodes the complete `{format, report}` JSON and markup/C1 escaping before accepting a size;
- measures the full fixed-delimiter block in UTF-8 bytes;
- binary-searches a Unicode-safe report prefix until the complete envelope is at most 16,000 bytes;
- never cuts JSON syntax or a UTF-16 surrogate pair;
- appends one fixed visible truncation marker inside the valid decoded report;
- retains exactly one opening and one closing model-visible delimiter.

### Evidence

`plugins/ca-pi/tools/test/activation.test.ts` validates all-escape markup, quotes, backslashes, C1/control characters, and multibyte emoji payloads. Every final block is valid JSON, contains one fixed boundary and the visible marker, preserves ordinary provenance, remains redacted, and is `<= 16,000` UTF-8 bytes.

Focused final result: activation/status/bridge/tool-guard `75/75` before the controller overlap addition; final cumulative Pi tools result is `134/134`.

## Finding 4 - failed-start status cleanup

### Implementation

- keyed status publication is tracked independently from the `enabled` flag;
- failed enabled startup can set `enabled=false` without losing cleanup ownership;
- shutdown clears codeArbiter's keyed status whenever codeArbiter published it;
- a reused process clears a stale prior status before starting a new dormant session;
- a never-published dormant lifecycle remains status-silent through shutdown;
- all parent session fields reset at each start and shutdown.

### Evidence

- unit sequence: failed enabled start -> dormant start clear -> failed retry -> shutdown clear;
- unit sequence: never-published dormant start -> shutdown -> zero status calls;
- real isolated Pi RPC confirms a bare repository remains status-silent while enabled startup/status ownership still work.

## Final verification

All commands ran from `C:\Users\brenn\projects\codeArbiter` unless a working directory is shown.

| Command | Result |
|---|---|
| `npm test -- --run test/activation.test.ts test/status.test.ts test/bridge.test.ts test/tool-guard.test.ts` (`plugins/ca-pi/tools`) | GREEN, 75/75 |
| controller overlap focused rerun (`activation`, `tool-guard`, `status`) | GREEN, 58/58 |
| `npm test -- --run` (`plugins/ca-pi/tools`) | GREEN, 134/134 |
| `npm run typecheck` (`plugins/ca-pi/tools`) | GREEN |
| `npm run build` (`plugins/ca-pi/tools`), repeated with before/after SHA-256 | GREEN, byte-deterministic |
| `python .github/scripts/test_pi_package.py -v` | GREEN, 19/19 |
| `python .github/scripts/test_pi_package.py --rpc-commands` | GREEN, 1/1 real isolated RPC test |
| authentic Windows poison + managed-hook execution test | GREEN, 1/1 |
| `python .github/scripts/test_pi_parity.py -v` | GREEN, 19/19 |
| `python .github/scripts/test_pi_doctor.py -v` | GREEN, 7/7 |
| `python plugins/ca/hooks/tests/test_git_hooks.py -v` | GREEN, 34/34 |
| `python -m unittest discover -s plugins/ca/hooks/tests -p "test_*.py"` | GREEN, 932/932 |
| `python .github/scripts/test_sync_core.py -v` | GREEN, 12 passed; 1 expected Windows permission skip |
| `python tools/sync-core.py --check` | GREEN, 43 canonical files x 3 plugins byte-identical |
| `python tools/build-host-packages.py --check` | GREEN |
| `python .github/scripts/test_host_descriptors.py -v` | GREEN, 13/13 |
| `python .github/scripts/test_build_surface.py -v` | GREEN, 34/34 |
| scoped `git diff --check` | GREEN |

## Workspace integrity and handoff

- Branch: `feat/pi-support`.
- Staged paths: none (`git diff --cached --name-only` returned no output).
- No commit, push, publish, branch switch, stash, reset, or clean was performed.
- Existing user-owned dirty and untracked files were preserved.
- The only required report write is this file.
- Tasks 6-9 remain untouched; Task 5/PI-AC-28 remain blocked on active dispatch.

Ready for the same integration and security reviewers to rereview the cumulative Batch 2 diff against `batch-2-combined-fix-brief.md`.
