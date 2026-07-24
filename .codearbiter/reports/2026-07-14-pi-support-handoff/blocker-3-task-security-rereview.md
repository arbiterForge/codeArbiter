# Blocker 3 task and security rereview

**Reviewed:** 2026-07-15
**Scope:** current blocker 3 source/tests and closure of `blocker-3-task-security-review.md`
**Spec compliant:** no
**Task quality:** needs fixes
**Security gate:** BLOCK — 0 CRITICAL, 1 HIGH, 0 MEDIUM, 0 LOW

### Spec Compliance

- ❌ One binding defect remains. The fixed bootstrap refusal is constant, but the ready/final unknown-tool guard still interpolates raw opaque `event.toolName` into the structured refusal (`plugins/ca-pi/tools/src/tool-guard.ts:222-228`). A secret-shaped/control-bearing unknown name can therefore enter serialized failure/RPC text, contrary to the no-raw-secret requirement (`.codearbiter/reports/2026-07-14-pi-support-handoff/blocker-3-brief.md:44-47`).
- ✅ Always-installed ordering is preserved: the bootstrap guard is registered before `installParent`, while final enforcement is installed only during enabled `session_start` (`plugins/ca-pi/tools/src/extension.ts:246-248`, `plugins/ca-pi/tools/src/extension.ts:290-308`).
- ✅ Enabled activation enters bootstrapping before bridge/enforcement work, and `markReady()` is reached only after the production installation callback completes (`plugins/ca-pi/tools/src/extension.ts:79-98`). A thrown/partial install leaves bootstrap active and not ready.
- ✅ Dormant activation and `session_shutdown` call `deactivate()` (`plugins/ca-pi/tools/src/extension.ts:79-83`, `plugins/ca-pi/tools/src/extension.ts:148-157`). Final guard and result handlers now share the installer's active predicate and return without governance while inactive (`plugins/ca-pi/tools/src/tool-guard.ts:174-183`, `plugins/ca-pi/tools/src/tool-guard.ts:216-246`).
- ✅ Every wrapper stage honors lifecycle state. Inactive wrappers delegate directly to a native definition rooted at the execution context's cwd with no bridge call; bootstrapping `READ` does the same, while direct mutating calls fail closed; ready calls retain canonical snapshot, bridge judgment, and final native execution (`plugins/ca-pi/tools/src/tool-guard.ts:60-107`).
- ✅ A changed enabled cwd causes extension-owned wrappers to be rebuilt/re-registered before readiness, while same-cwd retry stays idempotent (`plugins/ca-pi/tools/src/tool-guard.ts:114-133`, `plugins/ca-pi/tools/src/tool-guard.ts:186-196`).
- ✅ Unknown/opaque tools remain potentially mutating and blocked while active; explicit `READ` remains advisory/allowed (`plugins/ca-pi/tools/src/tool-guard.ts:146-155`, `plugins/ca-pi/tools/src/tool-guard.ts:222-235`).
- ✅ Existing ready-state final-argument/source guarantees remain present: canonical snapshots are passed unchanged to both bridge and executor, mutating bridge warnings fail closed, and active governed tools require the extension-owned final wrapper source (`plugins/ca-pi/tools/src/tool-guard.ts:36-57`, `plugins/ca-pi/tools/src/tool-guard.ts:84-105`, `plugins/ca-pi/tools/src/tool-guard.ts:229-235`).
- ✅ The real installed-Pi fault fixture is test-only and now proves the intended unique one-shot fault was consumed before asserting lifecycle continuation/refusal/no mutation (`.github/scripts/test_pi_package.py:174-277`, `.github/scripts/test_pi_package.py:1012-1068`). No production fault switch, environment variable, configuration, command, endpoint, manifest, or dependency is introduced in the current production source (`plugins/ca-pi/tools/src/extension.ts:188-310`, `plugins/ca-pi/tools/src/tool-guard.ts:1-263`).
- ✅ Pi 0.80.5 evidence is adequate. The exact local npm-cache object named in the fix report hashes to `18f605b87c3504dfb79b91b3c351c61f8d567450f36e994b6ae4b4cd849fd593a480a15deb0b4401c8dc841fef9b3f58b5319b40ec0409bb158fa1b1671ba780`; its package manifest identifies version `0.80.5`, and cached `package/dist/core/extensions/runner.js:648-665` immediately returns the first `result.block`. This check used only the existing integrity-addressed cache; no install or network operation was run.
- ⚠️ The implementer's reported full-suite results and deterministic bundle hashes were not rerun in this read-only rereview. Current source/test behavior and the focused local-cache evidence were inspected directly; command-result claims remain report evidence.

