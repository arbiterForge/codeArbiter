# Batch 2 remediation 1 - implementation report

**Status:** DONE_WITH_CONCERNS
**Branch:** `feat/pi-support`
**Commits/staging:** none

## Source-backed root cause

The confirmed execution path was present in the current source:

1. `plugins/ca-pi/tools/src/extension.ts` called `resolvePythonCommand()` inside the default
   extension entrypoint, before `installParent()` registered the `session_start` handler.
2. Dormancy was checked only later inside that handler with `isEnabled(context.cwd)`, so loading the
   extension in a dormant project had already performed Python discovery.
3. `plugins/ca-pi/tools/src/bridge.ts` passed bare `py`, `python`, and `python3` names to
   `spawnSync()` without `cwd`. Node therefore inherited Pi's project working directory while
   resolving the executable.
4. Although the probe accepted only Python 3 output containing an absolute `sys.executable`, that
   validation occurred after the bare candidate had already executed. `BridgeClient` also
   realpathed the selected interpreter before bridge use, but that did not protect the earlier
   discovery spawn.

Hypothesis: move discovery behind successful `arbiter: enabled` activation, use the Pi lifecycle
context in which trust has already been decided, and make every discovery spawn use the absolute
installed `ca-pi` package root as its `cwd`. This removes project-cwd candidate execution while
retaining absolute interpreter validation before bridge use.

## RED evidence

### Live poisoned-cwd regression

The test uses the real installed Pi loader on Windows, leaves the project dormant, places local
`py.exe` and `python.exe` candidates plus a `sitecustomize.py` sentinel in the project cwd, and loads
the shipped parent extension.

Command:

```powershell
cd plugins/ca-pi/tools
npm exec -- vitest run test/package.test.ts -t "real Pi dormant load never executes a project-cwd Python candidate"
```

Expected RED, exit 1:

```text
test/package.test.ts (8 tests | 1 failed | 7 skipped)
x real Pi dormant load never executes a project-cwd Python candidate
AssertionError: promise resolved "undefined" instead of rejecting
at test/package.test.ts:415
```

The assertion expected `access(sentinel)` to reject. It resolved, proving extension load executed
Python from the poisoned project-cwd search context before dormancy was known. Pi loading itself
reported no extension errors, so this was the intended poisoned-cwd/pre-trust failure rather than a
fixture or loader failure.

### Safe discovery-cwd regression

Command:

```powershell
cd plugins/ca-pi/tools
npm exec -- vitest run test/bridge.test.ts -t "resolves launcher-only Windows"
```

Expected RED, exit 1:

```text
expected 'py -3 @ undefined' to be 'py -3 @ C:/trusted-package'
```

This isolated the missing `cwd` propagation at the discovery-spawn boundary.

### Enabled/trust lifecycle regression

Command:

```powershell
cd plugins/ca-pi/tools
npm exec -- vitest run test/activation.test.ts -t "prepares the bridge only after enabled activation"
```

Expected RED, exit 1:

```text
expected [] to deeply equal [ { cwd: <enabled fixture>, trusted: true } ]
```

This proved the lifecycle had no explicit bridge-preparation seam after activation reached Pi's
trust-aware extension context.

## Minimal implementation

- Added an optional `prepareBridge(cwd, context)` lifecycle dependency. `installParent()` invokes it
  only after `isEnabled(context.cwd)` returns true; dormant session startup returns before it.
- The concrete parent uses that seam to resolve Python once. Loading the extension and invoking a
  dormant doctor path do not perform Python discovery.
- Python discovery now passes the absolute installed `ca-pi` package root as the spawn `cwd`.
  `resolvePythonCommand()` rejects a non-absolute search cwd and still accepts only a successful
  Python 3 probe whose reported executable is absolute.
- `BridgeClient` treats an unresolved interpreter as unavailable without spawning. Its existing
  request/category failure classifier warns for advisory lifecycle/read operations and blocks
  mutating tool calls. Enabled activation still installs the final-execution wrappers before the
  first bridge request, preserving fail-closed mutation when Python is absent.
- The default extension's Pi/Node compatibility check remains pre-registration. Its Python check is
  deferred to activation; the exported pure compatibility helper and its missing-Python contract
  remain unchanged.
- Rebuilt `plugins/ca-pi/extensions/codearbiter.js` only through `npm run build`. The child bundle was
  regenerated but remained byte-identical.

## GREEN and verification evidence

Focused tests:

```text
npm exec -- vitest run test/bridge.test.ts -t "resolves launcher-only Windows"
PASS - 1 passed, 11 skipped

npm exec -- vitest run test/activation.test.ts
PASS - 8 passed

npm exec -- vitest run test/package.test.ts -t "real Pi dormant load never executes a project-cwd Python candidate"
PASS - 1 passed, 7 skipped
```

