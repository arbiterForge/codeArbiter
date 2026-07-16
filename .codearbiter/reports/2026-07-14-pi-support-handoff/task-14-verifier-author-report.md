# Task 14 author report - aggregate verifier and preclosure gate

Date: 2026-07-16
Status: preclosure verifier complete; final hosted closure pending
Owns: PI-AC-37, PI-AC-38

## Outcome

`.github/scripts/verify_pi_support.py` is a read-only, two-phase aggregate verifier. Preclosure permits only the sequencing decision's explicit hosted and CodeQL pending rows. Final mode requires an exact ten-row final envelope, concrete hosted architectures and timings, an actual-semver canary row, canonical promotion Markdown, a real evidence commit that exists in Git and is an ancestor of `HEAD`, seven exact successful GitHub check runs for that commit, and only allowlisted evidence/status/report changes after that SHA across commits, the index, the working tree, and untracked files.

The full real preclosure verifier passed after running 42 named repository/Pi command gates plus three structural binding gates. It also passed branch, task/obligation owner inventory, exact 38-binding inventory, promotion sanitization, runtime-tree absence, package/orphan inventory, descriptor-owned policy-duplication, parity-exception, and isolated twice-written generator checks.

## Fail-closed properties

- Every PI-AC-01 through PI-AC-38 binding names one or more concrete gate labels; placeholder ownership cannot self-certify.
- A binding passes only when every named label exists and succeeded in that run.
- Promotion parsing rejects extra rows, duplicate/missing cells, non-finite or negative timings, unsafe tokens/home paths, fabricated final commit ancestry, incoherent canary result/diagnostic tuples, and `pending` final hosted architectures.
- Promotion Markdown must exactly match the deterministic rendering of the JSON record.
- Final hosted evidence is attested against the exact six adapter check names and the CodeQL check through GitHub's check-runs API.
- Final evidence ancestry is fail-closed: committed, staged, unstaged, and untracked changes after the attested SHA must stay inside the explicit evidence/status/report allowlist.
- The plan and obligation states must match the active phase; preclosure and final closure cannot self-certify each other's task states.
- Command diagnostics expose only bounded gate labels and exit codes, not captured command payloads.
- Real generators are written twice inside an isolated copied tree and byte-digested; the workspace remains unchanged.
- The descriptor oracle admits only exact Task 2-11 non-policy files and keeps unlisted policy/tool mutations fail-closed.

## Review remediation

- Restored the descriptor suite from 9/13 to 13/13 by independently modeling Pi-only role metadata and exact Task 6-11 artifacts.
- Added the machine-security script and CodeQL workflow to the `ca-pi` CI path filter with mutation tests.
- Corrected README missing-Python behavior: Pi mutations fail closed and existing-host shims surface a breadcrumb.
- Repaired PI-AC-31 so the Pi record runs the production TypeScript `wrapBuiltins`/BridgePort/native-executor boundary, with 5 warmups and exactly 100 measured events. The harness asserts four final wrappers plus 105 bridge and 105 native calls and proves the Pi record does not load generated Python `_host.py`.
- Replaced repeated `--check` as an idempotency claim with actual twice-written generator proofs in the platform aggregate and verifier.
- Kept enforcement fail-closed when Pi swallows a `session_start` registration failure: bootstrap readiness remains active and blocks a synthetic write executor.
- Bound final promotion evidence to canonical Markdown, coherent canary metadata, exact hosted check-run attestation, and evidence-only descendant plus dirty-tree state.

## Verification

- `python .github/scripts/test_verify_pi_support.py` - 17 passed.
- `python .github/scripts/test_host_descriptors.py` - 13 passed.
- `python .github/scripts/test_pi_benchmark.py` - 8 passed.
- `python .github/scripts/pi_benchmark.py --samples 100` - PASS; Pi adapter p95 0.0118 ms in the recorded local run, with startup and shared-core timing reported separately.
- `npm --prefix plugins/ca-pi/tools run typecheck` - PASS.
- `python .github/scripts/test_pi_security.py --evidence docs/reports/pi-support/promotion.json` - PASS.
- `python .github/scripts/test_public_pi_docs.py` - 11 passed.
- `python .github/scripts/test_pi_package.py PiPackageTests.test_real_rpc_enforcement_registration_failure_stays_fail_closed` - PASS; the full package suite passed 23/23.
- `python .github/scripts/verify_pi_support.py --mode preclosure` - PASS; 42/42 named command gates, three structural binding gates, and all aggregate rows passed.

## Remaining terminal gate

Task 14 remains `IN_PROGRESS`; PI-AC-37 and PI-AC-38 remain `OPEN`. Final mode must run after the PR's supported six-cell matrix and CodeQL are green and the evidence is updated on the same branch. No commit, PR, tag, publish, or merge was performed by this task.
