# Blocker 4 independent task and security rereview

**Recorded:** 2026-07-15
**Scope:** second-pass closure of the production admission-order and npm-latest canary findings

## Spec compliance

- ✅ **Spec compliant.** Both first-review findings are closed. The shipped default path now authenticates canonical Pi package identity and exact manifest version without module evaluation, applies exact admission, and only then loads runtime exports (`plugins/ca-pi/tools/src/extension.ts:188-197`, `plugins/ca-pi/tools/src/runtime-resolver.ts:105-167`).
- ✅ The exact supported set remains only `0.80.5` and `0.80.6`; the fixed unsupported diagnosis still contains neither raw input nor path/environment/package values, and admitted-version Node then Python prerequisite ordering is unchanged (`plugins/ca-pi/tools/src/compatibility.ts:9-33`).
- ✅ The supported CI matrix remains exactly three operating systems by two supported Pi versions, while npm latest remains a separate job-level nonblocking canary (`.github/workflows/ci.yml:205-229`, `.github/workflows/ci.yml:264-288`).

## Finding closure

### 1. Production admission before module/API evaluation - closed

- `resolvePiRuntimeIdentity` requires an absolute active CLI anchor; canonicalizes it; authenticates the owning package name, canonical root and manifest, declared bin target, internal export target, and external-to-plugin location; and freezes the exact versioned identity without importing the runtime module (`plugins/ca-pi/tools/src/runtime-resolver.ts:105-154`).
- The default extension applies `compatibilityDirection` to that authenticated manifest version before `loadPiRuntime` (`plugins/ca-pi/tools/src/extension.ts:188-197`). No supplied `ExtensionAPI` property is accessed before this point.
- Only a resolver-minted frozen identity can load. The admitted path re-resolves every identity field immediately before import, validates `VERSION`, `ModelRegistry`, `SettingsManager`, and all required tool factories, then re-resolves the identity after import (`plugins/ca-pi/tools/src/runtime-resolver.ts:47-48`, `plugins/ca-pi/tools/src/runtime-resolver.ts:97-103`, `plugins/ca-pi/tools/src/runtime-resolver.ts:161-199`). The public wrapper preserves the established strict path (`plugins/ca-pi/tools/src/runtime-resolver.ts:202-204`).
- Existing shipped-package coverage still rejects counterfeit/local-host resolution, wrong-package anchors, export escapes, and symlink escapes while proving the admitted real Pi `ModelRegistry` is the host's exact object (`plugins/ca-pi/tools/test/package.test.ts:620-728`, `plugins/ca-pi/tools/test/package.test.ts:800-826`).
- The new regression genuinely invokes the generated parent bundle's default export against a canonical external fake `0.80.7` package. Its module sets an evaluation sentinel and throws if evaluated; the supplied API is a property-counting proxy. Assertions require the fixed diagnosis, sentinel false, and zero API access (`plugins/ca-pi/tools/test/package.test.ts:904-949`). Focused rereview execution passed this regression.
- The generated parent bundle contains the same identity-before-admission/load-after-admission order and before/after identity checks, and does not publicly export the helper phases (`plugins/ca-pi/extensions/codearbiter.js:556-645`, `plugins/ca-pi/extensions/codearbiter.js:1308-1317`, `plugins/ca-pi/extensions/codearbiter.js:1438-1448`).

### 2. Canary authenticity and no-false-green validator - closed

- Installed runtime discovery now ignores a `PATH` entry with no platform Pi executable, selects the first executable-bearing entry, follows executable symlinks/canonical ancestors, and permits the npm-wrapper adjacent layout only in that same entry after package-name validation (`plugins/ca-pi/tools/test/package.test.ts:32-65`). The cross-platform stale-adjacent regression constructs a stale first entry without an executable and proves the actual later executable's package wins (`plugins/ca-pi/tools/test/package.test.ts:951-982`). Focused rereview execution passed it.
- The CI contract requires active job-level `continue-on-error: true`, then exact executable npm-latest install, `pi --version`, named installed-runtime admission, and broad package test in that order inside `ca-pi-latest` (`.github/scripts/test_pi_package.py:594-608`). The actual workflow has that exact structure (`.github/workflows/ci.yml:264-288`).
- Adversarial mutation coverage rejects echo/no-op latest install, version reporting, and named admission; a commented nonblocking declaration; and broad-before-focused ordering (`.github/scripts/test_pi_package.py:851-901`). The exact broad-test anchor in the sequence also rejects an echoed or commented broad command (`.github/scripts/test_pi_package.py:597-608`). The focused CI-contract test passed on rereview.

## Strengths and unchanged constraints

- Exact equality, raw-input-free diagnostics, and supported-version prerequisite ordering remain direct and easy to audit (`plugins/ca-pi/tools/src/compatibility.ts:9-33`).
- Source tables still cover both supported versions and all requested rejected shapes, including prerelease, build metadata, prefix, whitespace, partial, extra component, malformed, and `1.x` values (`plugins/ca-pi/tools/test/package.test.ts:856-900`).
- Independent SHA-256 checks matched the second-pass deterministic parent hash `1B91303B73A9091AD446D7F6E493891088F1A1D7CEBBD2D152E37CA736E9C9A7` and the preserved lock and child hashes recorded at `blocker-4-report.md:321-331`.
- Current root/plugin manifests still contain no runtime dependency, the tools manifest remains development-only, and no production test switch was introduced (`package.json:1-17`, `plugins/ca-pi/package.json:1-18`, `plugins/ca-pi/tools/package.json:1-21`).

## Issues

### Critical

None.

### Important

None.

### Minor

None.

## Assessment

**Task quality:** Approved.

**Reasoning:** Exact admission is now the real shipped default boundary, the admitted path retains strict runtime identity checks, and the latest canary cannot silently substitute text or a stale package for the installed runtime proof.

## Security review - 2026-07-15

### CRITICAL findings (0)

None.

### HIGH findings (0)

None.

### MEDIUM findings (0)

None. Both prior MEDIUM findings are resolved.

### LOW findings (0)

None.

### Gate status

**PASS** - 0 CRITICAL, 0 HIGH, 0 MEDIUM, 0 LOW.

The remaining same-user package-content race documented at `blocker-4-report.md:333-340` is consistent with the accepted cooperative trusted-runtime boundary in `.codearbiter/security-controls.md:274-298`; it is not reopened by this version-admission task.

## Focused rereview checks

- `npm test -- test/package.test.ts -t "shipped default rejects unsupported Pi|installed Pi discovery ignores"` - 2 passed, 12 skipped.
- `python .github/scripts/test_pi_package.py PiPackageTests.test_ci_has_pi_path_output_matrix_and_independent_version_guard -v` - 1 passed.
- Direct source/bundle inspection and SHA-256 comparison completed; no broad suite was rerun.
