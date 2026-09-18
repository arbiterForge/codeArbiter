# Structured-artifact default rollout implementation plan

## Source and execution boundary

Source: `.codearbiter/specs/structured-artifact-default-rollout.md`, approved by
the user on 2026-09-17 and amended at the user's direction to use one PR.

Recorded deviations: the approved one-PR sequence explicitly departs from
ADR-0037's qualify-before-default ordering until post-merge package read-back
completes, and the qualified preassembled Pi npm tarball explicitly departs from
ADR-0029's same-package invariant while the Git-tag package remains a supported
partial installation. Neither deviation permits a full-readiness claim before
the required receipts pass.

This plan implements and pre-publication-qualifies one release cohort. Actual
Claude/Codex/Pi publication and exact published-package read-back happen after
merge. The PR may become merge-ready when every task below is `ACCEPTED`; the
rollout may be called fully ready only after the release workflow emits and the
maintainer accepts all three immutable read-back receipts.

The intent backstop returned no findings. Negative completeness review answer:
if every criterion passed, no default-path consumer, package, authority,
human-review, rollback, or no-growth obligation would remain broken. The only
remaining event would be execution of the already-tested post-merge publication
and read-back gate, which AC-04 and AC-10 explicitly retain as external evidence.

## Acceptance-criterion ledger

- **AC-01 — Default pair creation.** Given a clean initialized repository and a
  normal qualified installation of any governance host, starting a new feature
  or sprint creates a validated `.codearbiter/specs/<slug>.html` and
  `.codearbiter/plans/<slug>.html` pair through the installed engine, and creates
  no Markdown authority for that pair.
- **AC-02 — Legacy authority isolation.** Given an existing Markdown spec/plan
  pair, resume, proof, finalization, and worktree planning continue to use that
  exact pair without automatic conversion; an explicit reviewed migration is
  the only operation that can replace its authority with HTML.
- **AC-03 — Partial-install failure boundary.** Given no payload, a corrupt
  payload, an unsupported advertised cell, or a manifest/binary identity
  mismatch, new HTML creation and existing HTML mutation fail before writing
  with a bounded repair diagnostic, while an unrelated existing Markdown
  workflow remains usable.
- **AC-04 — Release-owned payload.** The exact PR head assembles and
  cold-installs every host/platform package only from native-qualified candidates
  bound to that commit, protected CI workflow/run identity, platform, manifest,
  binary digest, and named test receipts; missing, extra, stale, cross-commit,
  or unqualified candidates block merge or publication. After merge, each exact
  published cohort package is installed and read back against those identities
  before full rollout readiness is asserted.
- **AC-05 — Complete consumer closure.** The authoritative consumer inventory
  and an independent repository search agree that every live spec/plan producer
  and reader on the default path is either HTML-capable or explicitly
  legacy-only, with no pending/default-path closure classification and no
  untracked public or startup-loaded surface.
- **AC-06 — Authority fidelity.** User, SMARTS, reviewer, task-state,
  verification, and acceptance transitions consumed by the HTML path are derived
  from the existing host authority boundaries and exact artifact identities;
  document text, checkboxes, status words, digests, or caller-supplied labels
  cannot manufacture or widen authority.
- **AC-07 — Installed-host workflow and resume.** A clean installed-host run
  completes spec creation, plan binding, task start, interruption, process
  recreation, reconciliation, redispatch, verification, review, atomic
  acceptance, commit proof, and finalization against one HTML pair without
  reading a shadow Markdown ledger or relying on repository/PATH/Go/network
  fallback.
- **AC-08 — Human review qualification.** Exact generated HTML bytes pass the
  declared native browser matrix for desktop, compact, print, doubled text,
  keyboard/focus, overflow, local-only loading, and automated accessibility
  checks; unsupported browser or accessibility claims remain explicit rather
  than inferred.
- **AC-09 — Rollback and upgrade safety.** The selected production-repository
  pilot demonstrates clean install or upgrade, normal HTML work,
  interruption-safe recovery, rollback that stops new dispatch, and exact
  preservation of evidence and prior legacy bytes; downgrade alone never
  reinterprets HTML as Markdown.
- **AC-10 — Activation and surface guard.** The one-PR activation change is
  rejected unless every pre-publication portion of criteria 1–9 and required
  exact-head CI are current and green and the post-merge publication-evidence
  deviation has formal rollout acceptance. Generated parity holds, the public
  command/agent/tool/top-level skill/startup-schema baselines do not grow, and
  `--farm` remains disabled. Merge alone is not a full-readiness assertion:
  exact published-package read-back for all three hosts closes the rollout,
  while any failure records a blocker and activates the stop/rollback path.