Final directly affected suite:

```text
npm test
PASS - 8 files, 94 tests

npm run typecheck
PASS - tsc --noEmit, exit 0

python .github/scripts/test_pi_package.py
PASS - 15 tests

python .github/scripts/test_pi_parity.py
PASS - 18 tests

python .github/scripts/test_pi_doctor.py
PASS - 5 tests
```

Deterministic build check:

```text
npm run build
codearbiter.js before=A70064D88486BA5EFD3979144A9856E05AA7B2196E9662B06368229B39C9FB8F
               after=A70064D88486BA5EFD3979144A9856E05AA7B2196E9662B06368229B39C9FB8F
codearbiter-child.js before=E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328
                     after=E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328
```

Additional checks:

- `git diff --check` exited 0 with no output.
- All six touched source/test/generated text files are UTF-8 without BOM and contain no CRLF.
- `plugins/ca-pi/tools/package-lock.json` remained unchanged at handoff SHA-256
  `9D3FE616FFBC306BC77B25F2C1CFEA3A4A2A41354F9C170CE102A101C1871CC2`.
- No Python source changed; package, parity, and doctor/backstop Python checks were run instead of an
  unrelated Python compilation sweep.

## Files changed

- `plugins/ca-pi/tools/src/bridge.ts`
- `plugins/ca-pi/tools/src/extension.ts`
- `plugins/ca-pi/tools/test/activation.test.ts`
- `plugins/ca-pi/tools/test/bridge.test.ts`
- `plugins/ca-pi/tools/test/package.test.ts`
- `plugins/ca-pi/extensions/codearbiter.js` - deterministic generated output
- `.codearbiter/reports/2026-07-14-pi-support-handoff/blocker-1-report.md` - this report

`plugins/ca-pi/extensions/codearbiter-child.js` was regenerated by the required build but its bytes
and recorded hash did not change.

## Self-review

- Scope is limited to blocker 1 and its tests/generated parent artifact. No activation-parser,
  bootstrap enforcement, supported-version, read-context, or doctor live-fire remediation was
  attempted.
- The resolver still uses argv arrays, `shell: false`, bounded probe timeout, minimal environment,
  and an explicit absolute cwd. Bridge execution still uses a realpathed absolute interpreter and
  installed script, explicit request cwd, bounded streams, and tree termination.
- No project trust is granted. Resolution occurs only after enabled session startup reaches Pi's
  trust-aware context; project-scope loading remains Pi's decision.
- A missing interpreter creates no process. Enabled activation installs enforcement and subsequent
  mutations receive the existing `PI-BRIDGE` block direction.
- Dormant session startup performs no bridge preparation, persona load, enforcement install, bridge
  call, status write, scaffold, or audit mutation.
- Existing user-owned dirt, audit logs, task board, scratch file, and temporary directories were not
  edited, staged, stashed, reset, cleaned, or attributed to this remediation.

## Concerns

- `[NEEDS-TRIAGE]` An explicitly invoked doctor in a dormant repo now intentionally does not probe
  Python, because the binding remediation forbids interpreter resolution before enabled activation.
  It therefore reports Python/bridge unavailable until the repo is enabled and a session-start
  activation has prepared the bridge. If dormant doctor UX must distinguish "not probed" from
  "missing", that wording/schema decision belongs with the already-recorded later doctor coverage
  remediation, not this security fix.
- The live poisoned executable regression is Windows-only because the confirmed exploit depends on
  Windows current-directory executable lookup. The resolver-cwd unit contract and the full Pi suite
  run on every platform; CI already includes Windows for the live test.

## Reviewer fix loop - dormant doctor audit mutation

**Status:** DONE
**Commits/staging:** none

### Confirmed root cause

The reviewer found one remaining dormant side effect. The registered `/ca-doctor` alias invoked the
real `collectPiDoctorInput()` path while Python intentionally remained unresolved. The collector
always called `dependencies.bridge.call()` to measure bridge health. The unprepared `BridgeClient`
classified that as an advisory `PI-BRIDGE` failure and `failed()` appended a `PI_BRIDGE_WARN` line to
the dormant project's `.codearbiter/gate-events.log` before returning the diagnosis.

This was not Python execution - the resolver and bridge process remained dormant - but it violated
the binding no-audit-mutation contract. The fix belongs at the doctor probe boundary: an unprepared
bridge is already known unhealthy and must be represented as such without invoking the transport's
auditing failure path.

### RED evidence

