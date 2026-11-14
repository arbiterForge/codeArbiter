# Complete implementation task ledger

All 82 tasks are PLANNED. This file carries every owner instruction, preserved invariant, acceptance case, source reference, migration rule and rollback note. The normalized cross-owner ordering below supersedes the raw owner ledgers only for dependency/decision identifiers and program status; it does not discard their implementation details.

Completion dependencies allow local work to start while final integration is pending. Coordination links do not silently become hard stops. Q-03 actual publication is excluded from PREPUBLICATION_READY and remains mandatory for final settlement.

| Task | Owner | Finding IDs | Start prerequisites | Completion prerequisites | Decision |
|---|---|---|---|---|---|
| P-00 | release-and-integration |  |  |  |  |
| P-01 | release-and-integration |  | P-00 |  |  |
| P-02 | integration-architect |  | P-00 |  |  |
| BUILD-G01 | packaging | SF13 | P-02 |  |  |
| DIST-M01 | packaging | SF04 | P-02 |  |  |
| DIST-M02 | packaging | SF15 | P-02 |  |  |
| FARM-R01 | farm | SF05 | P-02 |  |  |
| FARM-R02 | farm | SF06 | P-02 |  |  |
| FARM-R03 | farm | SF07 | P-02 |  |  |
| HW-01 | hooks-workflows | HOOK-F01 | P-02 |  |  |
| HW-02 | hooks-workflows | HOOK-F02 | P-02 |  |  |
| HW-03 | hooks-workflows | HOOK-F03 | P-02 |  |  |
| HW-05 | hooks-workflows | HOOK-F05 | P-02 |  |  |
| HW-07 | hooks-workflows | W-F02, HOOK-B01 | P-02 |  |  |
| HW-09 | hooks-workflows | W-F03 | P-02 |  | D-HIGH |
| HW-10 | hooks-workflows | W-F04, HOOK-B04 | P-02 |  |  |
| HW-17 | hooks-workflows | W-F06, HOOK-B03 | P-02 |  |  |
| HW-18 | hooks-workflows | W-F07 | P-02 |  |  |
| HW-19 | hooks-workflows | W-F08 | P-02 |  |  |
| HW-21 | hooks-workflows | W-F09 | P-02 |  |  |
| HW-22 | hooks-workflows | GEN-F01 | P-02 |  |  |
| HW-23 | hooks-workflows | GEN-F02 | P-02 |  |  |
| HW-24 | hooks-workflows | GEN-B01 | P-02 |  |  |
| HW-26 | hooks-workflows |  | P-02 |  |  |
| NT-01 | native |  | P-02 |  |  |
| PI-D01 | pi | SF01 | P-02 |  |  |
| PI-L01 | pi | SF02 | P-02 |  |  |
| PI-L02 | pi | SF03 | P-02 |  |  |
| R-01 | release-and-integration | C-F01 | P-02 |  |  |
| R-02 | release-and-integration | C-F02 | P-02 |  |  |
| R-03 | release-and-integration | C-F03 | P-02 |  | D-GOV-PRETAG |
| R-05 | release-and-integration | C-F05 | P-01, P-02 |  |  |
| R-06 | release-and-integration | C-F06, C-F07 | P-02 |  |  |
| R-07 | release-and-integration | C-F08 | P-02 |  |  |
| SBX-C01 | sandbox | SF08, SW-F06 | P-02 |  |  |
| SBX-C02 | sandbox | SF09 | P-02 |  |  |
| SBX-D02 | sandbox | SW-F02, SW-F03 | P-02 |  |  |
| SBX-D04 | sandbox | SW-F07, SW-F08 | P-02 |  |  |
| SITE-U01 | site | SF11 | P-02 |  |  |
| SITE-U02 | site | SF16 | P-02 |  |  |
| T-01 | measurement-tools | T-F01, T-F02, T-F03, T-F04 | P-02 |  |  |
| BUILD-G02 | packaging | SF14 | P-02, HW-21 |  |  |
| HW-11 | hooks-workflows | W-F04, HOOK-B04 | HW-10, P-02 |  |  |
| HW-16 | hooks-workflows | W-F05, HOOK-B02 | HW-01, HW-02, P-02 |  |  |
| HW-20 | hooks-workflows | W-F08, W-F03 | HW-09, P-02 |  |  |
| HW-25 | hooks-workflows | HOOK-B05 | P-02 | DIST-M01 |  |
| NT-02 | native | N-F01 | P-02 | NT-01 |  |
| NT-03 | native | N-F02 | P-02 | NT-01 |  |
| NT-04 | native | N-F09 | P-02 | NT-01 |  |
| NT-05 | native | N-F10 | P-02 | NT-01 |  |
| NT-07 | native | N-F06 | P-02 | NT-01 |  |
| NT-08 | native | N-F08 | P-02 | NT-01 |  |
| NT-09 | native | N-F03, N-F04 | P-02 | NT-01 | D-PROGRESS |
| NT-10 | native |  | PI-D01, P-02 | NT-01 |  |
| NT-11 | native |  | P-02 | NT-01 |  |
| PI-C01 | pi | SF12 | PI-D01, P-02 |  |  |
| PI-D02 | pi | SF01 | PI-D01, P-02 |  |  |
| Q-02 | release-and-qualification |  | R-01, R-02, R-06, P-01, P-02 |  |  |
| R-04 | release-and-integration | C-F04 | R-01, P-02 |  |  |
| SBX-C03 | sandbox | SF10 | SBX-C02, P-02 |  |  |
| SBX-D01 | sandbox | SW-F01 | SBX-C01, P-02 |  |  |
| HOST-D01 | hooks-workflows | SW-F09 | P-02, HW-16 |  |  |
| HW-04 | hooks-workflows | HOOK-F04 | P-02 | NT-04 |  |
| HW-08 | hooks-workflows | W-F02, HOOK-B01 | HW-07, P-02 | NT-11 |  |
| HW-12 | hooks-workflows | W-F04, HOOK-B04 | HW-11, P-02 |  |  |
| NT-06 | native | N-F05, N-F07 | NT-03, P-02 | NT-01 |  |
| PI-D03 | pi | SF01 | PI-D01, PI-D02, P-02 |  |  |
| R-08 | release-and-integration | SX-F01 | R-01, R-04, P-02 |  |  |
| SBX-D03 | sandbox | SW-F04, SW-F05 | SBX-C03, P-02 |  |  |
| HW-13 | hooks-workflows | W-F04, HOOK-B04 | HW-12, P-02 |  |  |
| NT-12 | native |  | NT-01, NT-02, NT-03, NT-04, NT-05, NT-06, NT-07, NT-08, NT-09, NT-10, NT-11, P-02 |  |  |
| PI-D04 | pi | SF01 | PI-D01, PI-D02, PI-D03, P-02, NT-10 |  |  |
| PI-D05 | pi | SF01 | PI-D02, PI-D03, PI-D04, P-02 |  |  |
| HW-06 | hooks-workflows | W-F01 | P-02 | PI-D05 |  |
| HW-14 | hooks-workflows | W-F04, HOOK-B04 | HW-11, HW-12, P-02 | PI-D04, PI-D05 |  |
| PI-D06 | pi | SF01, SF12 | PI-D01, PI-D04, PI-D05, P-02 |  |  |
| G-01 | governance-and-docs |  | P-02 | BUILD-G01, BUILD-G02, DIST-M01, DIST-M02, FARM-R01, FARM-R02, FARM-R03, HOST-D01, HW-01, HW-02, HW-03, HW-04, HW-05, HW-06, HW-07, HW-08, HW-09, HW-10, HW-11, HW-12, HW-13, HW-14, HW-16, HW-17, HW-18, HW-19, HW-20, HW-21, HW-22, HW-23, HW-24, HW-25, NT-01, NT-02, NT-03, NT-04, NT-05, NT-06, NT-07, NT-08, NT-09, NT-10, NT-11, PI-C01, PI-D01, PI-D02, PI-D03, PI-D04, PI-D05, PI-D06, PI-L01, PI-L02, R-01, R-02, R-03, R-04, R-05, R-06, R-07, R-08, SBX-C01, SBX-C02, SBX-C03, SBX-D01, SBX-D02, SBX-D03, SBX-D04, SITE-U01, SITE-U02, T-01 |  |
| HW-15 | hooks-workflows | W-F04, HOOK-B04 | HW-13, HW-14, HW-26, P-02 |  |  |
| PI-D07 | pi | SF01 | PI-D01, PI-D02, PI-D03, PI-D04, PI-D05, PI-D06, PI-L01, PI-L02, DIST-M01, P-02 | HW-26 |  |
| HW-27 | hooks-workflows | HOOK-F01, HOOK-F02, HOOK-F03, HOOK-F04, HOOK-F05, HOOK-B01, HOOK-B02, HOOK-B03, HOOK-B04, HOOK-B05, W-F01, W-F02, W-F03, W-F04, W-F05, W-F06, W-F07, W-F08, W-F09, GEN-F01, GEN-F02, GEN-B01 | HW-01, HW-02, HW-03, HW-04, HW-05, HW-06, HW-07, HW-08, HW-09, HW-10, HW-11, HW-12, HW-13, HW-14, HW-15, HW-16, HW-17, HW-18, HW-19, HW-20, HW-21, HW-22, HW-23, HW-24, HW-25, HW-26, P-02 | P-01, NT-12, G-01 |  |
| Q-01 | qualification |  | BUILD-G01, BUILD-G02, DIST-M01, DIST-M02, FARM-R01, FARM-R02, FARM-R03, G-01, HOST-D01, HW-01, HW-02, HW-03, HW-04, HW-05, HW-06, HW-07, HW-08, HW-09, HW-10, HW-11, HW-12, HW-13, HW-14, HW-15, HW-16, HW-17, HW-18, HW-19, HW-20, HW-21, HW-22, HW-23, HW-24, HW-25, HW-26, HW-27, NT-01, NT-02, NT-03, NT-04, NT-05, NT-06, NT-07, NT-08, NT-09, NT-10, NT-11, NT-12, P-00, P-01, P-02, PI-C01, PI-D01, PI-D02, PI-D03, PI-D04, PI-D05, PI-D06, PI-D07, PI-L01, PI-L02, Q-02, R-01, R-02, R-03, R-04, R-05, R-06, R-07, R-08, SBX-C01, SBX-C02, SBX-C03, SBX-D01, SBX-D02, SBX-D03, SBX-D04, SITE-U01, SITE-U02, T-01 |  |  |
| Q-03 | release-manager |  | Q-01, Q-02, G-01, R-01, R-02, R-03, R-04, R-08, P-02 |  |  |

## P-00 · Establish the integration branch and evidence baseline

**Status:** PLANNED. **Owner:** release-and-integration.

**Implementation prerequisites:** .
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Phase

0

### Owner

release-and-integration

### Finding ids

None.

### Source paths

- .github/workflows/ci.yml
- .github/workflows/release.yml
- .github/workflows/docs.yml

### Implementation

- Verify the exact origin owner/login and repository; fetch current main and tags without resetting any worktree. Record the inspected source SHA and compare to the audit SHA.
- Create or resume major/state-contracts from an inspected base. If it already exists, inspect its commits and worktrees; never force-reset it. Preserve unrelated uncommitted work by using a clean worktree.
- Import this corpus under docs/state-contracts-major/ or an equivalent documented branch-owned planning directory. Preserve baseline audit bytes and their hashes. Record the user decisions and the unresolved SMARTS/disposition choices.
- Use short-lived child branches whose PR base is major/state-contracts. A single final promotion PR targets main only after the complete acceptance record is ready. No partial fixes from this program are merged/cherry-picked into main.
- Create an explicit checkpoint after every slice with branch/head, finished and remaining task IDs, test commands/results, unknown outcomes, and the next concrete action. Never substitute a chat assertion for repository evidence.
- Preserve intake specifications and audit as historical evidence. Initialize execution/progress.json and execution/CHECKPOINT.md from the provided templates; record actual completion, later decisions and any newly discovered required work there. Resume from actual Git plus these live records, not historical PLANNED labels.

### Tests

- Run packet validation; compare HEAD and audit baseline; inspect all existing branch/worktree changes before choosing a resume path.
- Exercise bootstrap instructions in a disposable clone, including pre-existing branch and dirty-worktree cases; they must not discard changes.

### Acceptance

- Correct authorized repository and branch recorded.
- All 70 finding IDs and 287 machine families accounted for; no implementation is marked complete at import.
- No main branch, tag, release, marketplace or Pages mutation during bootstrap.

### Rollback

- Retain the branch and imported evidence; remove only a newly created empty/disposable worktree after verifying it contains no unique work.


## P-01 · Admit the integration branch to real CI without publication

**Status:** PLANNED. **Owner:** release-and-integration.

**Implementation prerequisites:** P-00.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Phase

0

### Owner

release-and-integration

### Finding ids

None.

### Source paths

- .github/workflows/ci.yml
- .github/workflows/docs.yml
- .github/workflows/codeql.yml
- .github/workflows/release.yml
- .github/scripts/payload_version_gate.py
- .github/scripts/check_auto_release_candidate.py
- tools/build-host-packages.py

### Implementation

- Extend the current ci workflow pull_request base-branch admission to major/state-contracts and add exact integration-branch push admission. Preserve main and the existing authorized branch entries. Add the planning/contract paths to push impact selection so policy-only program changes cannot skip required checks.
- Ensure integration push and final qualification can select all required domains and all six native platform/package cells, regardless of the latest small diff. A selective green child PR is not full program qualification.
- Extend docs validation and Pi security analysis to integration work while retaining explicit main-only Pages deployment and main-push release source checks. Do not grant branch/PR qualification npm, marketplace, release or Pages publication permissions.
- Handle payload-version checks explicitly: current helper compares payload changes to the PR base version, so reserving one future version does not by itself allow every child PR to keep that version. Introduce a narrowly scoped integration-candidate rule only for this branch, based on recorded main baseline plus current remote tags, synchronized manifests/changelogs and no publication. Final main/merge-group checks keep the normal strict advancement rule. Alternatively bump a fresh untagged development version per child change until the final major version; choose and record one supported policy rather than disabling the gate globally.
- Read effective branch rules and required checks through an authorized method. Unavailable administration evidence remains unavailable. Honor existing protection; do not claim a branch rule was installed merely because its YAML/test passed.
- Do not rely on a brand-new manual-only workflow on a non-default branch. A branch push workflow can bootstrap validation; verify the actual run and source SHA. Audit workflow_run consumers so a non-main run cannot reach privileged publication.
- Implement the integration candidate rule in both actual owners: payload_version_gate.py for its admitted targets and tools/build-host-packages.py --release-guard-base for Pi. The general helper deliberately excludes ca-pi. Preserve Pi changelog advancement, generated root metadata equality, payload identity and tag checks. Do not assume prerelease suffixes are accepted by the current portable version grammar; test a supported numeric candidate policy.
- For same-candidate integration updates, evaluate the Pi newly introduced changelog heading and required metadata-change checks against the recorded main candidate baseline, not an immediate integration base already containing that heading. Retain meaningful current content synchronization; the normal final-main guard keeps its strict actual-base checks.

### Tests

- Event matrix: integration push, child PR to integration, final PR to main, merge_group, main push, fork PR, canceled run, policy-only diff and docs-rule-only diff.
- Validate all applicable jobs are selected; no required missing/skipped lane is accepted as full qualification.
- Negative checks prove integration/fork events cannot deploy Pages, publish npm, update marketplace refs or create Releases.
- Version tests: same untagged candidate with multiple child changes only in the declared integration scope; changed/claimed tag, wrong base, malformed version and main unchanged-version payload all reject.
- Two successive Pi child PRs under the same untagged candidate pass only under the recorded integration rule; stale Pi changelog/root metadata, published candidate tag and unchanged-version main promotion still fail.

### Acceptance

- Actual integration CI and docs validation runs are recorded for the branch SHA.
- Publication remains main-only and separately gated.
- Supported branch-version semantics have fixtures and a written owner; no global version-gate bypass.

### Rollback

- Revert only integration admission/candidate special handling on the integration branch; leave main/release protections intact. Preserve diagnostic evidence.


## P-02 · Freeze owner contracts and compatibility traces before extraction

**Status:** PLANNED. **Owner:** integration-architect.

**Implementation prerequisites:** P-00.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Phase

1

### Owner

integration-architect

### Finding ids

None.

### Source paths

- core/hosts.json
- core/artifacts/internal/operations/protocol.go
- core/artifacts/internal/operations/engine.go
- core/surface/command-routes.json

### Implementation

- Assign every machine family to its existing owner and an explicit disposition: contract extraction, defect repair, instruction correction, or preservation under existing conformance. Pure parsing helpers do not need a new runtime framework.
- Declare a shared outcome vocabulary while keeping progress, evidence, authority, delivery, containment and identity/generation independent. Use existing native schema/wire conventions until a versioned change is justified.
- Record observable command grammar, exit codes, host exceptions, operation IDs/replay, file output classes, authority provenance, remote-effect timing and unavailable states before changing them.
- Add a result/effect contract at real state/effect boundaries; generate repeated capabilities, accepted bounds, diagnostics and catalogs from their owner. Do not add a universal workflow gate or a global cross-product state enum.
- Link each baseline row to meaningful existing tests, a new sequence test, or a reviewed instruction/conformance check. A planned mapping is not coverage execution and a comment/substring test is not semantic proof.

### Tests

- Compare representative old/new traces on unchanged inputs, including refusal, partial commit, lost response, replay and cancellation.
- Check every family/row/finding is assigned without assigning every row a trivial implementation-mirroring test.
- A missing owner/output class or divergent generated capability fails conformance.

### Acceptance

- All machine families and transition rows have traceable owners and dispositions.
- Compatibility baseline and named intended behavior changes are recorded.
- No new ordinary-work approval ceremony.

### Rollback

- Keep new contracts additive until readers and consumers are qualified; revert projections independently while retaining existing durable history.


## BUILD-G01 · Stage and validate owned generated outputs before replacement

**Status:** PLANNED. **Owner:** packaging.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Cross-owner coordination


##### Record

**task id**

Q-01

**kind**

downstream-program-gate

**reason**

Validated generated candidate consumed by whole-program qualification.


### Finding ids

- SF13

### Source paths

- tools/build-surface.py
- tools/sync-core.py
- site/scripts/generator/generate.ts
- site/scripts/generate-academy.ts
- site/scripts/pagefind-build.ts
- site/scripts/pagefind-build.test.ts
- site/scripts/generate-academy.test.ts

### Source refs

- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:tools/build-surface.py
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:tools/sync-core.py
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:site/scripts/generator/generate.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:site/scripts/generate-academy.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:site/scripts/pagefind-build.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:site/scripts/pagefind-build.test.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:site/scripts/generate-academy.test.ts

### Proposed paths

None.

### Behavior change

A failed generation cannot silently leave a partial tree eligible for packaging; old complete output survives replacement where the owning filesystem layout supports it.

### Implementation steps

- Inventory each generator owned output root and late validation boundary; distinguish whole-root generation from projections mixed with handwritten files.
- Render into a fresh owned staging tree, validate complete content/schema/links there, and replace only owned outputs using the platform-appropriate safe promotion procedure.
- For mixed/manual trees where one atomic rename is impractical, use explicit manifest/staging validation and failure-as-unusable gates without deleting handwritten files.
- Fix Pagefind old-output removal before rename; retain prior complete index until promotion succeeds or expose failed output as unusable.
- Ensure package/release consumers reject failed/incomplete generation rather than trusting leftover files; rerun deterministic canonical input safely.

### Existing behavior to preserve

- Deterministic generated content, approved host differences, handwritten adapters and user-owned files.
- Do not introduce a distributed saga for every reversible local generator.

### Tests

**acceptance**

- Injected render/validate/rename failure preserves previous complete owned output or clearly blocks consumption of a partial projection.
- A clean rerun converges to the same canonical output; successful package uses one complete generation.

**rejection and failure**

- Foreign/symlinked target root, mixed ownership, failed rename and incomplete output cannot be marked build-ready.

**concurrency and interruption**

- Two builders targeting same root serialize/refuse safely; consumer never observes an advertised ready mixture.
- Interrupted staging cleanup affects only owned temporary paths.


### Completion evidence

- Targeted generator fault tests and complete build/packaging verification for changed output owners.
- Explicit manifest of handwritten versus generated surfaces.

### Rollback

- Restore previous complete output; keep canonical sources and owned staging for diagnosis when needed.
- Never wipe a mixed output root to make rollback easy.

### Claim delta

- Successful deterministic rendering is different from atomic multi-file publication.

### Adr actions

None.


## DIST-M01 · Unify supported native release-manifest shape across consumers

**Status:** PLANNED. **Owner:** packaging.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Cross-owner coordination


##### HW-25

**kind**

downstream-integration-no-hard-cycle

**use**

Consumes DIST-M01 for Python optional context_qualification compatibility; original audit finding HOOK-B05.


##### R-06

**kind**

contract-coordination

**use**

Exact package qualification/evidence semantics.


### Finding ids

- SF04

### Source paths

- plugins/ca/tools/farm.ts
- tools/build-host-packages.py
- tools/install-artifact-payload.py
- core/pysrc/_artifactlib.py
- .github/scripts/_contextverificationlib.py
- .github/scripts/_npm_publishlib.py
- plugins/ca/tools/farm.unit.test.ts

### Source refs

- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca/tools/farm.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:tools/build-host-packages.py
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:tools/install-artifact-payload.py
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/pysrc/_artifactlib.py
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:.github/scripts/_contextverificationlib.py
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:.github/scripts/_npm_publishlib.py
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca/tools/farm.unit.test.ts

### Proposed paths

None.

### Behavior change

Farm accepts and validates the supported context_qualification extension on production-qualified manifests without weakening binary identity and confinement checks.

### Implementation steps

- Define one versioned manifest contract and derive/conformance-test parsers across TS/Python packaging, installation and verification.
- Preserve exact required fields and supported optional-field validation; reject unknown versions/fields and malformed optional values according to the chosen schema.
- Keep binary digests, platform entry, protocol/schema compatibility and path ownership checks; accepting a sixth field is not a reason to skip validation.
- Create a final qualified package fixture with context_qualification and pass it through installed farm binary admission, not only candidate five-key construction.
- Coordinate HOOK-B05 and hosted publish verifier parsing so source/enriched manifest phases remain distinct.

### Existing behavior to preserve

- Five-key candidate manifests where valid; richer qualified production phase; exact artifact provenance and host differences.

### Tests

**acceptance**

- Both valid candidate and qualified production shapes parse at their intended phases; final installed qualified package reaches the pinned engine.

**rejection and failure**

- Unknown field/version, malformed context entry, wrong platform/hash/path/protocol and stale qualification fail with precise stage reasons.

**concurrency and interruption**

- No shared mutable parser state; package replacement between observation and execution is detected by existing identity protections.


### Completion evidence

- Cross-language schema fixtures plus exact qualified-artifact farm admission receipt.
- No claim that an already published package failed unless its exact bytes were tested.

### Rollback

- Revert readers and producer schema together or keep old-format packaging on integration; never drop qualification metadata just to pass farm.
- Retain old artifacts unchanged.

### Claim delta

- Candidate versus qualified manifest is a versioned contract, not two unrelated key-set guesses.

### Adr actions

None.


## DIST-M02 · Preserve host promotion differences and recover uncertain pushes by observation

**Status:** PLANNED. **Owner:** packaging.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Cross-owner coordination


##### R-01

**kind**

contract-coordination

**use**

Shared publication completion/receipt-only recovery contract.


##### Q-03

**kind**

downstream-program-gate

**use**

Final observed distribution and exact publication bytes.


### Finding ids

- SF15

### Source paths

- tools/promote-claude-marketplace.py
- tools/promote-codex-marketplace.py
- .github/actions/publish-target/action.yml

### Source refs

- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:tools/promote-claude-marketplace.py
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:tools/promote-codex-marketplace.py
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:.github/actions/publish-target/action.yml

### Proposed paths

None.

### Behavior change

Both promoters expose exact ref observations and uncertain outcomes; malformed current-channel version cannot silently skip a monotonicity rule.

### Implementation steps

- Retain deterministic immutable distribution commits and same-version drift refusal.
- Keep Codex preexisting immutable-tag requirement separate from Claude combined tag/channel flow; do not force identical sequencing.
- Represent current channel version as known/absent/unreadable/malformed. If monotonicity is required, unknown is refusal rather than comparison skipped.
- After any uncertain push, use fresh observations of remote tag/channel/ref identity before retry; same desired ref is observed success, conflicting ref requires scoped reconciliation.
- Integrate root publication-receipt recovery so public effects and final receipt failure are not conflated.

### Existing behavior to preserve

- Lease-protected channel updates, immutable tags, independent Claude/Codex distribution semantics and optional npm identity where applicable.

### Tests

**acceptance**

- Idempotent rerun after successful but unacknowledged push reads desired exact refs and avoids duplicate publication.
- Each host retains its intended prerequisite sequencing.

**rejection and failure**

- Same-version content drift, malformed current version, downgrade, stale lease, wrong immutable tag or unknown readback cannot claim promotion complete.

**concurrency and interruption**

- Remote channel advances between fetch and push; push succeeds then response/readback fails; two promoters contend for one channel.


### Completion evidence

- Local disposable-remote tests with exact refs/commit IDs and uncertain-push scenarios; hosted candidate receipt links to final observed distribution.
- No published-artifact behavior claim from source helper tests alone.

### Rollback

- Do not rewrite immutable tags or force-reset a competing channel as rollback; observe and use approved new promotion/reversion procedure.
- Preserve successful remote effects and repair receipts separately.

### Claim delta

- Unknown remote observation differs from failed publication; host-specific flow differences remain intentional.

### Adr actions

None.


## FARM-R01 · Separate farm effect recovery from receipt repair and author retry

**Status:** PLANNED. **Owner:** farm.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Cross-owner coordination


##### HW-12

**kind**

contract-coordination

**use**

Selected-owner outcome reconciliation.


##### HW-13

**kind**

contract-coordination

**use**

Register durable harvest obligations at producer discovery.


##### T-01

**kind**

claim-propagation

**use**

Reporting-only farm diagnostics must not invent circuit-breaker cause or premium dispatch.


### Finding ids

- SF05

### Source paths

- plugins/ca/tools/farm.ts
- plugins/ca/tools/farm.test.ts
- plugins/ca/tools/farm-dist.test.ts
- core/surface/includes/farm.md
- tools/farm-first-pass.py
- core/surface/skills/subagent-driven-development/references/farm-dispatch.md

### Source refs

- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca/tools/farm.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca/tools/farm.test.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca/tools/farm-dist.test.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/surface/includes/farm.md
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:tools/farm-first-pass.py
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/surface/skills/subagent-driven-development/references/farm-dispatch.md

### Proposed paths

None.

### Behavior change

A final report failure preserves completed commits/merges and offers read-only reconciliation/receipt repair; a new run cannot silently truncate or replace old run evidence.

### Implementation steps

- Create run IDs exclusively; reject existing FARM_RUN_ID unless an explicit verified recovery mode is selected. Avoid recursive existing-directory adoption and stream truncation.
- Persist bounded task/worktree/branch/base/integration commit and tree identities around owned effects; distinguish author outcome, merge outcome, cleanup and report publication.
- Add recover-receipt path that re-observes refs and reconstructs only supportable reporting without scheduling authors, resetting integration or replacing task branches.
- Require explicit new attempt identity and resource preconditions for author retry. Unknown branch observations remain unknown.
- Correct installed farm guidance and diagnostic tools so report exit 3 does not instruct immediate redispatch or mislabel every abort as circuit breaker/premium reroute.
- Scope conflict holds to dependent task/branch/integration resources; retain independent work.

### Existing behavior to preserve

- Existing branch/worktree containment, task/quality/mutation outcomes and anti-gaming heuristic evidence limits.
- A green task result is not a published-report receipt; a missing report is not evidence effects never happened.

### Tests

**acceptance**

- Inject report failure after successful commits/merge and recover truthful receipt without invoking author or resetting refs.
- Fresh run ID creates new evidence; existing run ID rejects without truncation.

**rejection and failure**

- Changed/missing/unreadable refs, reused identity, incompatible record schema or unverified cleanup cannot produce a false recovered-green receipt.
- No recovery automatically force-resets a user/other-task branch.

**concurrency and interruption**

- Crash before/after commit/merge/report write; concurrent recoverers; same run ID race; branch advances between observation and action.
- Dependent tasks pause while independent task evidence remains usable.


### Completion evidence

- Real disposable Git integration tests with before/after ref digests, author call counts and preserved logs.
- Updated agent instructions explicitly separate recover, inspect and new attempt.

### Rollback

- Keep new records and refs; disable mutating recovery mode if needed, retaining read-only diagnostics.
- Do not roll back by deleting successful commits or rewriting old reports as never executed.

### Claim delta

- Receipt repair is distinct from author redispatch; aborted cause and premium routing must be observed.

### Adr actions

- Durable effect observation/recovery ADR covers farm-specific refs and report ownership.


## FARM-R02 · Preserve containment outcomes through quality gate retries

**Status:** PLANNED. **Owner:** farm.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Finding ids

- SF06