## Ordered task table

| ID | Work | Exact paths | Verification | Maps to | Covers | Depends on | Status |
|---|---|---|---|---|---|---|---|
| T-01 | Make new full-lane feature and sprint spec creation select installed HTML while preserving small-lane behavior. | `.github/scripts/test_artifact_authoring.py`; `core/pysrc/_artifactlib.py`; `core/surface/includes/artifacts.md`; `core/surface/commands/feature.md`; `core/surface/SPRINT.md`; `core/surface/skills/brainstorming/SKILL.md` | `python .github/scripts/test_artifact_authoring.py` | TDD obligation AC-01 default spec creation | AC-01, AC-03 | none | ACCEPTED |
| T-02 | Make plan creation bind to the HTML spec and prevent a shadow Markdown plan. | `.github/scripts/test_artifact_authoring.py`; `core/pysrc/_artifactlib.py`; `core/surface/skills/writing-plans/SKILL.md`; `core/surface/skills/tdd/SKILL.md` | `python .github/scripts/test_artifact_authoring.py` | TDD obligation AC-01 paired plan creation | AC-01, AC-06 | T-01 | ACCEPTED |
| T-03 | Preserve exact-format discovery and resume for existing Markdown and HTML pairs. | `.github/scripts/test_artifact_workflow.py`; `core/pysrc/_artifactlib.py`; `core/surface/commands/feature.md`; `core/surface/SPRINT.md`; `core/surface/skills/finishing-a-development-branch/SKILL.md`; `core/surface/skills/using-git-worktrees/SKILL.md` | `python .github/scripts/test_artifact_workflow.py` | TDD obligation AC-02 authority isolation | AC-02, AC-07 | T-02 | ACCEPTED |
| T-04 | Close execution, review, acceptance, commit-proof, finalization, and process-recreation consumers on the typed protocol. | `.github/scripts/test_artifact_workflow.py`; `core/pysrc/_artifactlib.py`; `core/surface/skills/executing-plans/SKILL.md`; `core/surface/skills/subagent-driven-development/SKILL.md`; `core/surface/skills/commit-gate/SKILL.md`; `core/surface/skills/finishing-a-development-branch/SKILL.md` | `python .github/scripts/test_artifact_workflow.py` | TDD obligations AC-06 authority and AC-07 end-to-end resume | AC-06, AC-07 | T-03 | ACCEPTED |
| T-05 | Prove missing/corrupt/unsupported payload failures occur before writes while legacy-only paths remain usable. | `.github/scripts/test_artifact_bridge.py`; `.github/scripts/test_artifact_package.py`; `core/pysrc/_artifactlib.py`; `core/surface/includes/artifacts.md` | `python .github/scripts/test_artifact_bridge.py && python .github/scripts/test_artifact_package.py` | TDD obligation AC-03 fail-closed capability | AC-03 | T-02 | ACCEPTED |
| T-06 | Add artifact capability and invalid-artifact diagnostics without eager schema loading. | `.github/scripts/test_artifact_consumers.py`; `.github/scripts/test_readinjectlib.py`; `plugins/ca/hooks/tests/test_doctor.py`; `core/pysrc/_readinjectlib.py`; `core/pysrc/doctor.py`; `core/surface/commands/status.md`; `core/surface/commands/doctor.md` | `python .github/scripts/test_artifact_consumers.py ArtifactConsumerClosureTest.test_consumer_closure ArtifactConsumerClosureTest.test_diagnostic_readers_are_on_demand_and_schema_free ArtifactConsumerClosureTest.test_status_and_doctor_define_bounded_artifact_diagnostics ArtifactConsumerClosureTest.test_unknown_live_reader_negative_control && python .github/scripts/test_readinjectlib.py && python -m unittest plugins.ca.hooks.tests.test_doctor`; full generated-parity consumer suite remains the T-17 hard gate | TDD obligations AC-03 diagnostics and AC-05 accounted readers | AC-03, AC-05 | T-03, T-05 | ACCEPTED |
| T-07 | Define a create-only promotion receipt that binds package payload bytes to exact native qualification inputs and rejects drift. | `.github/scripts/test_artifact_package.py`; `tools/build-host-packages.py`; `tools/install-artifact-payload.py` | `python .github/scripts/test_artifact_package.py` | TDD obligation AC-04 provenance-bound package assembly | AC-04 | T-05 | ACCEPTED |
| T-08 | Make CI assemble, retain, and cold-execute the complete exact-head host/package matrix needed by the release cohort. | `.github/scripts/test_ci_impact.py`; `.github/scripts/test_artifact_package.py`; `.github/requirements/artifact-conformance-py314.lock`; `.github/workflows/ci.yml`; `tools/build-artifacts.py`; `tools/build-host-packages.py` | `python .github/scripts/test_ci_impact.py && python .github/scripts/test_artifact_package.py` | TDD obligation AC-04 exact-head native package proof | AC-04, AC-10 | T-07 | ACCEPTED |
| T-09 | Carry the qualified payload through each normal Claude, Codex, and Pi package rather than an unused CI overlay. | `.github/scripts/test_artifact_package.py`; `.github/scripts/test_ci_impact.py`; `.github/scripts/check_codex_skill_resources.py`; `.github/scripts/test_codex_skill_resources.py`; `.github/scripts/check_codex_static_package.py`; `.github/scripts/test_codex_static_package.py`; `.github/workflows/ci.yml`; `plugins/ca/helpers/artifacts/**`; `plugins/ca-codex/helpers/artifacts/**`; `plugins/ca-pi/helpers/artifacts/**`; `tools/build-host-packages.py`; `tools/install-artifact-payload.py`; `.claude-plugin/marketplace.json`; `.agents/plugins/marketplace.json`; `package.json` | `python .github/scripts/test_artifact_package.py && python .github/scripts/test_ci_impact.py && python .github/scripts/test_codex_static_package.py && python .github/scripts/test_codex_skill_resources.py && python .github/scripts/test_pi_package.py` | TDD obligation AC-04 normal-channel payload closure | AC-04 | T-08 | ACCEPTED |
| T-10 | Gate release publication on the exact CI payload and retain per-target published-package identity/read-back receipts. | `.github/scripts/test_release_workflow.py`; `.github/scripts/test_artifact_package.py`; `.github/scripts/test_pi_package.py`; `.github/scripts/_npm_publishlib.py`; `.github/workflows/release.yml`; `.github/workflows/npm-publish.yml`; `.github/actions/publish-release/action.yml`; `.codearbiter/release-targets.md` | `python .github/scripts/test_release_workflow.py && python .github/scripts/test_artifact_package.py && python .github/scripts/test_pi_package.py` | TDD obligations AC-04 publication/read-back and AC-10 rollout stop | AC-04, AC-10 | T-09 | ACCEPTED |
| T-11 | Prove approval, SMARTS, task-state, verification, and reviewer inputs cannot be forged through artifact text or caller labels. | `.github/scripts/test_artifact_workflow.py`; `core/artifacts/internal/authority/receipt.go`; `core/artifacts/internal/operations/lifecycle.go`; `core/artifacts/internal/operations/engine_test.go` | `python .github/scripts/test_artifact_workflow.py && go test -buildvcs=false ./...` from `core/artifacts` | TDD obligation AC-06 authority fidelity | AC-06 | T-04 | ACCEPTED |
| T-12 | Exercise the complete installed-host HTML workflow for Claude, Codex, and Pi from their package roots without development fallbacks. | `.github/scripts/test_artifact_workflow.py`; `.github/scripts/test_consumer_smoke.py`; `.github/workflows/ci.yml`; `docs/artifacts/consumer-inventory.json` | `python .github/scripts/test_artifact_workflow.py && python .github/scripts/test_consumer_smoke.py` | TDD obligation AC-07 installed-host workflow | AC-07 | T-09, T-11 | ACCEPTED |
| T-13 | Add the declared native browser, responsive, print, keyboard/focus, local-only, and automated accessibility matrix over exact rendered bytes. | `site/test/browser/artifact-review.spec.ts`; `site/playwright.config.ts`; `.github/workflows/ci.yml`; `docs/artifacts/design/original-review2/tests/browser_review.py`; `docs/artifacts/browser-qualification.json` | `npm --prefix site run test:browser -- artifact-review.spec.ts` | TDD obligation AC-08 human-review qualification | AC-08 | T-08 | ACCEPTED |
| T-14 | Add upgrade, interruption, dispatch-stop, downgrade refusal, and exact-byte rollback cases to the selected production-repository pilot. | `.github/scripts/test_artifact_workflow.py`; `.github/scripts/test_artifact_package.py`; `docs/artifacts/DEFAULT-ROLLOUT-PILOT.json`; `docs/artifacts/migration-and-recovery.md` | `python .github/scripts/test_artifact_workflow.py && python .github/scripts/test_artifact_package.py` | TDD obligation AC-09 rollback and upgrade safety | AC-09 | T-12 | ACCEPTED |
| T-15 | Close the authoritative consumer inventory and independent search without reclassifying farm or future artifact kinds. | `.github/scripts/test_artifact_consumers.py`; `docs/artifacts/consumer-inventory.json`; `docs/artifacts/ABSORPTION-REVIEW.md` | `python .github/scripts/test_artifact_consumers.py` | TDD obligation AC-05 complete consumer closure | AC-05, AC-10 | T-06, T-12, T-14 | ACCEPTED |
| T-16 | Flip the canonical rollout declaration only after package, workflow, browser, pilot, and inventory gates are present; keep farm disabled. | `.github/scripts/test_artifact_authoring.py`; `.github/scripts/test_artifact_consumers.py`; `core/surface/commands/feature.md`; `core/surface/SPRINT.md`; `core/surface/skills/brainstorming/SKILL.md`; `core/surface/skills/writing-plans/SKILL.md`; `docs/artifacts/consumer-inventory.json` | `python .github/scripts/test_artifact_authoring.py && python .github/scripts/test_artifact_consumers.py && python .github/scripts/test_artifact_farm.py` | TDD obligations AC-01 activation and AC-10 farm/surface guard | AC-01, AC-10 | T-10, T-13, T-15 | ACCEPTED |
| T-17 | Regenerate all host adapters from canonical sources and prove byte parity and unchanged public/startup surface. | `plugins/ca/**`; `plugins/ca-codex/**`; `plugins/ca-pi/**`; `package.json`; `README.md`; `CHANGELOG.md`; `plugins/ca-codex/CHANGELOG.md`; `plugins/ca-pi/CHANGELOG.md` | `python tools/build-surface.py --check && python tools/sync-core.py --check && python .github/scripts/test_artifact_surface.py` | TDD obligation AC-10 generated and no-growth parity | AC-05, AC-10 | T-16 | ACCEPTED |
| T-18 | Reconcile final documentation and evidence disposition, explicitly separating merge-ready implementation from post-merge published read-back. | `docs/artifacts/ABSORPTION-REVIEW.md`; `docs/artifacts/SPEC-COMPLIANCE.md`; `docs/artifacts/SPEC-COMPLIANCE.json`; `docs/artifacts/PLAN-STATUS.json`; `docs/artifacts/PROTOCOL.md`; `docs/artifacts/spec-and-plan-format.md`; `.codearbiter/tech-stack.md` | `python .github/scripts/test_artifact_surface.py && python .github/scripts/test_artifact_consumers.py && python .github/scripts/test_artifact_package.py && python .github/scripts/test_artifact_workflow.py` | TDD obligation AC-10 evidence-backed activation disposition | AC-04, AC-05, AC-08, AC-09, AC-10 | T-13, T-14, T-17 | ACCEPTED |

