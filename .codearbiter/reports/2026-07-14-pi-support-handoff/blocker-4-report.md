# Blocker 4 report - exact Pi version admission

**Recorded:** 2026-07-15
**Branch:** `feat/pi-support`
**Source:** `blocker-4-brief.md` and the handoff HIGH "supported-version split"

## Outcome

The parent adapter now accepts only the exact canonical Pi version strings `0.80.5` and `0.80.6`.
Every older, later, decorated, partial, or malformed value returns one fixed diagnosis before the Pi
extension API object is touched:

```text
codeArbiter requires Pi 0.80.5 or 0.80.6; install a supported Pi version and run /ca-doctor.
```

The message does not interpolate the rejected value or any path/environment/package data. Supported
versions retain the prior prerequisite ordering: Node below `22.19.0` returns the existing Node
direction, then a non-Python-3 input returns the existing Python direction.

The supported CI matrix remains Windows/macOS/Linux x Pi `0.80.5`/`0.80.6`. The separate npm-latest
job remains `continue-on-error`, prints the installed `pi --version`, explicitly runs the named
installed-runtime admission test, then runs the broad package test. An unsupported latest therefore
fails the named test with the production fixed diagnosis; rejection cannot be interpreted as a
passing compatibility result.

## RED evidence

Tests were changed before production code.

```powershell
npm test -- test/package.test.ts -t "rejects unsupported Pi"
```

Result: exit 1. Vitest reported three independent failures because none of these production-boundary
calls threw:

- `0.80.7`
- `0.80.6-rc.1`
- `1.0.0`

Each failure was `expected [Function] to throw an error`, demonstrating the prior minimum/prefix
parser admitted the required negative cases.

```powershell
python .github/scripts/test_pi_package.py `
  PiPackageTests.test_ci_has_pi_path_output_matrix_and_independent_version_guard -v
```

Result: exit 1 because the npm-latest job did not contain the explicit named installed-runtime
production-admission command.

After the source fix but before bundle regeneration, the full package-path test also failed as
expected: the shipped parent still emitted the old minimum-version direction and admitted the new
negative table. This proved the package assertion exercised shipped `codearbiter.js`, not the
TypeScript source by accident.

## Implementation

### Exact production boundary

`plugins/ca-pi/tools/src/compatibility.ts` replaces the Pi minimum-version tuple/parser path with an
exact `Set` containing only `0.80.5` and `0.80.6`. The Node minimum parser remains unchanged and is
reached only after Pi admission. The default extension already evaluates this direction before its
first use of the supplied `ExtensionAPI`; the injected `createCodeArbiterPi` boundary provides the
same ordering for tests and canaries.

### Unit and shipped-package proof

`plugins/ca-pi/tools/test/package.test.ts` now covers:

- admitted: exact `0.80.5`, exact `0.80.6`;
- rejected: `0.80.4`, `0.80.7`, `0.81.0`, prerelease, build metadata, leading `v`, leading/trailing
  whitespace, partial, extra-component, malformed, and `1.0.0` values;
- unchanged Node and Python diagnosis ordering for an admitted Pi version;
- focused production-boundary RED cases for `0.80.7`, prerelease, and `1.x`;
- a shipped-bundle table that invokes `createCodeArbiterPi` with a Pi API `Proxy` and observes zero
  property accesses for every rejected shape;
- an installed-runtime canary that discovers the actual Pi package from `PATH`, reads its installed
  manifest version, invokes production `createCodeArbiterPi`, and asserts zero API access.

The local installed runtime was Pi `0.80.6`; the exact canary passed.

### Canary contract

`.github/workflows/ci.yml` invokes this sequence in `ca-pi-latest`:

```text
pi --version
npm test -- test/package.test.ts -t "installed Pi runtime is admitted by the production boundary"
npm test -- test/package.test.ts
```

`.github/scripts/test_pi_package.py` verifies that the report and named production-admission command
are executable commands in that order. Mutation checks replace each with `echo` and require the CI
contract validator to fail, preventing a text-only/no-op false green.

## Files changed

- `plugins/ca-pi/tools/src/compatibility.ts`
- `plugins/ca-pi/tools/test/package.test.ts`
- `.github/workflows/ci.yml`
- `.github/scripts/test_pi_package.py`
- `plugins/ca-pi/extensions/codearbiter.js` (deterministically regenerated)

No dependency, manifest, lockfile, install script, production test switch, runtime fault hook, child
bundle, or unrelated governance state was changed for this blocker.

## GREEN verification

### Focused admission and canary

```powershell
npm test -- test/package.test.ts -t "rejects unsupported Pi|exact supported Pi versions"
pi --version
npm test -- test/package.test.ts -t "installed Pi runtime is admitted by the production boundary"
python .github/scripts/test_pi_package.py `
  PiPackageTests.test_ci_has_pi_path_output_matrix_and_independent_version_guard -v
```

Results: focused source admission 4/4; installed Pi `0.80.6`; installed-runtime canary 1/1; CI
contract 1/1.

### Full TypeScript and package/RPC suites