### Source paths

- plugins/ca/tools/exec.ts
- plugins/ca/tools/farm.ts
- plugins/ca/tools/mutation.ts
- plugins/ca/tools/exec.test.ts
- plugins/ca/tools/farm.unit.test.ts
- plugins/ca/tools/farm.test.ts

### Source refs

- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca/tools/exec.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca/tools/farm.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca/tools/mutation.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca/tools/exec.test.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca/tools/farm.unit.test.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca/tools/farm.test.ts

### Proposed paths

None.

### Behavior change

A quality gate whose prior process tree is not verified stopped cannot be treated as an ordinary retryable test failure.

### Implementation steps

- Return typed command outcome, interrupt reason and containment result from exec through runGate/runTask and reporting.
- Reuse the mutation path policy that treats cleanupFailed as unsafe for subsequent reset/retry; preserve code 124 versus 125 information while migrating consumers.
- Stop admission to affected worktree mutations until owned cleanup/re-observation verifies containment; retain reason and process references.
- Use cancellation-independent bounded cleanup, and do not fabricate an output-overflow behavior that current farm exec does not implement.

### Existing behavior to preserve

- Verified-clean timeout can follow the documented retry policy; ordinary nonzero quality failures remain distinct.
- Scope holds to affected task/worktree/integration dependencies, not a blanket unrelated-project stop.

### Tests

**acceptance**

- Gate timeout with verified cleanup can proceed according to policy; cleanupFailed reaches runTask and prevents reset/author retry.
- After observed cleanup, explicit policy retry obtains a new attempt identity.

**rejection and failure**

- Unverified descendants, cleanup helper refusal and unknown state cannot become an ordinary gate failure or clean timeout.

**concurrency and interruption**

- A descendant writes after parent exit; verify retry/reset never races it.
- Cancellation during cleanup keeps cleanup ownership live; parallel unrelated task can finish.


### Completion evidence

- Maintained executor and farm integration tests asserting actual retry/reset call counts and process observations.
- Typed report fields carry containment independently from gate status.

### Rollback

- Fail the affected task safely with retained process/ref evidence if new typed route must be disabled; never revert to blind retry.

### Claim delta

None.

### Adr actions

None.


## FARM-R03 · Treat failed Git observations as unknown drift state

**Status:** PLANNED. **Owner:** farm.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Finding ids

- SF07

### Source paths

- plugins/ca/tools/farm.ts
- plugins/ca/tools/farm.unit.test.ts
- plugins/ca/tools/farm.test.ts

### Source refs

- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca/tools/farm.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca/tools/farm.unit.test.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca/tools/farm.test.ts

### Proposed paths

None.

### Behavior change

Git diff/ls-files failure cannot produce an observed-clean drift result.

### Implementation steps

- Use observed-clean, observed-dirty and unavailable results with command/diagnostic codes bounded and redacted.
- Allow bounded read-only observation retries for transient failures; preserve unknown after exhaustion.
- Require relevant clean observation before dependent commits/merges/reset decisions, without asserting no changes when the probe failed.

### Existing behavior to preserve

- Existing legitimate clean/dirty path calculations and protected-path checks.
- Unrelated task progress remains available.

### Tests

**acceptance**

- Successful empty observations are clean; successful paths are dirty; failed observations are unavailable.

**rejection and failure**

- Either or both Git probes fail, malformed output, timeout and revoked process access cannot be treated as empty path arrays.

**concurrency and interruption**

- Working tree changes between observations; final dependent action uses a current precondition.
- Retry cancellation leaves no invented clean result.


### Completion evidence

- Failure-injection tests for each observation edge and an integration case refusing a dependent mutation on unknown drift.

### Rollback

- Keep conservative unavailable state and expose inspect action; do not use empty-list fallback.

### Claim delta

None.

### Adr actions

None.


## HW-01 · Make persona delivery follow real mode transitions

**Status:** PLANNED. **Owner:** hooks-workflows.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Original finding ids

- HOOK-F01

### Baseline machine ids

- hooks:persona
- hooks:mode
- hooks:mode-audit

### Existing owner paths

- core/pysrc/prompt-submit.py
- core/pysrc/_modelib.py

### Proposed new paths

None.

### Semantic change scope

Behavioral defect correction: A→B→A delivers the current persona again; repeated delivery of an unchanged transition remains deduplicated.

### Implementation plan

- Replace the historical ever-delivered session/mode set as the sole delivery identity with a current transition epoch or equivalent last-delivered identity.
- Bind delivery to session, real mode transition, and compaction generation; advance on committed effective changes and recover partial mode/audit outcomes with HW-02.
- Keep same-mode no-op tokens and duplicate host events idempotent; generate all host copies from core.
- Record the ADR0030 successor clarification without rewriting its accepted body.

### Preserved invariants

- Exact whole-prompt token matching.
- Owed audit write-ahead and backing checks.
- No proof that the model consumed or forgot a persona merely from emission.

### Tests

**existing test paths**

- .github/scripts/test_prompt_submit.py
- .github/scripts/test_modelib.py
- .github/scripts/test_mode_compaction.py
- .github/scripts/test_mode_readers.py

**proposed test paths**

None.

**required cases**

- Arbiter→dangerous→arbiter and ops→arbiter→ops deliver each actual transition.
- Duplicate prompt delivery and repeated same-mode token do not grow repeated persona text.
- Compaction and new session redeliver under their actual generations.
- Mode marker/audit fault and recovery do not misreport guard state or suppress the eventual correct persona.

**execution state**

not run for this handoff; receiving agent must read test owners and execute the selected matrix


### Acceptance criteria

- Reproduce the original zero-length return-to-arbiter result, then observe a nonempty correct persona after the fix.
- Unchanged prompt/compaction/mode reader behavior remains consistent on all packaged hosts.
- Deterministic hook enforcement stays independent of mode.

### Completion evidence

- Record the exact implementation commit and any source drift from the audited baseline before making current-state claims.
- List changed canonical owners and generated derivatives; retain an exact source/package distinction.
- Attach focused meaningful test output and observed effect/failure evidence; an exit code alone is not proof of the intended target state.
- Audit reproduction: audit-work/probe_mode.py and probe_mode_results.json.

### Rollback

- Revert the new delivery algorithm as a source change without deleting owed audit rows.
- Version new delivery markers or make old readers ignore them safely; do not reinterpret a new marker as an authorization grant.

### Adr actions

- ADR0030 scoped successor: transition identity, delivery generation, and mode-independent guards.

### Coverage scope

None


## HW-02 · Expose truthful mode commit-point and audit recovery outcomes

**Status:** PLANNED. **Owner:** hooks-workflows.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Original finding ids

- HOOK-F02

### Baseline machine ids

- hooks:mode
- hooks:mode-audit
- hooks:persona

### Existing owner paths

- core/pysrc/_modelib.py
- core/pysrc/prompt-submit.py

### Proposed new paths

None.

### Semantic change scope

User-visible error/result correction with preserved write ordering: requested, persisted raw, ledger-backed effective, and delivered states become explicit.

### Implementation plan

- Define a typed partial outcome containing requested mode, raw marker outcome, effective mode, audit debt, and recoverable next action.
- Render failures from the actual outcome instead of the current blanket unchanged-session message.
- Retain owed-audit replay and exact duplicate prevention; coordinate delivery invalidation with HW-01.

### Preserved invariants

- Do not claim marker rollback unless observed.
- Raw selected mode does not override ledger backing.

### Tests

**existing test paths**

- .github/scripts/test_modelib.py
- .github/scripts/test_prompt_submit.py
- .github/scripts/test_mode_surface.py

**proposed test paths**

None.

**required cases**

- Inject failure before marker commit, after marker commit before audit settle, during owed-row replay, and after response loss.
- Assert raw/effective/delivered distinctions and exact audit rows after restart.
- No text claims modes switch deterministic gates off.

**execution state**

not run for this handoff; receiving agent must read test owners and execute the selected matrix


### Acceptance criteria

- The observed raw ops/effective arbiter partial result is reported accurately.
- A recoverable failure can settle audit debt without duplicate history.
- No failure message says no change when a persisted marker changed.

### Completion evidence

- Record the exact implementation commit and any source drift from the audited baseline before making current-state claims.
- List changed canonical owners and generated derivatives; retain an exact source/package distinction.
- Attach focused meaningful test output and observed effect/failure evidence; an exit code alone is not proof of the intended target state.
- Audit mode partial-failure probe is the initial regression oracle.

### Rollback

- Keep reader support for written outcome/marker versions during rollback.
- Never delete debt to make old output appear clean; preserve a readable recovery path.

### Adr actions

- ADR0030 scoped successor: remove contradictory gates-on/off interpretation and record partial commit outcomes.

### Coverage scope

None


## HW-03 · Align Pi doctor with the actual package identity

**Status:** PLANNED. **Owner:** hooks-workflows.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Original finding ids

- HOOK-F03

### Baseline machine ids

- hooks:doctor
- hooks:host

### Existing owner paths

- core/pysrc/doctor.py
- plugins/ca-pi/hooks/_host.py
- plugins/ca-pi/package.json

### Proposed new paths

None.

### Semantic change scope

Diagnostic correction only; no rename or relaxation of installation checks.

### Implementation plan

- Use the canonical host/package identity for @arbiterforge/ca-pi rather than the incorrect bare ca-pi literal.
- Check the scoped identity in both source and packaged layouts while preserving version, extension, skill, and discovery checks.

### Preserved invariants

None.

### Tests

**existing test paths**

- .github/scripts/test_pi_doctor.py
- plugins/ca-pi/tools/test/doctor.test.ts
- .github/scripts/test_pi_package.py

**proposed test paths**

None.

**required cases**

- Valid current scoped package passes identity; a different or malformed package fails.
- Absent extension/skills and inconsistent version still fail their own checks.
- Run doctor against the installed candidate, not a source-only synthetic bare-name fixture.

**execution state**

not run for this handoff; receiving agent must read test owners and execute the selected matrix


### Acceptance criteria

- Doctor no longer recommends reinstall solely because the legitimate package uses its actual scoped name.
- Other health failures retain accurate independent results.

### Completion evidence

- Record the exact implementation commit and any source drift from the audited baseline before making current-state claims.
- List changed canonical owners and generated derivatives; retain an exact source/package distinction.
- Attach focused meaningful test output and observed effect/failure evidence; an exit code alone is not proof of the intended target state.
- audit-work/probe_diagnostics_results.json shows the baseline false failure.

### Rollback

- Revert diagnostic identity lookup only if required; do not mutate or rename installed packages as rollback.

### Adr actions

None.

### Coverage scope

None


## HW-05 · Make spinner uninstall ownership-safe

**Status:** PLANNED. **Owner:** hooks-workflows.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Original finding ids

- HOOK-F05

### Baseline machine ids

- hooks:statusline-wiring

### Existing owner paths

- core/pysrc/wire-statusline.py

### Proposed new paths

None.

### Semantic change scope

Behavioral defect correction: preserve a setting changed by the user after installation.

### Implementation plan

- Persist the exact installed spinner value separately from the prior backup.
- Restore only while the current spinner value still equals the installed owned value; otherwise leave it and report ownership ended.
- Treat statusLine and spinner ownership independently; define a conservative migration for older backups lacking an owned-value stamp.

### Preserved invariants

None.

### Tests

**existing test paths**

- plugins/ca/hooks/tests/test_wire_statusline.py

**proposed test paths**

None.

**required cases**

- Install→uninstall restores previous value when still owned.
- Install→user custom spinner→uninstall preserves custom value.
- Missing setting, malformed/older backup, repeated uninstall, and partial settings write do not clobber unrelated keys.
- Existing statusLine ownership behavior remains intact.

**execution state**

not run for this handoff; receiving agent must read test owners and execute the selected matrix


### Acceptance criteria

- The audit clobber reproduction fails before the change and passes afterward.
- Uninstall never substitutes a whole old settings object for the current object.

### Completion evidence

- Record the exact implementation commit and any source drift from the audited baseline before making current-state claims.
- List changed canonical owners and generated derivatives; retain an exact source/package distinction.
- Attach focused meaningful test output and observed effect/failure evidence; an exit code alone is not proof of the intended target state.
- audit-work/probe_diagnostics_results.json contains the isolated settings reproduction.

### Rollback

- Preserve backup metadata across rollback; an older reader must not be allowed to blindly restore it over new user values.
- If old code cannot read new ownership metadata safely, disable that restoration path rather than delete user configuration.

### Adr actions

None.

### Coverage scope

None


## HW-07 · Allow corrected debug submissions without manufacturing truth or permission

**Status:** PLANNED. **Owner:** hooks-workflows.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Original finding ids

- W-F02
- HOOK-B01

### Baseline machine ids

- hooks:debug-handoff

### Existing owner paths

- core/surface/skills/debug/SKILL.md
- core/surface/skills/debug/references/preparation.md
- core/surface/skills/debug/references/handoff.md
- core/pysrc/_debughandofflib.py
- core/pysrc/debug-handoff.py

### Proposed new paths

None.

### Semantic change scope

User-selected recovery policy change: corrected input may be resubmitted; validator limits and diagnostic/causal authority remain unchanged unless a separate justified schema correction is needed.

### Implementation plan

- Replace blanket one-shot prohibition with distinct invalid-input, semantic-evidence, stale-binding, operational-failure, and actual-denial handling.
- Require correction provenance and current bindings; unchanged retry loops or interpreter/validator substitution cannot bypass a refusal.
- Retain five dispositions, genuine regression obligations, bounded safe diagnostics, and the fact that valid shape is not causal proof or repair permission.
- Do not create a persistent debug packet store; any recovery obligation carries only a sanitized follow-up.

### Preserved invariants

None.

### Tests

**existing test paths**

- .github/scripts/test_debug_handoff.py
- .github/scripts/test_debug_workflow.py
- .github/scripts/test_debug_helper_invocation.py
- .github/scripts/test_debug_qualification.py
- .github/scripts/test_debug_package.py

**proposed test paths**

None.

**required cases**

- Malformed packet→corrected valid packet accepted through the same installed validator, with unchanged authority.
- Exit2 semantic-evidence failure cannot be solved by changing only labels or fabricating observations.
- Stale runtime binding is refreshed only from real observation; actual denied operation stays denied.
- Exit3 operational retry preserves payload identity until a real correction is made.
- 65536-byte/depth/closed-field/diagnostic limits and output redaction remain effective.

**execution state**

not run for this handoff; receiving agent must read test owners and execute the selected matrix


### Acceptance criteria

- Corrected resubmission is explicitly allowed and actionable in all rendered debug resources.
- No validator success grants code-writing, external access, or publication permission.
- No whole rejected packet is persisted or echoed by the new recovery path.

### Completion evidence

- Record the exact implementation commit and any source drift from the audited baseline before making current-state claims.
- List changed canonical owners and generated derivatives; retain an exact source/package distinction.
- Attach focused meaningful test output and observed effect/failure evidence; an exit code alone is not proof of the intended target state.

### Rollback

- Revert workflow recovery policy only via an explicit policy decision; keep historical attempts and observations truthful.
- No data migration is needed if no debug store was added.

### Adr actions

- Focused successor/addendum if current accepted debug policy requires one: distinguish validation recovery from authorization.

### Coverage scope

None


## HW-09 · Resolve maintenance-only HIGH disposition as its own policy choice

**Status:** PLANNED. **Owner:** hooks-workflows.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** D-HIGH.

### Original finding ids

- W-F03

### Baseline machine ids

None.

### Existing owner paths

- core/surface/agents/dependency-reviewer.md
- core/surface/includes/reviewer-contract.md
- core/surface/agents/INDEX.md

### Proposed new paths

None.

### Semantic change scope

Unresolved semantic policy decision; do not infer its answer from permission to correct/resubmit.

### Implementation plan

- Present B and the receiving agent the exact conflicting owner clauses and representative maintenance-only/security examples.
- Choose explicitly between preserving universal HIGH blocking with a justified maintenance severity change, or retaining HIGH with a narrowly defined nonblocking maintenance disposition exception.
- If separating severity from disposition, make the allowed exception closed and auditable; never allow arbitrary findings to self-label nonblocking.
- Update shared contract, dependency owner, triage/aggregation consumers and generated index together after the decision.

### Preserved invariants

None.

### Tests

**existing test paths**

- .github/scripts/test_review_funnel.py
- .github/scripts/test_build_surface.py

**proposed test paths**

- .github/scripts/test_dependency_review_disposition.py

**required cases**

- Maintenance-only unmaintained dependency produces the explicitly chosen severity/disposition.
- Known high-impact vulnerability, malicious install script, denied license, and mixed maintenance/security findings retain the selected security gate.
- Resubmission with unchanged findings cannot change gate disposition.

**execution state**

not run for this handoff; receiving agent must read test owners and execute the selected matrix


### Acceptance criteria

- One exact user-attributed policy governs all consumers, with examples and no contradictory common/body rule.
- Independent tasks continue while this choice is open.

### Completion evidence

- Record the exact implementation commit and any source drift from the audited baseline before making current-state claims.
- List changed canonical owners and generated derivatives; retain an exact source/package distinction.
- Attach focused meaningful test output and observed effect/failure evidence; an exit code alone is not proof of the intended target state.

### Rollback

- Version/record the prior policy and revert all verdict producers/consumers together if the chosen rule is rolled back.
- Retain prior verdicts as historical observations; do not rewrite severity history.

### Adr actions

- Focused attributed policy decision recording severity versus disposition and any narrow exception.

### Coverage scope

None


## HW-10 · Define the closed durable workflow recovery contract and ADR boundaries

**Status:** PLANNED. **Owner:** hooks-workflows.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Original finding ids

- W-F04
- HOOK-B04

### Baseline machine ids

- hooks:startup
- hooks:knowledge
- hooks:work-owner

### Existing owner paths

- core/surface/includes/harvest.md
- core/surface/includes/knowledge.md
- .codearbiter/decisions/0008-commit-gate-board-sync-chokepoint.md
- .codearbiter/decisions/0036-bounded-authorization-cleanup-direction.md
- .codearbiter/decisions/0043-assistive-state-engine.md
- core/artifacts/internal/validate/input_policy.go

### Proposed new paths

- core/workflow-recovery-contract.json

### Semantic change scope

User-selected new local recovery capability; no new completion, approval, publication, or cleanup authority.

### Implementation plan

- Adopt/refine the explicit pending/claimed/settled/unavailable transition table in workflow-recovery-design.md.
- Define registered terminal-harvest kind, closed bounded record, source/work/session binding, stable obligation ID, candidate revision and immutable effect operation ID.
- Register Git-common storage ownership, inventory semantics, snapshot exclusion, retention, and compatibility before adding writes.
- Specify result fields that separate durable/observed/partial/unavailable/denied and prohibit an empty-success interpretation of incomplete reads.
- Record successor/addendum ADRs without mutating accepted history.

### Preserved invariants

- No automatic external issue/publication.
- No automatic task completion or review pass.
- No new enrollment prerequisite for ordinary work.

### Tests

**existing test paths**

None.

**proposed test paths**

- .github/scripts/test_workflow_recovery_contract.py

**required cases**

- Contract admits only registered kinds and bounded safe fields; unknown version/kind is unavailable.
- Every transition has a legal event/guard/effect and reject/no-op behavior.
- No transition maps validation pass, elapsed age, branch deletion or generic CLI success to authorization/completion.
- Git-common recovery state cannot be claimed as verification input.

**execution state**

not run for this handoff; receiving agent must read test owners and execute the selected matrix


### Acceptance criteria

- The design is implementable without a global daemon, database, generic command replay, or universal permission gate.
- Ordinary authorized work without a native task ID can register using explicit work_ref none.
- ADR0008 branch contingency and ADR0036 deletion boundary are preserved.

### Completion evidence

- Record the exact implementation commit and any source drift from the audited baseline before making current-state claims.
- List changed canonical owners and generated derivatives; retain an exact source/package distinction.
- Attach focused meaningful test output and observed effect/failure evidence; an exit code alone is not proof of the intended target state.

### Rollback

- Before any runtime writes ship, rollback is removal of unpublished contract changes.
- Once writers exist, retain versioned readers/export and never delete unknown-version or unresolved records.

### Adr actions

- ADR0008 scoped successor for early local capture versus terminal promotion/staging.
- ADR0043 implementation clarification for nonblocking local continuation.
- ADR0036 boundary note: no destructive cleanup authorization is granted by recovery.

### Coverage scope

None


## HW-17 · Document whole staged-candidate security evidence precisely

**Status:** PLANNED. **Owner:** hooks-workflows.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Original finding ids

- W-F06
- HOOK-B03

### Baseline machine ids

- hooks:commit-gates
- hooks:security-producers

### Existing owner paths

- core/surface/commands/override.md
- core/surface/includes/security-gate-record.md
- core/pysrc/security-pass.py
- core/pysrc/_sensitivelib.py
- core/pysrc/_bashguardlib.py
- core/pysrc/git-enforce.py

### Proposed new paths

None.

### Semantic change scope

Documentation and recovery-message correction; preserve the current full candidate/worktree binding.

### Implementation plan

- Replace sensitive-lines-only invalidation wording with worktree identity, complete staged UTF8 diff binding, and sensitive diagnostics.
- Explain that unrelated staged edits also invalidate the marker and that producer success does not itself prove semantic reviewer PASS.
- Keep binary override, actual review result, attributed override and staging semantics distinct.
- Ensure resubmission help routes to a current review/candidate rather than a freshness bypass.

### Preserved invariants

- Mode-independent deterministic guards.
- No marker equals proof of a reviewer decision without the owning workflow.

### Tests

**existing test paths**

- .github/scripts/test_hook_guards.py
- .github/scripts/test_build_surface.py

**proposed test paths**

None.

**required cases**

- Sensitive candidate with current marker passes existing checks; unrelated staged edit invalidates the same marker.
- Different worktree and altered sensitive diagnostics reject reuse.
- No blanket statement says every commit -a is blocked; actual sensitive/absorbed-candidate behavior remains as implemented.
- Actual denied override cannot be fixed by reformatting a packet.

**execution state**

not run for this handoff; receiving agent must read test owners and execute the selected matrix


### Acceptance criteria

- All help text predicts the same invalidation tuple enforced by Git and host guards.
- No scope narrowing or new TTL is introduced as an undocumented convenience.

### Completion evidence

- Record the exact implementation commit and any source drift from the audited baseline before making current-state claims.
- List changed canonical owners and generated derivatives; retain an exact source/package distinction.
- Attach focused meaningful test output and observed effect/failure evidence; an exit code alone is not proof of the intended target state.

### Rollback

- Retain enforced candidate binding; rollback of docs must follow source truth, not weaken checks.

### Adr actions

None.

### Coverage scope

None


## HW-18 · Correct watch process and polling claims

**Status:** PLANNED. **Owner:** hooks-workflows.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Original finding ids

- W-F07

### Baseline machine ids

None.

### Existing owner paths

- core/surface/commands/watch.md
- core/surface/commands/pr.md

### Proposed new paths

None.

### Semantic change scope

Documentation correction; preserve watcher/timeout/cancel/merge behavior.

### Implementation plan

- Describe one detached gh watch invocation that internally refreshes checks, with no repeated agent polling calls.
- Verify the exact supported gh help and official command documentation before asserting a default interval.
- Preserve no-auto-merge, red diagnosis behavior, branch-fix scope, auth failure and explicit/automatic watch opt-in differences.

### Preserved invariants

None.

### Tests

**existing test paths**

- .github/scripts/test_build_surface.py
- .github/scripts/test_routing_and_cleanup_surface.py

**proposed test paths**

None.

**required cases**

- All host renderings remove the server-side/no-polling assertion.
- Green still offers merge rather than performing it; cancellation and timeout remain documented truthfully.

**execution state**

not run for this handoff; receiving agent must read test owners and execute the selected matrix


### Acceptance criteria

- The public claim distinguishes model calls from CLI refresh behavior without changing the command flow.

### Completion evidence

- Record the exact implementation commit and any source drift from the audited baseline before making current-state claims.
- List changed canonical owners and generated derivatives; retain an exact source/package distinction.
- Attach focused meaningful test output and observed effect/failure evidence; an exit code alone is not proof of the intended target state.

### Rollback

- Revert wording only on supported gh behavior evidence; no watcher process behavior change is bundled.

### Adr actions

None.

### Coverage scope

None


## HW-19 · Generate command signatures and Tribunal lens counts from owners

**Status:** PLANNED. **Owner:** hooks-workflows.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Original finding ids

- W-F08

### Baseline machine ids

- generator:catalog-graph
- generator:public-catalog
- generator:rendering

### Existing owner paths

- core/surface/COMMANDS.md
- core/surface/commands/release.md
- core/surface/commands/tribunal.md
- core/surface/skills/tribunal/SKILL.md
- tools/build-surface.py
- site/scripts/generator/host-command-catalog.ts

### Proposed new paths

None.

### Semantic change scope

Generated factual contract correction; no command grammar or release-target support is removed.

### Implementation plan

- Define explicit owner metadata for supported release argument spelling/target grammar and active Tribunal lenses.
- Generate catalog signatures/counts and site derivatives from metadata instead of independent manual claims.
- Retain actual --dryrun spelling and numeric-sequence/SemVer target behavior unless a separately tested compatibility alias is intentionally added.

### Preserved invariants

None.

### Tests

**existing test paths**

- .github/scripts/test_command_catalog.py
- .github/scripts/test_build_surface.py
- .github/scripts/test_release_workflow.py
- site/test/generator/host-command-catalog.test.ts
- site/test/generator/command-catalog-discovery.test.ts

**proposed test paths**

None.

**required cases**

- Catalog count equals actual active owner lens set (13 at baseline).
- Release grammar and argument hints match the owner including numeric targets.
- Supported host views and compatibility routes are unchanged except corrected facts.

**execution state**

not run for this handoff; receiving agent must read test owners and execute the selected matrix


### Acceptance criteria

- A single owner fact regenerates every affected surface deterministically.
- No stale summary is used as a reason to change implemented command semantics.

### Completion evidence

- Record the exact implementation commit and any source drift from the audited baseline before making current-state claims.
- List changed canonical owners and generated derivatives; retain an exact source/package distinction.
- Attach focused meaningful test output and observed effect/failure evidence; an exit code alone is not proof of the intended target state.

### Rollback

- Keep compatible generated outputs and redirects when reverting generator metadata.
- Do not delete a supported flag or route to restore an old summary.

### Adr actions

None.

### Coverage scope

None


## HW-21 · Align compatibility retirement metadata with the approved public rule

**Status:** PLANNED. **Owner:** hooks-workflows.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Original finding ids

- W-F09

### Baseline machine ids

- generator:catalog-graph

### Existing owner paths

- core/surface/command-routes.json
- tools/build-surface.py
- core/surface/includes/command-compatibility.md
- .github/scripts/check_command_route_release_state.py

### Proposed new paths

None.

### Semantic change scope

Metadata/schema correction implementing the existing public major/1.0 floor plus separately approved named removal and fresh exact-release evidence; no route removal.

### Implementation plan

- Replace the contradictory minor-release-with-changelog-notice vocabulary with a structured/closed representation of the actual rule.
- Update schema validator, generated policy prose, release-state observer and fixtures together.
- Preserve confirmed non-draft GitHub release as the clock start and preserve the named historical exception without generalizing it.
- Require any future named removal decision separately; the requested major release alone does not satisfy it.

### Preserved invariants

None.

### Tests

**existing test paths**

- .github/scripts/test_command_route_compatibility.py
- .github/scripts/test_command_route_release_state.py
- .github/scripts/test_build_surface.py
- site/test/generator/command-url-stability.test.ts

**proposed test paths**

None.

**required cases**

- Version floor without named approval is insufficient.
- Draft/tag/source version without confirmed release evidence is insufficient.
- Named approved removal affects only that route; unrelated aliases remain.
- Current wrappers/grammars/URLs remain supported through this change.

**execution state**

not run for this handoff; receiving agent must read test owners and execute the selected matrix


### Acceptance criteria

- Registry, validator, policy and release observer encode one unambiguous rule.
- All currently supported aliases remain present unless another task carries a named user approval.

### Completion evidence

- Record the exact implementation commit and any source drift from the audited baseline before making current-state claims.
- List changed canonical owners and generated derivatives; retain an exact source/package distinction.
- Attach focused meaningful test output and observed effect/failure evidence; an exit code alone is not proof of the intended target state.

### Rollback

- Retain a compatibility reader for previous metadata where needed; fail explicit retirement assessment rather than drop routes on unknown schema.
- Rollback does not restore a looser hidden policy in only one consumer.

### Adr actions

None.

### Coverage scope

None


## HW-22 · Correct and couple prune nudge configuration semantics

**Status:** PLANNED. **Owner:** hooks-workflows.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Original finding ids

- GEN-F01

### Baseline machine ids

- generator:public-catalog
- hooks:prune-execute

### Existing owner paths

- site/scripts/generator/configuration-reference.ts
- core/pysrc/_prunelib.py

### Proposed new paths

None.

### Semantic change scope

Documentation correction only: threshold is estimated avoidable context freed, not total model context.

### Implementation plan

