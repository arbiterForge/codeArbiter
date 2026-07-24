# Blocker 4 independent task and security review

**Recorded:** 2026-07-15
**Scope:** exact Pi version admission and npm-latest canary
**Review mode:** read-only source review plus two focused, in-memory CI-contract mutation probes

## Spec compliance

- ❌ **Issues found.** The pure admission function accepts exactly `0.80.5` and `0.80.6`, but the real default entrypoint imports and validates Pi runtime APIs before calling it. The latest-canary contract also permits the latest installation to become an `echo` no-op while its validator remains green. These miss the brief's first-boundary and non-false-green requirements (`blocker-4-brief.md:19-31`).
- ✅ Exact string admission is correctly implemented with a two-member `Set`, with the fixed raw-input-free diagnosis evaluated before the supported-version Node and Python checks (`plugins/ca-pi/tools/src/compatibility.ts:9-33`). The shipped bundle contains the same set, diagnosis, and check order (`plugins/ca-pi/extensions/codearbiter.js:13-35`).
- ✅ The current supported CI matrix is exactly Windows/macOS/Linux by Pi `0.80.5`/`0.80.6`, and the separate npm-latest job remains job-level `continue-on-error` (`.github/workflows/ci.yml:205-229`, `.github/workflows/ci.yml:264-288`).

## Strengths

- The compatibility implementation uses exact equality rather than a semver-prefix parser, so older, later, prerelease, build-decorated, `v`-prefixed, whitespace-decorated, partial, extra-component, malformed, and `1.x` strings cannot enter the supported branch (`plugins/ca-pi/tools/src/compatibility.ts:9-25`).
- The rejection message is a fixed literal that names both supported versions and `/ca-doctor` without interpolating the raw version, environment, path, or package content (`plugins/ca-pi/tools/src/compatibility.ts:23-31`).
- Unit and shipped-package tables cover the requested version shapes and preserve the supported-version Node-then-Python prerequisite order (`plugins/ca-pi/tools/test/package.test.ts:632-658`, `plugins/ca-pi/tools/test/package.test.ts:814-873`). The injected boundary also proves zero property access on the supplied Pi API proxy for its focused unsupported cases (`plugins/ca-pi/tools/test/package.test.ts:875-889`).
- The committed parent bundle matches the source implementation at the admission boundary (`plugins/ca-pi/extensions/codearbiter.js:13-35`, `plugins/ca-pi/extensions/codearbiter.js:1273-1287`). Independent SHA-256 checks matched the handoff-preserved lock and child hashes; the current parent hash is the report's regenerated `7FAF81EDA124B1C5B4B498E7ADB47ED03E234F7A128D8EAB215CB406167DCDDC` (`blocker-4-report.md:154-164`).
- Current distribution manifests still declare no runtime dependencies, and the tools manifest remains development-only (`package.json:1-17`, `plugins/ca-pi/package.json:1-18`, `plugins/ca-pi/tools/package.json:1-21`). No production canary switch is present in the reviewed runtime sources.

## Issues

### Critical (must fix)

None.

### Important (should fix)

1. **The real default extension imports and reads Pi runtime APIs before exact version admission.** `codeArbiterPi` awaits the full runtime resolver before it calls `compatibilityDirection` (`plugins/ca-pi/tools/src/extension.ts:188-196`). That resolver dynamically imports the installed Pi module and reads/validates `ModelRegistry`, `SettingsManager`, and four tool factories before returning its manifest version (`plugins/ca-pi/tools/src/runtime-resolver.ts:128-153`). An unsupported later Pi whose export shape has changed can therefore execute/import and fail with `PI_RUNTIME_DIAGNOSIS` before the required fixed unsupported-version diagnosis. This is the API-drift case the upper bound is meant to contain. The new tests exercise only the injected `createCodeArbiterPi` seam (`plugins/ca-pi/tools/test/package.test.ts:875-903`), so they cannot detect the real ordering defect. Split canonical package/manifest/version resolution from module import and API-shape validation; exact-admit the canonical manifest version first, then import the runtime. Add a shipped default-entrypoint fixture whose unsupported manifest points at a module with an evaluation sentinel and drifted exports, and prove the fixed version diagnosis occurs without module evaluation or Pi API access.