```powershell
npm run typecheck
npm test
npm test -- test/package.test.ts
python .github/scripts/test_pi_package.py
python .github/scripts/test_pi_package.py --rpc-commands
```

Results: typecheck exit 0; full Pi suite 8 files and 107/107 tests; package TypeScript 12/12;
release/package/RPC-process suite 16/16; isolated real-Pi command/alias RPC 1/1.

### Parity, doctor, shared-hook, generation, and CI contracts

```powershell
python .github/scripts/test_pi_parity.py
python .github/scripts/test_pi_doctor.py
python .github/scripts/test_hooklib.py
python .github/scripts/test_host_descriptors.py
python tools/sync-core.py --check
python tools/build-surface.py --check
python tools/build-host-packages.py --check
git diff --check
```

Results: parity 18/18; doctor/backstop 5/5; shared activation/hooklib 69/69; host descriptors 13/13;
42 shared core files x 3 plugins byte-identical; Claude/Codex/Pi generated surfaces in sync; root and
Pi package descriptors in sync; diff check exit 0.

## Deterministic bundle evidence

Two consecutive final `npm run build` executions produced identical hashes:

| Artifact | First build | Second build |
|---|---|---|
| `plugins/ca-pi/extensions/codearbiter.js` | `7FAF81EDA124B1C5B4B498E7ADB47ED03E234F7A128D8EAB215CB406167DCDDC` | `7FAF81EDA124B1C5B4B498E7ADB47ED03E234F7A128D8EAB215CB406167DCDDC` |
| `plugins/ca-pi/extensions/codearbiter-child.js` | `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328` | `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328` |
| `plugins/ca-pi/tools/package-lock.json` | `9D3FE616FFBC306BC77B25F2C1CFEA3A4A2A41354F9C170CE102A101C1871CC2` | `9D3FE616FFBC306BC77B25F2C1CFEA3A4A2A41354F9C170CE102A101C1871CC2` |

The child and lock hashes are byte-identical to the preserved handoff values.

## Self-review

- Pi admission is exact-string equality; semver prefix matching, leading `v`, prerelease/build
  decorations, whitespace, and extra components cannot bypass it.
- The fixed failure message contains the complete supported set, remediation, and `/ca-doctor`, but
  no rejected/raw value.
- Rejected source and shipped-package calls observe zero Pi API proxy access.
- Supported-version Node/Python diagnoses and their order are unchanged.
- The six-cell supported matrix is unchanged; npm latest remains a separately visible nonblocking
  signal.
- The canary executes the installed version report and named production admission test; its contract
  mutation tests reject command no-ops.
- No dependency installation or network access was performed during implementation.
- No user-owned dirt, audit log, task board, later blocker, or Tasks 6-9 surface was intentionally
  changed.

## Residual concerns

The npm-latest job is intentionally nonblocking, so an unsupported newly published Pi will surface as
a failed canary without blocking the supported `0.80.5`/`0.80.6` matrix. Promoting any newer Pi now
requires an explicit supported-set change plus the normal live/versioned review evidence; this is the
desired contract, not an automatic semver-range promotion.

---

## Second pass - independent review fixes

The first independent task/security review found two task-quality gaps despite its security PASS:

1. The real default entrypoint called the full runtime resolver before exact admission, and that
   resolver evaluated Pi's module/API exports.
2. The canary validator accepted an echoed npm-latest installation and a commented nonblocking
   declaration, while the installed-package helper could select an adjacent stale package from a
   `PATH` entry with no `pi` executable.

Both findings were fixed test-first. This section supersedes the first-pass parent-bundle hash and
full-suite count above; the original evidence is retained as the chronological review record.

### Second-pass RED evidence

The shipped-default regression created an external fake Pi package with canonical CLI metadata,
manifest version `0.80.7`, and a module that sets an evaluation sentinel then throws. It set the fake
CLI as the active `process.argv[1]` anchor and invoked the shipped bundle's real default export through
a Pi API proxy.

```powershell
npm test -- test/package.test.ts `
  -t "shipped default rejects unsupported Pi|installed Pi discovery ignores"
```

Result: 2/2 failed before production changes.

- Default-entrypoint result was
  `{ diagnosis: PI_RUNTIME_DIAGNOSIS, moduleEvaluated: true, apiAccesses: 0 }`; expected was the fixed
  unsupported-version diagnosis, `moduleEvaluated: false`, and zero API access.
- PATH result selected `stale-bin/node_modules/.../pi-coding-agent` even though `stale-bin` contained
  no `pi` executable; expected was the later package tied to the first actual executable.

The in-memory CI mutations were also added before the validator fix:

```powershell
python .github/scripts/test_pi_package.py `
  PiPackageTests.test_ci_has_pi_path_output_matrix_and_independent_version_guard -v
```

Result: exit 1 because replacing the npm-latest installation with `echo npm install ...` still
returned no contract violations. The same test now also covers a commented job-level
`continue-on-error`, echo/no-op version and admission commands, and broad-before-focused ordering.

### Two-phase runtime boundary

`plugins/ca-pi/tools/src/runtime-resolver.ts` now separates runtime handling into two phases:

