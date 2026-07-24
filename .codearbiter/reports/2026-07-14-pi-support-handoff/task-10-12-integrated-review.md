# Tasks 10-12 integrated review

Date: 2026-07-16
Branch: `feat/pi-support`
Scope: Pi Tasks 10-12 only
Verdict: **PASS WITH FINDINGS — zero CRITICAL/HIGH findings; three MEDIUM findings**

## Review basis

The review read the accepted Pi spec, Tasks 10-12 of the implementation plan,
ADRs 0013 and 0014, `.codearbiter/security-controls.md`, all three author
reports, the actual workflow/scripts/tests, and the public/generated
documentation surface. In-progress Task 13/14 promotion-evidence files were
excluded.

Hosted CodeQL and the committed Windows/macOS/Linux by Pi 0.80.5/0.80.6 matrix
remain explicit later promotion checkpoints. This review does not treat local
Windows evidence as those hosted results.

## Findings

### MEDIUM — Changes to the security gate itself can skip the default machine security suite

**Path:** `.github/workflows/ci.yml:87`

The `ca-pi` path filter includes the benchmark/platform scripts but omits
`.github/scripts/test_pi_security.py` and `.github/workflows/codeql.yml`. A PR
that changes only the Python security gate therefore does not schedule the
six-cell `ca-pi-tools` job that runs `python .github/scripts/test_pi_security.py`
in its default adversarial mode. The separate CodeQL workflow is triggered by
the Python script, but invokes it only with `--sarif`; that does not exercise
the default adversarial suite inventory. A CodeQL-workflow-only change can also
skip the Vitest pin/scope assertion because the Pi tools job is not selected.

**Impact:** CI can miss a regression in the promotion gate's suite selection or
workflow contract on a gate-only maintenance PR.

**Remediation:** Add `.github/scripts/test_pi_security.py` and
`.github/workflows/codeql.yml` to the `ca-pi` filter (and retain the existing
CodeQL path triggers), then add a filter-contract assertion proving each path
selects the blocking Pi job.

### MEDIUM — The platform aggregate's repeated checks are not a write-idempotency proof

**Path:** `.github/scripts/test_pi_platform_contract.py:36`

The platform plan runs `tools/build-surface.py --check` twice and
`tools/build-host-packages.py --check` twice. Both `--check` modes are read-only
comparisons. Repeating them proves the checked-in tree is clean twice; it does
not exercise a first generator write followed by a no-op second write, which is
the Task 11 second-run idempotency obligation and the behavior claimed by the
runner comment at line 36.

The separate descriptor/generator tests contain real write-idempotency coverage,
but the Task 11 platform aggregate does not invoke that coverage on every
Windows/macOS/Linux cell.

**Impact:** platform-specific write-mode or second-run behavior could regress
while this aggregate remains green.

**Remediation:** Add a temp-workspace generator test to the aggregate that runs
write mode twice and requires the second write to report zero changes (for both
surface and root-package generation), or invoke an equivalent existing
write-idempotency suite in every platform cell.

### MEDIUM — Public prerequisite prose states the wrong missing-Python failure direction

**Path:** `README.md:130`

The shared installation section says that without Python "the gates and the
startup injection silently don't run." That is not the Pi contract: the
TypeScript adapter installs its bootstrap/final wrappers, an unavailable bridge
returns `PI-BRIDGE`, and mutating operations fail closed with a `/ca-doctor`
instruction (`plugins/ca-pi/tools/src/extension.ts:396` and
`plugins/ca-pi/tools/src/bridge.ts:201`). The existing host interpreter shim is
also documented as emitting a breadcrumb rather than silently going dormant.

**Impact:** operators are given an inaccurate security expectation at the main
installation boundary.

**Remediation:** Make the prerequisite host-specific: Python is required for
all hosts; Claude/Codex surface their interpreter diagnosis, while Pi retains
its TypeScript enforcement boundary and blocks mutations when the Python bridge
is unavailable.

## Resolved during review

### Former HIGH — Pi benchmark measured only the generated Python host mapper

The initial implementation loaded `plugins/ca-pi/hooks/_host.py` and timed its
normalization functions, never crossing the production TypeScript adapter. Its
approximately 0.005 ms Pi p95 and 1.45 ms startup therefore could not prove
PI-AC-31.

The repaired implementation adds
`plugins/ca-pi/tools/test/benchmark-boundary.ts`, imports production
`wrapBuiltins`, registers all four wrappers, and sends the canonical
read/bash/write corpus through snapshotting, `BridgePort`, lifecycle/final
execution, and the native result boundary for five warmups plus 100 measured
events. The orchestrator requires the internal inventory of four wrappers, 105
bridge calls, and 105 native calls, strips those internal fields from the
public schema, and no longer loads Pi's Python `_host.py`. Cold Pi startup is a
fresh Node process through bundle import and wrapper readiness; shared Python
core timing remains separate.

Independent retest:

- `npm --prefix plugins/ca-pi/tools run typecheck` — PASS.
- `python .github/scripts/test_pi_benchmark.py` — 8/8 PASS, including the
  poisoned Python Pi-host path regression.
- `python .github/scripts/pi_benchmark.py --samples 100` — PASS; Windows Pi
  startup 30.9398 ms, Pi adapter p95 0.0071 ms, Claude p95 0.0060 ms, Codex p95
  0.0062 ms, within the approved relative formula.
- `python .github/scripts/test_pi_platform_contract.py --fixtures-only` — four
  direct fixtures and all 11 aggregate steps PASS after the repair.

The former HIGH is **resolved**.

## Other verification evidence

- Official tag mapping: `github/codeql-action` annotated `v4.37.1` dereferences
  to commit `7188fc363630916deb702c7fdcf4e481b751f97a`; both CodeQL init and
  analyze use that immutable commit.
- `npm --prefix plugins/ca-pi/tools exec vitest run test/security.test.ts
  test/final-arguments.test.ts` — 14/14 PASS.
- `python .github/scripts/test_pi_security.py` — all eight local result codes
  PASS with result-code-only JSON.
- `python .github/scripts/test_hooklib.py` — 69/69 PASS.
- `python .github/scripts/test_hook_guards.py` — 106 assertions, zero failures.
- `python .github/scripts/test_pi_platform_contract.py --pi-version 0.80.6` —
  four direct fixtures and all 14 Windows installed-version steps PASS before
  the focused benchmark repair; the repaired benchmark and fixture aggregate
  were then rerun independently as listed above.
- `python .github/scripts/test_public_pi_docs.py` — 10/10 PASS.
- `python .github/scripts/check-plugin-refs.py ca`, `ca-codex`, and `ca-pi` —
  all reference graphs intact.
- `python .github/scripts/test_license_consistency.py` — 23/23 PASS.
- `python .github/scripts/check_license_consistency.py .` — PASS.
- `python tools/build-surface.py --check` — Claude/Codex/Pi synchronized.
- `python tools/build-host-packages.py --check` — root/nested Pi metadata
  synchronized.
- Scoped `git diff --check` — PASS.

## Final verdict

**PASS WITH FINDINGS.** No CRITICAL or HIGH finding remains, so Tasks 10-12 do
not block the next governed sprint step. The three MEDIUM gaps should be fixed
before final closure or carried as explicit tracked obligations; hosted CodeQL
and the six supported platform/version cells remain required Task 13/14
promotion evidence.