- Describe the actual context_bytes_freed token estimate predicate and current default.
- Where practical expose the predicate/default fact through canonical generated metadata rather than a second hand-maintained semantic claim.
- Preserve platform/host eligibility and recommendation timing.

### Preserved invariants

None.

### Tests

**existing test paths**

- site/test/generator/configuration-reference.test.ts
- .github/scripts/test_prune_nudge.py

**proposed test paths**

None.

**required cases**

- Large total context but insufficient freed-context benefit does not satisfy the threshold.
- Freed benefit at/below/above threshold follows the unchanged runtime comparator.
- Generated description and default match the runtime owner.

**execution state**

not run for this handoff; receiving agent must read test owners and execute the selected matrix


### Acceptance criteria

- No output claims the threshold measures total model context.
- Runtime decisions are unchanged by this documentation fix.

### Completion evidence

- Record the exact implementation commit and any source drift from the audited baseline before making current-state claims.
- List changed canonical owners and generated derivatives; retain an exact source/package distinction.
- Attach focused meaningful test output and observed effect/failure evidence; an exit code alone is not proof of the intended target state.

### Rollback

- Revert metadata coupling without changing predicate; retain accurate generated wording.

### Adr actions

None.

### Coverage scope

None


## HW-23 · Make hook extraction bounded, masked and honest about dynamic text

**Status:** PLANNED. **Owner:** hooks-workflows.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Original finding ids

- GEN-F02

### Baseline machine ids

- generator:hook-extractor
- generator:rendering

### Existing owner paths

- site/scripts/generator/extract-hook-gates.ts
- site/scripts/generator/render-hooks-reference.ts
- core/pysrc/_bashguardlib.py

### Proposed new paths

None.

### Semantic change scope

Extractor correctness and public claim correction; extracted text does not become runtime authorization logic.

### Implementation plan

- Apply lexical code masking to literal-tag extraction so comments/docstrings/examples are not treated as executable call sites.
- Represent static fragments, unresolved dynamic/helper fragments, bounded variable resolution and skipped-call census explicitly.
- Remove every-gate/never-drift runtime equivalence claims; expose omissions and source links in generated references.
- If a typed gate registry is introduced, retain runtime source ownership and test generated adapter/registry equivalence at actual messages.

### Preserved invariants

None.

### Tests

**existing test paths**

- site/test/generator/extract-hook-gates.test.ts
- site/test/generator/render-hooks-reference.test.ts

**proposed test paths**

None.

**required cases**

- Quoted/commented/docstring fake block calls are excluded.
- Dynamic recovery suffix is marked unresolved or rendered from a real typed owner, never silently presented as full runtime text.
- Variable assignment beyond current30-line window and unsupported expressions yield explicit gaps.
- Real executable call attribution and gate ordering remain correct under unrelated line shifts.

**execution state**

not run for this handoff; receiving agent must read test owners and execute the selected matrix


### Acceptance criteria

- The reference truthfully distinguishes extraction coverage from actual runtime-message equivalence.
- Known dynamic security recovery output is represented without a fabricated full message.
- A static false-positive possibility is not described as an observed production failure without a reproducer.

### Completion evidence

- Record the exact implementation commit and any source drift from the audited baseline before making current-state claims.
- List changed canonical owners and generated derivatives; retain an exact source/package distinction.
- Attach focused meaningful test output and observed effect/failure evidence; an exit code alone is not proof of the intended target state.

### Rollback

- Revert parser changes only with honest limitation text retained; do not reinstate unsupported completeness claims.

### Adr actions

None.

### Coverage scope

None


## HW-24 · Reserve emitted slugs globally and preserve published URLs

**Status:** PLANNED. **Owner:** hooks-workflows.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Original finding ids

- GEN-B01

### Baseline machine ids

- generator:discovery
- generator:catalog-graph

### Existing owner paths

- site/scripts/generator/assign-slugs.ts

### Proposed new paths

None.

### Semantic change scope

Bounded helper edge-case correction; actual production route impact must be measured before changing published assignments.

### Implementation plan

- Track all emitted slugs, not independent counters for base names only.
- Keep deterministic stable-input behavior and handle names that already end in numeric suffixes.
- Compare old/new real generated catalogs and preserve redirects or stable pinned routes for any published URL change.

### Preserved invariants

- Audit finding is a source-proven helper case; current production reachability was not demonstrated.

### Tests

**existing test paths**

- site/test/generator/assign-slugs.test.ts
- site/test/generator/command-url-stability.test.ts

**proposed test paths**

None.

**required cases**

- foo,foo,foo-2 yields three distinct outputs.
- Repeated names, numeric suffixes, slug normalization collisions and stable order remain deterministic.
- Actual candidate catalog diff identifies whether any published route changes; if none, state no observed current route impact.

**execution state**

not run for this handoff; receiving agent must read test owners and execute the selected matrix


### Acceptance criteria

- No duplicate output slug for supported arbitrary input.
- No previously published route disappears without compatible redirect/explicit policy.

### Completion evidence

- Record the exact implementation commit and any source drift from the audited baseline before making current-state claims.
- List changed canonical owners and generated derivatives; retain an exact source/package distinction.
- Attach focused meaningful test output and observed effect/failure evidence; an exit code alone is not proof of the intended target state.

### Rollback

- Preserve any introduced redirects during rollback; do not orphan URLs by reverting only one catalog.

### Adr actions

None.

### Coverage scope

None


## HW-26 · Preserve Pi test qualification and credential-isolation boundaries

**Status:** PLANNED. **Owner:** hooks-workflows.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Cross-owner coordination


##### Record

**task id**

PI-D07

**kind**

downstream-qualification-consumer

**reason**

PI-D07 consumes disposable-home/credential/identity qualification; HW-26 does not wait for author qualification.


### Original finding ids

None.

### Baseline machine ids

- pi-qualification:runtime-discovery
- pi-qualification:disposable-home

### Existing owner paths

- plugins/ca-pi/tools/test/benchmark-boundary.ts
- plugins/ca-pi/tools/test/live-pi-host.ts
- plugins/ca-pi/tools/test/setup-disposable-home.ts
- plugins/ca-pi/tools/test/runner-isolation.test.ts
- plugins/ca-pi/tools/test/security.test.ts

### Proposed new paths

None.

### Semantic change scope

Qualification preservation/verification; these helper transitions must not be reclassified as installed product behavior.

### Implementation plan

- Prove disposable-home preload for every new recovery/delegation test process before imports that can read auth.
- Use dummy credentials and exact new temp roots; never inspect the operator auth store.
- Record actual discovered Pi runtime version/package identity/digest at callers when those are qualification claims; PATH helper alone proves less.
- Preserve benchmark100-measured/5-warmup ready/complete protocol and label fixture bridge/native functions honestly.
- Document best-effort exit cleanup as possible test residue, not a live user cleanup guarantee.

### Preserved invariants

None.

### Tests

**existing test paths**

- plugins/ca-pi/tools/test/security.test.ts
- plugins/ca-pi/tools/test/runner-isolation.test.ts
- .github/scripts/test_pi_security.py
- .github/scripts/test_pi_package.py

**proposed test paths**

None.

**required cases**

- Home/auth variables point at disposable fixture before runtime access on supported platforms.
- Missing/malformed runtime package and unsupported version/digest are not falsely counted as installed-host proof.
- Benchmark measured sample count excludes5 warmups and preserves observed call counts.
- Abrupt test termination can leave only the exact disposable root; no production credential path is read or removed.

**execution state**

not run for this handoff; receiving agent must read test owners and execute the selected matrix


### Acceptance criteria

- Every new installed-host claim records its exact candidate/runtime binding and actual observation.
- Fixture-only passes remain separate from real host and release admission evidence.
- No new defect claim is invented from these helpers alone.

### Completion evidence

- Record the exact implementation commit and any source drift from the audited baseline before making current-state claims.
- List changed canonical owners and generated derivatives; retain an exact source/package distinction.
- Attach focused meaningful test output and observed effect/failure evidence; an exit code alone is not proof of the intended target state.

### Rollback

- Retain test isolation even if a new qualification feature is rolled back.
- Clean only exact disposable test roots and never operator resources.

### Adr actions

None.

### Coverage scope

Benchmark protocol already belongs to release-ci C36; avoid duplicate state-family counting.


## NT-01 · Pin old-reader fixtures and preservation contracts

**Status:** PLANNED. **Owner:** native.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Finding ids

None.

### Classification

test and contract baseline

### Owner

Native model/schema/store maintainers; integration CLI

### Decision status

authorized preparation; no product semantic choice

### Independent work policy

A task-specific unresolved decision or conflict blocks only its consumers; continue unrelated authorized work.

### Sources


##### Record

**path**

core/artifacts/go.mod

**symbol**



**lines**

None.

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/go.mod


##### Record

**path**

tools/test-artifact-mixed-schema.py

**symbol**

exercise

**lines**

- 62

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:tools/test-artifact-mixed-schema.py


##### Record

**path**

tools/test-artifact-work-old-client.py

**symbol**

exercise

**lines**

- 46

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:tools/test-artifact-work-old-client.py


##### Record

**path**

core/artifacts/internal/store/crash_test.go

**symbol**

TestProcessDeathRecovery

**lines**

- 17

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/store/crash_test.go


##### Record

**path**

core/artifacts/internal/operations/assistive_test.go

**symbol**



**lines**

None.

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/operations/assistive_test.go


### Files

- core/artifacts/internal/operations/assistive_test.go
- core/artifacts/internal/operations/dependency_advice_test.go
- core/artifacts/internal/store/crash_test.go
- tools/test-artifact-mixed-schema.py
- tools/test-artifact-work-old-client.py

### Implementation steps

- Record integration start commit, current source delta, exact built native binary SHA-256 and supported schema/protocol/profile versions before comparing behavior.
- Retain existing fixed 0.3.1→0.3.2 compatibility fixture; add current inspected 0.3.2 baseline→new candidate fixture when a new version is chosen. Do not edit the old fixture into pretending its historical client understands new fields.
- Build fixture states covering all seven current task labels; ordinary versus receipted REVIEW; DONE versus ACCEPTED; reported pass/fail/skip/unknown; scoped prerequisites; retired symbols; scope baselines; immutable evidence; prepared/committed/rolled-back journals.
- Capture byte/hash expectations for stable identity, stopped work, actual negative outcomes, bounded current history plus journal history, CAS, operation-ID replay and no authority creation during ordinary progress.
- Separate tests preserving required behavior from tests that encode deliberately changing semantics, notably task-block marking transitive work STALE. Such tests change only with NT-09's recorded decision.

### Acceptance sequences


##### Old reader and two later writes

**steps**

- Old client creates spec/plan and records explicit stop
- Candidate reads without mutation
- Candidate performs schema-changing write
- Candidate performs a later independent write
- Old client attempts read/write
- Replay original and later candidate requests
- Restore complete preupgrade store into a separate root

**expected**

- Original IDs and stop survive; candidate reads do not rewrite; old client refuses unsupported state; replay preserves later bytes; separate restoration is readable without replacing the live store

**existing owner files**

- tools/test-artifact-mixed-schema.py

**new test required**

True


##### Baseline ordinary work

**steps**

- Create a draft plan without approval/context ticket
- Start work, report implementation ready, record failed/unknown check
- Read eligibility and context

**expected**

- No fabricated authority files; ordinary progress remains available; reported failures and unassessed proof remain explicit

**existing owner files**

- core/artifacts/internal/operations/assistive_test.go
- core/artifacts/internal/operations/task_check_test.go

**new test required**

True


### Commands


##### Record

**command**

go test ./internal/model ./internal/schema ./internal/operations ./internal/store

**cwd**

core/artifacts

**note**

Planned invocation; not executed in this handoff.


##### Record

**command**

python tools/test-artifact-mixed-schema.py --old /absolute/old/ca-artifact --candidate /absolute/candidate/ca-artifact

**cwd**

.

**note**

Existing arguments; supply built exact-client paths and record their digests. Current script asserts 0.3.1→0.3.2; extend with an additional current-baseline case, do not claim it already covers future schema.


### Backward read

Preserve inspection of historical versions; never silently rewrite on read.

### Migration

Fixtures run only in disposable repositories. Capture complete-store backup and binding facts before introducing any new-format writer.

### Rollback

Test separate-root complete restoration and forward export with later writes retained; no universal downgrade claim.

### Completion evidence

- Fixture source commits and binary digests
- Observed exact old/new schema matrix
- Existing invariant assertions plus identified intentional-change assertions


## PI-D01 · Freeze the parent delegation, effect observation and trust-profile contracts

**Status:** PLANNED. **Owner:** pi.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Cross-owner coordination


##### NT-02

**kind**

conditional-contract-integration

**use**

Register and validate a closed namespace only if storage uses the reserved artifact root; otherwise retain agreed host bookkeeping owner.


### Finding ids

- SF01

### Source paths

- plugins/ca-pi/tools/src/contracts.ts
- plugins/ca-pi/tools/src/dispatch.ts
- plugins/ca-pi/tools/src/child-extension.ts
- plugins/ca-pi/tools/src/runner.ts
- plugins/ca-pi/tools/src/pi-api.d.ts
- plugins/ca-pi/tools/src/policy.ts
- plugins/ca-pi/tools/src/path-boundary.ts
- core/hosts.json

### Source refs

- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/contracts.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/dispatch.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/child-extension.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/runner.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/pi-api.d.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/policy.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/path-boundary.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/hosts.json

### Proposed paths

- plugins/ca-pi/tools/src/delegation-contract.ts

### Behavior change

Add a versioned internal parent-issued run grant plus per-operation admission and outcome contract. The minimum profile is exact tool/action/command admission under existing host trust, with no implied OS filesystem or network confinement.

### Implementation steps

- Record an ADR proposal with the user-selected functional author acceptance criterion and the explicit trusted-host versus confined execution profiles.
- Define bounded closed grant, operation, response, record and fd3-envelope decoders; parent-generated caller/run/child/generation bindings; role ceiling; exact request digest; expiry and revocation; resource-precondition and observation fields.
- Separate admission, execution, observation, containment and recovery dimensions; keep model judgment distinct from parent-observed effects.
- Specify strict repository/worktree identity and admitted direct request targets; do not use canonicalPath lexical fallback as proof of strict target authority.
- Choose one agreed host bookkeeping owner and agree NT-10 record/file-effect limits. Git-common bookkeeping may remain outside the artifact store; register a closed namespace with NT-02 only if using the reserved artifact root. Do not assume current CAS APIs can execute arbitrary source files.
- Preserve callers omitting optional scope proposals: proposals are untrusted requests, never tokens or executable paths. No hidden grant derived from task prose.
- Define initial exact-operation consent; finite preapproved batches are an optional later optimization and cannot become wildcard commands.

### Existing behavior to preserve

- Existing one author maximum per dispatch, role catalog tool ceilings, depth/concurrency/output limits, no recursive orchestration, child untrusted-project setting, and separate internal compaction with no tools.
- Current plan-mode planning-write exception remains separately bounded; a child does not acquire it merely by choosing a path.
- No universal Docker/sandbox dependency for ordinary delegation.

### Tests

**acceptance**

- Contract tests admit a legitimate author grant proposal after parent narrowing and retain legacy reviewer dispatch shape.
- All operation outcomes round-trip without collapsing unknown into failure/no-effect or containment into exit code.
- Every public claim names its execution profile and evidence level.

**rejection and failure**

- Unknown fields, version, tool/action class, oversized record, invalid target, duplicate identity with changed digest, and model-supplied authority fields are rejected.
- Read-only or handshake-only author behavior cannot satisfy the completion contract.

**concurrency and interruption**

- Two grants bind distinct parent run/generation identities even when role/task text matches.
- Grant lifetime cannot increase after wall-clock changes or parent restart.


### Completion evidence

- Reviewed contract/ADR diff with exact existing versus proposed APIs and a machine-readable decoder fixture set.
- Native/hook/root owners agree namespace, recovery notification seam and no cycle in implementation dependencies.

### Rollback

- Before release, revert contract consumers together or leave the new author capability disabled; do not parse a new format with old permissive decoders.
- Retain unknown-version records read-only and do not resurrect old authority.

### Claim delta

- Parent delegation remains planned until implementation and exact-artifact qualification.
- Exact operation admission does not imply arbitrary command confinement.

### Adr actions

- Propose scoped Pi parent delegation ADR; amend only conflicting child/permission passages while retaining isolation and final-argument requirements.


## PI-L01 · Make persona readiness an independent prerequisite and retryable state

**Status:** PLANNED. **Owner:** pi.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Finding ids

- SF02

### Source paths

- plugins/ca-pi/tools/src/extension.ts
- plugins/ca-pi/tools/src/status.ts
- plugins/ca-pi/tools/test/activation.test.ts

### Source refs

- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/extension.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/status.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/test/activation.test.ts

### Proposed paths

None.

### Behavior change

Prevent a ready/governed state from surviving missing persona content or being healed merely by unrelated bridge success.

### Implementation steps

- Represent persona and bridge readiness independently with explicit load failure/retry transitions.
- Choose the narrowest truthful readiness prerequisite: load required persona before full governed readiness, or expose a distinct unavailable capability that cannot appear fully ready.
- A retry reloads persona content for the current generation; bridge refresh may clear only bridge degradation.
- Use the same prerequisite vector for prompt construction, dispatch admission and status.

### Existing behavior to preserve

- Dormant/untrusted host behavior, existing safe bootstrap guard and current persona ordering/content semantics.
- Failure diagnostics remain bounded and do not accidentally make optional display work a governance prerequisite.

### Tests

**acceptance**

- Persona failure followed by success of bridge alone remains persona-unavailable.
- Explicit successful persona retry in current lifecycle produces correct prompt and readiness once.

**rejection and failure**

- Empty/missing/failed persona cannot mark full author readiness; late old persona cannot populate new session.

**concurrency and interruption**

- Session transition during persona read; retry races with bridge refresh; shutdown during load.


### Completion evidence

- Activation tests asserting both authority readiness and actual prompt content after fault/retry.
- Source path and generated bundle evidence match.

### Rollback

- Revoke current generation and restore prior complete adapter if needed; never roll back to a status that hides missing persona.

### Claim delta

None.

### Adr actions

None.


## PI-L02 · Cancel pending sidebar installation across disposal

**Status:** PLANNED. **Owner:** pi.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Finding ids

- SF03

### Source paths

- plugins/ca-pi/tools/src/sidebar-manager.ts
- plugins/ca-pi/tools/src/sidebar-compositor.ts
- plugins/ca-pi/tools/src/footer.ts
- plugins/ca-pi/tools/test/sidebar-manager.test.ts

### Source refs

- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/sidebar-manager.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/sidebar-compositor.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/footer.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/test/sidebar-manager.test.ts

### Proposed paths

None.

### Behavior change

A disposed sidebar cannot acquire terminal width or renderer hooks when an earlier asynchronous metrics request finishes.

### Implementation steps

- Reuse the footer generation/lease pattern for every sidebar install await and final compositor patch.
- Dispose invalidates pending installs and restores only hooks owned by that connection/generation.
- Keep late UI completion suppression separate from execution/resource cleanup ownership.

### Existing behavior to preserve

- Native rendering fallback, runtime support probe, existing sidebar geometry rules and fail-soft display behavior.

### Tests

**acceptance**

- Dispose-while-metrics-pending then resolve leaves installed=false, original columns and renderer unchanged.
- A new valid session can install once after old install is invalidated.

**rejection and failure**

- Probe or metrics failure cannot leave half-installed hooks or falsely claim unavailable native rendering.

**concurrency and interruption**

- Old and new metrics promises resolve in both orders; repeated dispose; geometry change during install.


### Completion evidence

- Regression of audit-work/probe-pi-sidebar-dispose.mjs promoted into maintained behavior test.
- Supported live sidebar test where that private runtime hook is claimed.

### Rollback

- Disable sidebar capability and return native rendering; do not retain stale compositor hooks.

### Claim delta

None.

### Adr actions

None.


## R-01 · Unify publication completion and receipt-only recovery

**Status:** PLANNED. **Owner:** release-and-integration.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Phase

3

### Owner

release-and-integration

### Finding ids

- C-F01

### Source paths

- .github/actions/publish-target/action.yml
- .github/scripts/release_target.py
- .github/workflows/release.yml

### Implementation

- Define per-target completion from exact tag/source identity, required asset/digest readback, registry/marketplace effects where applicable, and final publication receipt.
- Make eligibility and planning consume the same observed completion model. Public-but-missing-receipt remains eligible for the missing receipt effect; already complete is a no-op.
- Preserve immutable tags/assets, Pi pre-publication provenance verification and independent target recovery. Unknown remote outcomes trigger readback before retry; a receipt failure never implies safe republishing.

### Tests

- Inject failure after tag, draft, package/channel effect, public transition and receipt attachment.
- Public release with missing receipt must schedule only the missing effect.
- Wrong asset digest/source, moved tag, registry mismatch and unavailable readback must not be papered over.
- Run existing .github/scripts/test_release_target.py and test_release_workflow.py plus new composition fixtures.

### Acceptance

- eligible/plan agree for every publication state.
- Receipt-only recovery succeeds without replacing bytes, moving tags or repeating completed publication.

### Rollback

- Revert new planner before publication if necessary; after an external effect, recover forward from observed exact identity. Never delete or retarget immutable release history.


## R-02 · Bind operator release intent to the exact selected source and CI artifacts

**Status:** PLANNED. **Owner:** release-and-integration.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Phase

3

### Owner

release-and-integration

### Finding ids

- C-F02

### Source paths

- .github/workflows/release.yml

### Implementation

- Display the selected source SHA and successful main CI run in manual release planning. Correct current-head wording to match the actual default selection, preserving useful recovery of an earlier successful source.
- For this major promotion, require equality with the approved final source/artifact record. A later unrelated successful run or stale older run must not silently become the major release candidate.
- Reuse original-run recovery while retained artifacts exist; if bytes are rebuilt, establish new identities and repeat affected qualification.

### Tests

- Newer main failed while older main CI succeeded; no successful CI; old source no longer ancestor; artifact expired; selected approved source differs.
- Exact source/digest readback is displayed and enforced for major publication.

### Acceptance

- Every publication operation names its exact source and build run.
- Manual UI/report and implementation agree.

### Rollback

- Retain old immutable publication records; revert UI selection changes only when behavior/documentation remain consistent.


## R-03 · Resolve and encode pre-tag enforcement policy once

**Status:** PLANNED. **Owner:** release-and-integration.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** D-GOV-PRETAG.

### Phase

3

### Owner

release-and-integration

### Finding ids

- C-F03

### Source paths

- .github/scripts/check_auto_release_candidate.py
- .github/workflows/ci.yml
- .github/workflows/release.yml
- .codearbiter/decisions/0040-independent-per-target-release-with-consumer-safety-gates.md
- .codearbiter/decisions/0044-trusted-pi-npm-publication.md

### Implementation

- Preserve the currently required candidate check while drafting a successor ADR for the advisory-versus-required contradiction. Do not weaken current gates merely to match old prose.
- Define checks by concrete consumer-safety or qualification purpose and enforcement class. Derive CI/release reporting from that approved definition.
- Record the major-program completion gate as a release-specific requirement requested by B; do not silently turn it into an ordinary runtime permission system or permanent all-release cross-target transaction.

### Tests

- A required check failure blocks at the declared boundary; advisory failure is visible without being relabeled verified.
- CI candidate and publication planning use the same policy owner.
- An accepted ADR alone cannot mark a check implemented or qualified.

### Acceptance

- B/maintainer-approved enforcement disposition and source implementation agree.
- ADR0044 provenance requirements remain active.

### Rollback

- Keep current required candidate enforcement until replacement policy and tests are accepted; revert derivative wording if implementation is deferred.


## R-05 · Close documentation-rule event selection

**Status:** PLANNED. **Owner:** release-and-integration.

**Implementation prerequisites:** P-01, P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Phase

2

### Owner

release-and-integration

### Finding ids

- C-F05

### Source paths

- .github/workflows/docs.yml

### Implementation

- Add the voice checker and its implementation predicate to PR/integration input selection and derive the shared input set where practical.
- Preserve deliberate deployment event differences. Ensure validation of rule changes does not grant deployment permissions.

### Tests

- Change only .github/scripts/check_site_voice.py; change only core/pysrc/_sloplib.py; both must select their actual gate.
- Unrelated paths and fork/integration events must not publish Pages.

### Acceptance

- Actual input ownership is reflected in event/impact tests and workflow selection.

### Rollback

- Revert scoped selector changes without altering deployment authority.


## R-06 · Separate qualification verdicts and absent/invalid evidence

**Status:** PLANNED. **Owner:** release-and-integration.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Phase

2

### Owner

release-and-integration

### Finding ids

- C-F06
- C-F07

### Source paths

- .github/scripts/check_tag_immutability.py
- .github/scripts/check_branch_protection.py
- .github/scripts/check_codex_host.py
- .github/scripts/payload_version_gate.py

### Implementation

- Keep compatible exit behavior where necessary, but expose structured verified/skipped/unavailable/rejected observations with reason, scope and source identity. Each consumer declares which outcomes satisfy its requirement.
- Distinguish absent, valid and invalid base manifests. Genuine first-introduction remains allowed; corrupt or unusable base evidence is not absence.
- This major program accepts neither skipped nor unavailable for a required advertised capability. Deliberate N/A requires evidence and a scoped rationale, not an agent relabeling a failed test.

### Tests

- 403/unavailable branch-protection read; optional Codex host absent; missing/invalid/valid base version; malformed release declaration.
- Existing ordinary advisory behavior remains compatible while major-readiness aggregation rejects missing required evidence.

### Acceptance

- Every green major-readiness result has affirmative applicable evidence.
- First-introduction and invalid evidence take distinct tested paths.

### Rollback

- Maintain old exit codes during additive rollout; revert new projection without treating unknown as verified.


## R-07 · Bound verification subprocess waits and settle children

**Status:** PLANNED. **Owner:** release-and-integration.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Phase

2

### Owner

release-and-integration

### Finding ids

- C-F08

### Source paths

- .github/scripts/check_codex_host.py
- .github/scripts/pi_benchmark.py

### Implementation

- Apply a deadline to the initial install/subprocess and Pi benchmark first-line wait, not only the later communication phase.
- Preserve partial diagnostics; track cancellation/timeout and containment separately. Use the platform-qualified child/process-tree termination contract.
- Do not report qualification failure as evidence that a still-running child is quiescent.

### Tests

- Child never emits ready line; emits partial line; exits immediately; hangs during install; survives direct parent termination in a containment fixture.
- Run test_pi_benchmark.py and actual affected Codex host tests with bounded fake children before installed qualification.

### Acceptance

- Every pending verifier phase has a tested deadline and explicit cleanup outcome.

### Rollback

- Keep diagnostics and operation identity; restore prior runner only outside required qualification while clearly reporting the liveness gap.


## SBX-C01 · Make sandbox image identity stable and provenance-aware

**Status:** PLANNED. **Owner:** sandbox.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Finding ids

- SF08
- SW-F06

### Source paths

- plugins/ca-sandbox/tools/create.ts
- plugins/ca-sandbox/tools/build.ts
- plugins/ca-sandbox/tools/dephash.ts
- plugins/ca-sandbox/tools/build.test.ts
- plugins/ca-sandbox/tools/dephash.test.ts
- plugins/ca-sandbox/COMMANDS.md
- plugins/ca-sandbox/README.md
- plugins/ca-sandbox/commands/sandbox.md
- plugins/ca-sandbox/skills/sandbox-lifecycle/SKILL.md

### Source refs

- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/tools/create.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/tools/build.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/tools/dephash.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/tools/build.test.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/tools/dephash.test.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/COMMANDS.md
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/README.md
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/commands/sandbox.md
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/skills/sandbox-lifecycle/SKILL.md

### Proposed paths

None.

### Behavior change

Equal dependency/build inputs from different random staging directories can identify the same reusable image, while changed platform/builder/toolchain inputs invalidate it.

### Implementation steps

- Define cache-key version over dependency inputs, effective builder, actual toolchain/builder version, platform/architecture and material build options; keep repository basename cosmetic.
- Supply actual observed Nixpacks version and define a deterministic fallback-builder identity/version.
- Inspect required image provenance labels/digest before reuse; image existence or equal dephash alone is not a valid cache-hit proof.
- Propagate the bounded reuse claim to all command/skill/README/glossary surfaces from one owning fact.
- Choose non-destructive handling for old cache tags: miss/rebuild or explicit verified adoption, never unverified retagging.

### Existing behavior to preserve

- Node/Python fallback where supported, offline runtime policy and source volume separation.
- No automatic prune of other images merely because cache-key version changed.

### Tests

**acceptance**

- Two complete creates with identical inputs but distinct temporary checkout basenames select one verified reusable image.
- Changed manifest/platform/toolchain/fallback template selects a new identity; actual cache hit skips build only after provenance passes.

**rejection and failure**

- Malformed/unavailable version or missing/wrong provenance cannot masquerade as cache hit.

**concurrency and interruption**

- Concurrent same-key builds converge safely without adopting partial images; cancellation leaves honest build state.


### Completion evidence

- Unit identity tests plus real Docker two-create cache/rebuild fixture for each supported builder path.
- Docs distinguish equal key from observed reusable image.