2. **The npm-latest canary contract can false-green without installing npm latest.** The validator anchors `pi --version` and the named test, but it does not validate an executable `@latest` installation or an active `continue-on-error` property (`.github/scripts/test_pi_package.py:559-615`). The test uses substring assertions for those two requirements (`.github/scripts/test_pi_package.py:776-805`) and its mutation coverage only no-ops the report and admission commands (`.github/scripts/test_pi_package.py:847-865`). Focused in-memory probes replacing the latest install with `echo npm install ...@latest...` and commenting out `continue-on-error: true` both returned `pi_ci_contract_violations == []`. With a pre-existing supported Pi on `PATH`, the first mutation tests that stale runtime and reports the latest canary green. The helper increases this ambiguity by accepting an adjacent package before proving that a `pi` executable exists in that `PATH` entry (`plugins/ca-pi/tools/test/package.test.ts:30-52`). Anchor and order the actual latest install, version report, and named admission command inside `ca-pi-latest`; parse `continue-on-error` as an active job property; add comment/echo/no-op/order mutation cases; and tie package-root discovery to the first executable that `pi` resolution would actually select.

### Minor (nice to have)

None.

## Assessment

**Task quality:** Needs fixes.

**Reasoning:** The exact pure boundary and bundle are clean, but the production entrypoint reaches runtime APIs before admission and the canary's claimed no-false-green contract is not enforced. Both are central requirements rather than optional coverage polish.

## Security review - 2026-07-15

### CRITICAL findings (0)

None.

### HIGH findings (0)

None.

### MEDIUM findings (2)

**Severity:** MEDIUM
**File:** `plugins/ca-pi/tools/src/extension.ts:188`
**Description:** The default extension fully imports and validates an unsupported Pi runtime before exact version admission, so the claimed first active boundary is not the real production order and a drifted unsupported API receives a different pre-admission path.
**Control:** `.codearbiter/security-controls.md:274-298` - Pi adapter and child-process security; cooperative trusted runtime and load-bearing enforcement boundaries.
**Remediation:** Resolve and validate canonical package identity plus manifest version without importing runtime exports, reject unsupported versions with the fixed diagnosis, and only then import/validate runtime APIs.

**Severity:** MEDIUM
**File:** `.github/scripts/test_pi_package.py:594`
**Description:** The latest-version compatibility canary's validator accepts an echoed/no-op npm-latest installation, allowing a stale supported Pi on `PATH` to masquerade as a green latest-runtime admission result. This is a coverage gap on the version boundary rather than an active exploit; unsupported versions still fail closed before registration when the admission function is reached.
**Control:** `.codearbiter/security-controls.md:274-298` - Pi adapter security boundary; task brief's last-verified upper-bound control.
**Remediation:** Validate executable, ordered latest installation and exact executable-derived package identity/version, with adversarial comment/echo/no-op/order mutation tests.

### LOW findings (0)

None.

### Gate status

**PASS** - 0 CRITICAL and 0 HIGH findings. The two MEDIUM findings must remain in the checkpoint record, and the task-scoped quality gate remains **Needs fixes**.

## Focused checks

- Static source-to-bundle comparison: exact set, diagnosis, and ordering are present in both TypeScript and shipped JavaScript.
- SHA-256: lock and child matched preserved handoff values; parent matched the blocker report's deterministic rebuild value.
- In-memory CI mutation probes: latest install changed to `echo` -> `[]`; `continue-on-error` changed to a YAML comment -> `[]` from `pi_ci_contract_violations`.
- No broad suite was rerun; the implementer's reported green suite was treated as evidence, not as a substitute for direct source review (`blocker-4-report.md:109-164`).
