# Branch isolation, CI and major release runbook

## Branch topology and retention

Use `major/state-contracts` as the integration branch. The name is a proposed working convention, not a claim that a remote branch exists. Inspect before creation. Child task branches are based on it and PRs target it. The final integration PR alone targets main after complete qualification. Keep the integration branch through publication verification and any required recovery.

Never force-reset an existing shared branch. Preserve unrelated work in its original worktree. Merge inspected main changes into the integration branch through a reviewed sync when needed; record the new source identity and invalidate/re-run affected evidence. Rebase only private task branches where repository policy permits it. Do not cherry-pick partial program fixes into main.

The receiving agent is authorized by B's task to implement this program on that branch. Normal repository controls and actual host permissions still apply. Do not add repeated approval ceremonies to routine reversible work.

## Bootstrap safely

1. Verify `git remote -v`, local status and worktree inventory; check the exact authorized origin. Fetch main/tags through the authorized Git identity.
2. Record audit SHA `fd7eb34b2da439551443d09526ab48fd1d1bb9bf`, live base SHA, branch existence and the source differences. The handoff's live check matched the audit; execution must check again.
3. Create a clean integration worktree only if the branch is absent, or attach to the verified existing integration branch. Handle existing work rather than overwriting it.
4. Import the corpus, then implement P-01 as the first branch change. Verify actual branch CI before merging child tasks.
5. Initialize `execution/CHECKPOINT.md` and `execution/progress.json` from the intake templates; use those live records and the structured task specifications for continuation. A resumed agent reads current Git state first, then the checkpoint and exact tests/effects already performed.

Do not run placeholder commands with an invented SHA/path. A receiving agent should select concrete paths after inspection. No script in this packet creates a branch or publishes a release automatically.

## Current CI constraint

At the audited commit, `.github/workflows/ci.yml` admits PR bases `main` and `feat/codex-support-m0`, and push builds on main. The docs workflow admits main PRs/pushes and deploys only main. Release admission is a successful same-repository main push CI or a main dispatch; branch CI must not become publication authority.

P-01 adds exact integration admission and required domain selection. A branch push workflow is suitable for bootstrap. GitHub documents that push workflows can execute before merging to the default branch; manual-only workflow discoverability has default-branch constraints. Inspect actual runs rather than assuming a new manual-only workflow is available. Sources: [GitHub events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows), [trigger filters](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).

Preserve read-only PR/branch qualification credentials. Keep all release, npm, marketplace and Pages write permissions behind their existing trusted main-only owners. Do not use `pull_request_target` to execute untrusted candidate code with publication privileges. Preserve merge-group support for final main promotion where required; effective repository rules must be observed, not inferred from comments.

## Candidate versions during a long branch

Current payload guards compare the child PR's payload against its base manifest version. There are two relevant owners: `.github/scripts/payload_version_gate.py` deliberately excludes ca-pi; Pi is checked by `tools/build-host-packages.py --release-guard-base` in CI. Update and test both owners while preserving Pi changelog and generated root-metadata checks. Therefore bumping to one future version in the first commit does not automatically make every later child PR pass. P-01 must explicitly choose and test a supported integration-only candidate rule, or advance fresh untagged development versions on changes until final freeze. Never disable normal main/merge-group payload-version protection.

Recommended integration rule: bind the program's recorded main baseline, the candidate version per target, synchronized metadata and the current tag namespace. For Pi, also bind newly introduced changelog-heading and required metadata-change comparisons to the recorded main baseline, because an immediate integration base may already contain the candidate heading. Preserve meaningful current content synchronization and strict final-main actual-base checks. Permit same untagged candidate evolution only on verified PRs targeting `major/state-contracts`; any tag claim, wrong base, divergent metadata or main-targeted change still uses strict admission. On final promotion, use normal advancement checks against current main and require the version/tag to be unused. This is a proposed branch policy with tests, not current behavior. Do not assume prerelease suffixes fit the current portable version grammar; select and test a supported numeric candidate policy.

## Observed target identities

| Target | Source manifest at audit | Observed release state | Tag dereference |
|---|---|---|---|
| ca / codeArbiter | 3.8.5 | `v3.8.5` published | `fd7eb34b2da439551443d09526ab48fd1d1bb9bf` |
| ca-codex | 0.26.5 | `ca-codex-v0.26.5` published | `fd7eb34b2da439551443d09526ab48fd1d1bb9bf` |
| ca-pi | 0.27.5 | `ca-pi-v0.27.5` draft; retrieved published 0.27.3 also recorded | draft `fd7eb34b2da439551443d09526ab48fd1d1bb9bf`; published `27e6cb12eb0195bc89b4e91ee7d8d8093ac490fa` |
| ca-sandbox | 0.1.10 | `ca-sandbox-v0.1.10` published | `cfee5a82707eb477013496b96146f1c309cb7faa` |

These are GitHub metadata and dereferenced tag observations, not byte/installed qualification. No cause for the Pi draft state was established. Diagnose current drafts through actual logs and registry/provenance observations; do not attribute them to a particular audit finding without evidence.

The requested next major product release has **4.0.0 as a proposed ca target** while the observed current major is 3. Re-resolve current versions and tag availability before committing the final version. Codex/Pi/sandbox keep their independent version namespaces; select their versions from actual public-contract changes and the approved release policy. The user did not authorize inventing a shared numeric version or deleting compatibility aliases just because a major is released.

Root `package.json` is generated Pi publication metadata. Update the nested owner and regenerate via the actual build owner. Preserve per-target changelogs, declared tag prefixes and only ca's latest-eligible role.

## Required publication sequence

