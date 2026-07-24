# Task 10 author report - security promotion gates and static analysis

Date: 2026-07-16
Status: locally complete; hosted CodeQL result is intentionally deferred to the Task 13 evidence checkpoint
Owns: PI-AC-30, PI-AC-36

## Outcome

The ADR-0014 threat gate is `PROCEED-WITH-CONSTRAINTS`. The local promotion surface now has dedicated adversarial final-argument, unknown-tool, owner-replacement, lifecycle, environment, output, SARIF, compaction, package, farm, and isolation evidence. No raw prompt, environment value, provider body, tool result, or stderr is written to the machine-readable report.

The review found and closed one HIGH stale-lifecycle farm/activation defect; see `task-9-security-rereview.md`. ADR-0014 was preserved without relaxation.

## Implemented gates

- Added `test/security.test.ts` and `test/final-arguments.test.ts` with final-executor mutation proof, unknown/prototype tool refusal, governed owner replacement, farm ownership/key isolation, opaque lifecycle leases, stale activation rejection, pre-spawn lease checks, pinned CodeQL scope, and result-only SARIF evidence.
- Added `.github/scripts/test_pi_security.py`. It emits only schema, fixed result codes, pass/fail, and finding counts. Its default gate suppresses raw test output and covers adversarial, isolation, ownership, compaction, farm, and package suites.
- Added `.github/workflows/codeql.yml` for JavaScript/TypeScript `security-extended` analysis over `plugins/ca-pi/tools/src/**` and shipped `plugins/ca-pi/extensions/**`, excluding `node_modules`. Checkout and CodeQL actions are commit-SHA pinned; lower findings upload normally, while security severity 7.0 or higher fails through the SARIF result-code gate.
- Added the machine security gate to the required cross-platform Pi CI matrix.
- Fixed the hook-guard harness import path exposed by the required full security evidence; production hook behavior was unchanged.

## Result codes

- `PI-SEC-ACTIONS-PIN`
- `PI-SEC-CODEQL-SCOPE`
- `PI-SEC-ADVERSARIAL`
- `PI-SEC-ISOLATION`
- `PI-SEC-OWNERSHIP`
- `PI-SEC-COMPACTION`
- `PI-SEC-FARM`
- `PI-SEC-PACKAGE`
- `PI-SEC-CODEQL-HIGH` (hosted SARIF or deterministic fixture input)

## Verification

- RED: dedicated Vitest run failed on missing CodeQL workflow and security harness; lifecycle regressions additionally failed on boolean readiness, stale farm authorization, and spawn without a lease recheck.
- `npm --prefix plugins/ca-pi/tools run typecheck` - PASS
- `npm --prefix plugins/ca-pi/tools exec vitest run test/security.test.ts test/final-arguments.test.ts` - 14 passed
- `npm --prefix plugins/ca-pi/tools test` - 253 passed, 1 skipped
- `npm --prefix plugins/ca-pi/tools exec vitest run test/farm.test.ts` - 11 passed after terminal/cancellation additions
- `python .github/scripts/test_pi_security.py` - PASS for all eight local result codes
- `python .github/scripts/test_hooklib.py` - 69 passed
- `python .github/scripts/test_hook_guards.py` - 106 assertions, 0 failed
- `git diff --check` - PASS

## Hosted evidence boundary

Local execution proves workflow shape, pinning, source scope, high-severity SARIF failure behavior, and a synthetic high finding without retaining its message. The authoritative real CodeQL database/result cannot exist until GitHub runs the committed PR SHA. Under the accepted Task 13/14 sequencing decision, Task 13 must record the hosted CodeQL check and require zero unresolved HIGH/CRITICAL findings before final promotion evidence closes.
