# Plan: Tribunal vNext review-quality modernization

**ID:** `PLAN-TRIBUNAL-VNEXT-001` (legacy Markdown workflow identity)
**Spec:** `SPEC-TRIBUNAL-VNEXT-001`, [tribunal-vnext-review-quality.md](../specs/tribunal-vnext-review-quality.md)
**Source:** PR #887 at `50c19c32d4746cbd3fbcaeeeb3012fc5f4f0a8c5`, current main `cd5b0a0e21ddbc97183c079106ce6418bc1cf7b1`.
**Authority:** User requested implementation on 2026-10-05 and directed that the spec and implementation merge together later. Earlier direction delegates reasonable implementation choices and asks to reduce interruptions. This plan decomposes that scope; it does not claim a separate user review or authorize merge/publication.
**Format:** Installed resolver selected the existing lone `.md` spec and same-format plan. No conversion or shadow artifact.

## Scope and execution

Implement the 38 approved criteria on the existing PR branch. Keep one generic
lens reviewer, existing public lens names, historical records, and explicit audit
cost/filing/telemetry consent. Use standard-library helpers and focused tests;
reuse the existing CI lanes. Claude's SMARTS work remains outside this plan.

Each task uses a fresh author and test-first behavioral verification. Independent
spec reviews and fresh coordinator tests precede acceptance; security/coverage
review applies once to the combined scope. Work proceeds under the user's
existing implementation direction without renewed per-batch permission questions.

## Acceptance ledger

Each ID refers to the identically numbered criterion in the approved spec.

| IDs | Required outcome | Tasks |
| --- | --- | --- |
| AC-01, AC-02 | Exact reviewed-source binding and drift rejection | T-01, T-05 |
| AC-03 | Exclusive fresh-run allocation, including forced collisions | T-01 |
| AC-04, AC-05 | Explicit terminal event and follow-up-only resume | T-01, T-05 |
| AC-06, AC-07 | Durable leads and lens-independent root-cause identity | T-01, T-05 |
| AC-08 | Factual uncertainty stays distinct from product decisions | T-01, T-05 |
| AC-09 | Author-independent severity and risk routing | T-03, T-05 |
| AC-10, AC-11 | Host-supported profiles and honest independence | T-02, T-05, T-06 |
| AC-12, AC-13 | Deterministic inventory without executing project code | T-02, T-05 |
| AC-14 | Complete applicability and evidence contracts on every card | T-03 |
| AC-15, AC-16 | Evidence cannot grant authority or arbitrary execution | T-03, T-05 |
| AC-17, AC-18 | Finding/evidence scope and ownership of absence claims | T-03, T-05 |
| AC-19, AC-20, AC-21 | Semantic, change-closure, and verification-quality detection | T-03, T-04, T-06 |
| AC-22, AC-23, AC-24, AC-25, AC-26 | Domain-specific evidence and clean controls | T-03, T-04, T-06 |
| AC-27, AC-28 | Serious-finding verification and no filing refuted claims | T-01, T-05 |
| AC-29, AC-30, AC-31 | Paired corpus, metrics, and critical-regression comparison | T-04, T-06 |
| AC-32, AC-33 | Historical compatibility and preserved logs/references | T-01, T-05 |
| AC-34 | Existing lens URLs remain valid | T-03, T-06 |
| AC-35 | Opt-in aggregate-only telemetry | T-05 |
| AC-36 | Generated hosts and public docs match canonical sources | T-06 |
| AC-37 | Behavioral run-state, trust, schema, routing and projection tests | T-01, T-02, T-03, T-04, T-05, T-06 |
| AC-38 | Actual incumbent/candidate benchmark on frozen corpus | T-04, T-06 |

## Ordered tasks

Commands run at the repository root unless stated. Focused unittest invocations
are the scoped form of `tech-stack.md:254-256`; generator and build commands come
from its Test section. New tests live in the existing discovered hook suite.
No new mandatory CI job or inference dependency is introduced.

