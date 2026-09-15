# Site rolling release applicability plan

**Spec:** `.codearbiter/specs/site-rolling-release-applicability.md`
**Mode:** autonomous sprint under the repository owner's recorded continuous-campaign and SMARTS authority
**MVP slice:** T-01 through T-08

## Acceptance ledger

- **AC-01:** Select the highest stable SemVer independently for `ca`, `ca-codex`, and `ca-pi`; reject missing, duplicate, malformed, prerelease-only, or unsupported target data.
- **AC-02:** Read and validate each declared historical manifest at its receipt commit; reject tag/version, SHA, object, or source substitution failures.
- **AC-03:** Bind GitHub Actions to exact `GITHUB_SHA == HEAD`; bind local output to exact HEAD plus dirty state.
- **AC-04:** Report direct-hook applicability only when current and latest-published exact source digests both match.
- **AC-05:** Generate one deterministic record carrying build, host, proof, source, and evidence-boundary fields.
- **AC-06:** Render independent host rows and exact build identity on Compatibility; render proof applicability and a record link in HookProof.
- **AC-07:** Publish the same record at `/release-applicability.json` with JSON content type.
- **AC-08:** Give both Pages jobs full history and trigger them on release receipts and release declarations.
- **AC-09:** Preserve RED/GREEN evidence; pass focused/full site, type, build, link, coverage, CI-impact, review, PR, exact-head CI, merge, Pages, and live proof without a product release.

Mechanical `uncovered-intent` returned empty against the approved spec. Negative completeness check: no WEB-022/011 obligation remains if AC-01 through AC-09 pass; WEB-031/035 browser-quality work remains a separate, explicitly recorded residual.

## Ordered tasks

| ID | Paths | Verification | Maps to | Covers | Depends on | Status |
|---|---|---|---|---|---|---|
| T-01 | `site/test/release-applicability/release-applicability.test.ts`, `site/scripts/release-applicability.ts` | `npm --prefix site exec -- vitest run test/release-applicability/release-applicability.test.ts` proves independent stable SemVer selection and fail-closed target/ledger parsing | TDD obligations O-01 and O-02 | AC-01 | none | ACCEPTED |
| T-02 | `site/test/release-applicability/release-applicability.test.ts`, `site/scripts/release-applicability.ts` | The focused Vitest file proves historical manifest lookup, exact tag/version equality, invalid SHA rejection, exact CI HEAD binding, and local dirty-state reporting | TDD obligations O-03 through O-06 | AC-02, AC-03 | T-01 | ACCEPTED |
| T-03 | `site/test/release-applicability/release-applicability.test.ts`, `site/scripts/release-applicability.ts` | The focused Vitest file proves dual proof-digest comparison, explicit mismatch output, deterministic serialization, source inventory, and the `release-and-build-identity` boundary | TDD obligations O-07 through O-09 | AC-04, AC-05 | T-02 | ACCEPTED |
| T-04 | `site/scripts/gen.ts`, `site/test/release-applicability/generation.test.ts`, `site/src/generated/release-applicability.json` (generated/ignored) | `npm --prefix site exec -- vitest run test/release-applicability/generation.test.ts` and `npm --prefix site run gen` prove the prebuild writes the strict record from the real repository inputs | TDD obligation O-10 | AC-05 | T-03 | ACCEPTED |
| T-05 | `site/src/components/ReleaseApplicability.astro`, `site/src/content/docs/getting-started/compatibility.md`, `site/src/content/docs/getting-started/compatibility.mdx`, `site/test/release-applicability/presentation.test.ts` | Focused presentation test proves the stable-route MDX page renders all three independent rows, exact full-SHA link, record link, and evidence boundary | TDD obligations O-11 and O-12 | AC-06 | T-04 | ACCEPTED |
| T-06 | `site/src/components/HookProof.astro`, `site/test/landing/landing-page.test.ts`, `site/test/release-applicability/presentation.test.ts` | Focused landing and presentation tests prove the caption exposes exact latest-published `ca` applicability and links to the shared record without weakening the existing replay boundary | TDD obligation O-13 | AC-04, AC-06 | T-04 | ACCEPTED |
| T-07 | `site/src/pages/release-applicability.json.ts`, `site/test/release-applicability/endpoint.test.ts` | Focused endpoint test proves the static GET body is byte-equivalent JSON data and uses `application/json; charset=utf-8` | TDD obligation O-14 | AC-07 | T-04 | ACCEPTED |
| T-08 | `.github/workflows/docs.yml`, `.github/scripts/test_ci_impact.py`, `site/test/release-applicability/workflow.test.ts` | `python .github/scripts/test_ci_impact.py` plus the focused workflow test prove both checkouts use `fetch-depth: 0` and push/PR triggers include `.github/published-tags.json` and `.codearbiter/release-targets.md` | TDD obligations O-15 and O-16 | AC-08 | T-01 | ACCEPTED |
| T-09 | all MVP paths | `npm --prefix site test`, `npm --prefix site run typecheck`, `$env:GITHUB_SHA=(git rev-parse HEAD); npm --prefix site run build`, `npm --prefix site run link-audit`, and `npm --prefix site run coverage` all pass; site lines and branches each remain at or above the stage-2 70% floor | TDD Phase 4 and Phase 5 | AC-09 | T-01..T-08 | ACCEPTED |
| T-10 | all changed paths | Independent spec-compliance, code-quality, security/trust-boundary, and coverage reviews report no unresolved blocking finding; `git diff --check` passes | TDD Phase 6 and sprint two-pass review | AC-09 | T-09 | ACCEPTED |
| T-11 | `.codearbiter/specs/site-rolling-release-applicability.md`, `.codearbiter/plans/site-rolling-release-applicability.md`, `.codearbiter/sprint-log.md`, all accepted implementation paths | The ca-commit gate creates the governed commit; PR opens without merge; exact-head required CI and unresolved-thread checks pass | commit-gate and finishing-a-development-branch | AC-09 | T-10 | PENDING |
| T-12 | hosted PR, merge result, Pages deployment, `https://codearbiter.dev/release-applicability.json`, rendered Compatibility and hook proof | After the sprint returns, the campaign controller applies the already-recorded standing merge authority only if exact-head gates remain green, then verifies exact-main Pages deployment plus live JSON/rendered identity. No tag or package release occurs. | campaign post-PR delivery boundary | AC-09 | T-11 | PENDING |

## Bijection proof

- AC-01 → T-01
- AC-02 → T-02
- AC-03 → T-02
- AC-04 → T-03, T-06
- AC-05 → T-03, T-04
- AC-06 → T-05, T-06
- AC-07 → T-07
- AC-08 → T-08
- AC-09 → T-09, T-10, T-11, T-12

Every task advances at least one criterion. Every criterion has at least one exact-path task and concrete verification. The graph is acyclic. T-01 through T-08 form the smallest shippable slice; T-09 through T-12 are mandatory validation and delivery, not optional expansion.

## Approval record

The repository owner has already granted standing authority to fix and disposition campaign issues, directed continuous execution without inter-task acknowledgements, and explicitly required rolling host-version behavior with SMARTS favoring enforceable freshness. This plan is a direct decomposition of checkpoint-044's recorded acceptance and introduces no new user-visible fork, spend, credential, release, destructive operation, or trust-boundary expansion. The spec and plan are therefore approved under that existing explicit authority; irreversible and hard-gate conditions remain stops.