Added one integration regression that registers and invokes the actual `ca-doctor` alias with the
real doctor collector and unprepared `BridgeClient`. The fixture snapshots the dormant project root,
the `.codearbiter` entry list, and existing audit bytes, and supplies a bridge-script sentinel that
would record any Python execution.

Command:

```powershell
cd plugins/ca-pi/tools
npm exec -- vitest run test/activation.test.ts -t "actual dormant doctor command"
```

Expected RED, exit 1:

```text
test/activation.test.ts (9 tests | 1 failed | 8 skipped)
x keeps the actual dormant doctor command side-effect free while the bridge is unprepared
AssertionError: expected 'existing-audit\n[... PI_BRIDGE_WARN ...]' to be 'existing-audit\n'
at test/activation.test.ts:266
```

The Python sentinel remained absent. The only observed state change was the exact reviewer finding:
one appended `HOST: pi | RULE: PI-BRIDGE | AUDIT: PI_BRIDGE_WARN` audit line.

### Minimal fix

- Made `bridgePrepared` a required `PiDoctorCollectorDependencies` input.
- `collectPiDoctorInput()` probes the bridge only when that input is true. False directly represents
  `bridge.healthy = false`; it never calls the bridge and therefore cannot enter bridge failure
  auditing.
- The parent extension computes preparation from both current activation and resolver lifecycle:
  `enabledForDoctor && pythonResolutionAttempted`. A dormant cwd stays unprepared even if the same
  extension process previously attempted Python resolution for an enabled session.
- Reused the same `enabledForDoctor` value for the existing live-fire enable flag. No live-fire
  behavior, scope, dispatcher coverage, or later doctor blocker was changed.
- Existing doctor collector tests declare `bridgePrepared: true`, preserving their real bridge
  health-probe contract.

### GREEN and final verification

```text
npm exec -- vitest run test/activation.test.ts -t "actual dormant doctor command"
PASS - 1 passed, 8 skipped

npm exec -- vitest run test/activation.test.ts test/doctor.test.ts
PASS - 2 files, 27 tests

npm exec -- vitest run test/package.test.ts
PASS - 1 file, 8 tests

npm test
PASS - 8 files, 95 tests

npm run typecheck
PASS - tsc --noEmit, exit 0

python .github/scripts/test_pi_package.py
PASS - 15 tests

python .github/scripts/test_pi_parity.py
PASS - 18 tests

python .github/scripts/test_pi_doctor.py
PASS - 5 tests
```

Deterministic rebuild:

```text
plugins/ca-pi/extensions/codearbiter.js
before=844D0E42711870E1A3354C6C7F662732E9D7DC801CD5229F76F6D51A1C575750
after =844D0E42711870E1A3354C6C7F662732E9D7DC801CD5229F76F6D51A1C575750

plugins/ca-pi/extensions/codearbiter-child.js
before=E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328
after =E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328
```

`git diff --check` exited 0. Touched source, tests, report, and generated parent bundle remain UTF-8
without BOM and LF-only. The reviewed lockfile remained unchanged at SHA-256
`9D3FE616FFBC306BC77B25F2C1CFEA3A4A2A41354F9C170CE102A101C1871CC2`.

### Files changed in this loop

- `plugins/ca-pi/tools/src/doctor.ts`
- `plugins/ca-pi/tools/src/extension.ts`
- `plugins/ca-pi/tools/test/activation.test.ts`
- `plugins/ca-pi/tools/test/doctor.test.ts`
- `plugins/ca-pi/extensions/codearbiter.js` - deterministic generated output
- `.codearbiter/reports/2026-07-14-pi-support-handoff/blocker-1-report.md`

The child bundle was regenerated but remained byte-identical.

### Self-review and concerns

- The regression asserts all three binding properties through the command path: no bridge-script
  sentinel, byte-identical audit content, and identical dormant root/state entry lists.
- Prepared enabled doctors still perform the existing bridge health probe. Only the known
  unprepared/dormant state bypasses the transport.
- Missing Python in an enabled activation remains fail-closed for mutation and may emit the existing
  enabled audit failure; this loop changes only dormant doctor behavior.
- The reviewer explicitly accepted Python remaining unprobed until enabled activation, reliance on
  Pi's established trust decision without rejecting `false`, and Windows-only live poisoned-cwd
  coverage. Those are no longer open concerns for this remediation.
- No later doctor live-fire correction, activation parser, bootstrap guard, version policy, or
  read-context work was attempted.
- No new concern was found. Preserved audit/task-board dirt and the unchanged lockfile were not
  edited, staged, stashed, reset, cleaned, or attributed to this fix loop.