| ID | Exact owned paths | Verification | Maps-to | Covers | Depends-on | Status |
| --- | --- | --- | --- | --- | --- | --- |
| T-01 | `core/pysrc/_tribunalrunlib.py`, `core/pysrc/tribunal.py`, `plugins/ca/hooks/tests/test_tribunal_run.py` | `python -m unittest discover -s plugins/ca/hooks/tests -p test_tribunal_run.py -v`; syntax check touched Python | Source, lifecycle, durable-record and serious-finding outcome obligations; real temporary Git repositories and forced collision fixtures | AC-01–08, AC-27–28, AC-32–33, AC-37 | none | ACCEPTED |
| T-02 | `core/pysrc/_tribunalinventorylib.py`, `plugins/ca/hooks/tests/test_tribunal_inventory.py` | `python -m unittest discover -s plugins/ca/hooks/tests -p test_tribunal_inventory.py -v`; syntax check | Facts extracted without execution; host-native profiles, bounded evidence cost inputs and explicit unavailable capabilities | AC-10–13, AC-37 | none | ACCEPTED |
| T-03 | `core/surface/skills/tribunal/references/lenses/`, `core/surface/skills/tribunal/references/ai-markers.md`, `core/surface/skills/tribunal/references/review-risk.md`, `core/surface/skills/tribunal/references/verification-quality.md`, `plugins/ca/hooks/tests/test_tribunal_lenses.py` | `python -m unittest discover -s plugins/ca/hooks/tests -p test_tribunal_lenses.py -v`; card-by-card independent spec review | Applicability, evidence, trust and modern failure-family mandates; preserve URLs and one generic executor | AC-09, AC-14–26, AC-34, AC-37 | none | ACCEPTED |
| T-04 | `.github/fixtures/tribunal/`, `tools/tribunal-eval.py`, `plugins/ca/hooks/tests/test_tribunal_eval.py` | `python -m unittest discover -s plugins/ca/hooks/tests -p test_tribunal_eval.py -v`; offline fixture and comparison validation | Twenty defect/control families; blind public inputs separated from oracle; honest scoring and critical regression guard | AC-19–26, AC-29–31, AC-37–38 | none | ACCEPTED |
| T-05 | `core/surface/skills/tribunal/SKILL.md`, `core/surface/skills/tribunal/references/{cost-and-models,finding-record,schemas,triage,report,issue-filing,telemetry}.md`, `core/surface/agents/{tribunal-lens-reviewer,map-structure,map-deps}.md`, `core/pysrc/tribunal.py`, `plugins/ca/hooks/tests/test_tribunal_workflow.py`, `.github/scripts/test_build_surface.py` | `python -m unittest discover -s plugins/ca/hooks/tests -p test_tribunal_workflow.py -v`; fresh helper CLI exercise; focused existing surface tests | End-to-end workflow uses helpers, bounded packets, verifier mode, root-cause triage, follow-up resume and privacy | AC-01–02, AC-04–13, AC-15–18, AC-27–28, AC-32–33, AC-35, AC-37 | T-01, T-02, T-03 | ACCEPTED |
| T-06 | Generated `plugins/ca/`, `plugins/ca-codex/`, `plugins/ca-pi/` counterparts of changed canonical sources; their manifests/changelogs; `core/hosts.json`, version literals in `core/pysrc/hostapi.py` and host `hooks/_host.py`, Codex npm metadata, root `package.json`, `README.md`, `CHANGELOG.md`; `site/src/curated/{skills/tribunal,commands/tribunal,agents/tribunal-lens-reviewer}.md`; `site/test/generator/lens-pages.test.ts`, `site/test/reference-sidebar.test.ts`, `site/test/content/trust-policy-claims.test.ts`; `.github/fixtures/tribunal/qualification/`; `.codearbiter/reports/2026-10-05-tribunal-vnext-qualification.md`; this plan and spec | Core/surface/package generators and checks, routing/resource closure, relevant site tests/build, focused complete Tribunal suite; actual blind incumbent/candidate comparison followed by offline score; exact-head hosted CI after push | Complete shipped projections, existing URL compatibility, honest benchmark and release metadata | AC-10–11, AC-19–26, AC-29–31, AC-34, AC-36–38 | T-01, T-02, T-03, T-04, T-05 | ACCEPTED |

The first functional slice is T-01 through T-03 plus T-05: source-safe resumable
audits with modern review and verification contracts. T-04 and T-06 supply the
required qualification and distribution closure; this PR is not complete until
all six tasks pass. There is no dependency cycle, uncovered criterion, or task
without a criterion.

## Verification boundaries

`tech-stack.md` states: "There is **no coverage tooling for the Python hooks or
build tools** (`core/pysrc/*.py`, `plugins/*/hooks/*.py`, `.github/scripts/*.py`,
`tools/*.py`)." Use that documented exemption with behavioral obligations and
focused fault/mutation evidence; do not invent a numeric Python coverage result.
Generated prose uses contract review and projection checks. CI owns exhaustive
platform checks. Model quality is measured separately from deterministic tests.