### Rollback

- Old images remain intact; revert key use to cache-miss behavior if necessary, not unsafe reuse.

### Claim delta

- Cross-create cache reuse depends on all declared material inputs and verified image provenance.

### Adr actions

None.


## SBX-C02 · Treat Docker output overflow as lost observation requiring containment

**Status:** PLANNED. **Owner:** sandbox.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Finding ids

- SF09

### Source paths

- plugins/ca-sandbox/tools/docker.ts
- plugins/ca-sandbox/tools/exec.ts
- plugins/ca-sandbox/tools/exec.test.ts
- plugins/ca-sandbox/tools/deadline.test.ts

### Source refs

- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/tools/docker.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/tools/exec.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/tools/exec.test.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/tools/deadline.test.ts

### Proposed paths

None.

### Behavior change

Overflow is a distinct interrupted outcome; terminating Docker CLI observation cannot be reported as contained workload completion.

### Implementation steps

- Carry overflow reason and observation state in the Docker client result rather than ordinary exit 1.
- Apply the same owned target-aware stop/verify policy used for timeout/cancel whenever observation is lost.
- Report command result and container containment separately, retaining target ID for reconciliation if stop cannot be proven.
- Keep cleanup bounded and independent from the cancelled/overflowed client signal.

### Existing behavior to preserve

- Existing explicit timeout and user-cancel behavior; named target scope; no global prune.

### Tests

**acceptance**

- Overflowing real container command is stopped/verified, or reports containment unknown with its exact target retained.
- Ordinary command exit 1 without observation loss remains an ordinary command failure.

**rejection and failure**

- Killed CLI alone, failed stop, failed relist and missing status cannot claim workload stopped.

**concurrency and interruption**

- Overflow races with exit/abort; stop runs once; descendant workload survives CLI kill until verified containment.
- Unrelated concurrently created container is never selected for cleanup.


### Completion evidence

- Maintained regression from probe-sandbox-lifecycle plus real Docker containment observation, not fake call count alone.

### Rollback

- Disable the affected exec path with honest unknown result if cleanup route fails; preserve resources and inspection IDs.

### Claim delta

None.

### Adr actions

None.


## SBX-D02 · Separate shell detach, named destruction and explicit broad prune

**Status:** PLANNED. **Owner:** sandbox.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Finding ids

- SW-F02
- SW-F03

### Source paths

- plugins/ca-sandbox/commands/sandbox-shell.md
- plugins/ca-sandbox/commands/sandbox-destroy.md
- plugins/ca-sandbox/skills/sandbox-lifecycle/SKILL.md
- plugins/ca-sandbox/tools/destroy.ts
- plugins/ca-sandbox/tools/teardown.test.ts

### Source refs

- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/commands/sandbox-shell.md
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/commands/sandbox-destroy.md
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/skills/sandbox-lifecycle/SKILL.md
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/tools/destroy.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/tools/teardown.test.ts

### Proposed paths

None.

### Behavior change

Workflow instructions preserve persistent boxes after shell exit and verify only the frozen selected targets of a destroy operation.

### Implementation steps

- Declare shell exit/detach and destruction as different events; remove contradictory automatic teardown instruction.
- Named destroy affects and verifies only that instance and its selected owned resources; explicit prune/no-ID chooses the broader set.
- Keep-volume exceptions and other/new boxes are reported separately; global-empty wording does not authorize deleting them.
- Generate/check parallel command and lifecycle descriptions from one lifetime/target contract.

### Existing behavior to preserve

- Current runtime persistent-box behavior, explicit destructive action scope, keep-volume option and target-aware cleanup.

### Tests

**acceptance**

- Agent instruction fixture for shell exit leaves box running; named destroy preserves another active box.
- Explicit prune selects the documented broad snapshot and reports its remaining targets.

**rejection and failure**

- No hidden auto-destroy on shell close and no global cleanup merely to satisfy a zero-resources phrase.

**concurrency and interruption**

- Box created after target snapshot is preserved; repeated targeted cleanup verifies only its retained target set.


### Completion evidence

- Source driver and instruction behavior cases agree; real Docker targeted cleanup test where claimed.

### Rollback

- Preserve resources; rollback instructions to accurate persistent/explicit cleanup behavior.

### Claim delta

- Session lifetime and resource lifetime are separate; label ownership is broader than operation target scope.

### Adr actions

None.


## SBX-D04 · Ship consumer prerequisites and distinguish guidance from enforced Claude-inside guards

**Status:** PLANNED. **Owner:** sandbox.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Finding ids

- SW-F07
- SW-F08

### Source paths

- plugins/ca-sandbox/skills/sandbox-claude-inside/SKILL.md
- plugins/ca-sandbox/README.md
- plugins/ca-sandbox/tools/claude-inside-cli.ts
- plugins/ca-sandbox/tools/claude-inside.ts
- plugins/ca-sandbox/tools/claude-inside-cli.test.ts

### Source refs

- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/skills/sandbox-claude-inside/SKILL.md
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/README.md
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/tools/claude-inside-cli.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/tools/claude-inside.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/tools/claude-inside-cli.test.ts

### Proposed paths

None.

### Behavior change

Consumers use a packaged current capability contract instead of missing maintainer spike/ADR files, and phase enforcement claims match the actual CLI checks.

### Implementation steps

- Replace mandatory consumer-root maintainer evidence paths with plugin-owned current prerequisites; keep historical spike/ADR references commit-bound provenance.
- List actual machine-enforced guards (token argv/source volume/policy/isolation/runtime checks) separately from model-guided caller/store/image/phase review.
- Retain separate supported entrypoint, but remove assertion that binary placement alone enforces five workflow phases.
- Do not copy fake ADRs into user projects or introduce new mandatory proof/approval ceremony as a documentation fix.

### Existing behavior to preserve

- Existing actual CLI guards, token handling, source-volume isolation and separate entrypoint.
- Any new mechanical phase authority requires its own concrete approved design.

### Tests

**acceptance**

- Clean consumer fixture without codeArbiter maintainer files can perform applicable preflight using packaged instructions.
- Instruction assertions accurately map each enforced guard to executable rejection behavior.

**rejection and failure**

- Missing actual platform/token/policy prerequisite still refuses; no claim that caller/store/image review is mechanically enforced absent a consuming check.

**concurrency and interruption**

- Package update changes capability reference atomically with docs; old consumer working tree never needs manufactured maintainer evidence.


### Completion evidence

- Exact package includes referenced prerequisites; CLI rejection fixtures and claim inventory identify guidance versus enforcement.

### Rollback

- Keep packaged accurate prerequisite text and actual guard behavior; do not resurrect consumer-path STOP prerequisites.

### Claim delta

- Executable placement is not phase-completion proof.
- Historical maintainer evidence is not a consumer runtime prerequisite.

### Adr actions

None.


## SITE-U01 · Add search query and expansion failure/retry state

**Status:** PLANNED. **Owner:** site.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Finding ids

- SF11

### Source paths

- site/src/components/Search.astro
- site/test/search/search-contract.test.ts
- site/test/browser/search-bundle.spec.ts

### Source refs

- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:site/src/components/Search.astro
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:site/test/search/search-contract.test.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:site/test/browser/search-bundle.spec.ts

### Proposed paths

None.

### Behavior change

Search/result-data rejection shows a recoverable current-query error and cannot leave stale results looking current or the expansion button permanently disabled.

### Implementation steps

- Add per-query and expansion error states under the existing query generation token.
- Use try/catch/finally around Pagefind search and data expansion; retain input and mark retained results stale when appropriate.
- Clear busy/disabled state only for the current generation; supply retry using the same user query.
- Keep existing module-load retry and keyboard/navigation behavior.

### Existing behavior to preserve

- Search ranking/filter semantics, accessibility focus management and bundled Pagefind import path.

### Tests

**acceptance**

- Module success + query rejection, result-data rejection and expansion rejection all yield usable retry controls.
- Retry success replaces stale state and restores enabled controls.

**rejection and failure**

- Old-query failures cannot overwrite a newer successful result set; rejected promise does not escape as unhandled UI failure.

**concurrency and interruption**

- Rapid query changes while data promises settle in different orders; close/reopen during search; repeated show-all click.


### Completion evidence

- Browser tests against built search bundle with controlled rejection and keyboard/focus assertions.

### Rollback

- Keep input/retry and restore stable search behavior; do not ship an index/UI mismatch after rollback.

### Claim delta

None.

### Adr actions

None.


## SITE-U02 · Own all documentation-drawer listeners across reconnect

**Status:** PLANNED. **Owner:** site.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Finding ids

- SF16

### Source paths

- site/src/components/SplashDocsRail.astro
- site/test/browser/concepts-execution.spec.ts

### Source refs

- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:site/src/components/SplashDocsRail.astro
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:site/test/browser/concepts-execution.spec.ts

### Proposed paths

None.

### Behavior change

Disconnect/reconnect of one drawer element cannot accumulate opener, close, tray or document handlers.

### Implementation steps

- Give each connection one AbortController for all owned listeners or implement an equivalent symmetric setup/cleanup contract.
- Dispose the document Escape listener and local listeners together, resetting initialization only when reinstallation is safe.
- Add one browser test that reconnects the same element; do not claim the old audit executed this behavior.

### Existing behavior to preserve

- Open/close/focus/escape behavior, CSS presentation and progressive navigation.

### Tests

**acceptance**

- One click after reconnect toggles once; Escape closes once; focus restoration remains correct.

**rejection and failure**

- Repeated setup/dispose cannot produce duplicate side effects or retained document listener.

**concurrency and interruption**

- Connect-disconnect-reconnect same node, repeated cycles and close during teardown.


### Completion evidence

- Browser behavior receipt on actual supported page lifecycle; source-only theoretical risk remains labeled until executed.

### Rollback

- Restore a once-bound listener scheme with correct document reattachment; no broad event disabling.

### Claim delta

None.

### Adr actions

None.


## T-01 · Make measurement and illustration verdicts trustworthy

**Status:** PLANNED. **Owner:** measurement-tools.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Phase

2

### Owner

measurement-tools

### Finding ids

- T-F01
- T-F02
- T-F03
- T-F04

### Source paths

- tools/statusline-bench.py
- tools/live-smarts-exercise.py
- tools/ci20_baseline.py
- tools/ci20_inventory.py
- tools/statusline-screenshot.py

### Implementation

- Reject empty/unknown benchmark populations and incompatible harness identities before PASS. Keep selected subsets visible.
- Separate live SMARTS subprocess completion from output quality; evaluate actual alternatives/material comparison, not literal lens-name count. Use reviewed qualitative evidence where a structural checker cannot establish reasoning quality.
- Bind CI20 workflow bytes to the recorded commit, or prove exact blob equality. Label counterfactual selection separately from live workflow execution.
- Require successful nonempty renderer output before screenshotting and own all temporary file/browser cleanup. Retain explicit mock-data provenance.

### Tests

- Empty population, invalid scenario, mismatch/harness version and real nonempty comparison.
- Three lens names without material alternatives must fail the SMARTS quality criterion; nonzero child exit cannot pass because output contains keywords.
- Dirty workflow at clean HEAD fails identity binding; same committed blob succeeds.
- Failed renderer and browser error leave no misleading successful image or untracked fixture residue.

### Acceptance

- No success verdict based on zero measurements or a failed producer.
- Measurement/proof labels identify what was actually exercised.

### Rollback

- Retain historical reports as historical; remove invalid new verdicts and regenerate after correcting the harness.


## BUILD-G02 · Bind compatibility removal to release-history authority

**Status:** PLANNED. **Owner:** packaging.

**Implementation prerequisites:** P-02, HW-21.
**Completion prerequisites:** None.
**Decision dependencies:** None.

**Shared implementation owner:** HW-21. Coordinate one change; do not duplicate competing owners.

### Cross-owner coordination


##### HW-21

**kind**

shared-implementation-owner

**use**

One coordinated compatibility metadata/policy change; preserve public major/1.0 floor, named removal decision and historical exception. Do not duplicate implementation.


##### R-04

**kind**

contract-coordination

**use**

Observed published-release history is eligibility input, not removal permission.


### Finding ids

- SF14

### Source paths

- tools/build-surface.py
- core/surface/command-routes.json
- plugins/ca-pi/includes/command-compatibility.md

### Source refs

- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:tools/build-surface.py
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/surface/command-routes.json
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/includes/command-compatibility.md

### Proposed paths

None.

### Behavior change

Compatibility metadata and generated prose reflect the actual history-backed removal contract rather than treating a validated slogan as authorization.

### Implementation steps

- Coordinate the root-owned compatibility floor/governed-removal rule and approved exceptions; preserve its actual policy rather than choosing a new floor here.
- Define canonical removal eligibility facts from exact publication history, version floor and required notice/decision evidence.
- Use build-surface for shape/projection validation and a separate authoritative removal gate for semantic eligibility.
- Generate compatible wording and validate changed route removal against history; distinguish an unpublished tag/draft from a published release.

### Existing behavior to preserve

- Existing approved compatibility exceptions, host-specific aliases and legitimate command differences.
- An ADR or literal removalRequires value alone does not prove eligibility.

### Tests

**acceptance**

- Eligible removal with complete published-history evidence passes; canonical docs reflect the same conditions.

**rejection and failure**

- Missing notice, unmet floor, draft/tag-only event, absent approval where required and malformed history cannot authorize removal.

**concurrency and interruption**

- History changes between check/candidate finalization require revalidation; independent generation does not silently advance eligibility.


### Completion evidence

- Root-approved exact policy fixture matrix and regenerated compatibility surfaces.
- Reference to governing decision and publication observations, not only JSON string equality.

### Rollback

- Retain the alias/route if eligibility is uncertain; restore generated docs without changing user command semantics prematurely.

### Claim delta

- Taxonomy validation is not semantic removal authorization.

### Adr actions

- Amend compatibility decision/prose only where it conflicts with the selected enforceable history contract.


## HW-11 · Implement crash-safe local recovery storage and bounded projections

**Status:** PLANNED. **Owner:** hooks-workflows.

**Implementation prerequisites:** HW-10, P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Original finding ids

- W-F04
- HOOK-B04

### Baseline machine ids

- hooks:startup
- hooks:native-client
- hooks:plan-file

### Existing owner paths

- core/pysrc/_hooklib.py
- core/pysrc/_artifactauthoritylib.py
- core/pysrc/_reconciliationlib.py
- core/pysrc/_planfilelib.py

### Proposed new paths

- core/pysrc/_workflowrecoverylib.py
- core/pysrc/workflow-recovery.py

### Semantic change scope

New shared runtime owner for local obligations, with explicit commit points and nonblocking bounded readers.

### Implementation plan

- Implement versioned Git-common records, OS-held per-obligation locking, revision CAS, atomic durable writes and recoverable record/index updates.
- Implement register/get/scan/claim/reconcile/settle and reason-specific unavailable outcomes through a closed helper interface, never arbitrary executable handlers.
- Authenticate the installed helper owner using existing host/protected-state patterns; do not introduce a broad exception permitting arbitrary commands to write Git metadata.
- Keep automatic scan physically read-only: an incomplete write intent yields partial/unavailable and routes to explicit locked recovery, rather than silently repairing during startup.
- Use a paged index so automatic reads touch at most32 summaries/256KiB; registration max64KiB and max32 candidates per batch, with explicit partial/oversize results.
- Maintain stable origin/ID lookup and compacted terminal tombstones; never age out unresolved records.
- Expose truthfully whether a write committed, was observed, or remains uncertain.

### Preserved invariants

- Local bookkeeping is not native evidence or a reusable authorization ticket.
- A failed scanner never blocks unrelated ordinary work.

### Tests

**existing test paths**

None.

**proposed test paths**

- .github/scripts/test_workflow_recovery.py
- .github/scripts/test_workflow_recovery_cli.py

**required cases**

- Crash at every record/index/journal commit point and response-loss replay.
- Concurrent claim/correct/settle using multiple processes; live lock cannot be stolen by TTL.
- Malformed file, path traversal, symlink, unknown version, untrusted helper invocation, disk/write failure, and broken index produce safe unavailable results.
- Large history still yields bounded paged reads; stale cursor cannot claim complete empty state.
- Tombstone compaction preserves exact dedup lookup; rollback leaves pending state intact.

**execution state**

not run for this handoff; receiving agent must read test owners and execute the selected matrix


### Acceptance criteria

- Every acknowledged registration remains discoverable or explicitly unavailable after restart.
- No unbounded whole-history read/sort is hidden inside an automatic scan.
- The helper reports real state after partial write failure and never overwrites concurrent state.
- No injected path or payload can cause arbitrary command execution or target deletion.

### Completion evidence

- Record the exact implementation commit and any source drift from the audited baseline before making current-state claims.
- List changed canonical owners and generated derivatives; retain an exact source/package distinction.
- Attach focused meaningful test output and observed effect/failure evidence; an exit code alone is not proof of the intended target state.

### Rollback

- Disable new writers and automatic notices while retaining compatible reads/export.
- Keep unresolved records, durable intents, and terminal tombstones; do not remove the store to roll back a code release.

### Adr actions

None.

### Coverage scope

None


## HW-16 · Correct persona/startup ownership and storage side-effect documentation

**Status:** PLANNED. **Owner:** hooks-workflows.

**Implementation prerequisites:** HW-01, HW-02, P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Original finding ids

- W-F05
- HOOK-B02

### Baseline machine ids

- hooks:startup
- hooks:persona
- hooks:git-install
- hooks:task-lock-exclusion

### Existing owner paths

- core/surface/commands/init.md
- README.md
- plugins/ca/README.md
- core/pysrc/session-start.py
- core/pysrc/prompt-submit.py
- core/pysrc/_githooks.py
- core/pysrc/_taskexcludelib.py

### Proposed new paths

None.

### Semantic change scope

Documentation correction; do not move runtime behavior just to fit stale claims.

### Implementation plan

- Describe per-turn prompt-submit persona composition/delivery separately from SessionStart mode cleanup, statusline repair, Git-hook install and briefing.
- Correct .codearbiter-only/no-behavior claims to name actual Git-common/global owned effects where relevant.
- Preserve the explicit-root passive inspection distinction and active-project initialization boundaries.
- Include the new recovery runtime path only when HW-11 exists.

### Preserved invariants

None.

### Tests

**existing test paths**

- .github/scripts/test_mode_surface.py
- .github/scripts/test_build_surface.py
- plugins/ca/hooks/tests/test_session_start.py

**proposed test paths**

None.

**required cases**

- Canonical and generated docs identify the actual event owner and mode-independent guards.
- Claims about dormant/active writes match representative observed startup branches.
- No claim of released behavior appears without exact-artifact evidence.

**execution state**

not run for this handoff; receiving agent must read test owners and execute the selected matrix


### Acceptance criteria

- Owner documentation and distributed surfaces make truthful activation/startup statements.
- No behavioral activation or storage migration is hidden in a prose fix.

### Completion evidence

- Record the exact implementation commit and any source drift from the audited baseline before making current-state claims.
- List changed canonical owners and generated derivatives; retain an exact source/package distinction.
- Attach focused meaningful test output and observed effect/failure evidence; an exit code alone is not proof of the intended target state.

### Rollback

- Revert factual text only if the corresponding runtime owner changes; preserve history of the corrected claim.

### Adr actions

None.

### Coverage scope

None


## HW-20 · Generate reviewer index summaries from selected disposition policy

**Status:** PLANNED. **Owner:** hooks-workflows.

**Implementation prerequisites:** HW-09, P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Original finding ids

- W-F08
- W-F03

### Baseline machine ids

- generator:public-catalog
- generator:rendering

### Existing owner paths

- core/surface/agents/INDEX.md
- core/surface/agents/coverage-auditor.md
- core/surface/agents/dependency-reviewer.md
- core/surface/includes/reviewer-contract.md
- tools/build-surface.py

### Proposed new paths

None.

### Semantic change scope

Index accuracy correction with a scoped dependency on the separately selected HIGH policy.

### Implementation plan

- Correct coverage summary so MEDIUM uncovered-source findings are not misrepresented as universal BLOCK; preserve HIGH threshold/critical-negative-path behavior.
- Derive concise reviewer summaries from explicit owner metadata, retaining distinct severity and disposition if selected in HW-09.
- Keep unresolved HIGH policy visible until chosen; command/lens corrections in HW-19 proceed independently.

### Preserved invariants

None.

### Tests

**existing test paths**

- .github/scripts/test_review_funnel.py
- .github/scripts/test_build_surface.py

**proposed test paths**

- .github/scripts/test_reviewer_catalog.py

**required cases**

- Coverage MEDIUM, HIGH missing critical negative evidence, no-tooling exemption and partial overall evidence map to truthful summaries.
- Dependency maintenance and security dispositions match the selected HW-09 rule.
- Rendered agent index cannot silently strengthen or weaken the owner body.

**execution state**

not run for this handoff; receiving agent must read test owners and execute the selected matrix


### Acceptance criteria

- Index roles and gate summaries reflect the actual selected owner contract.
- No reviewer behavior changes solely to make an old index line true.

### Completion evidence

- Record the exact implementation commit and any source drift from the audited baseline before making current-state claims.
- List changed canonical owners and generated derivatives; retain an exact source/package distinction.
- Attach focused meaningful test output and observed effect/failure evidence; an exit code alone is not proof of the intended target state.

### Rollback

- Revert derived summaries with their selected policy owner metadata; retain historical verdicts.

### Adr actions

None.

### Coverage scope

Coverage-only summary correction may proceed before HW-09; definitive dependency HIGH summary waits for that scoped decision.


## HW-25 · Verify optional context qualification manifest compatibility end to end

**Status:** PLANNED. **Owner:** hooks-workflows.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** DIST-M01.
**Decision dependencies:** None.

### Cross-owner coordination


##### Record

**task id**

DIST-M01

**owner**

host_site_lifecycle

**reason**

Owns SF04 shared supported optional-field release manifest decoder.


### Original finding ids

- HOOK-B05

### Baseline machine ids

- hooks:native-client

### Existing owner paths

- core/pysrc/_artifactlib.py
- plugins/ca/tools/farm.ts

### Proposed new paths

None.

### Semantic change scope

Cross-owner compatibility integration; the host manifest decoder is primary implementation owner.

### Implementation plan

- Integrate DIST-M01 shared supported manifest schema with Python acceptance of five base fields or those plus context_qualification.
- Define validation of the optional field at the proper owner instead of assuming the current Python loader validates its value.
- Retain exact platform, binary magic, native_tested and digest checks, and distinguish missing/unsupported/invalid qualification.

### Preserved invariants

None.

### Tests

**existing test paths**

- .github/scripts/test_artifact_farm.py
- .github/scripts/test_artifact_package.py
- .github/scripts/test_artifact_bridge.py

**proposed test paths**

None.

**required cases**

- Valid five-field legacy and valid six-field qualified manifests pass the correct consumers.
- Invalid optional value, unknown fields, wrong platform/digest/native_tested fail according to the selected closed schema.
- Candidate qualification is verified against the exact artifact, not merely a field presence.

**execution state**

not run for this handoff; receiving agent must read test owners and execute the selected matrix


### Acceptance criteria

- Python and farm accept the same supported valid manifest variants.
- Optional presence does not imply qualification evidence was verified.

### Completion evidence

- Record the exact implementation commit and any source drift from the audited baseline before making current-state claims.
- List changed canonical owners and generated derivatives; retain an exact source/package distinction.
- Attach focused meaningful test output and observed effect/failure evidence; an exit code alone is not proof of the intended target state.

### Rollback

- Keep legacy supported manifest decoding and qualification status truthful; do not strip fields to conceal incompatibility.

### Adr actions

None.

### Coverage scope

None


## NT-02 · Close context-preview producer/output-consumer contract

**Status:** PLANNED. **Owner:** native.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** NT-01.
**Decision dependencies:** None.

### Finding ids

- N-F01

### Classification

confirmed compatibility bug fix

### Owner

Native operations, contextdocument, store and evidence owners

### Decision status

authorized compatibility/preservation work

### Independent work policy

A task-specific unresolved decision or conflict blocks only its consumers; continue unrelated authorized work.

### Sources


##### Record

**path**

core/artifacts/internal/operations/context_assistive.go

**symbol**

contextOrdinaryPreview

**lines**

- 40

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/operations/context_assistive.go


##### Record

**path**

core/artifacts/internal/store/infrastructure.go

**symbol**

PutDerived

**lines**

- 168

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/store/infrastructure.go


##### Record

**path**

core/artifacts/internal/evidence/snapshot.go

**symbol**

internalOutputsWith

**lines**

- 88

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/evidence/snapshot.go


##### Record

**path**

core/artifacts/internal/evidence/completion_workspace.go

**symbol**

completionWorkspace

**lines**

- 452

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/evidence/completion_workspace.go


### Files

- core/artifacts/internal/operations/context_assistive.go
- core/artifacts/internal/store/infrastructure.go
- core/artifacts/internal/evidence/snapshot.go
- core/artifacts/internal/evidence/completion_workspace.go
- core/artifacts/internal/contextdocument/contract.go

### Implementation steps

- Add context-previews to a closed typed internal-output contract consumed by PutDerived admission and evidence output recognition. Avoid a broad ignore rule or unvalidated 'known directory' shortcut.
- Factor the existing codearbiter.context-preview/0.1.0 record contract into a dependency-safe owner; validate required/unknown fields, mode, bound document/target, hashes, bounded before-images and actual request semantics.
- Distinguish stored-format validation from current applicability: old valid previews remain recognizable outputs after target bytes change, while context-apply retains exact preview/current-before-image checks.
- Use the same validated output recognition for Snapshot and normalized completion closure; preserve bounded scans, anchored no-follow traversal, retained byte limits and arbitrary reserved-output rejection.
- Keep existing ordinary preview/apply behavior, hashes, filenames, no-permission boundary and response omissions stable.

### Acceptance sequences


##### Composed ordinary preview and strict consumers

**steps**

- Create a valid ordinary context preview
- Take strict Snapshot
- Collect normalized completion workspace
- Apply unchanged preview
- Repeat original apply

**expected**

- Preview no longer produces UNRECOGNIZED_OUTPUT; preview remains derived, not authority; actual context mutation keeps CAS and idempotent replay

**existing owner files**

- core/artifacts/internal/operations/context_assistive_test.go
- core/artifacts/internal/evidence/snapshot_test.go
- core/artifacts/internal/evidence/completion_workspace_test.go

**new test required**

True


##### Historical valid and invalid output

**steps**

- Retain a valid preview then change its target
- Read snapshot/completion
- Try applying stale preview
- Introduce malformed/digest-mismatched/nested/linked preview entries

**expected**

- Valid historical preview is recognizable; stale application refuses; malformed/unsafe reserved contents still fail closed

**existing owner files**

- core/artifacts/internal/operations/context_assistive_test.go
- core/artifacts/internal/evidence/snapshot_hardening_test.go

**new test required**

True


### Commands


##### Record

**command**

go test ./internal/contextdocument ./internal/operations ./internal/evidence

**cwd**

core/artifacts

**note**

Planned invocation; not executed in this handoff.


### Backward read

Accept existing valid preview objects without changing their bytes or upgrading receipt authority.

### Migration

No model migration required for valid 0.1.0 previews. Repair damaged previews only through an explicit, bounded owned repair; never delete history automatically.

### Rollback

Reverting only the consumer fix restores the prior defect; keep reader support with any producer that can emit the namespace. Retain existing preview and journal bytes.

### Completion evidence

- Positive preview→snapshot→completion run
- Negative closed-format/path cases
- Observed snapshot and completion closure parity


## NT-03 · Unify operation discovery and finite effect traits

**Status:** PLANNED. **Owner:** native.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** NT-01.
**Decision dependencies:** None.

### Finding ids

- N-F02

### Classification

compatibility fix plus behavior-preserving internal refactor

### Owner

Native operations protocol/dispatch owner

### Decision status

authorized compatibility/preservation work

### Independent work policy

A task-specific unresolved decision or conflict blocks only its consumers; continue unrelated authorized work.

### Sources


##### Record

**path**

core/artifacts/internal/operations/protocol.go

**symbol**

operations

**lines**

- 1

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/operations/protocol.go


##### Record

**path**

core/artifacts/internal/operations/protocol.go

**symbol**

RequestSchema

**lines**

- 63

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/operations/protocol.go


##### Record

**path**

core/artifacts/internal/operations/protocol.go

**symbol**

JournaledMutation

**lines**

- 56

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/operations/protocol.go


##### Record

**path**

core/artifacts/internal/operations/engine.go

**symbol**

repair

**lines**

- 562

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/operations/engine.go


### Files

- core/artifacts/internal/operations/protocol.go
- core/artifacts/internal/operations/engine.go
- core/artifacts/internal/operations/protocol_test.go
- core/artifacts/internal/operations/capabilities_test.go

### Implementation steps

- Advertise repair-apply and define one compile-time repository-owned descriptor for every implemented operation.
- Have Names, request contract mapping and finite operation traits derive from or be exhaustively checked against that descriptor set. Keep domain transition/guard code explicit in its owning package.
- Describe actual operation mode: selected read/contextual read, journaled model mutation, immutable capture/derived metadata writes, lock policy and evidence-claim versus ordinary progress. JournaledMutation is not a permission or no-write classifier.
- Add reverse dispatch coverage; iterating Names alone cannot detect omitted handlers. Verify unknown operations and unknown request keys remain rejected.
- Expose descriptors through a versioned compatible capability/result shape only after checking current consumers; preserve existing operation names and protocol unless explicitly versioned.

