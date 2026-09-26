# Verification runner contracts repair

## Incident and scope

The reading-first site plan reached approval with verification definitions that
the installed authority adapter could not execute and attest. The first snapshot
failed because exclusions such as `node_modules` did not intersect the declared
`site` root; exclusions are repository-relative paths. After correcting that
policy, the verifier hook rejected the first Playwright command with
`UNSUPPORTED_COLLECTOR`. A read-only inventory found 32 unsupported definitions
among 35 commands in the 30-task plan.

The user requested a complete regression-first fix and two independent sweeps of
the failure class. The repair starts from `a5a3d79c` in an isolated worktree. The
site work and its approval history remain in their original worktree.

## Independent sweep findings

The runner sweep identified missing Playwright and npm-wrapper contracts,
token-anywhere runner misclassification, duplicate pass/skip names accepted as
success, nonverbose unittest commands incorrectly classified as named-result
producers, and ambiguous reporter forwarding through compound npm scripts.

A native Windows diagnostic also showed that passing `& echo` as arguments to
`npm.cmd` executes the echo despite `subprocess.Popen(shell=False)`. This was a
harmless diagnostic, not a verification receipt. Supported npm launchers must
resolve to pinned native Node and npm JavaScript entry points; unsupported batch
launchers must fail closed.

The lifecycle sweep identified late collector validation, a separate paired
approval route that needs the same preflight, ineffective exclusions outside
selected roots, explicit roots bypassing exclusions, and oversized explicit
files losing their original size diagnostic during directory fallback.

Neither sweep edited production code or manufactured authority events.

## Repair obligations

| ID | Obligation |
| --- | --- |
| VR-01 | Recognize actual supported runner entry points and simple npm wrappers; reject incidental tokens and ambiguous script chains. |
| VR-02 | Attest exact named Playwright and Vitest results; reject missing, skipped, duplicate, retried, flaky, malformed, or prefix-only evidence. |
| VR-03 | Preserve literal Windows arguments and bind native executable and launcher inputs against drift. |
| VR-04 | Validate supported verifier quoting explicitly while preserving host correlation and rejection of compound shell calls. |
| VR-05 | Preflight every plan command before ordinary and paired approval, with bounded reads and identity checks, without executing proposed tests. |
| VR-06 | Keep snapshot and path-coverage policy consistent and report ineffective exclusions and oversized inputs with actionable paths. |
| VR-07 | Preserve fail-closed authority capture, process containment, source binding, and exact required-test identity. |

These obligations derive from the observed incident, the requested class repair,
and the existing exact-command/exact-result authority contract. A successful
fixture test is local regression evidence, not production host attestation.

## Verification record

### Regression-first record

The baseline authority suite passed 75 tests with one platform skip before the
repair. The first runner regression set then produced 19 failing subcases and
four errors for the observed missing contracts, false-positive outcomes, wrapper
selection, and literal Windows argument failures. Seven lifecycle regressions
and four Go input-policy regressions independently reproduced the late approval
checks and snapshot failures.

Further review findings each received a failing regression before repair:
ignored direct-Node entrypoint drift, Windows rooted/drive-relative npm prefix
escape, unbounded manifest growth after stat, malformed/nonfinite manifest input,
missing Windows browser-discovery variables, and native unittest CRLF handling.
The packaged bridge test also caught an inappropriate authority import; moving
preflight to `_approvallib` restored the unchanged offline bridge contract. No
allowlist or trust gate was relaxed.

Red outputs are retained locally as `codearbiter-*-red.txt` under the Windows
temporary directory. They are diagnostic logs, not production authority receipts.

### Obligation mapping