1. Finish every accepted implementation/migration/docs task on the integration branch.
2. Resolve the scoped semantic decisions; record accepted ADR successors through the normal workflow.
3. Freeze a candidate SHA and versions; execute the complete test/installed-artifact matrix against exact candidate bytes. Record failures and correct them on the branch.
4. Prepare the final promotion PR. Test the prospective merged source. If main changes, refresh the candidate and affected evidence.
5. Merge only the fully completed program through existing review/merge controls. Keep the branch available.
6. Build the final main source through the trusted pipeline. Compare exact payload identities to the qualified candidate. If rebuilt bytes differ, run required exact-artifact qualification before public effects.
7. Verify the **major-release readiness record** described below. Only then allow the first target publication/channel effect.
8. Publish targets using the sanctioned hosted mechanisms. Treat each target's settlement independently; there is no atomic multi-target rollback.
9. Read back immutable tags, assets, registry/marketplace identities and final publication receipts. Recover only missing effects. Run release observation and correct site claims from observed state.
10. Record the final release evidence and user migration instructions. Keep any partial target state visible until settled.

## Exact-artifact readiness barrier (new implementation required)

Current release automation starts after successful main CI. A plan that waits to perform exact installed qualification after that trigger can publish too early. Implement and regression-test the Q-02 verifier before promotion. Q-02 closes that implementation task on the integration candidate; the actual final-main readiness record is a later execution input checked during Q-03 before public effects. Do not make the existence of a future main commit a prerequisite for Q-02 implementation completion.

The proposed record attests **PREPUBLICATION_READY**. Actual publication and public receipt/readback evidence belongs to the later **DISTRIBUTION_SETTLED** state; requiring it in readiness would be circular. All required implementation, candidate tests, migrations and decisions remain prepublication requirements. This is release-specific evidence, not runtime authorization. It binds:

- program ID and completed prepublication task/disposition manifest digest, explicitly excluding Q-03 actual publication/public readback/receipt settlement;
- accepted decision/ADR identities and unresolved-decision count;
- exact source commit and source tree identity;
- trusted build workflow/run/job and artifact IDs;
- target/version/tag intentions and archive/member digests;
- required platform/runtime/scenario population with concrete results and evidence references;
- qualification producer identity, time and retention location;
- migration/readback/rollback qualification and any explicit supported exception.

Place the record outside the source identity it attests, such as a declared trusted Actions artifact. A committed self-assertion with `passed: true` cannot certify itself. Verify source/run/workflow identity and artifact digests through the authenticated observed run, then verify every required result. Reject forged, unavailable, skipped, partial, expired or mismatched required evidence. Do not grant candidate PRs secrets or publication authority to generate it.

Recommended wiring: extend the trusted release preflight with a program-specific readiness verification before any tag/package/channel/public-Release effect. It can observe a trusted qualification run/artifact for the selected CI build. Missing readiness leaves publication pending with a precise next action; it never pretends the product release completed. A verified rerun resumes only through an event/source combination admitted by the existing publisher. For a new Pi npm publish, `GITHUB_SHA` must equal selected `SOURCE_COMMIT`. If readiness finishes after main advances, inspect whether the original matching event/run can still publish. If it cannot, choose, rebuild and requalify a new exact eligible source and unused version where required. Never rewrite `trusted-sha`, bypass provenance or infer that a new manual dispatch may publish any older selected build. Existing byte-identical npm recovery is a separate observed-state case. Preserve the main-source checks and Pi provenance gate. This new contract must receive strict schema/identity and event tests before use.

If all required exact-artifact checks can be performed within the existing trusted main CI before its success, its verified artifact/results may serve as the producer. Otherwise use the declared separately completed qualification run and rerun publication after readback. Neither route may silently replace exact-byte qualification with a source-only or version-only assertion.

The user requested coordinated **program readiness**, not an atomic cross-target publication transaction. Once the complete program is ready, target publishing/recovery remains independent. Successful targets are not unpublished because another target needs recovery.

## Recovery and rollback

Before publication, keep changes on the integration branch or withdraw a not-yet-published candidate through the existing process. After an external effect, read back its real state before retry. Never move a published tag, overwrite an npm version, reuse a conflicting asset, delete history, or rerun authors merely because their report failed. Correct published defects with a new version and accurate release notes. Use the dedicated receipt recovery path for missing receipts.

Source owners: [.github/workflows/ci.yml](https://github.com/arbiterForge/codeArbiter/blob/fd7eb34b2da439551443d09526ab48fd1d1bb9bf/.github/workflows/ci.yml), [release.yml](https://github.com/arbiterForge/codeArbiter/blob/fd7eb34b2da439551443d09526ab48fd1d1bb9bf/.github/workflows/release.yml), [docs.yml](https://github.com/arbiterForge/codeArbiter/blob/fd7eb34b2da439551443d09526ab48fd1d1bb9bf/.github/workflows/docs.yml), [payload version gate](https://github.com/arbiterForge/codeArbiter/blob/fd7eb34b2da439551443d09526ab48fd1d1bb9bf/.github/scripts/payload_version_gate.py), [Pi version/package guard](https://github.com/arbiterForge/codeArbiter/blob/fd7eb34b2da439551443d09526ab48fd1d1bb9bf/tools/build-host-packages.py), [release targets](https://github.com/arbiterForge/codeArbiter/blob/fd7eb34b2da439551443d09526ab48fd1d1bb9bf/.codearbiter/release-targets.md), [publication action](https://github.com/arbiterForge/codeArbiter/blob/fd7eb34b2da439551443d09526ab48fd1d1bb9bf/.github/actions/publish-target/action.yml).