### Prior Finding Closure

1. **Prior HIGH — bootstrap raw-name serialization:** closed for the bootstrap path. The bootstrap handler classifies the raw name but emits a fixed `/ca-doctor` reason with no name interpolation (`plugins/ca-pi/tools/src/tool-guard.ts:146-155`), and the adversarial serialization test checks secret text plus CR/LF/NUL absence (`plugins/ca-pi/tools/test/tool-guard.test.ts:115-132`). The same security property is still violated by the ready/final unknown-tool path, reported below as the remaining HIGH.

2. **Prior MEDIUM — inactive final state:** closed. The active predicate gates the final guard/result handler, wrappers use current execution-context cwd while inactive, and the table-driven regression covers guard-only, result-handler, each partial wrapper stage, no bridge activity, and no stale cwd (`plugins/ca-pi/tools/src/tool-guard.ts:72-83`, `plugins/ca-pi/tools/src/tool-guard.ts:174-196`, `plugins/ca-pi/tools/src/tool-guard.ts:222-246`, `plugins/ca-pi/tools/test/tool-guard.test.ts:150-203`). Reactivation coverage proves bootstrapping read/current-cwd delegation, direct mutation refusal, wrapper replacement, and ready bridge/executor use of the new cwd (`plugins/ca-pi/tools/test/tool-guard.test.ts:205-254`). Shutdown invokes deactivation before retry in the lifecycle test (`plugins/ca-pi/tools/test/activation.test.ts:340-369`).

3. **Prior LOW — unproven fault consumption:** closed. The fixture restores `Map.prototype.set`, writes the exact marker with exclusive-create mode immediately before the unique throw, and the Python test reads it before temporary-root cleanup and requires its exact value (`.github/scripts/test_pi_package.py:184-205`, `.github/scripts/test_pi_package.py:1012-1052`). It still separately requires one lifecycle error, later `agent_settled`, one failed real `write`, `/ca-doctor`, and no mutation sentinel (`.github/scripts/test_pi_package.py:1038-1068`).

4. **Prior task-quality gap — deactivation tested only on a fresh installer:** closed by the partial-stage table and reactivation/current-cwd regression (`plugins/ca-pi/tools/test/tool-guard.test.ts:150-254`).

### Strengths

- Lifecycle state is centralized and read live by every persistent handler/wrapper rather than copied at registration time (`plugins/ca-pi/tools/src/tool-guard.ts:136-196`).
- Defense in depth does not depend solely on Pi's handler short-circuit: while bootstrapping, direct mutating wrapper execution fails before bridge/native execution (`plugins/ca-pi/tools/src/tool-guard.ts:71-82`).
- Partial reinstallation cannot reuse stale wrapper cwd; all four names carry explicit bound-cwd bookkeeping and are replaced when activation cwd changes (`plugins/ca-pi/tools/src/tool-guard.ts:120-132`, `plugins/ca-pi/tools/src/tool-guard.ts:142-145`).
- The real fault marker materially eliminates the earlier unrelated-install-error false green without adding a production seam (`.github/scripts/test_pi_package.py:174-205`, `.github/scripts/test_pi_package.py:1048-1052`).

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

1. `plugins/ca-pi/tools/src/tool-guard.ts:222-228` — ready-state unknown-tool refusals still serialize the untrusted raw tool name. The bootstrap-specific fix does not satisfy the global no-raw-name/no-secret failure-text requirement once readiness yields to the final guard. Replace the unknown-tool reason with a fixed diagnostic or pass the complete reason through a proven redaction boundary, and add a ready/final `guardUnknownTools` regression using the same secret-shaped/control-bearing opaque name asserted by the bootstrap test. Preserve the structured block and `/ca-doctor` direction.

#### Minor (Nice to Have)

None.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The prior lifecycle, stale-cwd, partial-stage, shutdown, and real-fault-authenticity findings are convincingly closed, and supported Pi handler short-circuit behavior is source-proven for both 0.80.5 and 0.80.6. Approval remains blocked because the ready/final unknown-tool boundary still echoes opaque tool names into serialized refusal text.

## Security Review — 2026-07-15

### CRITICAL findings (0)

None.

### HIGH findings (1)