1. `resolvePiRuntimeIdentity` performs read-only canonical metadata resolution. It authenticates the
   active absolute CLI anchor, owning Pi package name, canonical package/manifest root, declared CLI
   bin target, internal export target, and exact manifest version without importing the Pi module.
2. The default entrypoint runs `compatibilityDirection` against that canonical manifest version.
   Unsupported versions stop here with the fixed raw-input-free diagnosis.
3. Only an admitted version reaches `loadPiRuntime`. It accepts only an immutable identity minted by
   the resolver, re-resolves and exact-compares all canonical identity fields before import, evaluates
   the canonical internal module, validates `VERSION`, `ModelRegistry`, `SettingsManager`, and all
   required tool factories, then re-resolves the identity after import to detect manifest/path drift.

The existing public `resolvePiRuntime` contract remains as a two-phase wrapper, preserving the prior
counterfeit package, poisoned local package, CLI mismatch, export escape, and symlink escape checks.
The helper phases were not added to the shipped extension's public exports.

The shipped fake-`0.80.7` regression is now green with the exact fixed diagnosis, no module sentinel,
and zero Pi API proxy access. Supported real-Pi package loading and strict `ModelRegistry` identity
remain green.

### Canary authenticity and parser hardening

The installed-runtime helper now searches each `PATH` entry for an actual platform Pi executable
before considering that entry's package. It follows a selected executable with `realpath` and first
walks its canonical ancestors; Windows/npm wrapper layouts may then use the package adjacent to that
same executable directory after package-name validation. An adjacent package in an entry without a
Pi executable is ignored. No npm config, user config, subprocess, network, or package manager lookup
is used.

The stdlib-only CI contract validator now requires within the actual `ca-pi-latest` job:

- active job-level `continue-on-error: true` at the correct indentation;
- executable exact npm-latest installation;
- executable `pi --version`;
- executable named installed-runtime admission;
- executable broad package test;
- that exact order from install through broad test.

Anchored command matching rejects comments, `echo` prefixes, text-only mentions, and ordering drift.
Adversarial in-memory mutations prove each required command/property is load-bearing.

### Second-pass files changed

- `plugins/ca-pi/tools/src/runtime-resolver.ts`
- `plugins/ca-pi/tools/src/extension.ts`
- `plugins/ca-pi/tools/test/package.test.ts`
- `.github/scripts/test_pi_package.py`
- `plugins/ca-pi/extensions/codearbiter.js` (deterministically regenerated)

No dependency, manifest, lockfile, install script, production test switch, child bundle, supported CI
matrix, audit state, or later-task surface changed.

### Second-pass GREEN verification

```powershell
npm run typecheck
npm test -- test/package.test.ts
npm test
python .github/scripts/test_pi_package.py
python .github/scripts/test_pi_package.py --rpc-commands
python .github/scripts/test_pi_parity.py
python .github/scripts/test_pi_doctor.py
python .github/scripts/test_hooklib.py
python .github/scripts/test_host_descriptors.py
python tools/sync-core.py --check
python tools/build-surface.py --check
python tools/build-host-packages.py --check
git diff --check
```

Final results after the last source/bundle change:

- typecheck: exit 0;
- focused blocker regressions: 3/3 including supported real-loader identity;
- package TypeScript: 14/14;
- full Pi: 8 files, 109/109;
- release/package/RPC-process: 16/16;
- isolated real-Pi command/alias RPC: 1/1;
- parity: 18/18;
- doctor/backstop: 5/5;
- shared activation/hooklib: 69/69;
- host descriptors: 13/13;
- sync-core, generated surfaces, root/Pi package metadata, and diff check: green.

### Final deterministic hashes

Two consecutive builds after the second-pass fixes produced:

| Artifact | First build | Second build |
|---|---|---|
| `plugins/ca-pi/extensions/codearbiter.js` | `1B91303B73A9091AD446D7F6E493891088F1A1D7CEBBD2D152E37CA736E9C9A7` | `1B91303B73A9091AD446D7F6E493891088F1A1D7CEBBD2D152E37CA736E9C9A7` |
| `plugins/ca-pi/extensions/codearbiter-child.js` | `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328` | `E04A1CF31ABF22F7EB7FFE77B5584E7892EC46DAED2CB6915E725172EDABD328` |
| `plugins/ca-pi/tools/package-lock.json` | `9D3FE616FFBC306BC77B25F2C1CFEA3A4A2A41354F9C170CE102A101C1871CC2` | `9D3FE616FFBC306BC77B25F2C1CFEA3A4A2A41354F9C170CE102A101C1871CC2` |

The child and lock remain byte-identical to the handoff values.

### Second-pass residual

Canonical metadata is checked immediately before and after module evaluation, and runtime `VERSION`
must equal the admitted manifest version. As with Pi's existing cooperative trusted-runtime boundary,
this is not a signed-content or hostile same-user filesystem guarantee: a same-user actor that can
replace admitted package bytes in the final filesystem-to-ESM-loader race already controls the trusted
Pi process. Expanding to hostile package-content integrity would require a separate signed/hash-pinned
runtime design and is outside this version-admission blocker.
