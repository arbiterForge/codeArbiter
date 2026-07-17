# Tasks 13-14 preclosure security review

Date: 2026-07-16
Branch: `feat/pi-support`
Scope: promotion JSON/Markdown, aggregate verifier and tests, Pi security harness,
supported-version CI, CodeQL, generated/runtime inventory, and the post-build
enforcement-registration failure path.

## Verdict

**PASS — 0 CRITICAL, 0 HIGH, 0 MEDIUM, 0 LOW.**

The local preclosure is security-review clean at BLOCK level. The Windows/macOS/Linux x Pi
0.80.5/0.80.6 matrix and CodeQL are still explicitly pending by design; this verdict does not
claim hosted evidence. Final closure must use the verifier's GitHub check-run attestation against
the evidence commit.

## Current findings

None.

## BLOCK-level issues found and remediated during review

1. **Enforcement registration failure had become fail-open after rebuilding the real bundle.**
   The activation catch deactivated the already-installed bootstrap guard after Pi swallowed the
   `session_start` error, allowing the native write executor to run. The catch now leaves the
   bootstrap guard active and unready (`plugins/ca-pi/tools/src/extension.ts:231`), while clearing
   all ready/dispatch leases. The real RPC regression at
   `.github/scripts/test_pi_package.py:1490` now observes one refused write and no mutation.

2. **Promotion fields and public Markdown were not initially bound tightly enough.** The strict
   validator now token-bounds every string field, enumerates architectures, requires exact
   local/pending/final row states and positive measured timings, and records the resolved canary
   SemVer (`.github/scripts/verify_pi_support.py:82`). `promotion.md` is now an exact rendering of
   the sanitized JSON and is checked before PI-AC-35 can pass
   (`.github/scripts/verify_pi_support.py:188`, `:479`).

3. **Hosted success was initially self-certified by JSON plus ancestry.** Final evidence now
   requires all six exact matrix job names and the exact CodeQL job to be completed successfully
   on the evidence SHA through the GitHub check-runs API
   (`.github/scripts/verify_pi_support.py:298`, `:317`, `:496`). The same final-envelope SHA must
   also be an ancestor of `HEAD`, including during the second preclosure phase
   (`.github/scripts/verify_pi_support.py:261`, `:475`).

4. **The second preclosure state was initially circular.** The state machine now admits exactly
   Task 13 `IN_PROGRESS` with PI-AC-35 `OPEN`, or Task 13 `ACCEPTED` with PI-AC-35 `COVERED`, while
   Task 14 and PI-AC-37/38 remain open until the final verifier phase
   (`.github/scripts/verify_pi_support.py:453`).

5. **Descendant and working-tree code drift could initially reuse older hosted evidence.** Final
   evidence now requires every committed, staged, unstaged, and untracked path after the attested
   commit to stay inside the explicit evidence/status/report allowlist. A later source change fails
   before Task 14 can be accepted (`.github/scripts/verify_pi_support.py:261`, `:272`).

6. **The nonblocking canary initially admitted contradictory result tuples.** It now requires a
   passing canary to use `NONE`, and a failing canary to use one of the explicit nonblocking failure
   diagnostics (`.github/scripts/verify_pi_support.py:129`).

## Security-control disposition

- **ADR-0014 opaque authentication boundary:** preserved. Promotion artifacts contain only bounded
  tokens, booleans, numeric timings, and a commit SHA; no prompt, provider body, environment value,
  raw JSONL/stderr, auth path, or home path is admitted.
- **Fail-closed Pi mutations:** restored and reproduced against the real Pi RPC loop after the
  production bundle rebuild. A failed partial enforcement install remains bootstrap-active and
  cannot fall through to the native mutator.
- **Generated/runtime inventory:** the aggregate delegates exact package/orphan checks to the Pi
  package and host-descriptor suites, requires the declared release entrypoints, and rejects shipped
  dependency/runtime trees. The verifier's generator proof writes twice only in a disposable copy.
- **CI/supply chain:** supported Pi installs and toolchain installs use `--ignore-scripts`; the six
  supported cells remain blocking and the latest canary remains explicitly nonblocking. The CodeQL
  init/analyze action is pinned to commit `7188fc363630916deb702c7fdcf4e481b751f97a`, independently
  confirmed as the dereferenced official `v4.37.1` tag.
- **Bounded diagnostics:** verifier command output exposes gate labels and exit codes only; GitHub
  check-run payloads, command stdout/stderr, and evidence parse details are captured and not emitted.

## Fresh independent evidence

- The sprint controller's post-remediation preclosure aggregate passed all 43 command gates plus
  three structural gates; the focused independent reproductions below cover the security-sensitive
  portions of that aggregate.
- `python .github/scripts/test_verify_pi_support.py` — 17/17 passed, including committed,
  staged, unstaged, and untracked descendant-drift rejection.
- `python .github/scripts/test_pi_security.py --evidence docs/reports/pi-support/promotion.json` —
  `PI-SEC-ACTIONS-PIN`, `PI-SEC-CODEQL-SCOPE`, and `PI-SEC-PROMOTION-EVIDENCE` passed.
- `python .github/scripts/test_public_pi_docs.py` — 11/11 passed.
- `npm --prefix plugins/ca-pi/tools exec vitest run test/activation.test.ts test/tool-guard.test.ts`
  — 55/55 passed.
- `python .github/scripts/test_pi_package.py PiPackageTests.test_real_rpc_enforcement_registration_failure_stays_fail_closed`
  — passed against the rebuilt production bundle.
- Direct current-artifact check — `strict_promotion(..., "preclosure")` returned true and
  `promotion.md` matched `render_promotion_markdown(promotion.json)` exactly.
- Official upstream pin check — `git ls-remote` dereferenced `github/codeql-action` tag `v4.37.1`
  to `7188fc363630916deb702c7fdcf4e481b751f97a`.

## Pending final gate

Do not convert this report into hosted success. After the governed checkpoint commit and PR, the
same evidence SHA must have eight exact successful check runs (six supported Pi cells, CodeQL, and
the repository aggregate),
Task 13/PI-AC-35 must be independently accepted, and the final status/evidence update must pass the
second preclosure and final verifier phases before the PR is closure-complete.