## Dependency order and batches

- **Batch 1 — MVP workflow slice:** T-01 through T-04. This is the minimal
  contiguous slice that creates and resumes an HTML pair through the existing
  premium feature/sprint workflow. It is not independently releasable because
  packaging remains absent.
- **Batch 2 — capability and package boundary:** T-05 through T-10.
- **Batch 3 — authority and qualification:** T-11 through T-14.
- **Batch 4 — activation and reconciliation:** T-15 through T-18.

There are no dependency cycles. The shippable MVP is the complete T-01 through
T-18 sequence because the approved contract forbids enabling a workflow whose
normal packages, consumers, and qualification are incomplete. Batch 1 is the
functional MVP slice used for checkpointing; it is not rollout permission.

## Bijection proof

| Criterion | Covering tasks |
|---|---|
| AC-01 | T-01, T-02, T-16 |
| AC-02 | T-03 |
| AC-03 | T-01, T-05, T-06 |
| AC-04 | T-07, T-08, T-09, T-10, T-18 |
| AC-05 | T-06, T-15, T-17, T-18 |
| AC-06 | T-02, T-04, T-11 |
| AC-07 | T-03, T-04, T-12 |
| AC-08 | T-13, T-18 |
| AC-09 | T-14, T-18 |
| AC-10 | T-08, T-10, T-15, T-16, T-17, T-18 |

Every AC has at least one task. Every task advances at least one AC. No farm
promotion, future artifact kind, mass migration, new public surface, database,
runtime plugin loader, or eager schema was added to the task set.

## Post-merge release-completion evidence

After merge, the existing release path publishes the declared cohort. For each
host, retain the tested release workflow's immutable package/read-back receipt
and compare its tag, commit, package version, payload manifest, native platform,
and binary digest to AC-04. Until all three pass, report the implementation as
merged with rollout qualification incomplete. This evidence step does not amend
task status or retroactively claim it existed at PR review time.