Mechanical `uncovered-intent` against the approved spec returned no uncovered
items. Negative completeness review: passing only card-presence tests would
still leave resume and actual detection behavior unproven; T-01/T-05 exercise
real source and lifecycle changes, and T-04/T-06 require captured blind reviews.
No additional missing in-scope criterion was identified.

## Evidence ledger

S1 (T-01 through T-03) accepted on 2026-10-05 after independent spec review,
fresh coordinator verification, and corrected security/coverage review. The
three original findings remain in review history and are all resolved; the
corrected triage accounts for two DONE/PASS units and no outstanding findings.

| Task | Target-red and corrected behavior | Fresh coordinator verification | Independent result |
| --- | --- | --- | --- |
| T-01 | Original run/source regressions failed before implementation. Declared ignored evidence correction produced five target failures; writer-guard mutation now fails all four persisted operations. | 26 tests PASS, 27.927s; helper `0d2127afc2277bb5d57b5dc058d7ef906c99ce215617d6c083de0963e1f1f4c2` | Full spec review plus correction PASS. Security independently reproduced declared-evidence refusal; coverage independently killed the stale-write mutation. |
| T-02 | Inert extraction and profiles target-red; real signed-history verifier regression failed before `--no-show-signature`, and removing that fix fails again. | 24 tests PASS, 9.090s; helper `ae84751a3f3c8b4c454b499eb3b031ba16ff4e865b7387f484b8e17ea0bc4347` | Full spec review plus correction PASS; security independently reran the original configured-verifier reproduction. |
| T-03 | Fourteen contract tests exposed 39 old-contract assertion failures before the thirteen cards/shared references were updated. | 14 tests PASS, 0.010s; all 13 cards read independently and 29 resource links resolved | Spec and combined S1 security/coverage PASS. Existing card names and URLs retained. |

T-04 accepted after corrected independent spec, security and coverage review:
fresh coordinator 13 tests PASS (0.475s). The two original HIGH findings are
resolved: exception records now bind both adjudications, and isolated tests kill
both previously masked safeguard mutations. Canonical crypto/secret review also
passed. Corrected triage has three DONE/PASS units and no outstanding findings;
the earlier failed security attempt remains history, superseded by the actual
completed review. Frozen corpus and blind packet remain unchanged.

T-05 accepted after final independent spec and quality review, with two DONE/PASS
units and no findings. Fresh coordinator verification: 10 workflow tests PASS
(12.281s), six rendered surface tests PASS (1.172s), and a separate 19-operation
CLI exercise PASS. Coverage independently killed an omitted-verification
forwarding fault. The final CLI is
`0dc8482472f542e1373a1ba2f0c1f996699e97f8fd264516afa75d00bf7c747e`.
The final review binding supersedes the earlier context selection while retaining
that history. Status-only plan updates do not alter reviewed implementation bytes.

T-06 accepted after independent spec review and the completed dependency and
coverage reviews. Final triage accounts for two DONE/PASS units, no findings and
no incomplete results. The actual incumbent/candidate reviews and independent
adjudications are retained. Both verified all twenty seeded defects and flagged
none of twenty clean controls; the critical-regression gate is clear. This is
parity on a small synthetic corpus, not improved general detection accuracy.

Fresh coordinator checks passed: 87 Tribunal tests, 34 rebuilt-host usage tests,
post-correction card/workflow/surface tests, all three generator parity checks,
resource closure, 32 site tests, typecheck, build and 34,976 internal links.
Coverage independently reproduced the comparison and verified the retained
fresh-launch records and exact resource-notation delta. The qualification report
records the evidence and its limits. Exact-head hosted CI remains a separate
pre-merge requirement after push, not local implementation acceptance.

Commit-time provenance healing is limited to the changed release manifests and
changelogs. Release-target paths/roles remain valid; the code-map's three plugin
version annotations follow the reviewed manifests. Only those inspected claims
and their selected provenance records are refreshed.

The T-06 exact path set now names the three existing site test files needed for
roster/link/privacy closure. This is a verification-method refinement within
the approved distribution scope, with no additional product requirement.

T-06 packaging verification found 50 nested Codex resource links. Its bounded
correction owns only the offending canonical Tribunal link notation plus regenerated
outputs; reviewer rules, schemas and helper behavior do not change. Existing reference
validation supplies the failing reproduction and required green result. The earlier
component reviews and actual captured model outputs remain historical evidence.