### Acceptance sequences


##### Discover and execute repair

**steps**

- Query capabilities
- Select repair-preview and repair-apply from advertised operations
- Apply valid repair with CAS
- Replay exact operation

**expected**

- Both operations discoverable; correct side-effect/lock traits; original outcome replayed without repeated mutation

**existing owner files**

- core/artifacts/internal/operations/capabilities_test.go
- core/artifacts/internal/operations/protocol_test.go
- core/artifacts/internal/operations/engine_test.go

**new test required**

True


##### Registry reverse closure

**steps**

- Enumerate handlers independently of Names
- Compare schemas, descriptors and discoverable names
- Submit unknown operation/key

**expected**

- Omitted or extra operation fails test; invalid calls remain closed; no hidden dynamic registration

**existing owner files**

- core/artifacts/internal/operations/protocol_test.go
- core/artifacts/internal/operations/protocol_boundary_test.go

**new test required**

True


### Commands


##### Record

**command**

go test ./internal/operations -run 'TestAllOperationSchemasClosed|TestCapabilities|TestCaptureRequest|TestApplyRejects'

**cwd**

core/artifacts

**note**

Planned invocation; not executed in this handoff.


##### Record

**command**

python .github/scripts/test_artifact_surface.py

**cwd**

.

**note**

Planned invocation; not executed in this handoff.


### Backward read

Existing wire names and request grammar stay stable. Older capability consumers must tolerate the explicitly selected descriptor version or receive their supported projection.

### Migration

None for existing artifact models; new capability metadata needs consumer-parity checks, not silent addition to a closed old schema.

### Rollback

Keep compatibility list coverage while reverting implementation changes; never leave advertised operations without dispatch or dispatched mutations hidden.

### Completion evidence

- Exact operation-set equality witnesses
- Repair discovery/apply/replay result
- Canonical and generated consumer parity


## NT-04 · Align role-aware launch-file bounds across native and Python

**Status:** PLANNED. **Owner:** native.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** NT-01.
**Decision dependencies:** None.

### Finding ids

- N-F09

### Classification

confirmed producer/consumer compatibility bug fix

### Owner

Native observation/evidence owners with hook producer owner

### Decision status

authorized compatibility/preservation work

### Independent work policy

A task-specific unresolved decision or conflict blocks only its consumers; continue unrelated authorized work.

### Sources


##### Record

**path**

core/artifacts/internal/observation/contract.go

**symbol**

commandBindingSchema

**lines**

- 118

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/observation/contract.go


##### Record

**path**

core/artifacts/internal/observation/runner_contract.go

**symbol**

validateQualifiedBinding

**lines**

- 36

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/observation/runner_contract.go


##### Record

**path**

core/artifacts/internal/evidence/completion_workspace.go

**symbol**

completionWorkspacesOnce

**lines**

- 364

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/evidence/completion_workspace.go


### Cross owner dependencies

- Hook producer integration task consumes NT-04; use actual _bind_commands fixtures

### Files

- core/artifacts/internal/observation/contract.go
- core/artifacts/internal/observation/runner_contract.go
- core/artifacts/internal/evidence/completion_workspace.go
- core/artifacts/internal/observation/runner_contract_test.go
- core/artifacts/internal/evidence/completion_workspace_test.go

### Implementation steps

- Centralize native maximum launch-file and per-role limits; preserve 32 workspace-manifest roles and bounded total 37 for the actual admitted npm layout.
- Use the same limits in schema, qualified role semantic validation and completion consumer. observation is already imported by evidence; prefer a small helper/constant over a new dependency cycle.
- Retain unique paths, singleton non-workspace roles, role/path/argv agreement, manifest containment, executable/runtime identity, hashes and repeated read identity checks.
- Check producer contract through shared versioned fixture data or generated metadata, including actual POSIX producer results; coordinate rather than duplicate Python business rules.
- Keep historical declared-command profiles distinct. Do not reinterpret older unqualified evidence or execute stored command text while inspecting bindings.

### Acceptance sequences


##### Actual producer boundaries

**steps**

- Create real temporary npm/Git layouts with 30, 31 and 32 workspace manifests
- Produce bindings through actual Python helper
- Pass those exact binding bytes through native qualified contract and completion

**expected**

- Total 32/33/34 accepted for valid POSIX cases; declared workspace role cap stays 32; no verifier command executes as a side effect of binding validation

**existing owner files**

- core/artifacts/internal/observation/runner_contract_test.go
- core/artifacts/internal/evidence/completion_workspace_test.go
- audit-work/probe_launch_binding.py

**new test required**

True


##### Windows and negative boundary

**steps**

- On native Windows construct supported wrapper/runtime/CLI/prefix+32 workspace layout
- Validate 37 launch files
- Try 38 total, 33 workspace roles, duplicate singleton/path, changed launch bytes or identity and relabeled profile

**expected**

- Valid 37 accepted; each malformed/changed binding rejected; historical profiles retain prior semantics

**existing owner files**

- core/artifacts/internal/observation/runner_contract_test.go
- core/artifacts/internal/evidence/completion_identity_windows_test.go

**new test required**

True


### Commands


##### Record

**command**

go test ./internal/observation ./internal/evidence

**cwd**

core/artifacts

**note**

Planned invocation; not executed in this handoff.


### Backward read

No format expansion beyond the existing admitted 37-file schema; preserve historical profile branches and strict identities.

### Migration

None required for valid retained bindings. Existing failures retry with the same logical evidence/request only if their prior outcome is known; changed input needs a newly captured observation.

### Rollback

Producer and consumer must remain compatible as a cohort. Do not ship the old 32-total consumer with a producer capable of valid larger output.

### Completion evidence

- Exact cross-language fixture bytes/digests
- Native POSIX and Windows boundary outputs
- Malformed role/path/identity negative results

### Evidence status

Python producer count reproduced during audit; native rejection source-confirmed only until these tests execute.


## NT-05 · Preserve typed retirement and historical execution ownership

**Status:** PLANNED. **Owner:** native.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** NT-01.
**Decision dependencies:** None.

### Finding ids

- N-F10

### Classification

bug fix requiring explicit versioned representation/migration

### Owner

Native model/schema/symbol/operations/validation/render owners

### Decision status

authorized compatibility/preservation work

### Independent work policy

A task-specific unresolved decision or conflict blocks only its consumers; continue unrelated authorized work.

### Sources


##### Record

**path**

core/artifacts/internal/operations/mutations.go

**symbol**

syncExecution

**lines**

- 90

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/operations/mutations.go


##### Record

**path**

core/artifacts/internal/operations/mutations.go

**symbol**

Changes

**lines**

- 208

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/operations/mutations.go


##### Record

**path**

core/artifacts/internal/symbol/index.go

**symbol**

Build

**lines**

- 27

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/symbol/index.go


##### Record

**path**

core/artifacts/internal/validate/validate.go

**symbol**

planStructure

**lines**

- 236

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/validate/validate.go


##### Record

**path**

core/artifacts/internal/render/render.go

**symbol**

Prepare

**lines**

- 50

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/render/render.go


### Files

- core/artifacts/internal/operations/mutations.go
- core/artifacts/internal/symbol/index.go
- core/artifacts/internal/validate/validate.go
- core/artifacts/internal/schema/common.schema.json
- core/artifacts/internal/schema/plan.schema.json
- core/artifacts/internal/model/artifact.go
- core/artifacts/internal/render/render.go

### Implementation steps

- Design a closed versioned retirement record that retains original kind, exact ID, retirement revision/reason/replacement and ownership of retained historical execution/checkpoint data.
- Populate new original-kind information from the pre-mutation symbol index, including nested records; never from an ID-prefix guess.
- Change syncExecution/structural validation together so checked tasks and scopes can retire without ORPHAN_STATE, and retained retired data cannot appear as live scheduling or proof.
- Keep all reported checks, baseline hashes, evidence references, original reasons and transaction history. Do not delete data to pass validation.
- Read legacy untyped tombstones conservatively. Resolve original kind only from verified preimages/exact historical models; otherwise preserve explicitly unclassified history and constrain only operations needing its ownership.
- Preserve no-ID-reuse and immutable-tombstone rules; version old/new schemas and compatibility readers together.
- Recompute canonical/model/normative hashes through the actual versioned codec. Keep old evidence bound to its original hashes as history; do not rewrite receipts or mark migrated evidence current merely because the structural repair succeeded.

### Acceptance sequences


##### Checked task retirement

**steps**

- Create task and record pass then fail
- Retire task with reason and update current references
- Read/render retained task history
- Try adding a new task with retired ID

**expected**

- Retirement succeeds; both outcomes retained; retired task absent from live scheduling; ID reuse rejected

**existing owner files**

- core/artifacts/internal/operations/migration_test.go
- core/artifacts/internal/operations/task_check_test.go
- core/artifacts/internal/validate/validate_test.go
- core/artifacts/internal/symbol/index_test.go

**new test required**

True


##### Checkpoint retirement and interruption

**steps**

- Create receipted scope baseline
- Retire checkpoint and its current ownership according to valid plan partition
- Interrupt journal stages/replace
- Complete or rollback
- Inspect history and retry

**expected**

- No orphan baseline; exact scope history remains historical; no mixed/duplicate retirement; existing third-party edits never overwritten

**existing owner files**

- core/artifacts/internal/operations/migration_test.go
- core/artifacts/internal/store/crash_test.go
- core/artifacts/internal/render/render_test.go

**new test required**

True


##### Unknown legacy kind

**steps**

- Read old tombstone without kind and without trustworthy preimage
- Preview migration
- Try task-proof inference from ID prefix
- Continue unrelated valid work

**expected**

- Ambiguity retained; unsupported inference rejected; no blanket semantic block

**existing owner files**

- core/artifacts/internal/operations/migration_test.go
- core/artifacts/internal/validate/validate_test.go

**new test required**

True


### Commands


##### Record

**command**

go test ./internal/operations ./internal/model ./internal/schema ./internal/symbol ./internal/validate ./internal/render ./internal/store

**cwd**

core/artifacts

**note**

Planned invocation; not executed in this handoff.


### Backward read

Old tombstones remain inspectable; old clients refuse unsupported new representation before mutation. Original typed evidence is never reinterpreted by name.

### Migration

Explicit preview and CAS-bound versioned write; record source hashes and complete store. Can proceed independently of progress/evidence choice if its schema migration composes with the chosen final version.

### Rollback

Existing prepared-transaction recovery only; after later edits preserve current store and forward recover/export. Restore complete old snapshot into a separate root.

### Completion evidence

- Retirement sequences with checks and scope baselines
- No-ID-reuse/immutable tombstone negatives
- Legacy ambiguity and exact-client migration evidence


## NT-07 · Label schema-only work check statuses without inventing transitions

**Status:** PLANNED. **Owner:** native.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** NT-01.
**Decision dependencies:** None.

### Finding ids

- N-F06

### Classification

behavior-preserving schema/capability claim correction

### Owner

Native work/schema/render owners

### Decision status

authorized compatibility/preservation work

### Independent work policy

A task-specific unresolved decision or conflict blocks only its consumers; continue unrelated authorized work.

### Sources


##### Record

**path**

core/artifacts/internal/schema/work.schema.json

**symbol**



**lines**

- 1

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/schema/work.schema.json


##### Record

**path**

core/artifacts/internal/operations/work.go

**symbol**

workCreate

**lines**

- 106

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/operations/work.go


##### Record

**path**

core/artifacts/internal/operations/work.go

**symbol**

workUpdate

**lines**

- 731

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/operations/work.go


##### Record

**path**

core/artifacts/internal/operations/work_adopt.go

**symbol**

workAdopt

**lines**

- 312

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/operations/work_adopt.go


### Files

- core/artifacts/internal/schema/work.schema.json
- core/artifacts/internal/operations/work.go
- core/artifacts/internal/operations/work_adopt.go
- core/artifacts/internal/render/work_view.go

### Implementation steps

- Document accepted stored vocabulary unknown/passed/failed separately from public native events that actually set it.
- Keep create/adopt initialization and updates honest; do not infer passed/failed from progress, completion or self-report.
- Preserve reading/rendering historical passed/failed fields without claiming the current engine produced a verification event.
- If capability metadata lists state/event reachability, mark these schema-only values explicitly; no new mutator or proof producer is added by this task.

### Acceptance sequences


##### Work lifecycle does not fabricate proof

**steps**

- Create/adopt work
- Apply implemented lifecycle transitions and mark implementation complete
- Read/render check_status
- Read valid stored passed/failed historical fixtures

**expected**

- Native progress does not manufacture check success/failure; historical values remain readable with honest provenance

**existing owner files**

- core/artifacts/internal/operations/work_test.go
- core/artifacts/internal/render/work_view_test.go

**new test required**

True


### Commands


##### Record

**command**

go test ./internal/operations -run 'TestWork'

**cwd**

core/artifacts

**note**

Planned invocation; not executed in this handoff.


##### Record

**command**

go test ./internal/render

**cwd**

core/artifacts

**note**

Planned invocation; not executed in this handoff.


### Backward read

All currently accepted check_status values remain accepted and preserved.

### Migration

None; never rewrite historical passed/failed to unknown merely because no current public event creates it.

### Rollback

No data rewrite; retain old serialized values.

### Completion evidence

- Capability vocabulary versus reachable events
- Lifecycle no-proof-minting fixtures


## NT-08 · Fix unsupported-platform diagnostic without new support claims

**Status:** PLANNED. **Owner:** native.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** NT-01.
**Decision dependencies:** None.

### Finding ids

- N-F08

### Classification

diagnostic bug fix

### Owner

Native store/capabilities owner

### Decision status

authorized compatibility/preservation work

### Independent work policy

A task-specific unresolved decision or conflict blocks only its consumers; continue unrelated authorized work.

### Sources


##### Record

**path**

core/artifacts/internal/store/fs_other.go

**symbol**

unsupported

**lines**

- 26

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/store/fs_other.go


##### Record

**path**

core/artifacts/internal/store/fs_portable.go

**symbol**

NativeWrites

**lines**

- 41

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/store/fs_portable.go


### Files

- core/artifacts/internal/store/fs_other.go
- core/artifacts/internal/store/fs_portable.go
- core/artifacts/internal/operations/capabilities_test.go

### Implementation steps

- Replace Linux-only/pending-Windows-macOS prose with the actual unsupported GOOS/backend and bounded supported-backend diagnostic.
- Use existing NativeWrites and Backend declarations rather than a new independent platform list where possible.
- Keep source capability distinct from native-tested package or released qualification; do not enable a platform, fetch a binary or infer installed-host enforcement.

### Acceptance sequences


##### Supported and unsupported capabilities

**steps**

- Build/test supported backend capability paths
- Compile unsupported backend/test diagnostic
- Query capabilities

**expected**

- Linux/Darwin/Windows source declarations remain accurate; unsupported GOOS remains unavailable with truthful message; no unsupported runtime success is claimed

**existing owner files**

- core/artifacts/internal/operations/capabilities_test.go
- core/artifacts/internal/store/fs_other.go

**new test required**

True


### Commands


##### Record

**command**

go test ./internal/operations -run '^TestCapabilitiesReportActualStorageBackend$'

**cwd**

core/artifacts

**note**

Planned invocation; not executed in this handoff.


### Backward read

No format or supported backend change.

### Migration

None.

### Rollback

Diagnostic-only rollback has no model migration; do not reintroduce inaccurate support claims.

### Completion evidence

- Supported native capability results
- Unsupported build/message evidence clearly distinct from native execution


## NT-09 · Implement the chosen progress/evidence representation and projections

**Status:** PLANNED. **Owner:** native.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** NT-01.
**Decision dependencies:** D-PROGRESS.

### Finding ids

- N-F03
- N-F04

### Classification

intentional semantic change; design decision still open

### Owner

B + receiving CLI for decision; native lifecycle/schema/read/render owners for implementation

### Decision status

PENDING B: compare A compatibility overlay, B independent progress with derived assessment (provisional moderate recommendation), C independent progress with persisted assessments

### Independent work policy

A task-specific unresolved decision or conflict blocks only its consumers; continue unrelated authorized work.

### Sources


##### Record

**path**

core/artifacts/internal/operations/assistive.go

**symbol**

recordWork

**lines**

- 152

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/operations/assistive.go


##### Record

**path**

core/artifacts/internal/operations/lifecycle.go

**symbol**

progress

**lines**

- 278

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/operations/lifecycle.go


##### Record

**path**

core/artifacts/internal/operations/lifecycle.go

**symbol**

invalidateDependents

**lines**

- 252

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/operations/lifecycle.go


##### Record

**path**

.codearbiter/decisions/0043-assistive-state-engine.md

**symbol**



**lines**

- 1

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:.codearbiter/decisions/0043-assistive-state-engine.md


##### Record

**path**

core/artifacts/internal/operations/assistive.go

**symbol**

recordWork

**lines**

- 152

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/operations/assistive.go


##### Record

**path**

core/artifacts/internal/operations/lifecycle.go

**symbol**

progress

**lines**

- 278

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/operations/lifecycle.go


##### Record

**path**

core/artifacts/internal/operations/prerequisite_observation.go

**symbol**

finishScope

**lines**

- 66

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/operations/prerequisite_observation.go


### Execution gate

Do not choose a persisted representation or migrate overloaded legacy states until B decides. Current-behavior characterization and independent fixes proceed.

### Files

- core/artifacts/internal/operations/assistive.go
- core/artifacts/internal/operations/lifecycle.go
- core/artifacts/internal/operations/prerequisite_observation.go
- core/artifacts/internal/operations/task_context.go
- core/artifacts/internal/operations/task_check.go
- core/artifacts/internal/schema/common.schema.json
- core/artifacts/internal/schema/plan.schema.json
- core/artifacts/internal/model/artifact.go
- core/artifacts/internal/read/read.go
- core/artifacts/internal/render/render.go

### Implementation steps

- Discuss native-smarts.md with B using the actual six canonical lenses; record only the actual resulting decision through the owning lifecycle. Do not mint a pending recommendation as a selected option or approval.
- Characterize and expose current ordinary REVIEW versus receipt-bearing REVIEW, and DONE versus ACCEPTED, with honest basis/currentness. Never infer independent proof from a label or receipt presence alone.
- Implement the selected representation in all mutators and consumers together; progress, dependency readiness and evidence assessment must remain separately explainable under the approved semantic rules.
- Preserve user-decided dependent-only conflicts: unresolved prerequisites and consequential decisions identify affected task/claim paths; independent work proceeds. Clear a stop only through a real resolution, never an upstream success or corrected JSON.
- Preserve actual observations and later failures, explicit unknown/truncated history, duplicate-start protection, schema closure, stable IDs, CAS and idempotent replay.
- Classify ordinary no-receipt progress as ordinary; preserve optional strict consumers without requiring receipts, context tickets or reviewer restarts for normal work.
- For option B, compute applicability in one domain owner and make caches disposable/input-keyed. For C, define every invalidation event and current-basis recheck. For A, preserve visible legacy ambiguity rather than fake recovered progress.
- Update deliberate old STALE tests, canonical guides and generated host projections only after the decision. Compatibility projection/version must be explicit for old consumers.

### Acceptance sequences


##### Separate progress from adverse evidence

**steps**

- Report implementation complete
- Record actual applicable failure after an earlier pass
- Read UI/context/eligibility/strict verification
- Correct work and record fresh actual pass

**expected**

- Progress never manufactures proof; failure remains in history and affects only dependent claims; fresh actual result is distinct from mutation of old evidence

**existing owner files**

- core/artifacts/internal/operations/assistive_test.go
- core/artifacts/internal/operations/task_check_test.go
- core/artifacts/internal/operations/check_conflicts_test.go

**new test required**

True


##### Transitive scope and independent stop

**steps**

- Create A→B→C plus independent X
- Record B's user stop
- Block A
- Resolve A
- Inspect B/C/X selection

**expected**

- Only dependent work waits; B's independent denial/reason survives; unrelated X continues; no duplicate dispatch

**existing owner files**

- core/artifacts/internal/operations/dependency_advice_test.go
- core/artifacts/internal/operations/prerequisite_observation_test.go

**new test required**

True


##### Meaningful and irrelevant change

**steps**

- Capture explicit evidence for exact task/input
- Change presentation or routine receipt bookkeeping
- Change relevant requirement/source separately
- Read assessment

**expected**

- No automatic re-review for unchanged subject; affected evidence becomes inapplicable after real relevant change; progress/history retained

**existing owner files**

- core/artifacts/internal/operations/completion_rerun_test.go
- core/artifacts/internal/operations/task_check_test.go

**new test required**

True


##### Legacy ambiguous state

**steps**

- Read historical STALE and mixed ordinary/strict REVIEW fixtures
- Preview selected migration
- Interrupt and resume cutover
- Use old and new clients

**expected**

- No guessed prior progress or proof; exact raw history preserved; old client safe refusal where needed; later edits survive retry

**existing owner files**

- tools/test-artifact-mixed-schema.py
- core/artifacts/internal/operations/migration_test.go

**new test required**

True


### Commands


##### Record

**command**

go test ./internal/operations ./internal/model ./internal/schema ./internal/read ./internal/render ./internal/evidence

**cwd**

core/artifacts

**note**

Planned invocation; not executed in this handoff.


##### Record

**command**

python tools/test-artifact-mixed-schema.py --old /absolute/old/ca-artifact --candidate /absolute/candidate/ca-artifact

**cwd**

.

**note**

Extend with chosen new schema matrix; current test is not a generic future-schema proof.


### Backward read

Reader adapters preserve exact old bytes and basis. Legacy STALE cannot be mapped to done/in-progress/pending without trustworthy recorded history. Old clients reject unsupported writes.

### Migration

Only approved chosen representation; explicit preview/CAS and complete-store history. No new schema for SMARTS rationale itself—the current spec approach/decisions/SEC-SMARTS convention remains.

### Rollback

Retain new data and forward recover after later writes; compatible complete snapshot restoration into separate root only. Ordinary optional strict evidence must not be reinterpreted as a mandatory default during rollback.

### Completion evidence

- B's actual decision and exact authored semantics
- Versioned old/new projection matrix
- All cross-axis sequences, negative claims and on-host consumer readbacks


## NT-10 · Integrate durable Pi effect recovery with a bounded native persistence seam

**Status:** PLANNED. **Owner:** native.

**Implementation prerequisites:** PI-D01, P-02.
**Completion prerequisites:** NT-01.
**Decision dependencies:** None.

### Finding ids

None.

### Classification

new authorized host behavior; preserve existing native integrity kernel

### Owner

Pi parent delegation owner with native storage owner

### Decision status

authorized direction; exact internal interface to be implemented, not an existing API

### Independent work policy

A task-specific unresolved decision or conflict blocks only its consumers; continue unrelated authorized work.

### Sources


##### Record

**path**

core/artifacts/internal/store/transaction.go

**symbol**

Commit/Lookup/Recover

**lines**

- 183
- 258
- 414

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/store/transaction.go


##### Record

**path**

core/artifacts/internal/operations/engine.go

**symbol**

Run

**lines**

- 76

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/operations/engine.go


##### Record

**path**

core/artifacts/internal/store/fs_portable.go

**symbol**



**lines**

None.

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/store/fs_portable.go


##### Record

**path**

.codearbiter/security-controls.md

**symbol**



**lines**

None.

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:.codearbiter/security-controls.md


### Downstream consumers

- PI-D04

### Files

- core/artifacts/internal/store/transaction.go
- core/artifacts/internal/store/fs_portable.go
- core/artifacts/internal/store/fs_linux.go
- plugins/ca-pi/tools/src/ (exact new host-owned files chosen by PI-D01/PI-D04)

### Implementation steps

- Agree exact parent-owned delegation/effect record interface from PI-D01 before selecting storage reuse; PI-D04 consumes it, avoiding circular implementation dependencies.
- Record exact repository/root identity, bounded path/action/request scope, before identity/hash, attempt/effect identity, phase and bounded outcome/uncertainty; no secrets and no claim that a digest grants host permission.
- Keep host workflow progress records distinct from native multi-file transaction states and review evidence. Register a new artifact reserved namespace only if actually used there; Git-common local bookkeeping retains its own owner.
- For the minimum trusted-host profile, implement bounded host claim/outcome persistence and parent-owned operations with strict static request/target admission, refusal of known stale preconditions, serialized Arbiter writes and observed pre/post state. Do not claim atomic CAS or race-free containment from Pi tool calls. If a stronger profile promises those guarantees, first implement and qualify a narrow safe primitive or confined executor. Never expose arbitrary source paths through an artifact API or mistake the append audit log for a replay journal.
- Private intent/payload staging may precede a claim. Persist and confirm the durable exclusive claim before any visible source/command effect; persist durable outcome before acknowledgement. Reconcile uncertain effects before retry; do not blindly restore over observed user edits. Idempotency belongs to the actual effect, not a model report.
- Preserve native CAS/journals/before-images/terminal replay and no-follow identity checks. Pending canonical transactions remain store-integrity dependencies until safely reconciled.
- Handle revoked/expired permission, process-tree interruption and concurrent parent/child edits explicitly; completed effects are not undone by token revocation. Ordinary unrelated authorized work stays available.

### Acceptance sequences


##### Lost acknowledgement and resumed parent

**steps**

- Authorize exact supported child action
- Durably claim
- Perform source effect
- Kill before outcome acknowledgement
- Restart parent and reconcile exact effect identity
- Retry same attempt

**expected**

- One intended effect; outcome recovered or explicitly unknown; no duplicate execution; no new permission inferred; independent safe work remains available

**existing owner files**

- core/artifacts/internal/store/crash_test.go
- PI-D04 host effect-journal test owner

**new test required**

True


##### Concurrent edit and cancellation

**steps**

- Freeze target before-hash
- Apply independent parent edit or replace target/ancestor with link
- Submit child effect
- Revoke during/after an admitted effect

**expected**

- Known stale or statically unsafe request is rejected without mutation; changes racing after admission are not claimed atomically excluded by the trusted-host profile. Detect/report actual observations and uncertainty; never perform blind recovery overwrite. A stronger advertised profile must additionally pass real race-free/CAS backend tests. Revocation affects matching scope and does not fabricate rollback of completed effects.

**existing owner files**

- core/artifacts/internal/store/store_test.go
- core/artifacts/internal/store/junction_windows_test.go
- PI-D05 host conflict/revocation test owner

**new test required**

True


##### Native pending integrity boundary

**steps**

- Interrupt a canonical multi-file write
- Attempt dependent canonical read/write
- Continue an independent safe host task
- Complete/rollback through verified recovery

**expected**

- Unsafe canonical store stays guarded; independent work does not require global semantic approval; recovery never overwrites third-party bytes

**existing owner files**

- core/artifacts/internal/store/crash_test.go
- core/artifacts/internal/store/store_test.go
- PI-D04 host recovery test owner

**new test required**

True


### Commands


##### Record

**command**

go test ./internal/store -run 'TestProcessDeathRecovery|TestJournalPublicationCrash|TestTransactionalCAS|TestRecoveryConflictPreservesExternalEdit'

**cwd**

core/artifacts

**note**

Planned invocation; not executed in this handoff.


##### Record

**command**

go test ./internal/store ./cmd/ca-artifact

**cwd**

core/artifacts

**note**

Planned invocation; not executed in this handoff.


### Backward read

Existing journal versions and terminal outcomes remain readable. New Pi records must be versioned, bounded and owned by the parent; old hosts must refuse unsupported mutation contracts.

### Migration

No automatic conversion of audit lines into durable replay claims. Existing ambiguous/unfinished child effects are observed and marked unknown; do not fabricate earlier admissions.

### Rollback

Do not downgrade while new in-flight effects are unaccounted for. Quiesce/reconcile, preserve all records, then use compatible read-only inspection or explicit export. No pretending local rollback reverses completed external effects.

### Completion evidence

- Agreed PI-D01↔NT-10↔PI-D04 interface
- Actual supported-host replay/interruption/concurrency results
- Existing native platform containment/CAS preservation results; evidence for any stronger new source-effect guarantee only if that profile is implemented and advertised.
- No ordinary-progress attestation dependency


## NT-11 · Support corrected reviewer attempts without reopening terminal evidence

**Status:** PLANNED. **Owner:** native.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** NT-01.
**Decision dependencies:** None.

### Finding ids

None.

### Classification

user-authorized workflow semantics plus native compatibility validation

### Owner

Host reviewer producer owner and native observation/authority owners

### Decision status

authorized corrected resubmission; never overrides real host/user denial

### Independent work policy

A task-specific unresolved decision or conflict blocks only its consumers; continue unrelated authorized work.

### Sources


##### Record

**path**

core/artifacts/internal/observation/contract.go

**symbol**

reviewDecisionSchema/reviewContractHash/validateReview

**lines**

- 165
- 603
- 611

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/observation/contract.go


##### Record

**path**

core/artifacts/internal/authority/receipt.go

