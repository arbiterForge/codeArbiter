# Blocker 6 independent task and security review

**Recorded:** 2026-07-15
**Scope:** truthful Pi doctor dispatcher coverage
**Review mode:** read-only source/API/evidence review; no implementation edits, staging, or test reruns

## Spec compliance

- ✅ **Spec compliant.** The supported Pi API boundary was checked against the operator-installed
  0.80.6 `dist/core/extensions/types.d.ts` (`ExtensionAPI`, lines 839-999) and the integrity-addressed
  cached 0.80.5 tarball's same public declaration. Both expose event/command/tool registration,
  message injection, shell `exec`, and tool introspection/activation, but no deterministic active
  tool-dispatch method. Command context adds session control, not a tool dispatcher (0.80.6 public
  declaration lines 208-297 and 824-829). The relabel path is therefore justified.
- ✅ No private or undocumented Pi dispatch seam was added. Production uses public
  `getCommands`, `getActiveTools`, `getAllTools`, `registerTool`, and event registration through the
  typed ports at `plugins/ca-pi/tools/src/contracts.ts:51` and
  `plugins/ca-pi/tools/src/contracts.ts:102`. The doctor directly invokes only its stored wrapper at
  `plugins/ca-pi/tools/src/extension.ts:285` and
  `plugins/ca-pi/tools/src/tool-guard.ts:246`.
- ✅ The runtime always emits `active-dispatch` as `degraded`, with the exact supported-version
  limitation and promotion/CI remediation, at `plugins/ca-pi/tools/src/doctor.ts:360`. No input or
  wrapper result can promote that row. Report formatting necessarily produces an overall degraded
  verdict when no unhealthy row exists at `plugins/ca-pi/tools/src/doctor.ts:411`.
- ✅ The stored wrapper self-test uses only the exact dry-run command at
  `plugins/ca-pi/tools/src/tool-guard.ts:246`. Only an error beginning with exact
  `BLOCKED [H-03]` followed by `:` or end-of-message is healthy; native execution, a different H-ID,
  textual H-03 bait, and dormant execution are rejected or degraded at
  `plugins/ca-pi/tools/src/doctor.ts:374`. Those cases are pinned at
  `plugins/ca-pi/tools/test/doctor.test.ts:252`,
  `plugins/ca-pi/tools/test/doctor.test.ts:270`, and
  `plugins/ca-pi/tools/test/doctor.test.ts:286`.
- ✅ The installed real-Pi RPC check parses the actual structured report envelope, requires one
  exact row per diagnosis ID, pins the wrapper and active-dispatch messages/remediation, rejects
  `live-fire`, requires `doctor: DEGRADED`, and compares staged paths before/after at
  `.github/scripts/test_pi_package.py:1191`. Because the assertions target the parsed JSON report
  value, matching prose in the generated skill cannot create a false green.
- ✅ Canonical and generated Pi doctor/preview/catalog wording consistently says wrapper
  self-test and active-dispatch gap at `core/surface/commands/doctor.md:26`,
  `plugins/ca-pi/skills/ca-doctor/SKILL.md:15`,
  `core/surface/commands/preview.md:59`,
  `plugins/ca-pi/generated/command-catalog.json:83`, and
  `plugins/ca-pi/COMMANDS.md:60`. The only `live-fire` text in Pi's shared mechanical doctor is in
  the explicit non-Pi branch; Pi selects the truthful branch at `core/pysrc/doctor.py:253`.
  Claude/Codex generated doctor and preview surfaces retain their live-fire wording, with no Pi
  wrapper/dispatch terminology, as pinned at `.github/scripts/test_pi_doctor.py:165`.
- ✅ Durable coverage remains honest: PI-AC-28 is `BLOCKED` at
  `.codearbiter/plans/pi-support.md:123`; Task 5 is blocked and distinguishes its direct wrapper test
  from active dispatch at `.codearbiter/plans/pi-support.md:704`; pending Task 13 explicitly owns
  supported-version independent active-dispatch evidence at
  `.codearbiter/plans/pi-support.md:1378`. No completed-evidence link is claimed.
- ✅ The checked-in parent bundle contains the same wrapper call, exact matcher, and permanently
  degraded diagnosis at `plugins/ca-pi/extensions/codearbiter.js:880` and
  `plugins/ca-pi/extensions/codearbiter.js:1172`. Current SHA-256 values match the implementer report:
  parent `700E81D51769FEB7A52AE77BE21F1AB7AAF7B283E695D04470AAEDFFDAE682AF`, unchanged child
  `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328`, and unchanged lock
  `9D3FE616FFBC306BC77B25F2C1CFEA3A4A2A41354F9C170CE102A101C1871CC2`.

## Strengths

- The implementation separates useful wrapper/shared-core evidence from unavailable active-host
  dispatcher evidence instead of preserving a stronger label than the API can support.
- Exact structured-report assertions and before/after index checks make the installed-host doctor
  test meaningfully resistant to prose matches and mutation false greens.
- Pi-specific surface conditionals preserve the existing Claude/Codex contract while keeping the
  shared mechanical doctor byte-identical across all generated host copies.

## Issues

### Critical

None.

### Important

None.

### Minor

None.

## Assessment

**Task quality:** Approved
**Reasoning:** The implementation matches the truthful relabel decision, keeps the acceptance gap
durably blocked, and supplies exact unit/generated/real-host evidence without inventing a dispatcher
capability.

## Security review

### CRITICAL findings (0)

None.

### HIGH findings (0)

None.

### MEDIUM findings (0)

None.

### LOW findings (0)

None.

### Gate status

**PASS** (0 CRITICAL, 0 HIGH). The scoped change adds no dependency, manifest/lock mutation,
production switch, network/auth access, shell interpolation, or private host-boundary crossing.
The self-test remains non-mutating and cannot convert missing active-dispatch proof into health.