**Severity:** HIGH
**File:** `plugins/ca-pi/tools/src/tool-guard.ts:222-228`
**Description:** When enforcement is active/ready, an unknown opaque tool name is interpolated verbatim into the structured block reason. Pi can serialize that refusal into tool/RPC output, allowing secret-shaped or control-bearing attacker/model input into failure text.
**Control:** Blocker 3 no-raw-secret requirement (`.codearbiter/reports/2026-07-14-pi-support-handoff/blocker-3-brief.md:47`); security-reviewer secret rule (`plugins/ca/agents/security-reviewer.md:55-57`).
**Remediation:** Emit a fixed unknown-tool diagnostic or sanitize the complete reason, and prove serialized output excludes an adversarial opaque name while retaining `block: true` and `/ca-doctor`.

### MEDIUM findings (0)

None.

### LOW findings (0)

None.

### Gate status

BLOCK (0 CRITICAL, 1 HIGH must resolve before merge)

## Final rereview — second fix pass (2026-07-15)

**Final spec compliant:** yes
**Final task quality:** approved
**Final security gate:** PASS — 0 CRITICAL, 0 HIGH, 0 MEDIUM, 0 LOW

### Remaining HIGH closure

- ✅ The READY/final `OTHER` branch still classifies the raw event name, but its complete structured refusal is now fixed text: `{ block: true, reason: "An unknown Pi tool is potentially mutating and is blocked; classify it in the generated descriptor or run /ca-doctor." }` (`plugins/ca-pi/tools/src/tool-guard.ts:222-228`). The opaque name is not interpolated.
- ✅ The adversarial READY-state regression uses a secret-shaped name carrying CR, LF, NUL, and a distinct control payload; it stringifies the complete refusal, requires `block: true` plus `/ca-doctor`, and proves none of the secret/control text or serialized control escapes appears (`plugins/ca-pi/tools/test/tool-guard.test.ts:444-460`).
- ✅ Default unknown-tool behavior remains fail-closed with `/ca-doctor` (`plugins/ca-pi/tools/test/tool-guard.test.ts:435-460`). Descriptor-known governed source drift remains separately blocked (`plugins/ca-pi/tools/src/tool-guard.ts:229-235`, `plugins/ca-pi/tools/test/tool-guard.test.ts:462-468`). That latter reason can name only a value that passed exact descriptor lookup as a non-`OTHER`, non-`READ` governed tool; opaque names take the fixed branch first (`plugins/ca-pi/tools/src/tool-guard.ts:224-233`).
- ✅ No blocker-3 opaque-name refusal path now echoes the raw name: bootstrap uses fixed text (`plugins/ca-pi/tools/src/tool-guard.ts:146-155`) and READY unknown-tool enforcement uses fixed text (`plugins/ca-pi/tools/src/tool-guard.ts:222-228`). No regression is visible in the lifecycle predicates, wrapper state, canonical snapshot, final source, or result-handler code reviewed in the preceding rereview.

### Generated bundle verification

- ✅ Current `plugins/ca-pi/extensions/codearbiter.js` has SHA-256 `E5FC3166D2AA3608C97A8D7973B0B1D769254666DF79B90F997121D7B77749AF`, exactly matching both deterministic builds recorded in `blocker-3-fix-report.md:277-282`.
- ✅ The generated parent contains the fixed bootstrap diagnostic at `plugins/ca-pi/extensions/codearbiter.js:773` and the fixed READY unknown-tool diagnostic at `plugins/ca-pi/extensions/codearbiter.js:836`. The obsolete raw-name prefix `Unknown Pi tool ` is absent from the bundle.
- ✅ The second fix pass changes no production fault switch, dependency, manifest, lockfile, configuration surface, public command, endpoint, or network behavior; the appended fix report scopes the change to the fixed final refusal, regression, and deterministic regeneration (`.codearbiter/reports/2026-07-14-pi-support-handoff/blocker-3-fix-report.md:204-285`).

### Carried-forward conclusions

- The previously closed inactive/partial-stage/current-cwd lifecycle finding remains closed.
- The previously closed one-shot real-Pi fault-authenticity finding remains closed.
- The integrity-verified Pi 0.80.5 and installed Pi 0.80.6 handler short-circuit conclusions remain adequate.
- No new finding invalidates final-argument snapshot, source-identity, unknown-tool, dormant, retry, or shutdown behavior.

### Final issues

#### Critical

None.

#### Important

None.

#### Minor

None.

### Final assessment

**Spec compliance:** ✅ Spec compliant.

**Task quality:** Approved.

**Security:** PASS (0 CRITICAL, 0 HIGH, 0 MEDIUM, 0 LOW).

**Reasoning:** The sole remaining HIGH is closed in the READY path across the complete structured/serialized refusal, unknown tools still block with `/ca-doctor`, and the deterministic shipped parent reflects the fixed source. All previously closed blocker-3 conclusions carry forward without regression.