**symbol**

ReceiptSchema/EventSchema/Inspect

**lines**

None.

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/authority/receipt.go


##### Record

**path**

core/artifacts/internal/operations/lifecycle.go

**symbol**

progress/capture

**lines**

None.

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/operations/lifecycle.go


##### Record

**path**

core/surface/agents/authority-reviewer.md

**symbol**

Output

**lines**

- 41

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/surface/agents/authority-reviewer.md


### Cross owner dependencies

- Hook HW reviewer-attempt task owns parent request persistence/linkage and canonical charter changes; native acceptance stays coordinated

### Files

- core/artifacts/internal/observation/contract.go
- core/artifacts/internal/observation/contract_test.go
- core/artifacts/internal/observation/native_v1_test.go
- core/artifacts/internal/observation/native_v2_test.go
- core/artifacts/internal/authority/receipt.go
- core/artifacts/internal/authority/observed_event_test.go
- core/artifacts/internal/operations/completion_rerun_test.go

### Implementation steps

- Preserve a rejected/malformed/changes_requested attempt as terminal history in the owning producer workflow. Corrected content opens a linked new request attempt, not an edit of old evidence.
- Use fresh actual launch correlation and a currently frozen target/contract/context. Same subject can be re-reviewed; a changed subject must receive refreshed exact bindings.
- Retain pass-only authority-bearing observation semantics, no BLOCK findings and all profile/launch/coverage/target checks. A rejection is not a passed receipt.
- Keep same-request idempotent transport retry separate from new logical corrected submission. Fresh first_stop must be the first stop of that newly captured attempt; never relabel a later old-child stop.
- Native has no global 'only one review ever' gate. Prefer existing formats where a fresh valid attempt fits. If new linkage must enter the content-addressed native record, introduce a closed version/profile and backward inspection; do not add keys to the old closed schema.
- Preserve real user/host denial as a separate scoped stop; corrected serialization is not authority to clear it. Ordinary progress remains independent of optional review proof.
- Coordinate debug resubmission only at its workflow owner; do not turn a debug retry into a native verification or approval event.
- Rejected/malformed replies belong to bounded host attempt history; current native observation formats admit successful authority-bearing reviews only. Do not force a rejection into that success schema.

### Acceptance sequences


##### Rejected then corrected

**steps**

- Capture actual rejected/malformed first attempt
- Create linked new request with current frozen bindings
- Launch new reviewer attempt and submit a valid observed pass
- Capture twice and consume receipt through exact mutation replay

**expected**

- Prior rejection retained; new attempt can succeed; immutable capture/replay does not duplicate effect; no synthetic approval or reused denied request

**existing owner files**

- core/artifacts/internal/observation/contract_test.go
- core/artifacts/internal/authority/observed_event_test.go
- core/artifacts/internal/operations/completion_rerun_test.go

**new test required**

True


##### Do not launder a terminal record

**steps**

- Mutate a prior retained rejected-submission record or an immutable native observation
- Reuse old request/launch identity for changed content
- Relabel second stop as first or change target/contract/coverage/profile
- Try corrected submission under actual scoped denial

**expected**

- Tampering and mismatched evidence rejected; denial remains; independent work unaffected

**existing owner files**

- core/artifacts/internal/observation/contract_test.go
- core/artifacts/internal/observation/native_v1_test.go
- core/artifacts/internal/observation/native_v2_test.go
- Host reviewer-attempt tests

**new test required**

True


### Commands


##### Record

**command**

go test ./internal/observation ./internal/authority ./internal/operations

**cwd**

core/artifacts

**note**

Planned invocation; not executed in this handoff.


### Backward read

Old receipts/observations retain exact interpretation; historical inspection does not confer current authority. Old request terminal status is never reset.

### Migration

No migration needed if only new host attempts use existing native formats. Any linkage format addition needs explicit version dispatch, old reader refusal, current-target tests and namespace closure if stored in reserved outputs.

### Rollback

Retain rejected and corrected attempts and source bytes. Do not remove later successful evidence or reopen a rejected request to emulate old behavior.

### Completion evidence

- Actual host rejected→new corrected attempt sequence
- Native acceptance and mutated/stale/profile-negative controls
- Existing immutable receipt inspection and replay preserved


## PI-C01 · Resolve private Pi approval runtime and evidence-mode mismatch

**Status:** PLANNED. **Owner:** pi.

**Implementation prerequisites:** PI-D01, P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Cross-owner coordination


##### R-06

**kind**

contract-coordination

**use**

Separate synthetic versus host-observed qualification and optional evidence status.


##### G-01

**kind**

claim-propagation

**use**

Artifact attestation docs and capability canon.


### Finding ids

- SF12

### Source paths

- plugins/ca-pi/tools/src/approval-entry.ts
- plugins/ca-pi/tools/src/approval-dialog.ts
- plugins/ca-pi/tools/src/compatibility.ts
- plugins/ca-pi/tools/test/approval-dialog.test.ts
- tools/build-host-packages.py
- core/surface/includes/artifacts-attestation.md

### Source refs

- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/approval-entry.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/approval-dialog.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/compatibility.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/test/approval-dialog.test.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:tools/build-host-packages.py
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/surface/includes/artifacts-attestation.md

### Proposed paths

None.

### Behavior change

Optional private artifact prompt support is versioned and qualified independently from ordinary parent tool consent and child authorship.

### Implementation steps

- Read exact private entry admission and choose a concrete supported-runtime outcome: qualify/update it for admitted Pi or advertise it unavailable with accurate legacy/private evidence.
- Preserve one-shot/private caller binding and refusal of ordinary agent-flow self-arm; do not turn artifact approval into a general child grant.
- Record source/runtime-gated/synthetic-policy-event/host-observed evidence modes separately and correct stale broad Pi no-authority or all-installed-approval claims.
- Leave ordinary progress and the functional parent delegation path independent of optional artifact attestation.

### Existing behavior to preserve

- Existing artifact authority provenance/one-shot guards and host differences.
- Exact current compatibility value is 1.1.0; old private 1.0.2 gate is not qualification proof.

### Tests

**acceptance**

- Chosen optional capability is accurately admitted/denied on exact runtimes and public matrix matches actual entry behavior.
- If support is claimed, exact installed artifact real prompt/one-shot flow is observed.

**rejection and failure**

- Ordinary child/agent cannot self-arm; mismatched runtime, caller binding, replay or synthetic-only evidence cannot claim host-observed approval.

**concurrency and interruption**

- Prompt cancellation/replay/session change retains one-shot/refusal semantics; stale UI cannot arm a new caller.


### Completion evidence

- Exact optional capability receipt with evidence mode and runtime/artifact binding, or explicit supported-matrix unavailable claim.
- No broad ordinary-permission claim derived from private prompt test.

### Rollback

- Disable only optional private approval capability and keep honest matrix; retain ordinary parent/author functions.

### Claim delta

- Optional artifact prompt authority is separate from ordinary consent and author capability.

### Adr actions

None.


## PI-D02 · Plumb parent authority and reuse the final operation permission gate

**Status:** PLANNED. **Owner:** pi.

**Implementation prerequisites:** PI-D01, P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Finding ids

- SF01

### Source paths

- plugins/ca-pi/tools/src/extension.ts
- plugins/ca-pi/tools/src/dispatch.ts
- plugins/ca-pi/tools/src/tool-guard.ts
- plugins/ca-pi/tools/src/policy.ts
- plugins/ca-pi/tools/src/contracts.ts
- plugins/ca-pi/tools/src/plan-mode.ts
- plugins/ca-pi/tools/test/tool-guard.test.ts
- plugins/ca-pi/tools/test/dispatch.test.ts
- plugins/ca-pi/tools/test/final-arguments-live.test.ts

### Source refs

- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/extension.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/dispatch.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/tool-guard.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/policy.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/contracts.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/plan-mode.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/test/tool-guard.test.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/test/dispatch.test.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/test/final-arguments-live.test.ts

### Proposed paths

- plugins/ca-pi/tools/src/operation-gate.ts

### Behavior change

Make child effects cross the same final-argument bridge, descriptor policy, live trust, mode, source ownership and parent consent boundary as parent operations.

### Implementation steps

- Pass parent current mode, immutable caller correlation, lifecycle authorization, trusted cwd, registry/source identity and parent UI context through an internal dispatch admission port.
- Extract/reuse the existing gate sequence rather than copying a weaker child policy. Freeze final parameters; call bridge; preserve hard-block versus advisory-warning distinctions; evaluate policy; confirm exact operation when required.
- Use the actual host tool-call ID for parent correlation instead of ignoring it. Keep random activity IDs informational.
- Recheck trust, generation, mode, raw/canonical parameters, registry ownership, original executor identity, target observations and abort after every relevant await.
- Record consent source honestly: parent human confirmation, admitted finite batch or policy allow. Configuration handshake attestation never supplies consent.
- Keep headless authors unavailable unless a concrete supported explicit host-authority route is separately implemented; do not forge TUI context or mutate project trust.

### Existing behavior to preserve

- Bootstrap/final source guard; current hard rules; plan source/config/shell denies; read/inspection behavior and bounded native plan-write exception.
- Existing direct parent operations retain permission behavior and final argument binding.
- Permission refusal does not permanently bar corrected debug/reviewer submissions.

### Tests

**acceptance**

- Parent TUI approval of a frozen admitted write/edit/command reaches exactly one effect executor.
- Bridge warning remains advisory through permission; hard block bypasses UI and execution.
- Legacy parent tool tests and installed-host final-argument ordering cells remain green with their evidence substitutions stated.

**rejection and failure**

- Missing/throwing trust, plan mode, no UI, declined/timed-out UI, foreign wrapper, unsupported descriptor, changed command/args, changed native function and audit admission failure execute nothing.
- An ambient child marker or successful handshake cannot bypass permission.

**concurrency and interruption**

- Mutate arguments, mode, trust, owner, executor and lifecycle during bridge/UI/journal awaits; stale operations never execute.
- A valid new lifecycle remains operational after an old approval becomes stale.


### Completion evidence

- Exact test output showing no direct-parent regression and final-argument identity before real effect invocation.
- Review of the dispatch registration path demonstrates mode/authority are actually plumbed, not inferred from task text.

### Rollback

- Disable new delegated admission and revoke live grants before reverting; retain existing parent gate unchanged.
- Preserve denied/unknown operation records for later inspection.

### Claim delta

- Parent source ownership is a prerequisite, not proof of task permission.

### Adr actions

None.


## Q-02 · Add an exact-candidate major-release readiness barrier

**Status:** PLANNED. **Owner:** release-and-qualification.

**Implementation prerequisites:** R-01, R-02, R-06, P-01, P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Phase

5

### Owner

release-and-qualification

### Finding ids

None.

### Source paths

None.

### Implementation

- Q-02 completion means the readiness verifier and its valid/invalid/noncircular regression cases are implemented and tested on the integration candidate. The actual final-main readiness instance is verified during Q-03 before publication; Q-02 does not require a future main commit or Q-03 completion before promotion.
- Implement the release-specific readiness protocol described in BRANCH-AND-RELEASE.md before final promotion. It must guard the first externally visible publication/channel effect for this major program.
- Bind the readiness receipt to exact source commit, CI build/run identity, target versions, archive/member digests, installed qualification cells and accepted program decisions. Obtain evidence from the declared trusted producer; an edited project JSON with passed:true is not authority.
- If final-main packages differ from the qualified integration candidate, keep major publication pending while qualifying those exact bytes. Never rely on matching version strings or tree identity as byte equality.
- Keep current main-only publication and independent target retry. Global program readiness precedes publication; it is not an atomic cross-target release transaction or a new ordinary-work gate.
- The current workflow auto-releases after successful main CI. Wire readiness before that can publish; do not plan to notice missing final qualification after the release has already happened.
- Use a noncircular PREPUBLICATION_READY predicate. Require completed implementation, migration, tests, decisions and exact-candidate qualification tasks, but exclude Q-03 actual publication/public readback/receipt settlement from this precondition. DISTRIBUTION_SETTLED requires Q-03 afterward. Test both populations explicitly; a readiness record never claims the release already exists.
- For a new Pi npm publication preserve GITHUB_SHA == selected SOURCE_COMMIT at the actual release event. Delayed readiness cannot override this provenance check. If main advances and the original matching event/run cannot publish, select/rebuild/requalify an eligible exact source and unused version as required; never substitute a trusted-sha or weaken ADR0044. Byte-identical already-published npm recovery remains a separate observed-state case.

### Tests

- Missing, forged, stale, wrong-source, wrong-run, wrong-artifact, unknown-cell and partial readiness all prevent first publication.
- Valid exact receipt admits publication; subsequent missing-receipt recovery does not repeat completed package/channel effects.
- Unrelated pre-existing target release behavior remains governed by its approved policy.
- PREPUBLICATION_READY can be valid while Q-03/publication is pending; DISTRIBUTION_SETTLED cannot be valid before every required external readback/receipt is observed. No circular readiness dependency.
- Qualification completes after main advances: mismatched Pi event/source refuses a new npm publish; matching exact source permits it; already-published byte-identical recovery follows its own policy.

### Acceptance

- Exact built bytes and required installed scenarios are verified before first major publication.
- Automatic main release cannot outrun final qualification.

### Rollback

- Keep publication pending before effects; after effects, reconcile forward and publish corrected new versions where needed. No moved tags or overwritten registry versions.


## R-04 · Record actual route-publication observations without authorizing removals

**Status:** PLANNED. **Owner:** release-and-integration.

**Implementation prerequisites:** R-01, P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Phase

3

### Owner

release-and-integration

### Finding ids

- C-F04

### Source paths

- .github/scripts/check_command_route_release_state.py
- .github/workflows/ci.yml
- .github/workflows/release.yml
- .github/actions/publish-target/action.yml

### Implementation

- Wire the existing non-mutating publication observer after observed target settlement and persist its exact source/tag/release identity and outcome.
- Distinguish planned, tag-only, draft, published, unavailable and mismatch. Observation failure records unknown; it must not claim successful publication or silently undo external effects.
- Keep compatibility-removal authorization separate. A major version or elapsed clock alone does not authorize alias removal; the default handoff preserves existing aliases.

### Tests

- Observer runs against published, tag-only, draft, missing, API unavailable and identity mismatch fixtures.
- Receipt recovery followed by observation is idempotent; policy-only declarations cannot become published evidence.

### Acceptance

- Publication clock has actual observation evidence.
- No alias removal occurs without its distinct approved conditions.

### Rollback

- Keep observations as historical evidence; revert consumer projection if necessary, leaving publication unknown rather than inventing freshness.


## SBX-C03 · Unify sandbox resource observations and truthful compensation

**Status:** PLANNED. **Owner:** sandbox.

**Implementation prerequisites:** SBX-C02, P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Finding ids

- SF10

### Source paths

- plugins/ca-sandbox/tools/registry.ts
- plugins/ca-sandbox/tools/destroy.ts
- plugins/ca-sandbox/tools/create.ts
- plugins/ca-sandbox/tools/claude-inside.ts
- plugins/ca-sandbox/tools/docker.ts
- plugins/ca-sandbox/tools/create.test.ts
- plugins/ca-sandbox/tools/claude-inside.test.ts
- plugins/ca-sandbox/tools/teardown.test.ts

### Source refs

- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/tools/registry.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/tools/destroy.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/tools/create.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/tools/claude-inside.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/tools/docker.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/tools/create.test.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/tools/claude-inside.test.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/tools/teardown.test.ts

### Proposed paths

None.

### Behavior change

Failed resource discovery remains unavailable, and compensation claims destroyed only after target-aware absence is observed.

### Implementation steps

- Reuse the explicit destroy/prune observed/unknown contract for registry listings, create compensation and Claude-inside firewall failure.
- Use an un-aborted bounded cleanup context; inspect rm/stop results and re-observe target absence before claiming destruction.
- Retain created container/volume/temp staging IDs until cleanup is confirmed; record partial cleanup without broadening selected targets.
- Propagate cancellation through clone/build helper paths and bound helper cleanup.
- Expose empty-known versus unavailable in CLI/UI output.

### Existing behavior to preserve

- Explicit target set, no-ID prune semantics, keep-volume exception and unrelated/new sandbox preservation.
- Runtime isolation guards and separate Claude-inside entrypoint.

### Tests

**acceptance**

- Known zero resources displays empty; failed listing displays unavailable.
- Firewall/create failure with successful verified compensation reports destroyed; failed compensation retains exact resource IDs.

**rejection and failure**

- Pre-aborted signal, denied Docker, nonzero rm, relist failure and temp removal failure never yield a false clean/destruction statement.

**concurrency and interruption**

- Container created during another target cleanup stays untouched; cancel during each create/build/firewall phase retains recoverable ownership.
- Retry re-observes the original frozen target set.


### Completion evidence

- Fault-injected unit cases and real Docker resource verification for compensation and partial cleanup.
- No ignored cleanup return path remains in owned create/Claude compensation routes.

### Rollback

- Keep read-only registry/recovery available; never delete unselected resources to restore a clean label.

### Claim delta

- Unknown discovery is distinct from no resources; cleanup action requested is distinct from absence observed.

### Adr actions

None.


## SBX-D01 · Derive sandbox prerequisites from actual supported build capabilities

**Status:** PLANNED. **Owner:** sandbox.

**Implementation prerequisites:** SBX-C01, P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Finding ids

- SW-F01

### Source paths

- plugins/ca-sandbox/commands/sandbox.md
- plugins/ca-sandbox/skills/sandbox-lifecycle/SKILL.md
- plugins/ca-sandbox/README.md
- plugins/ca-sandbox/tools/build.ts
- plugins/ca-sandbox/tools/build.test.ts

### Source refs

- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/commands/sandbox.md
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/skills/sandbox-lifecycle/SKILL.md
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/README.md
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/tools/build.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/tools/build.test.ts

### Proposed paths

None.

### Behavior change

Installed instructions permit the existing supported Node/Python fallback when Nixpacks is absent and still refuse unsupported stacks.

### Implementation steps

- Own a concise driver capability/prerequisite contract and project its effective preflight into command, skill and README.
- Tie fallback eligibility to actual detected stack/builder behavior; no blanket Nixpacks STOP when a verified fallback is available.
- Link build-cache version/provenance semantics from SBX-C01 rather than duplicate an optimistic reuse promise.

### Existing behavior to preserve

- Hard failure for unsupported stack or required Docker/tool failure; no automatic unsupported dependency installation.

### Tests

**acceptance**

- Nixpacks absent + supported Node/Python fallback proceeds to the same driver path described in docs.
- Nixpacks present path remains supported.

**rejection and failure**

- Unsupported stack without builder remains a clear preflight refusal.

**concurrency and interruption**

- Capability observations are revalidated before build when tool availability changes; no additional global lock required.


### Completion evidence

- Driver fixture matrix plus generated/checked command-skill-README assertions against capability owner.

### Rollback

- Restore bounded accurate prerequisite text; do not reintroduce a false blanket dependency requirement.

### Claim delta

- Fallback support is stack-specific and evidence-bound.

### Adr actions

None.


## HOST-D01 · Correct Claude dormant maintenance and write-scope claims

**Status:** PLANNED. **Owner:** hooks-workflows.

**Implementation prerequisites:** P-02, HW-16.
**Completion prerequisites:** None.
**Decision dependencies:** None.

**Shared implementation owner:** HW-16. Coordinate one change; do not duplicate competing owners.

### Cross-owner coordination


##### HW-16

**kind**

shared-claim-owner

**use**

Coordinate one source-consistent host maintenance/write-scope correction.


### Finding ids

- SW-F09

### Source paths

- plugins/ca/README.md
- core/pysrc/session-start.py
- core/pysrc/_githooks.py
- core/pysrc/_taskexcludelib.py

### Source refs

- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca/README.md
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/pysrc/session-start.py
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/pysrc/_githooks.py
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/pysrc/_taskexcludelib.py

### Proposed paths

None.

### Behavior change

Describe repository enforcement activation separately from host startup maintenance and opted-in Git metadata writes.

### Implementation steps

- Document mode-marker cleanup/owned global statusline healing that occurs before dormant repository exit.
- List opted-in Git hook and Git-common info/exclude/bookkeeping writes outside .codearbiter with their existing consent/ownership boundaries.
- Cross-check hook owner implementation changes and generated host docs so corrections do not drift.
- Treat this as claim correction, not removal of useful maintenance or broader write permission.

### Existing behavior to preserve

- Useful owned host maintenance, existing init opt-in, shared Git-common path ownership and dormant repository enforcement behavior.

### Tests

**acceptance**

- README claims map to actual startup order and opt-in paths; clean dormant repository still avoids governed repository enforcement.

**rejection and failure**

- No claim hooks always do nothing before active check; no blanket writes-only-.codearbiter statement.

**concurrency and interruption**

- Documentation update follows final hook behavior; no new runtime race or permission change introduced by this task.


### Completion evidence

- Hook-owner reviewed source/claim diff and exact candidate installed README consistency.

### Rollback

- Revert only inaccurate claim changes; preserve runtime behavior and user-owned configuration.

### Claim delta

- Host maintenance, repository enforcement and opted-in Git metadata writes have different scopes.

### Adr actions

None.


## HW-04 · Prove shared npm launch-binding boundary across Python and Go

**Status:** PLANNED. **Owner:** hooks-workflows.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** NT-04.
**Decision dependencies:** None.

### Cross-owner coordination


##### Record

**task id**

NT-04

**owner**

native_states

**reason**

Owns N-F09 Go schema/role/completion reconciliation.


### Original finding ids

- HOOK-F04

### Baseline machine ids

- hooks:verifier

### Existing owner paths

- core/pysrc/_artifactauthoritylib.py
- core/artifacts/internal/observation/contract.go
- core/artifacts/internal/observation/runner_contract.go
- core/artifacts/internal/evidence/completion_workspace.go

### Proposed new paths

None.

### Semantic change scope

Cross-language contract correction; legitimate producer bindings must be accepted without broadening unrelated roles or evidence authority.

### Implementation plan

- Coordinate schema, role cardinalities, and completion checks with native NT-04.
- Use shared boundary fixtures for base launch roles plus 0/30/31/32 workspace manifests and the supported platform launch shapes.
- Preserve exact executable/manifest hashes, argv/cwd binding, actual host launch observation, and historical profile handling.

### Preserved invariants

None.

### Tests

**existing test paths**

- .github/scripts/test_artifact_npm_nested_launch.py
- .github/scripts/test_artifact_authority_adapter.py

**proposed test paths**

None.

**required cases**

- POSIX producer 30/31/32 workspaces yields valid 32/33/34-file bindings and native completion agrees.
- Supported Windows launch shape reaches its declared role-derived maximum (source bound 37); verify on the required platform cell.
- 33 workspace-manifest roles, duplicate roles, changed fingerprints, unknown roles, and malformed bindings remain rejected.
- Old supported host/profile fixtures keep their declared bounds.

**execution state**

not run for this handoff; receiving agent must read test owners and execute the selected matrix


### Acceptance criteria

- No admitted producer output is refused solely by the former completion max32 mismatch.
- The canonical role-based upper bound is identical at validation and completion.
- A source-only Windows bound is not reported as executed Windows evidence.

### Completion evidence

- Record the exact implementation commit and any source drift from the audited baseline before making current-state claims.
- List changed canonical owners and generated derivatives; retain an exact source/package distinction.
- Attach focused meaningful test output and observed effect/failure evidence; an exit code alone is not proof of the intended target state.
- audit-work/probe_launch_binding.py and probe_launch_binding_results.json; probe did not execute project test commands.

### Rollback

- Ship producer/consumer rollback as a compatible pair; retain readers for already issued supported observations.
- Do not silently reinterpret a previously rejected result as verified success.

### Adr actions

None.

### Coverage scope

None


## HW-08 · Link corrected reviewer attempts to fresh immutable requests

**Status:** PLANNED. **Owner:** hooks-workflows.

**Implementation prerequisites:** HW-07, P-02.
**Completion prerequisites:** NT-11.
**Decision dependencies:** None.

### Cross-owner coordination


##### Record

**task id**

NT-11

**owner**

native_states

**reason**

Verifies fresh valid observed pass under existing native profiles and preserves terminal history.


### Original finding ids

- W-F02
- HOOK-B01

### Baseline machine ids

- hooks:authority-request
- hooks:claude-review
- hooks:codex-review

### Existing owner paths

- core/surface/agents/authority-reviewer.md
- core/surface/includes/reviewer-contract.md
- core/pysrc/_artifactauthoritylib.py

### Proposed new paths

None.

### Semantic change scope

User-selected reviewer recovery: a corrected submission may create a fresh linked request, while old request finality and authority-bearing native result schemas remain intact.

### Implementation plan

- Distinguish exact transport retry from a corrected logical submission in adapter results and help.
- Preserve old rejected/failed/changes-requested requests; create a new request/attempt with current frozen target, contract, context and actual host child launch when needed.
- Keep the current not-under-the-same-request finality rule; do not misstate it as a ban on all future requests.
- Consume NT-11 native compatibility results; avoid extra fields in closed old observations and avoid synthetic first_stop labels.
- Keep W-F03 severity/disposition decision separate.

### Preserved invariants

- A valid native pass remains bound to actual captured launch and current target/contract.
- Actual denial remains an authority constraint.

### Tests

**existing test paths**

- .github/scripts/test_artifact_authority_adapter.py
- .github/scripts/test_artifact_installed_host.py
- .github/scripts/test_review_funnel.py

**proposed test paths**

- .github/scripts/test_review_resubmission.py

**required cases**

- Malformed reviewer result→fresh corrected request with real new capture→valid pass.
- Prior rejection/denial remains immutable and auditable.
- Exact response-loss replay is idempotent; later stop of the same child cannot be treated as a new first_stop.
- Changed target/contract and nonindependent steered child reject stale evidence.
- changes_requested and BLOCK findings never become success receipts solely through resubmission.

**execution state**

not run for this handoff; receiving agent must read test owners and execute the selected matrix


### Acceptance criteria

- Receiving agent demonstrates a supported corrected-review flow on each claimed host, with real attempt linkage.
- No new implicit permission, reviewer independence exception, or denial-to-pass mutation is introduced.

### Completion evidence

- Record the exact implementation commit and any source drift from the audited baseline before making current-state claims.
- List changed canonical owners and generated derivatives; retain an exact source/package distinction.
- Attach focused meaningful test output and observed effect/failure evidence; an exit code alone is not proof of the intended target state.

### Rollback

- Retain previously written attempt links and terminal requests; old readers must ignore or read versioned metadata safely.
- Rollback can stop new retry creation without invalidating observed independent results or overwriting history.

### Adr actions

None.

### Coverage scope

W-F02 supplies the validation-versus-authorization analogy; reviewer resubmission is additionally and explicitly user-authorized, not claimed as an original debug-only runtime defect.


## HW-12 · Add idempotent selected-owner harvest adapters and outcome reconciliation

**Status:** PLANNED. **Owner:** hooks-workflows.

**Implementation prerequisites:** HW-11, P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Original finding ids

- W-F04
- HOOK-B04

### Baseline machine ids

- hooks:work-owner
- hooks:taskwrite
- hooks:knowledge

### Existing owner paths

- core/pysrc/_worklib.py
- core/pysrc/work.py
- core/pysrc/taskwrite.py
- core/pysrc/_taskboardlib.py
- core/surface/includes/harvest.md

### Proposed new paths

None.

### Semantic change scope

New recoverable local promotion adapters; retain existing owner choice, origin deduplication, confirmation and branch contingency.

### Implementation plan

- Call the selected native or legacy owner; ambiguous/changed ownership makes only the affected obligation unavailable.
- Reconcile response loss by exact operation/origin lookup across active/archive before any retry; do not treat legacy operation ID echoes as a durable ledger.
- Implement a narrow CAS/idempotent adapter for nonblocking deferred-decision append and decline audit if existing owners cannot provide that guarantee.
- Route blocking decisions to existing dependent-only resolution; do not auto-confirm or silently retag them.
- Record per-item target readback receipts and partial-batch outcomes; no status-only parent completion.

### Preserved invariants

- Exact origin including suffix is unchanged.
- Origin matching is not same-title guessing.
- Archive-first legacy recovery remains valid.

### Tests

**existing test paths**

- .github/scripts/test_taskwriter.py
- .github/scripts/test_taskboardlib.py
- .github/scripts/test_artifact_work_cli.py

**proposed test paths**

- .github/scripts/test_workflow_harvest_recovery.py

**required cases**

- Native target committed/response lost creates exactly one item and settles on readback.
- Legacy origin replay across open/archive does not duplicate; same-title different-origin item is not selected.
- Deferred decision/decline append commits once despite response loss.
- Dual owner, changed project identity, unknown target outcome, blocked decision, and changed source preserve unresolved state.
- One batch failure leaves earlier successful receipts and later pending items intact.

**execution state**

not run for this handoff; receiving agent must read test owners and execute the selected matrix


### Acceptance criteria

- All enabled adapters have a demonstrated idempotency/reconciliation contract before retries ship.
- Interactive promotion still uses its existing scoped confirmation; sprint uses only already valid in-scope authority.
- No automatic remote issue, staging, completion, archive, or cleanup occurs.

### Completion evidence

