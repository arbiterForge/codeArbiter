# Independent review of root implementation handoff

**Reviewer:** native/storage/release cross-review agent.  
**Source:** arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf.  
**Disposition:** Three material corrections identified and sent to the root author; the root author acknowledged all three. One Markdown presentation correction was also sent. This review is source analysis, not CI or release execution.

## Reviewed completely

- handoff-work/docs/BRANCH-AND-RELEASE.md
- handoff-work/docs/PROGRAM.md
- handoff-work/docs/TEST-AND-QUALIFICATION.md
- handoff-work/docs/ADR-PROPOSALS.md
- handoff-work/root-tasks.json

Actual source reread for the concerns below: payload_version_gate.py (complete), check_auto_release_candidate.py (complete), codeql.yml (complete), ADR-0040/0044 (complete), release-targets.md (complete), and the relevant CI, docs, release, publication action and Pi release-guard functions. Prior full release/CI audit coverage remains in audit-work/release-ci-read-files.txt.

## CR-01 — The integration candidate policy must cover Pi's separate guard

**Severity:** medium; direct implementability gap in P-01.

The root plan originally named payload_version_gate.py as the candidate-policy implementation owner without explicitly including tools/build-host-packages.py. The former deliberately excludes Pi. CI runs a separate Pi guard:

    python tools/build-host-packages.py --check --release-guard-base "$BASE_COMMIT"

validate_pi_release_advance requires strict advancement, regenerated root metadata, a changed changelog and a heading newly introduced relative to the supplied base. Merely permitting an unchanged untagged candidate in payload_version_gate.py would leave repeated Pi child PRs failing the separate guard.

**Correction:** Add the Pi owner and the actual CI caller to P-01. Define the same narrowly scoped integration policy for both owners, preserving Pi's manifest/root synchronization and meaningful changelog binding. Test repeated child changes against an integration base already containing the candidate heading, plus wrong-base, claimed-tag and final-main strict cases. An exception only to the SemVer comparison is insufficient if heading/root-change requirements still compare against the immediate integration base.

**Evidence:**

- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:.github/scripts/payload_version_gate.py — module contract and GATED_MANIFESTS.
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:.github/workflows/ci.yml — version-bump-pi, lines 3082–3108.
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:tools/build-host-packages.py — validate_pi_release_advance and pi_release_guard, lines 1962–2055.

**Author response:** acknowledged; adding the explicit Pi guard owner and coverage.

## CR-02 — Prepublication readiness must not depend on completed publication

**Severity:** medium; circular completion risk.

PROGRAM originally required every accepted task to be complete before promotion, while Q-02's readiness record bound a completed program task manifest. Q-03 includes actual external publication, final receipt and distribution readback. Those outcomes cannot be complete before the barrier allows the first external effect. The qualification document also includes release settlement as a layer, so a verifier that naïvely requires every listed scenario/task to be complete creates a deadlock.

**Correction:** Define three separate completion predicates:

| Predicate | Required content |
|---|---|
| INTEGRATION_QUALIFIED | Required implementation, documentation, migration and prepublication candidate tests complete on the integration candidate. |
| PREPUBLICATION_READY | Final exact source/build/package identities and every required prepublication qualification result verified; final external delivery tasks explicitly excluded from this predicate. |
| DISTRIBUTION_SETTLED | Actual per-target public/registry/channel effects, receipts and readbacks complete; includes Q-03 and final delivery obligations. |

The final program still requires distribution settlement. This changes sequencing, not scope. Test that absent prepublication evidence blocks, valid prepublication evidence admits the first effect, and missing postpublication receipt remains an incomplete but recoverable settlement state without making readiness impossible.

**Evidence:** Internal dependency and acceptance statements in the reviewed root documents/tasks; current publication action creates tag/draft/channel/npm/public Release effects and records final settlement later.

- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:.github/actions/publish-target/action.yml — external-effect sequence, lines 261–517.

**Author response:** acknowledged; introducing these three predicates and an explicit noncircular readiness test.

## CR-03 — Delayed readiness must preserve Pi's event/source provenance equality

**Severity:** medium; recovery/runbook implementability.

The proposed barrier can defer publication while exact installed qualification finishes. A later rerun/dispatch is not sufficient by itself for a new Pi npm publication. The current action requires event GITHUB_SHA to equal selected SOURCE_COMMIT before creating a new Pi tag/draft, and checks equality again immediately before npm publish. Manual dispatch selects the newest successful main push CI, which can be older than the event's main SHA.

**Correction:** Add the explicit delayed-readiness/main-advanced case. Retain equality and ADR-0044. If an original matching release event cannot publish the selected source, choose an eligible exact source/version as required, rebuild and requalify its actual bytes; never substitute a trusted-sha label, reuse mismatched qualification, or weaken provenance. Keep recovery of an already existing byte-identical npm version separate from new publication.

**Evidence:**

- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:.github/workflows/release.yml — source selection, lines 79–100.
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:.github/actions/publish-target/action.yml — pre-tag equality gate, lines 246–258; repeated publish gate, lines 414–426; registry/provenance verification, lines 430–463.
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:.codearbiter/decisions/0044-trusted-pi-npm-publication.md — exact intended-source identity and existing-version recovery requirements.

**Author response:** acknowledged; adding the fixture and runbook branch.

## Presentation correction

TEST-AND-QUALIFICATION.md originally omitted the Markdown separator row after the cross-owner scenario table header. Add the three-column separator so all 31 sequences render as a table. Sent to the author.

## Confirmed sound boundaries

The inspected source supports the handoff's description of current CI admission, main-only release admission, main-only Pages deployment, and the need for new integration-branch admission. The proposal correctly keeps branch qualification read-only, preserves merge-group checks and independent per-target recovery, distinguishes the final publication receipt from Pi provenance, and marks the major-specific readiness barrier as a new contract rather than existing behavior.

No additional material contradiction was found in the reviewed documents' preserved shared-store recovery boundary, scoped semantic waiting, historical evidence retention or pending progress/evidence decision.

## Validation limits

No repository files were modified, no CI runs were initiated and no external settings/releases were changed. No exact installed package or live npm provenance was independently exercised in this review. Effective GitHub branch rules, trusted-publisher account settings, actual integration workflow execution and final-artifact readiness remain implementation/qualification evidence to obtain. Root-author acknowledgements are not proof that revised prose or new code has been validated; the final corpus assembly must include the corrections and validate its task predicates.