| Obligation | Behavioral evidence | Status |
| --- | --- | --- |
| VR-01 | Authority tests for runner position, verbose qualification, prefixed npm scripts, compound scripts and malformed manifests | COVERED |
| VR-02 | Exact Playwright/Vitest/unittest/named-line outcomes, prefix and suffix refusals, duplicate pass/skip/fail, retry/repeat, malformed JSON and CRLF regressions | COVERED |
| VR-03 | Native Windows literal-metacharacter launch; isolated before/after wrapper, Node, npm CLI and manifest drift; ignored Node entrypoint drift | COVERED |
| VR-04 | Single/double quoted wrapper and malformed-selector tests plus existing correlation/containment regressions | COVERED |
| VR-05 | Complete plan paging/exact reads, source identity drift, aggregated failures, ordinary/pair refusal before pending state, and unchanged offline bridge guard | COVERED |
| VR-06 | Real filesystem snapshot overlap, exclusion, missing-root and explicit/directory oversized-input tests; readiness policy diagnostics | COVERED |
| VR-07 | Go qualified producer schema and semantic mutations, profile relabelling refusal, native npm engine capture and existing complete task/scope lifecycle fixture | COVERED |

### Native Windows checks

- Full authority suite: 104 tests completed in 73.097 seconds; 103 passed and the
  POSIX-only process-group test was skipped on Windows. This includes both the
  complete packaged task/scope lifecycle and native npm engine receipt capture.
- Approval adapter: 53 tests passed.
- Authoring contract: 5 tests passed; artifact surface: 13 passed; consumer closure:
  16 passed; adapter/manifest version identity: 1 passed.
- Go observation, evidence, validation and operations packages passed. Focused
  observation/evidence/validation `go vet` passed.
- Canonical Python syntax checks passed. Core, surface and host-package generator
  parity passed; plugin reference closure and `git diff --check` passed.
- The read-only redacting secret scan reported fixed synthetic fixture tokens and
  existing plugin-root placeholders. The newly added token is the literal
  `plan-preflight-token`; no credential was introduced. No commit-stage marker
  was manufactured from this worktree diagnostic.

Two real-run diagnostics used the preserved site worktree without creating any
authority receipt:

- Playwright 1.63.0 ran the actual reading-first browser baseline through the
  candidate npm binding, restricted environment and process supervisor. Exit 0;
  its exact 96-character native test title passed the JSON collector. Stdout:
  25,065 bytes, SHA-256
  `0ec6a8ccf62d9b6bda85ed3052b435269167410b28918ba4a02570f21eef4ecc`.
- Vitest 4.1.9 ran `test/rehype-table-shell.test.ts` through the candidate direct
  Node binding. Exit 0; all three tests ran, and the collector attested the exact
  `rehypeTableShell > wraps a rendered table without changing the table element`
  identity. Stdout: 900 bytes, SHA-256
  `1d0166d48fcfddc4a257f115f5c8f2214f1767f330f4fecfb57cd1de40b14584`.

### Independent review

The fresh coverage auditor passed VR-01 through VR-07 after the launcher-drift,
bounded-manifest and genuine-reporter checks. The security reviewer reproduced
and then independently verified repairs for two HIGH findings: ignored direct
Node entrypoint drift and Windows npm prefix escape. Both reviewers ended with
no outstanding findings. The security reviewer also passed the approval-helper
move after checking both routes, unchanged bridge restrictions and fresh-process
import orders.
The final CRLF-only collector change also passed a separate security delta
review, including mixed-newline duplicate cases; version changes were confirmed
to be literal metadata updates.

### Delivery and live-proof boundary

The isolated branch is `codex/fix-verification-runner-contracts`; its base is
`a5a3d79c`. Candidate versions are ca 2.22.1, ca-codex 0.14.1 and ca-pi 0.15.1.
These are local changes, not published releases. The default checkout's dirty
work and the site task's staged baseline files are preserved.

This report records local verification, not a merge, release, installed-plugin
replacement, or production verification receipt. Hosted exact-head and cross-platform CI remain required
before merge. Installation must use the qualified release, followed by genuine
host verification. The site plan still needs one complete amendment for explicit
supported reporters, exact test identities, and the compound T028 commands;
fresh approval and execution must follow that amendment. Its existing approvals
and armed request have not been reinterpreted as successful verification.

The owner replied "Yes approved" to the explicit commit, push and PR request,
then "Merge on Green and done". This authorizes the guarded PR merge after
current exact-head checks and review gates pass. It does not authorize release
publication or installed-plugin replacement.

No unrelated backlog items were raised by this repair.

## Coverage measurement scope

The Python no-tooling exemption is grounded in the repository's explicit statement:

> There is **no coverage tooling for the Python hooks** (`plugins/*/hooks/*.py`,
> `.github/scripts/*.py`). No numeric floor exists for those surfaces, so `tdd`
> Phase 5 and `refactor` Phase 2 and Phase 6 all take the **no-tooling exemption**

The Go artifact-engine surface is unmentioned in the configured Coverage section.
Its focused test and vet results are behavioral proof, not a line/branch coverage
percentage. The complete current section is quoted below for the no-configured-
tooling assessment; its historical TypeScript figures are not measurements of
this patch. Independent obligation review remains required for both surfaces.

### Complete `.codearbiter/tech-stack.md` Coverage section

> One command per TypeScript tree, only when that tree changed:
>
> ```sh
> npm --prefix plugins/ca/tools run coverage
> npm --prefix plugins/ca-pi/tools run coverage
> npm --prefix plugins/ca-sandbox/tools run coverage
> npm --prefix site run coverage
> ```
>
> Each prints a text summary and writes an html report to that tree's `coverage/`
> (gitignored — run output, never project state). Scope, provider and reporters
> live in each tree's `vitest.config.ts`.
>
> **The COMMAND is identical on every platform. The REPORT is not** (issue #521).
> The script takes no arguments, so nothing about the invocation varies — but code
> behind a platform fork cannot execute off its own platform, and a single-host
> report scores the other platform's arm as uncovered no matter how well tested it
> is. Measured here: `plugins/ca/tools` reads 66.18% branches on Windows and
> 65.35% on Linux, and `exec.ts` alone reads 87.50% against 76.38% — an 11-point
> gap that is entirely `awaitTaskkill` plus the win32 `treeKill` arm on one side
> and the POSIX arm on the other.
>
> **A quoted figure is the union across a tree's supported hosts**, per tree:
>
> | tree | forks on platform | union in CI |
> | --- | --- | --- |
> | `plugins/ca/tools` | yes — `exec.ts` on `process.platform` | **ubuntu + windows**, merged |
> | `plugins/ca-pi/tools` | yes — Windows supervisor / process-tree paths | **ubuntu + windows**, merged |
> | `plugins/ca-sandbox/tools` | no | single-host (ubuntu); docker caveat below |
> | `site/` | no | single-host (ubuntu) |
>
> CI produces the union for both forked trees — `[CHECK] | [REPO] | Coverage union`
> for `plugins/ca/tools` and `[CHECK] | [PI  ] | Coverage union` for
> `plugins/ca-pi/tools` — one advisory matrix cell per host writing a vitest
> **blob** report, merged with `vitest --merge-reports`. Before testing,
> `coverage_union.py prepare` binds each host's source, configuration, lockfile,
> and checkout identity; `prepare --check` rechecks those inputs afterward.
> `coverage_union.py verify` validates the host receipts and compatible coverage
> maps, then writes normalized copies into a fresh merge directory. Original
> reports remain unchanged. Missing-host output is explicitly partial; invalid
> evidence cannot be reported as a union.
>
> Vitest alone does not normalize Windows and Linux absolute source paths. The
> earlier same-host disjoint-suite demonstration did not prove cross-host union:
> PR #740 exposed 41 sources counted as 82 files. The behavioral regression now
> requires complementary host coverage to retain one identity per source, while
> preserving legitimately distinct files. Historical figures below are not
> accepted cross-host evidence until remeasured through the verified path.
>
> Each tree's blobs are namespaced `coverage-blob-<tree>-os-<host>`, so one
> tree's merge cannot collect another's. The naive names collided — a `ca-*` glob
> also matches `ca-pi-*` — which would have merged two trees into one figure under
> `ca`'s name, silently and with a plausible number.
>
> Locally, one host's report is a legitimate figure — **name the host** and say the
> other's contribution is missing. The rule and its conditions live in
> `plugins/ca/includes/maturity-coverage.md`; this table is the per-tree half it
> refers to.
>
> **The threshold is not encoded in the tooling.** `tdd` Phase 5 and `refactor`
> Phase 2/6 apply it, reading `stage:` from `.codearbiter/CONTEXT.md` against
> `plugins/ca/includes/maturity-coverage.md`. **Lines and branches must both
> clear it**; a report satisfying one and not the other does not pass. Putting the
> number in three `vitest.config.ts` files would fork that single source of truth
> and the copies would drift the first time the stage moves.
>
> Historical baseline at stage 2 (≥ 70%), recorded 2026-07-29 from CI. The two
> platform-forked figures require remeasurement after the cross-host identity
> repair; the other rows are single-host measurements. Each row names its
> measurement scope:
>
> | tree | lines | branches | verdict | host |
> | --- | --- | --- | --- | --- |
> | `plugins/ca/tools` | 76.82% | 73.15% | unverified historical identity merge | ubuntu + windows, before identity repair |
> | `plugins/ca-pi/tools` | 82.51% | 77.10% | unverified historical identity merge | ubuntu + windows, before identity repair |
> | `plugins/ca-sandbox/tools` | 86.13% | 79.96% | clears | windows |
> | `site` | 91.29% | 84.85% | clears | ubuntu-equivalent (no platform fork) |
>
> **Historical motivation for union measurement.** #511 drove `plugins/ca/tools`
> against 66.18% branches on Windows and 65.35% on Linux — both below the floor.
> The previously reported merged 73.15% is not current proof that the union clears
> the floor: cross-host file identity must first be verified. Platform-forked
> `exec.ts` code still cannot execute off its own host, which is why a single-host
> figure is not a substitute for the required union.
>
> Two caveats when reading a local report:
>
> - **ca-sandbox self-skips its docker-gated suites** on a host without Docker, so
>   a local number reads lower than required CI's. Compare against a run with
>   `CA_SANDBOX_REQUIRE_DOCKER=1` before concluding that tree regressed.
> - **No CI job enforces coverage.** It is an orchestrator gate the skills run, not
>   a required check — deliberately, since wiring a red `ca/tools` into required CI
>   would block every merge on an unrelated backfill.
>
> **`site/` is inside the coverage gate** (#514 / DECISION-0032). It was the one
> tested tree with no command, so `tdd` Phase 5 reached it and took the no-tooling
> exemption on a tree that has 438 real tests — the #507 failure mode, by a
> different door. It now runs vitest 4 like the plugin trees, with
> `@vitest/coverage-v8` pinned to the same exact version (the two are peer-pinned;
> a caret on one and not the other is how they drift apart).
>
> Its coverage `include` is scoped to `scripts/` — the generator, link-audit and
> rehype helpers that the suites actually exercise. Deliberately NOT `src/`: those
> are Astro components rendered at build time and covered by the build plus the
> link audit, so counting them would report a large permanently-dark surface no
> test in this tree was ever meant to reach.
>
> `COVERAGE_EXEMPT` in `.github/scripts/test_ci_impact.py` is now **empty**, and a
> companion test still fails on a stale entry. (It is a CI allowlist for the
> doc-contract test — never the agent-facing exemption, and it cannot be taken in
> place of one.)
>
> One thing that does NOT transfer: `site/` is the only tree here with production
> dependencies (astro, starlight, markdown-remark) and is deliberately off the
> dev-inclusive CVE gate, whose sweep lives in `docs.yml`. Adding a coverage
> provider does not change that posture — the provider is a dev dependency, and
> the audit scope is unchanged.
>
> There is **no coverage tooling for the Python hooks** (`plugins/*/hooks/*.py`,
> `.github/scripts/*.py`). No numeric floor exists for those surfaces, so `tdd`
> Phase 5 and `refactor` Phase 2 and Phase 6 all take the **no-tooling exemption**
> — whose conditions live in `plugins/ca/includes/maturity-coverage.md` and are
> NOT restated here. In short: it requires a citation, not an assertion, and the
> sentence above is the passage to quote.
>
> This paragraph previously read "use the per-symbol direct-test proof alone and
> say so in the phase record" — a local copy of the old, laxer rule, naming only
> `refactor` Phase 2. That is exactly the drift the exemption's single-source rule
> exists to stop: project state was instructing an agent to assert on the one
> surface class in this repo where the exemption actually fires, while the include
> required it to cite. Deferring, rather than restating, is the fix.