- Record the exact implementation commit and any source drift from the audited baseline before making current-state claims.
- List changed canonical owners and generated derivatives; retain an exact source/package distinction.
- Attach focused meaningful test output and observed effect/failure evidence; an exit code alone is not proof of the intended target state.

### Rollback

- Disable a failing kind adapter while retaining its unresolved intent and receipts.
- Do not remove target items already created or restore old board files over later edits.

### Adr actions

None.

### Coverage scope

None


## NT-06 · Declare actual read effects, platform locks and bounded task-context reads

**Status:** PLANNED. **Owner:** native.

**Implementation prerequisites:** NT-03, P-02.
**Completion prerequisites:** NT-01.
**Decision dependencies:** None.

### Finding ids

- N-F05
- N-F07

### Classification

behavior-preserving claim/contract correction

### Owner

Native read/operations/store owners and generated documentation owner

### Decision status

authorized compatibility/preservation work

### Independent work policy

A task-specific unresolved decision or conflict blocks only its consumers; continue unrelated authorized work.

### Sources


##### Record

**path**

core/artifacts/internal/read/read.go

**symbol**

Page

**lines**

- 320

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/read/read.go


##### Record

**path**

core/artifacts/internal/store/fs_lock_darwin.go

**symbol**

nativeLock

**lines**

- 12

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/store/fs_lock_darwin.go


##### Record

**path**

core/artifacts/internal/store/fs_portable.go

**symbol**

lockFile

**lines**

- 624

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/store/fs_portable.go


##### Record

**path**

core/artifacts/internal/store/fs_lock_windows.go

**symbol**

ObservationLock

**lines**

- 59

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/store/fs_lock_windows.go


##### Record

**path**

core/artifacts/internal/operations/engine.go

**symbol**

initStore

**lines**

- 57

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/operations/engine.go


##### Record

**path**

core/artifacts/internal/operations/task_context.go

**symbol**

taskContext

**lines**

- 13

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/operations/task_context.go


##### Record

**path**

core/artifacts/internal/operations/task_check.go

**symbol**

assessTaskChecks

**lines**

- 151

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/operations/task_check.go


##### Record

**path**

core/artifacts/internal/operations/input_scope.go

**symbol**

scopedInputDigest

**lines**

- 39

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/artifacts/internal/operations/input_scope.go


### Files

- core/artifacts/internal/read/read.go
- core/artifacts/internal/operations/task_context.go
- core/artifacts/internal/operations/task_check.go
- core/artifacts/internal/operations/input_scope.go
- core/artifacts/internal/operations/engine.go
- core/artifacts/internal/store/fs_lock_darwin.go
- core/artifacts/internal/store/fs_lock_windows.go
- core/artifacts/internal/store/fs_portable.go

### Implementation steps

- Replace overbroad no-write/no-source-read comments with actual operation/mode/platform effects.
- Classify contextual token writes separately from exact read, and metadata initialization separately from user/canonical changes.
- Document Darwin shared-lock metadata creation, Windows existing-only observation locking and Linux backend behavior without changing locking semantics to satisfy prose.
- Retain bounded source applicability reads in taskContext through assessTaskChecks/scopedInputDigest and disclose the declared input scope and unknown/omitted portions.
- Keep exact/batch reads from claiming current worktree applicability they did not assess; no expanded source scan or automatic command execution.

### Acceptance sequences


##### Read modes and metadata

**steps**

- Run exact and contextual reads with present/absent metadata on each native platform
- Compare created files and lock access
- Run Windows read-only existing metadata path

**expected**

- Declared traits match actual effects; existing locking safeguards remain; unsupported/missing metadata is explicit

**existing owner files**

- core/artifacts/internal/read/read_test.go
- core/artifacts/internal/operations/read_only_windows_test.go
- core/artifacts/internal/store/readonly_lock_windows_test.go
- core/artifacts/internal/operations/concurrent_readers_test.go

**new test required**

True


##### Bounded context applicability

**steps**

- Record a command check
- Change declared task/shared source
- Read task-context
- Change unrelated source and exact-read same task

**expected**

- Relevant change affects applicability; unrelated source does not trigger broader claims; no checks execute; exact read keeps currentness unassessed

**existing owner files**

- core/artifacts/internal/operations/input_scope_test.go
- core/artifacts/internal/operations/task_context_test.go
- core/artifacts/internal/operations/task_check_test.go

**new test required**

True


### Commands


##### Record

**command**

go test ./internal/read ./internal/operations ./internal/store

**cwd**

core/artifacts

**note**

Planned invocation; not executed in this handoff.


### Backward read

No persisted model change; retain old read modes and locks. Additional diagnostics need existing response compatibility checks.

### Migration

None; canonical/generator descriptions change as one source-owned correction.

### Rollback

Revert only descriptors/docs if needed, preserving safe lock and source-read behavior.

### Completion evidence

- Actual native-platform file-effect matrix
- Scoped/unrelated-source sequence
- Exact read no-current-proof assertion


## PI-D03 · Implement authenticated child proxies and parent-owned effect execution

**Status:** PLANNED. **Owner:** pi.

**Implementation prerequisites:** PI-D01, PI-D02, P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Finding ids

- SF01

### Source paths

- plugins/ca-pi/tools/src/child-extension.ts
- plugins/ca-pi/tools/src/runner.ts
- plugins/ca-pi/tools/src/process-tree.ts
- plugins/ca-pi/tools/src/windows-supervisor.ts
- plugins/ca-pi/tools/src/child-env.ts
- plugins/ca-pi/tools/src/inference-broker.ts
- plugins/ca-pi/tools/src/background-jobs.ts
- plugins/ca-pi/tools/src/runtime-resolver.ts
- plugins/ca-pi/tools/build.mjs
- plugins/ca-pi/tools/test/runner-isolation.test.ts
- plugins/ca-pi/tools/test/windows-supervisor.test.ts
- plugins/ca-pi/tools/test/runner-broker-lifecycle.test.ts

### Source refs

- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/child-extension.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/runner.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/process-tree.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/windows-supervisor.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/child-env.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/inference-broker.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/background-jobs.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/runtime-resolver.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/build.mjs
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/test/runner-isolation.test.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/test/windows-supervisor.test.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/test/runner-broker-lifecycle.test.ts

### Proposed paths

- plugins/ca-pi/tools/src/delegation-channel.ts
- plugins/ca-pi/tools/src/delegated-executor.ts

### Behavior change

Child write/edit/bash tools become explicit bounded proxies to a parent-owned executor; successful admission no longer depends on a child TUI or child self-grant.

### Implementation steps

- Create a purpose-separated local operation transport with per-child token and parent registry binding; do not reuse inference-broker tokens or general RPC confirmation messages.
- Replace the 32-byte-only fd3 format with the agreed bounded versioned envelope for matching new bundles; keep strict old/new refusal and one-shot nonce semantics. Test raw Windows fd3 forwarding without repurposing supervisor fd4–fd7.
- Keep the existing child final guard and source owner, but route the delegated branch to proxy execution instead of local mutation factories.
- Parent executes admitted effects, owns deadlines/output limits/managed process trees, and returns observed results. A boolean approval followed by child-local mutation is not sufficient.
- For shell execution verify the exact supported Pi options before use. Do not invent an environment option on the generic createBashToolDefinition record. Reuse/extract internal piShellLaunch/process-tree behavior or an owned helper with qualified tool-result adaptation.
- Use a bounded credential-blind command environment/private home and operator setting projection; never inherit full parent process.env or expose inference/operation tokens to project commands.
- Keep inference endpoint/credential authority separate, close/revoke both channels on child retirement, and choose one owner for correlated post-write bridge effects.

### Existing behavior to preserve

- Exact Node/Pi/package/charter/skills launch validation; no project extension/context loading; private environment; broker-supported provider restrictions; no recursive dispatch/farm in child.
- Existing shell prefix/platform behavior must be preserved or explicitly rejected with a bounded diagnostic, never silently ignored.
- No promise of transitive filesystem or network confinement in the trusted-host profile.

### Tests

**acceptance**

- A packaged child sends a real write/edit/command request through the channel; parent performs it and child receives the corresponding bounded tool result.
- Local transport and process supervision work on every declared supported OS/architecture; token is absent from logs, prompts and subprocess environments.
- Read-only reviewers and compaction retain their separate capabilities.

**rejection and failure**

- Wrong child/run/token/purpose/version, nonlocal peer, invalid method/content type, oversize frame, excessive concurrent requests, malformed fd3, replayed bootstrap and unexpected RPC UI request execute nothing.
- Unsupported upstream runtime or unavailable executor yields explicit degraded authorship, not unguarded native fallback.
- Tests attempt to read known sentinel provider credentials/tokens through command environment and final output; no leak is accepted.

**concurrency and interruption**

- Child dies during bootstrap, request, result, or cleanup; parent revokes and closes listeners while preserving owned settlement.
- Cancellation during Windows containment readiness never delivers mutation capability before readiness.
- Parent/child mixed-version bundles fail before task effects.


### Completion evidence

- Source and built-bundle protocol tests, exact managed process traces and credential-negative fixtures.
- Artifact receipts distinguish fake provider/bridge pieces from real host/real executor routes.

### Rollback

- Revoke channel tokens, deny new requests, settle owned processes and retain effect journals before disabling the feature.
- Old bundles must not adopt new records or bootstrap envelopes permissively.

### Claim delta

- New delegation channel is an internal Arbiter protocol, not an upstream Pi API.
- Host-trusted exact commands can run project code and use host resources under that profile.

### Adr actions

None.


## R-08 · Derive site publication labels from observed release state

**Status:** PLANNED. **Owner:** release-and-integration.

**Implementation prerequisites:** R-01, R-04, P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Phase

3

### Owner

release-and-integration

### Finding ids

- SX-F01

### Source paths

- site/scripts/release-applicability.ts
- site/src/release-applicability-presentation.ts
- .github/actions/publish-target/action.yml

### Implementation

- Supply a durable observed publication record keyed to immutable tag/source/payload identity. Stable local tags alone cannot be labeled published.
- When publication evidence is absent or unavailable, render that state honestly while retaining valid content/source applicability information.
- Do not make an obsolete receipt ledger a blanket prerequisite for unrelated new releases; use the current publication owner and preserve stale/historical labels.

### Tests

- Highest stable local tag is draft or tag-only; empty receipt ledger; actual published identity; stale receipt; wrong payload/source; offline build.
- Build rendered pages and assert visible label, underlying JSON endpoint and proof applicability agree.

### Acceptance

- Tag and published-release states stay distinct through generated data, rendered page and source API.

### Rollback

- Revert the presentation to explicit unknown/tag labeling; preserve exact historical records.


## SBX-D03 · Correct host staging and effective network-policy claims

**Status:** PLANNED. **Owner:** sandbox.

**Implementation prerequisites:** SBX-C03, P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Finding ids

- SW-F04
- SW-F05

### Source paths

- plugins/ca-sandbox/commands/sandbox.md
- plugins/ca-sandbox/skills/sandbox-lifecycle/SKILL.md
- plugins/ca-sandbox/README.md
- plugins/ca-sandbox/tools/create.ts
- plugins/ca-sandbox/tools/run.ts
- plugins/ca-sandbox/tools/network.ts

### Source refs

- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/commands/sandbox.md
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/skills/sandbox-lifecycle/SKILL.md
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/README.md
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/tools/create.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/tools/run.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-sandbox/tools/network.ts

### Proposed paths

None.

### Behavior change

Docs state actual host temporary build staging and ordinary offline runtime behavior; standalone allowlist helper or Claude-inside firewall does not imply ordinary integration.

### Implementation steps

- Describe temporary host checkout copy location/lifetime and observed cleanup separately from runtime no-host-bind/no-socket/no-privileged guards.
- Expose requested versus effective network policy and current capability availability. Ordinary NETWORKED_POLICIES-empty path remains offline.
- Mark unsupported ordinary allowlist selection unavailable instead of describing it as applied; retain the separate Claude-inside networking contract.
- Any future ordinary network mode is a separately approved implementation/verification task, not an incidental documentation correction.

### Existing behavior to preserve

- Current offline ordinary runtime, actual isolation flags, host staging cleanup owner and supported separate Claude-inside behavior.

### Tests

**acceptance**

- Help/README/skill accurately show host staging and effective offline mode; cleanup unknown appears as unknown.
- Driver invocation assertions confirm no host bind/socket/privileged expansion.

**rejection and failure**

- A helper function existing on disk cannot set ordinary allowlist-supported=true; no claim of zero host source bytes while staging occurs.

**concurrency and interruption**

- Cancelled build with incomplete temp cleanup retains accurate lifetime/unknown status; policy availability change cannot silently widen network.


### Completion evidence

- Claim-to-owner matrix and driver fixtures for requested/effective policy; exact installed docs match candidate implementation.

### Rollback

- Preserve offline behavior; revert inaccurate new wording without enabling network or deleting user resources.

### Claim delta

- Runtime mount isolation is separate from host build staging.
- Effective offline behavior is separate from optional helper capability.

### Adr actions

None.


## HW-13 · Register harvest obligations at discovery in each workflow producer

**Status:** PLANNED. **Owner:** hooks-workflows.

**Implementation prerequisites:** HW-12, P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Original finding ids

- W-F04
- HOOK-B04

### Baseline machine ids

- hooks:knowledge
- hooks:work-owner

### Existing owner paths

- core/surface/includes/harvest.md
- core/surface/skills/tdd/SKILL.md
- core/surface/skills/brainstorming/SKILL.md
- core/surface/skills/writing-plans/SKILL.md
- core/surface/skills/commit-gate/SKILL.md
- core/surface/commands/checkpoint.md
- core/surface/SPRINT.md

### Proposed new paths

None.

### Semantic change scope

Workflow behavior change: durable capture happens when a qualifying bounded candidate is known; promotion remains at the existing authorized step.

### Implementation plan

- Update every declared harvest producer with exact registration inputs, source origin and source binding at discovery.
- Keep commit-gate harvest before staging and retain work-commit contingency under ADR0008.
- Make registration failure visible without stopping unrelated work or claiming conversation-only material is durable.
- Use bounded producer batches and capture only sanitized candidate text; never full transcripts or secret-bearing raw evidence.
- Remove stale terminal-only/no-backstop claims once HW-11/12/14 actually implement recovery.

### Preserved invariants

None.

### Tests

**existing test paths**

- .github/scripts/test_build_surface.py
- .github/scripts/test_debug_workflow.py
- .github/scripts/test_artifact_workflow.py

**proposed test paths**

- .github/scripts/test_workflow_recovery_surface.py

**required cases**

- Each producer can be interrupted before terminal harvest and resume the registered exact candidate.
- No qualifying candidate creates no fictitious successful obligation.
- An unregistered candidate is not claimed recovered.
- Branch abandonment/source change does not silently publish/promote on another branch.
- Rendered host resources preserve exact origin suffix and current helper resolution.

**execution state**

not run for this handoff; receiving agent must read test owners and execute the selected matrix


### Acceptance criteria

- Every declared harvest producer has a source-level registration and terminal settlement path.
- The producer contract reports durable:false honestly when local storage cannot commit.
- No workflow gains an extra universal gate for ordinary authorized work.

### Completion evidence

- Record the exact implementation commit and any source drift from the audited baseline before making current-state claims.
- List changed canonical owners and generated derivatives; retain an exact source/package distinction.
- Attach focused meaningful test output and observed effect/failure evidence; an exit code alone is not proof of the intended target state.

### Rollback

- Stop new registration calls while retaining already registered obligations and explicit resume support.
- Do not return to claiming guaranteed harvest if terminal-only behavior is restored.

### Adr actions

- ADR0008 implementation evidence for early local capture plus unchanged terminal promotion/staging.

### Coverage scope

None


## NT-12 · Verify the integrated native cohort and migration before major release

**Status:** PLANNED. **Owner:** native.

**Implementation prerequisites:** NT-01, NT-02, NT-03, NT-04, NT-05, NT-06, NT-07, NT-08, NT-09, NT-10, NT-11, P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Finding ids

None.

### Classification

integration verification gate; no new product semantics

### Owner

Receiving CLI native integration owner with release/host owners

### Decision status

required before native completion; release owned by root handoff

### Independent work policy

A task-specific unresolved decision or conflict blocks only its consumers; continue unrelated authorized work.

### Sources


##### Record

**path**

.github/workflows/ci.yml

**symbol**

artifact native tests, race gate and mixed-schema fixture

**lines**

- 738
- 763
- 960
- 981

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:.github/workflows/ci.yml


##### Record

**path**

tools/go_test_parallel.py

**symbol**



**lines**

None.

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:tools/go_test_parallel.py


##### Record

**path**

tools/generate-artifact-types.py

**symbol**



**lines**

None.

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:tools/generate-artifact-types.py


##### Record

**path**

tools/test-artifact-mixed-schema.py

**symbol**



**lines**

None.

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:tools/test-artifact-mixed-schema.py


##### Record

**path**

tools/test-artifact-work-old-client.py

**symbol**



**lines**

None.

**ref**

arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:tools/test-artifact-work-old-client.py


### Files

- core/artifacts/**
- tools/test-artifact-mixed-schema.py
- tools/test-artifact-work-old-client.py
- tools/generate-artifact-types.py
- .github/workflows/ci.yml

### Implementation steps

- Run focused new and preservation sequences on the integration branch, then the existing complete population, race, type generation and public-surface checks for exact final source.
- Run actual native Linux/Darwin/Windows persistence/path/lock and launch-binding tests. Distinguish cross-compiled output from executed platform tests.
- Exercise old→candidate version matrix, ordinary work with failed/unknown checks, dependency-scoped conflicts, interrupted migration, lost acknowledgement, corrected reviewer attempt and supported Pi scoped mutation/recovery.
- Prove canonical/generator/host adapters all agree on operations, output namespaces, role limits and progress/evidence semantics before calling native work complete.
- Record exact commands/toolchain/platform/source/binary digests, successful and negative outcomes, and outstanding blockers. No source-only finding becomes runtime verified because the code was edited.
- Keep branch isolated until the whole corpus is implemented/tested; root release owner then qualifies exact installed/distributed artifacts and new major release. No partial slice shipping.

### Acceptance sequences


##### Whole native sequence

**steps**

- New/legacy repo ordinary context preview
- Snapshot and completion
- Start/report/record failure
- Block only dependency chain
- Correct reviewer attempt
- Retire checked task/checkpoint
- Interrupt and resume mutation
- Run old client against migrated store
- Preserve later writes and export/restore separate snapshot

**expected**

- Every domain contract composes; no hidden output rejection, invented proof, orphaned history, duplicate effect, cleared stop or silent downgrade

**existing owner files**

- Existing native operations/evidence/store/conformance suites
- tools/test-artifact-mixed-schema.py
- Installed-host qualification owners

**new test required**

True


### Commands


##### Record

**command**

python tools/go_test_parallel.py --module core/artifacts --build-flag=-race

**cwd**

.

**note**

Existing Linux CI race command; invoke with pinned Go 1.27.1 unless integration deliberately updates the toolchain through its owning gates.


##### Record

**command**

go test ./...

**cwd**

core/artifacts

**note**

Planned invocation; not executed in this handoff.


##### Record

**command**

python tools/generate-artifact-types.py --check

**cwd**

.

**note**

Planned invocation; not executed in this handoff.


##### Record

**command**

python .github/scripts/test_artifact_surface.py

**cwd**

.

**note**

Planned invocation; not executed in this handoff.


##### Record

**command**

python tools/test-artifact-mixed-schema.py --old /absolute/old/ca-artifact --candidate /absolute/candidate/ca-artifact

**cwd**

.

**note**

Planned invocation; not executed in this handoff.


##### Record

**command**

python tools/test-artifact-work-old-client.py --old /absolute/old/ca-artifact --candidate /absolute/candidate/ca-artifact

**cwd**

.

**note**

Planned invocation; not executed in this handoff.


### Backward read

All supported historical formats/profiles are exercised against exact clients; unsupported combinations refuse before destructive writes.

### Migration

Actual complete-store, idempotent cutover and forward recovery evidence for final chosen schema—not a mock serializer demonstration.

### Rollback

Publish a concrete retention/recovery playbook preserving later work; tested separate-root restoration. Keep compatibility reader available with new-format stores.

### Completion evidence

- All native findings dispositioned and linked to passing meaningful sequences
- All current user-directed native/host interfaces exercised
- Platform and exact-client matrix
- Branch commit and qualified candidate byte identities
- Remaining limitations explicitly reported to release owner


## PI-D04 · Add exclusive effect claims, durable outcomes and read-only reconciliation

**Status:** PLANNED. **Owner:** pi.

**Implementation prerequisites:** PI-D01, PI-D02, PI-D03, P-02, NT-10.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Cross-owner coordination


##### NT-10

**kind**

implementation-contract

**use**

Bounded host delegation record/file-effect seam after PI-D01; current store is not a source executor.


##### NT-02

**kind**

conditional-contract-integration

**use**

Namespace registration only if journal uses artifact reserved root; separate host bookkeeping otherwise.


##### HW-14

**kind**

downstream-integration-no-hard-cycle

**use**

Shared notice consumes PI-D04 observations and PI-D05 revocation. Agree observation shape now; HW-14 implementation depends on Pi, not the reverse.


##### HW-11

**kind**

contract-coordination

**use**

Shared durable recovery ownership/storage conventions, no mandatory artifact journal.


##### HW-12

**kind**

contract-coordination

**use**

Selected-owner read-only reconciliation; preserve resource scope and no grant restoration.


### Finding ids

- SF01

### Source paths

- plugins/ca-pi/tools/src/audit-sink.ts
- plugins/ca-pi/tools/src/tool-guard.ts
- plugins/ca-pi/tools/src/dispatch.ts
- plugins/ca-pi/tools/src/runner.ts
- plugins/ca-pi/tools/src/extension.ts
- plugins/ca-pi/tools/test/audit-sink.test.ts

### Source refs

- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/audit-sink.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/tool-guard.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/dispatch.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/runner.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/extension.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/test/audit-sink.test.ts

### Proposed paths

- plugins/ca-pi/tools/src/delegation-journal.ts

### Behavior change

Persist operation identity before delegated mutations, deduplicate identical requests, retain uncertain outcomes and recover observations without replaying effects or restoring authority.

### Implementation steps

- Implement bounded versioned records under one agreed host bookkeeping owner with exact owner/repository/worktree identity and exclusive operation IDs. Register with NT-02 only if using the artifact reserved root; do not require that root or a universal host-effect pending guard.
- Use state transitions proposed→admitted→claimed→executing→observed/unknown; persist claim before execution and observed outcome before successful response.
- Do not treat appendAuditLine false as proof no row exists: it can fail after append/sync. Operation journal writes need explicit durable/unknown semantics.
- Same ID+digest returns or joins the stored outcome; same ID+different digest rejects. No second executor is created merely because a response or receipt is missing.
- Track direct-file pre/post observations and command/process references separately. Desired bytes observed after a crash do not prove causal exactly-once execution; never roll back over user edits.
- Implement bounded read-only reconciliation and shared startup/reentry notification. A restart retires grants; records cannot mint new live tokens.
- Read-only/ordinary progress does not require closing every historical recovery item. Only dependent effects wait for relevant unresolved resources.

### Existing behavior to preserve

- Existing permission audit failure policy; redaction; host state path ownership; unrelated workflow progress.
- Native artifact journal/CAS is not automatically an arbitrary source-file executor. NT-10 may choose host-specific bounded storage.
- No automatic replay for arbitrary shell or external effects.
- If a shared store is chosen, its real pending-journal integrity dependency remains until reconciled; this does not turn semantic task/delegation conflicts into a global stop.

### Tests

**acceptance**

- Exactly one persisted claim and one executor under duplicate requests; stable stored response after response loss.
- Fresh parent reports recoverable old observations and issues one bounded notice without recreating authority.
- A disjoint ordinary edit can proceed while an unrelated old effect remains unresolved.

**rejection and failure**

- Linked/junction/hardlinked/foreign-owner journal, corrupt/unknown version, quota overflow, failed durable claim, identity drift and changed request digest do not start new effects.
- A source hash matching intended output after a crash is reported as observed state unless causal completion was independently recorded.

**concurrency and interruption**

- Crash/fault before claim, after claim, before/after effect, before/after outcome write, before response and during restart.
- Concurrent duplicate and differing operations; user edits during recovery; process cleanup unknown; audit bytes written then return false.
- Journal lock/version contention is scoped and bounded, with no global ordinary-work deadlock.


### Completion evidence

- Crash matrix with recorded operation transitions, call counts, resource observations and replay refusal.
- Storage confinement/platform tests for any new primitive and explicit evidence boundaries for non-atomic native file tools.
- Hook owner confirms recovery notice consumes observations only.

### Rollback

- Retain journals and user files; revoke grants; use read-only downgrade reader or refuse unknown schema with actionable inspection.
- Do not delete records to make rollback appear clean and do not compensate arbitrary commands automatically.

### Claim delta

- Separate observed effect from model judgment and from desired-state coincidence.

### Adr actions

- Propose durable effect observation/recovery decision with dependent-resource conflict scope.


## PI-D05 · Complete revocation, expiry, concurrency and settlement ownership

**Status:** PLANNED. **Owner:** pi.

**Implementation prerequisites:** PI-D02, PI-D03, PI-D04, P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Finding ids

- SF01

### Source paths

- plugins/ca-pi/tools/src/extension.ts
- plugins/ca-pi/tools/src/dispatch.ts
- plugins/ca-pi/tools/src/runner.ts
- plugins/ca-pi/tools/src/tool-guard.ts
- plugins/ca-pi/tools/src/process-tree.ts
- plugins/ca-pi/tools/src/background-jobs.ts
- plugins/ca-pi/tools/test/activation.test.ts
- plugins/ca-pi/tools/test/tool-guard.test.ts
- plugins/ca-pi/tools/test/process-tree.test.ts

### Source refs

- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/extension.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/dispatch.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/runner.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/tool-guard.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/process-tree.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/background-jobs.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/test/activation.test.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/test/tool-guard.test.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/test/process-tree.test.ts

### Proposed paths

None.

### Behavior change

Retire authority immediately on lifecycle changes while preserving cleanup/reconciliation, and confine conflicts to dependent resources.

### Implementation steps

- Connect explicit task cancel, timeout, trust withdrawal, plan-mode transition, session switch/fork/reload/unload/shutdown and child close to grant retirement.
- Use a separate settling owner for cleanup and read-only observation so generation invalidation does not abandon owned processes/resources.
- Bound operation queue/concurrency and sequence numbers; retain one author maximum per dispatch. Serialize overlapping owned source effects and reject changed preconditions.
- Require new admission for corrected operations after refusal; permit legitimate corrected debug/reviewer resubmission rather than permanent stale bans.
- Keep global authority loss distinct from dependent-work conflict. Unknown unbounded shell effects need honest resource-scope limitations.
- Make late rendering/activity failures informational and unable to grant, revoke or falsely complete operations.

### Existing behavior to preserve

- Current cancellation limits and platform containment; native planning exception; same-generation direct parent behavior.
- Unrelated tasks/read operations stay available for scoped conflicts.
- Trust withdrawal still retires project-lifecycle mutation authority.

### Tests

**acceptance**

- Task-specific cancel retires only its grant and settles its owned work.
- New valid lifecycle works while old token and pending approval remain unusable.
- Corrected request with new ID and current authority can proceed after a prior refusal.

**rejection and failure**

- Expired/revoked/sibling/stale-generation operations never execute, including after fresh reactivation.
- Source owner/executable settings drift cannot spend prior consent.

**concurrency and interruption**

- Race mode/trust/session transition at each async boundary; old approval versus new session; late child response versus retirement.
- Two calls on same resource serialize or conflict; identical calls deduplicate; disjoint reads continue.
- Cancellation/output overflow with surviving descendant reports containment unverified and holds only affected dependencies.


### Completion evidence

- Race/fault suite on supported platforms with independent admission and settlement assertions.
- No orphan process/token/listener in retirement matrix; retained unknown records when proof is unavailable.

### Rollback

- Disable new admissions, drain/observe existing ownership and preserve unresolved records before reverting lifecycle wiring.
- Never make cleanup disappear by applying stale-UI suppression to it.

### Claim delta

None.

### Adr actions

None.


## HW-06 · Apply dependent-only conflict pauses consistently

**Status:** PLANNED. **Owner:** hooks-workflows.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** PI-D05.
**Decision dependencies:** None.

### Cross-owner coordination


##### Record

**task id**

PI-D05

**owner**

host_site_lifecycle

**reason**

Dependency-scoped parent delegation pause/revocation.


### Original finding ids

- W-F01

### Baseline machine ids

- hooks:append-conflict

### Existing owner paths

- core/surface/commands/conflict.md
- core/surface/SPRINT.md
- core/surface/skills/context-check/SKILL.md
- core/surface/COMMANDS.md
- .codearbiter/decisions/0043-assistive-state-engine.md

### Proposed new paths

None.

### Semantic change scope

User-selected workflow policy change: conflicting rules pause only work whose authority/data/decision dependency intersects the conflict.

### Implementation plan

- Replace universal stop wording with an explicit affected-scope record and dependency reasoning.
- Preserve exact conflicting statements, source references, hierarchy/recency context, and the rule against the agent choosing the resolution.
- Allow unrelated authorized work, including independent mutations within scope; do not restrict continuation to read-only work unless a real boundary requires it.
- Keep explicit global user/host stops global; propagate affected scope through sprint and child delegation.

### Preserved invariants

- No autonomous choice between contradictory governing rules.
- Actual stops and denials remain binding.

### Tests

**existing test paths**

- .github/scripts/test_context_workflow.py
- .github/scripts/test_routing_and_cleanup_surface.py
- .github/scripts/test_build_surface.py

**proposed test paths**

- .github/scripts/test_conflict_scope_surface.py

**required cases**

- Conflict in task A pauses A and actual dependents while independent authorized B continues.
- Shared security/authority dependency correctly expands the affected scope.
- An explicit global stop remains global; no ADR resolution is auto-chosen.
- Rendered Claude/Codex/Pi surfaces agree.

**execution state**

not run for this handoff; receiving agent must read test owners and execute the selected matrix


### Acceptance criteria

- No remaining universal-all-work sentence contradicts the selected dependent-only owner.
- Scope unknown is reported as unknown and conservatively narrowed from evidence; no invented dependency graph or silent authority selection.
- Child task pause/revocation observes the same scope.

### Completion evidence

- Record the exact implementation commit and any source drift from the audited baseline before making current-state claims.
- List changed canonical owners and generated derivatives; retain an exact source/package distinction.
- Attach focused meaningful test output and observed effect/failure evidence; an exit code alone is not proof of the intended target state.

### Rollback

- Revert policy text and generated derivatives together only through an explicit decision change; preserve recorded unresolved conflicts.
- Do not erase decisions or unblock an affected denied operation during rollback.

### Adr actions

- ADR0043 implementation clarification/successor aligned to the user-selected dependency scope.

### Coverage scope

None


## HW-14 · Expose bounded nonblocking startup and reentry recovery on all hosts

**Status:** PLANNED. **Owner:** hooks-workflows.

**Implementation prerequisites:** HW-11, HW-12, P-02.
**Completion prerequisites:** PI-D04, PI-D05.
**Decision dependencies:** None.

### Cross-owner coordination


##### Record

**task id**

PI-D04

**owner**

host_site_lifecycle

**reason**

Parent/child durable outcome observations and recovery.


##### Record

**task id**

PI-D05

**owner**

host_site_lifecycle

**reason**

Revocation/dependent-work conflict scope remains authoritative.


### Original finding ids

- W-F04
- HOOK-B04

### Baseline machine ids

- hooks:startup
- hooks:persona
- hooks:pi-python-bridge
- hooks:codex-pretool

### Existing owner paths

- core/pysrc/session-start.py
- core/pysrc/prompt-submit.py
- core/pysrc/_standuplib.py
- core/surface/commands/standup.md
- core/surface/commands/status.md
- plugins/ca-pi/hooks/pi-bridge.py
- plugins/ca-pi/tools/src/bridge.ts
- plugins/ca-pi/tools/src/extension.ts
- plugins/ca-codex/hooks/pre-tool-adapter.py

### Proposed new paths

None.

### Semantic change scope

New bounded read-only continuation notice; automatic startup/reentry never executes promotion or restores authorization.

### Implementation plan

- Read an existing ledger only for an already active project; missing/dormant state does not create directories or activate the project.
- Share complete/partial/unavailable summary and opaque cursor across host event seams and explicit status/standup.
- Deduplicate presentation by session/ledger revision without deleting underlying obligations; keep notification independent of persona delivery state.
- Consume Pi-D04 observations through supported parent delegation paths; inspection/reconciliation cannot resurrect a revoked child grant.
- Expose a bounded explicit resume route and explain busy/unavailable reasons without a new universal permission prompt.

### Preserved invariants

None.

### Tests

**existing test paths**

- plugins/ca/hooks/tests/test_session_start.py
- plugins/ca/hooks/tests/test_standup.py
- .github/scripts/test_prompt_submit.py
- plugins/ca-pi/tools/test/bridge.test.ts
- plugins/ca-pi/tools/test/activation.test.ts
- plugins/ca-pi/tools/test/status.test.ts

**proposed test paths**

- .github/scripts/test_workflow_recovery_hosts.py

**required cases**

- Startup after crash shows pending and unavailable subsets without mutating targets.
- Repeated prompt/reentry/compaction does not duplicate notices or lose obligations.
- Missing/unknown/damaged ledger yields honest absent/unavailable status while independent work continues.
- Dormant project remains dormant and no storage is created by scan.
- Pi new session can read retained state but cannot reuse an expired/revoked scoped grant.
- Measure automatic scan work and host latency against actual startup budget.

**execution state**

not run for this handoff; receiving agent must read test owners and execute the selected matrix


### Acceptance criteria

- All supported packaged hosts expose equivalent state and recovery actions through their real event seams.
- Automatic readers obey record/byte bounds and never label a partial scan complete.
- No automatic task/issue/stage/cleanup/review effect runs at startup.

### Completion evidence

- Record the exact implementation commit and any source drift from the audited baseline before making current-state claims.
- List changed canonical owners and generated derivatives; retain an exact source/package distinction.
- Attach focused meaningful test output and observed effect/failure evidence; an exit code alone is not proof of the intended target state.

### Rollback

- Disable notices while preserving explicit compatible recovery reads.
- Do not delete ledger entries to silence a notice or restore old grants.

### Adr actions

None.

### Coverage scope

None


## PI-D06 · Project truthful delegation capability and evidence diagnostics

**Status:** PLANNED. **Owner:** pi.

**Implementation prerequisites:** PI-D01, PI-D04, PI-D05, P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Finding ids

- SF01
- SF12

### Source paths

- plugins/ca-pi/tools/src/doctor.ts
- plugins/ca-pi/tools/src/status.ts
- plugins/ca-pi/tools/src/dispatch.ts
- plugins/ca-pi/tools/src/extension.ts
- core/surface/includes/pi-host-notes.md
- core/hosts.json
- core/surface/command-routes.json

### Source refs

- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/doctor.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/status.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/dispatch.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/extension.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/surface/includes/pi-host-notes.md
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/hosts.json
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:core/surface/command-routes.json

### Proposed paths

None.

### Behavior change

Expose admitted/available/qualified/degraded author capability, recovery scope and evidence mode without claiming handshake or optional artifact approval proves authorship.

### Implementation steps

- Generate or derive capability facts from actual runtime/permission contracts; distinguish reviewer read, author write/edit/command, optional artifact prompt and stronger isolation profiles.
- Show fixed bounded reason codes for no parent UI, revoked grant, executor unavailable, journal unknown and unverified cleanup; preserve human detail privately where appropriate.
- Keep current child judgment separately visible from parent effect/containment/recovery state.
- Propagate one owning capability fact into help, doctor, role/host notes and public claims; handwritten adapters remain handwritten where appropriate.
- Read-only fallback is marked transient degraded author capability and cannot satisfy the program completion check.

### Existing behavior to preserve

- No secret-bearing prompts/paths/credentials in general audit output; no new routine attestation ceremony.
- Host-specific capability differences and supported-runtime boundaries.

### Tests

**acceptance**

- Diagnostic fixture matrix yields distinct and accurate capability/evidence states.
- A mutating fixture produces parent-observed effects and current qualified package identity in its receipt.

**rejection and failure**

- Handshake-only, fake accepted child, synthetic artifact policy event and source-only probe cannot set author-qualified or released flags.
- Degraded state cannot be cleared by unrelated bridge success if required author capability remains unavailable.

**concurrency and interruption**

- Late old-run activity/status cannot overwrite a new lifecycle capability or pending recovery observation.


### Completion evidence

- Claim matrix linked to owning contracts and exact evidence records, with source/planned/qualified/released distinctions.
- UX review of parent confirmation and recovery notice with no implementation jargon in ordinary flow.

### Rollback

- Restore previous honest capability labels while retaining records; never retain a qualified label after disabling the executor.

### Claim delta

- Capability-specific matrix replaces broad Pi supported/unsupported claims.

### Adr actions

None.


## G-01 · Reconcile ADRs, claims and generated guidance with accepted behavior

**Status:** PLANNED. **Owner:** governance-and-docs.

**Implementation prerequisites:** P-02.
**Completion prerequisites:** BUILD-G01, BUILD-G02, DIST-M01, DIST-M02, FARM-R01, FARM-R02, FARM-R03, HOST-D01, HW-01, HW-02, HW-03, HW-04, HW-05, HW-06, HW-07, HW-08, HW-09, HW-10, HW-11, HW-12, HW-13, HW-14, HW-16, HW-17, HW-18, HW-19, HW-20, HW-21, HW-22, HW-23, HW-24, HW-25, NT-01, NT-02, NT-03, NT-04, NT-05, NT-06, NT-07, NT-08, NT-09, NT-10, NT-11, PI-C01, PI-D01, PI-D02, PI-D03, PI-D04, PI-D05, PI-D06, PI-L01, PI-L02, R-01, R-02, R-03, R-04, R-05, R-06, R-07, R-08, SBX-C01, SBX-C02, SBX-C03, SBX-D01, SBX-D02, SBX-D03, SBX-D04, SITE-U01, SITE-U02, T-01.
**Decision dependencies:** None.

### Phase

4

### Owner

governance-and-docs

### Finding ids

None.

### Source paths

- .codearbiter/decisions/0030-orchestration-mode-plane-with-composed-persona.md
- .codearbiter/decisions/0036-bounded-authorization-cleanup-direction.md
- .codearbiter/decisions/0037-extensible-structured-artifact-engine.md
- .codearbiter/decisions/0040-independent-per-target-release-with-consumer-safety-gates.md
- .codearbiter/decisions/0043-assistive-state-engine.md
- .codearbiter/decisions/0044-trusted-pi-npm-publication.md
- .codearbiter/decisions/0045-merge-observed-github-work-effects.md

### Implementation

- Use ADR-PROPOSALS.md and owner designs to prepare new decisions/addenda through the repository workflow. Allocate real decision IDs at execution; preserve accepted bodies/history and link supersession explicitly.
- Record B-approved dependent-work scope, corrected submissions, actual scoped Pi authorship and nonblocking durable recovery. Keep progress/evidence and reviewer HIGH disposition pending until resolved in their worksheets.
- Update canonical owner content before generated host surfaces and site projections. Correct facts without broadening legal/privacy/security or organization-wide claims.
- Record proposed Project claim-registry deltas with exact new source/package evidence. Other repositories remain separate scope; Academy compatibility is verified against its exact release before making a new compatibility claim.

### Tests

- ADR decisions, implemented handlers, capabilities, diagnostics and model-guided instructions agree for every changed outcome.
- Build/sync checks for all shared Python and surface/catalog projections; no manual generated-only fix.
- Claim records distinguish planned, implemented, source verified and released/installed qualified.

### Acceptance

- Every affected accepted-decision conflict has a recorded disposition.
- No source or documentation labels a proposed protocol already supported.

### Rollback

- Revert new derivative claims if qualification fails; preserve historical ADR and audit records.


## HW-15 · Qualify recovery interruptions, migration, concurrency and rollback

**Status:** PLANNED. **Owner:** hooks-workflows.

**Implementation prerequisites:** HW-13, HW-14, HW-26, P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Original finding ids

- W-F04
- HOOK-B04

### Baseline machine ids

- hooks:startup
- hooks:work-owner
- hooks:taskwrite
- hooks:cleanup-journal

### Existing owner paths

- .github/scripts/test_artifact_installed_host.py
- .github/scripts/test_hooks_cold_install.py
- .github/scripts/test_artifact_package.py
- plugins/ca-pi/tools/test/setup-disposable-home.ts

### Proposed new paths

None.

### Semantic change scope

Verification task; no independent new runtime authority or cleanup behavior.

### Implementation plan

- Run the design failure matrix against canonical helper and installed candidate packages.
- Exercise multiprocess locks/CAS, record-index transaction repair, exact-target reconciliation, per-item batch results, unknown schema, capacity bounds and tombstone dedup.
- Verify older/no-ledger installs and downgrade preserve all unresolved records and target state.
- Keep pending recovery, progress claims, native verification, publication and cleanup as separate facts.

### Preserved invariants

None.

### Tests

**existing test paths**

None.

**proposed test paths**

- .github/scripts/test_workflow_recovery_installed.py

**required cases**

- All interruption rows in workflow-recovery-design.md have observable target and ledger assertions.
- Replay after settlement produces no duplicate local effect and never reruns an external effect.
- Disk or notification failures do not globally block ordinary authorized work.
- Test harness imports disposable home before code that can inspect auth; real credentials are never read.

**execution state**

not run for this handoff; receiving agent must read test owners and execute the selected matrix


### Acceptance criteria

- Exact candidate, host/platform, test source commit, and pass/failure outcomes are attached.
- No current acceptance gap is described as passed because a unit double succeeded.
- Rollback procedure is executed in a disposable installation and retains pending state.

### Completion evidence

- Record the exact implementation commit and any source drift from the audited baseline before making current-state claims.
- List changed canonical owners and generated derivatives; retain an exact source/package distinction.
- Attach focused meaningful test output and observed effect/failure evidence; an exit code alone is not proof of the intended target state.
- Attach per-interruption ledger/target observations, installed package hashes, and measured scan bounds.

### Rollback

- Use the tested compatibility reader/export and disable new feature writes if rollout fails.
- Do not drop local history or undo independently edited targets to make rollback look complete.

### Adr actions

None.

### Coverage scope

None


## PI-D07 · Qualify real packaged author behavior and regressions on supported hosts

**Status:** PLANNED. **Owner:** pi.

**Implementation prerequisites:** PI-D01, PI-D02, PI-D03, PI-D04, PI-D05, PI-D06, PI-L01, PI-L02, DIST-M01, P-02.
**Completion prerequisites:** HW-26.
**Decision dependencies:** None.

### Cross-owner coordination


##### Q-01

**kind**

downstream-program-gate

**use**

Full behavior/migration/installed-artifact matrix.


##### Q-02

**kind**

downstream-program-gate

**use**

Exact-candidate major-release readiness.


##### Q-03

**kind**

downstream-program-gate

**use**

Publish identical qualified bytes and verify distributions.


### Finding ids

- SF01

### Source paths

- plugins/ca-pi/tools/test/runner-isolation.test.ts
- plugins/ca-pi/tools/test/dispatch.test.ts
- plugins/ca-pi/tools/test/final-arguments-live.test.ts
- plugins/ca-pi/tools/test/package.test.ts
- plugins/ca-pi/tools/test/windows-supervisor.test.ts
- plugins/ca-pi/tools/src/compatibility.ts
- tools/build-host-packages.py
- plugins/ca-pi/tools/build.mjs

### Source refs

- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/test/runner-isolation.test.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/test/dispatch.test.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/test/final-arguments-live.test.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/test/package.test.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/test/windows-supervisor.test.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/src/compatibility.ts
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:tools/build-host-packages.py
- arbiterForge/codeArbiter@fd7eb34b2da439551443d09526ab48fd1d1bb9bf:plugins/ca-pi/tools/build.mjs

### Proposed paths

None.

### Behavior change

Make functional parent-mediated child write/edit/command and negative/recovery evidence against exact packaged bytes a major-release gate.

### Implementation steps

- Build matching parent/child/helper bundles and candidate package only on the isolated integration branch; record complete loaded closure and artifact digests.
- Install the exact candidate into disposable homes and use the actual admitted Pi runtime/extension loader/tool loop, real file effects and managed command execution.
- Drive a write, edit and command fixture through real child proxies and parent confirmation; include visible parent TUI confirmation evidence, not only an injected true callback.
- Retain installed-host final-argument fixture while labeling substituted bridge/factories; deterministic local provider is acceptable when declared and sufficient for the local effect claim.
- Execute rejection/replay/interruption/race/platform matrix from the design. Add update/disable/uninstall and mixed-bundle refusal cells.
- Only call functional authorship qualified when required cells pass for exact bytes. Publication must use identical bytes or requalify rebuilt artifacts.

### Existing behavior to preserve

- No real secret disclosure, user repo mutation, paid provider requirement or inferred release from main.
- Existing platform/runtime support decisions remain explicit; qualify each claimed cell rather than assume every version above a floor.

### Tests

**acceptance**

- Actual resulting file bytes and command result match approved frozen requests; one executor per operation.
- Reviewer chain can inspect effects; no-change task reports honest no-change outcome.
- Exact artifact install/update/disable/uninstall succeeds under supported-host contracts.

**rejection and failure**

- A source module probe, fake runner success, handshake-only flow or permanently read-only author causes the new gate to fail.
- Package digest/runtime mismatch, stale qualification or unsupported executor profile prevents qualification.

**concurrency and interruption**

- Run full kill-point and concurrency cases on POSIX and Windows where supported, including actual supervisor fd3 forwarding.
- A killed parent cannot leave a usable token or silently replay an unknown effect on next startup.


### Completion evidence

- Machine-readable exact-artifact receipts: package/bundle SHA-256, Pi identity, Node/Python, OS/architecture, policy/executor profile, test route, substitutions, outcomes and limitations.
- Complete program gate reviewed before main integration and major publication.

### Rollback

- Keep feature degraded and program unreleased if any required cell fails; preserve evidence and fix the specific failing contract.
- Distribution rollback points to last qualified artifact and retains recoverable records.

### Claim delta

- Source admission of Pi 1.1.0/Node >=22.19.0/Python 3 is not all-platform qualification.

### Adr actions

None.


## HW-27 · Hold the integrated hook/workflow candidate until behavior and artifacts agree

**Status:** PLANNED. **Owner:** hooks-workflows.

**Implementation prerequisites:** HW-01, HW-02, HW-03, HW-04, HW-05, HW-06, HW-07, HW-08, HW-09, HW-10, HW-11, HW-12, HW-13, HW-14, HW-15, HW-16, HW-17, HW-18, HW-19, HW-20, HW-21, HW-22, HW-23, HW-24, HW-25, HW-26, P-02.
**Completion prerequisites:** P-01, NT-12, G-01.
**Decision dependencies:** None.

### Cross-owner coordination


##### Record

**task id**

P-00

**kind**

integration-baseline

**reason**

Original ROOT-INTEGRATION-AND-RELEASE placeholder: integration branch and baseline.


##### Record

**task id**

P-01

**kind**

completion-prerequisite

**reason**

Actual branch CI admission.


##### Record

**task id**

Q-01

**kind**

downstream-program-gate

**reason**

Q-01 consumes HW-27; this is not a reverse prerequisite.


##### Record

**task id**

Q-03

**kind**

downstream-delivery

**reason**

Final publication follows program qualification.


##### Record

**task id**

NT-09

**kind**

decision-dependent-integration

**decision id**

D-PROGRESS

**reason**

Original NATIVE-SMARTS-PROGRESS-EVIDENCE placeholder.


### Original finding ids

- HOOK-F01
- HOOK-F02
- HOOK-F03
- HOOK-F04
- HOOK-F05
- HOOK-B01
- HOOK-B02
- HOOK-B03
- HOOK-B04
- HOOK-B05
- W-F01
- W-F02
- W-F03
- W-F04
- W-F05
- W-F06
- W-F07
- W-F08
- W-F09
- GEN-F01
- GEN-F02
- GEN-B01

### Baseline machine ids

- hooks:activation
- hooks:host
- hooks:mode
- hooks:mode-audit
- hooks:persona
- hooks:startup
- hooks:read-context
- hooks:hook-admission
- hooks:protected-state
- hooks:shell-parser
- hooks:commit-gates
- hooks:security-producers
- hooks:push
- hooks:approval-single
- hooks:approval-pair
- hooks:prerequisite
- hooks:reconciliation
- hooks:reply-routing
- hooks:authority-request
- hooks:verifier
- hooks:codex-review
- hooks:claude-review
- hooks:debug-handoff
- hooks:native-client
- hooks:authoring-route
- hooks:context-writer
- hooks:context-provenance
- hooks:context-snapshot
- hooks:context-scout
- hooks:command-evidence
- hooks:context-delivery
- hooks:knowledge
- hooks:work-owner
- hooks:taskwrite
- hooks:work-adoption
- hooks:legacy-advisories
- hooks:plan-file
- hooks:append-conflict
- hooks:legacy-context-recovery
- hooks:adr-lifecycle
- hooks:cleanup-eligibility
- hooks:cleanup-journal
- hooks:prune-plan
- hooks:prune-execute
- hooks:claude-accounting
- hooks:session-accounting
- hooks:pi-accounting
- hooks:git-install
- hooks:git-dispatch
- hooks:task-lock-exclusion
- hooks:advisory-runtime
- hooks:update-notice
- hooks:statusline-wiring
- hooks:doctor
- hooks:release-confirmation
- hooks:tribunal-inventory
- hooks:tribunal-run
- hooks:tribunal-lock-leads
- hooks:tribunal-usage
- hooks:pi-python-bridge
- hooks:pi-approval
- hooks:codex-pretool
- hooks:display-git-probes

### Existing owner paths

- tools/build-surface.py
- .github/scripts/test_build_surface.py
- .github/scripts/test_hooks_cold_install.py
- .github/scripts/test_artifact_package.py
- .github/scripts/test_artifact_installed_host.py
- .github/scripts/check_command_route_release_state.py

### Proposed new paths

None.

### Semantic change scope

Integration/qualification gate for the held branch; no automatic publication or approval inference.

### Implementation plan

- Consume the detailed original transition catalogs as the before-behavior inventory and map each changed family to its task.
- Regenerate shared Python/host/surface/site artifacts and verify equality; do not patch generated copies independently.
- Run focused regressions plus the required existing integration/package/host acceptance matrix for changed semantics.
- Record unresolved scoped decisions honestly and complete them before claiming the full selected effort done; independent tasks can land on the held branch meanwhile.
- Hand exact candidate evidence, migrations and rollback to the root major-release workflow; source tests do not count as publication/readback.

### Preserved invariants

None.

### Tests

**existing test paths**

- .github/scripts/test_build_surface.py
- .github/scripts/test_hooks_cold_install.py
- .github/scripts/test_hook_guards.py
- .github/scripts/test_artifact_package.py
- .github/scripts/test_artifact_installed_host.py
- .github/scripts/test_command_route_release_state.py

**proposed test paths**

None.

**required cases**

- Changed hook states satisfy their new event/guard/effect contract; preserved safeguards remain effective.
- Absent/dormant project, unsupported host/profile, closed schema, actual denial, stale evidence, untrusted execution and protected push/cleanup branches retain truthful refusal behavior.
- Shared generated copies, installed helper resolution, package identity and target manifests agree.
- No false completion, cleanup, release, or native verification claim from local recovery bookkeeping.

**execution state**

not run for this handoff; receiving agent must read test owners and execute the selected matrix


### Acceptance criteria

- All27 tasks have evidence or an explicit approved exclusion; no unreviewed scope silently disappears.
- No open HIGH disposition or progress/evidence policy is falsely called resolved.
- Integration branch remains held until root whole-effort criteria and exact-artifact qualification pass.
- Release/version/alias changes follow root selected policy and exact release evidence.

### Completion evidence

- Record the exact implementation commit and any source drift from the audited baseline before making current-state claims.
- List changed canonical owners and generated derivatives; retain an exact source/package distinction.
- Attach focused meaningful test output and observed effect/failure evidence; an exit code alone is not proof of the intended target state.
- The original audit records63 hook families/388 rows at its commit; this task does not assert every unchanged transition was newly executed.
- List which branches were dynamically tested, statically revalidated, externally qualified, or remain unsupported.

### Rollback

- Use task-specific compatibility rollback without deleting records or overwriting independently edited targets.
- If the integrated candidate fails a gate, keep it unmerged/unpublished and retain evidence for correction.
- A rollback of publication, if needed later, belongs to the root release owner and does not rewrite immutable release history.

### Adr actions

None.

### Coverage scope

None


## Q-01 · Close the complete behavioral, migration and installed-artifact matrix

**Status:** PLANNED. **Owner:** qualification.

**Implementation prerequisites:** BUILD-G01, BUILD-G02, DIST-M01, DIST-M02, FARM-R01, FARM-R02, FARM-R03, G-01, HOST-D01, HW-01, HW-02, HW-03, HW-04, HW-05, HW-06, HW-07, HW-08, HW-09, HW-10, HW-11, HW-12, HW-13, HW-14, HW-15, HW-16, HW-17, HW-18, HW-19, HW-20, HW-21, HW-22, HW-23, HW-24, HW-25, HW-26, HW-27, NT-01, NT-02, NT-03, NT-04, NT-05, NT-06, NT-07, NT-08, NT-09, NT-10, NT-11, NT-12, P-00, P-01, P-02, PI-C01, PI-D01, PI-D02, PI-D03, PI-D04, PI-D05, PI-D06, PI-D07, PI-L01, PI-L02, Q-02, R-01, R-02, R-03, R-04, R-05, R-06, R-07, R-08, SBX-C01, SBX-C02, SBX-C03, SBX-D01, SBX-D02, SBX-D03, SBX-D04, SITE-U01, SITE-U02, T-01.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Phase

5

### Owner

qualification

### Finding ids

None.

### Source paths

None.

### Implementation

- Collect completion evidence for all implementation tasks, all finding dispositions, all machine owners and all transition coverage mappings. One sequence test may cover many rows if its asserted effects/guards are identified.
- Run the canonical complete suites plus targeted fault-injection sequences, source-to-bundle checks, six native/cold package platform cells and supported host runtime matrix. Preserve deliberate advisory lanes; do not confuse them with required new behavior qualification.
- Exercise upgrade from each relevant last published adapter artifact, existing state with checks/history/pending journal, new state, uninstall after user edits, interruption, restart and recovery. Verify rollback before new writes and explicit forward reconciliation after incompatible writes.
- For Pi, demonstrate real delegated write/edit and authorized verification execution under the supported host, plus denied/wrong-scope/revoked/stale attempts. Mock-only or read-only cannot close authorship.
- Measure UX/DX/AX acceptance: ordinary prompts do not increase due to optional evidence; dependent stops stay scoped; truthful outcome and recovery are discoverable; contract facts have one owner. Use actual user/agent scenario evidence, not only keyword tests.

### Tests

- Execute the complete TEST-AND-QUALIFICATION.md matrix with exact commit/platform/runtime/artifact digest and result population.
- An unavailable required runtime/platform keeps the release requirement open.
- Differential traces preserve all behavior except the explicit user-approved change list.

### Acceptance

- No open defect or unqualified required capability in the accepted program scope.
- All remaining N/A decisions are evidence-backed and reviewed; no blanket waiver substitutes for entire completion.
- Program candidate is fully built and tested on the integration branch.

### Rollback

- Retain integration branch and exact candidate artifacts; fix and requalify there. Do not promote partially completed work.


## Q-03 · Promote once, publish the new major, and verify each distribution

**Status:** PLANNED. **Owner:** release-manager.

**Implementation prerequisites:** Q-01, Q-02, G-01, R-01, R-02, R-03, R-04, R-08, P-02.
**Completion prerequisites:** None.
**Decision dependencies:** None.

### Phase

6

### Owner

release-manager

### Finding ids

None.

### Source paths

None.

### Implementation

- Resolve the remaining scoped decisions with B and confirm the integration-qualified program record is complete, with only final exact-main qualification/publication/readback outstanding. Prepare the single integration-to-main promotion PR through normal review/merge rules; no partial earlier merges.
- Choose an unused next major in the product ca namespace. At this observation ca is 3.8.5, so 4.0.0 is a proposed target only; re-resolve versions and tags immediately before freezing. Preserve independent Codex/Pi/sandbox version namespaces and choose each according to its actual changed contract.
- Keep root Pi package.json generated from its owner. Build and qualify the final exact source/bytes under Q-02. Publish through existing sanctioned hosted mechanisms, not improvised local npm/token paths.
- Read back tag dereference, GitHub non-draft state, exact asset digests, final publication receipt, relevant marketplace ref/install identity, Pi registry integrity/provenance and documented update/uninstall behavior. Record partial publication explicitly and recover only missing target effects.
- Retain the integration branch through final verification and recovery. B requested this work stay isolated until complete; closing a task or green subset of CI does not permit early promotion.
- If final-main verification exposes a needed implementation fix, return that fix to the held integration program and repeat reviewed qualification/promotion. Do not silently implement unfinished features directly on main. Publication remains pending until PREPUBLICATION_READY; Q-03 completes only at DISTRIBUTION_SETTLED.

### Tests

- Final merge/queue SHA and exact post-merge package qualification; immutable tag readback; clean installed upgrade/current install for each changed advertised target.
- Publication interruption/retry and docs publication observation on the final immutable identities.

### Acceptance

- New major publication has exact per-target completion and installed-behavior evidence.
- No required program item remains unfinished or merely marked deferred.
- Release notes distinguish changed behavior, migration/rollback boundaries, known intentional exceptions and qualification scope.

### Rollback

- Before promotion, withdraw the pending PR and continue on the integration branch. After promotion but before publication, keep publication pending and route any source correction back through the held integration branch and reviewed qualification; do not force-reset main. After publication preserve immutable artifacts/tags, fix forward with a new version, and report partial settlement truthfully.

