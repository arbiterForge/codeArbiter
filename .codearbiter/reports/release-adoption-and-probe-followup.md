# Release follow-up: implementation and verification boundary

Date: 2026-09-23 (America/New_York)
Repository: arbiterForge/codeArbiter
Inspected source base: 75b4d442ea42bdd19241608647419a390e1ee360
Scope: the three remaining findings from the post-#845 review. This does not reopen the deferred product decisions in #570.

## Implemented

- RR-01: replace the adoption-commit-equals-HEAD fallback with an executable, read-only window decision. A confirmed, reachable adoption boundary with an empty first-release payload window proposes an explicit confirm-or-replace decision across fast-forward, squash, and ordinary merge commits. It never widens silently. Tagged empty windows, missing payload arguments, invalid/unreachable revisions, and a failed history read cannot take that proposal path.
- RR-02: centralize the direct clean-tree predicate in an executable shell guard: the existing target-aware probe must exit zero AND print no porcelain output. Dirty, failed, and timed-out inspection stop the invoking lane before its following operation. Wire the guard through preparation, post-commit, hosted-build, and recovery call sites without changing the underlying helper exit-code contract.
- RR-03: execute installed shell definitions in real temporary consumer repositories. The new tests create a local bare origin, publish application history, validate the declaration's reconciliation ledger, land it using three merge methods, fetch it, and re-enter from a new release branch. Refusal tests place an actual guard invocation before a controlled write attempt. Existing partial ancestry/tag fixtures are now labeled as partial; their useful assertions are retained, while a consecutive-snapshot no-op assertion is removed.

Canonical source owns the change. tools/build-surface.py regenerated the Claude, Codex, and Pi release instructions. No public command was added or removed; `release --dry-run` preflight behavior changed as described below. No published tag or repository setting was changed.

## Source verification

GitHub Actions run 35939912227, attempt 1, preparation commit 27339feccf50a6452722922b2bbc34b0c21c0e8b, artifact 10783758772 verified the hash-bound candidate built from the inspected base. The preparation branch is not part of the product change. Its runner stored only checked blobs and a preserving tree; it did not advance the source branch, merge, tag, or publish.

| Command | Observed result |
|---|---|
| python -m unittest discover -s plugins/ca/hooks/tests -p test_release_workflow_followup.py -v | 15 run, all passed |
| python .github/scripts/test_release_lib.py | 677 run, 1 skipped, no failures |
| python .github/scripts/test_consumer_smoke.py | 107 run, all passed |
| python .github/scripts/test_release_workflow.py | 171 run, all passed |
| python .github/scripts/test_payload_version_gate.py | 34 run, all passed |
| python .github/scripts/test_release_trace.py | 29 run, 1 skipped, no failures |
| python tools/sync-core.py --check | passed |
| python tools/build-surface.py --check | passed |
| python tools/build-host-packages.py --check | passed |
| git diff --check | passed |

The changed Python files compile. A separate local scan of added source/test text using the repository's _hooklib.SECRET_RE returned zero matches. This does not substitute for the required hosted secret scan.

## Initial PR qualification status (before slice 2)

This is source-candidate evidence, not installed-host, publication, or independent agent-judgment proof. The archive portions of test_consumer_smoke.py read committed HEAD, which was the base during preparation; rerun them on the final committed PR candidate.

check_skill_proof_fresh.py correctly failed because the rendered Claude skill changed: its current candidate SHA-256 is 55d91f619fb23de12e5d5439b79e457a216596e3d7347fa67bb09b6be44da445, while the recorded independent exercise covers older bytes. No exercise, reviewer, approval, or replacement proof hash was fabricated. The historical proof record was not rewritten.

Before merge: prepare the required affected-host version/changelog/provenance updates against then-current main, obtain the required fresh independent release-skill exercise and exact-candidate qualification, rerun the committed consumer checks, and require the normal exact-head CI aggregate. Keep the PR draft until those obligations are satisfied. Source-test success is not permission to bypass any of them.

## Rollback and issue disposition

Before merge, retain or revise the PR rather than changing main. After an authorized merge, any rollback must use a reviewed revert and the repository's required new release identities; never move or delete a published tag. The original #570 deferred modes and policy questions remain open. This follow-up supplies no blanket closure for #570 or automatic issue-state changes.

## Slice 2: release metadata and CI failure repair

Date: 2026-09-23 (America/New_York; hosted timestamps use UTC on September 24).
The user authorized fixing failed CI and adding this next slice to the same PR.
Inspected PR head: `3261e140b4ff5a350ceb86bfd92931bd5d8df590`.
The default branch remained `75b4d442ea42bdd19241608647419a390e1ee360`.

### Observed failures and correction

Normal PR CI run `35940274002`, attempt 1, completed with four root failures:
CA, Codex, and Pi payload-version gates rejected changed payloads at their old
versions; the release-candidate gate rejected the old Codex changelog intent
because it no longer bound the changed payload. Merge readiness failed as a
consequence. The other required job classes succeeded or were impact-skipped;
this includes the committed consumer smoke checks and cross-platform hook checks.

Advance only the changed adapters to candidate versions CA `2.21.12`, Codex
`0.13.12`, and Pi `0.14.12`. Keep their runtime host identities synchronized,
generate the root Pi manifest and shared hostapi copies from their owning sources,
update the checked CA badge, and add matching intent-bearing changelog sections.
Every prior changelog section and the existing Unreleased content remain unchanged.
Rebaseline only the changed source hashes and corresponding version claims in the
existing provenance records. Sandbox, release declarations, publisher workflows,
confirmation policy, published tags, and all historical qualification records are
unchanged. These are candidate identities, not a publication claim.

### Exact source verification

Preparation run `35942063422`, attempt 1, at preparation commit
`dd01fe07656832792d7f3402873b7dd13d3db87a` passed all twelve declared command groups.
The source candidate tree is `86105c836ab2a708caa1481503f5b2a1024e5601`, built on the
inspected PR head. Artifact `10785810525` retains commands, exit statuses, source
bytes, and blob identities. Its downloaded ZIP SHA-256 is
`0186f983937c14afc1a55ecc0549dbddf293e532b9908548bb40fb4288c891fb`.
The separately stored Git tree and every returned source byte matched the locally
reviewed candidate. The preparation workflow is not part of this PR's tree or
ancestry. Its read-only verification and write-permission object store were
separate jobs; neither advanced a product branch or published a release.

Verified: CA and Codex payload-version guards, Pi's committed-history release
guard, automatic candidate-intent binding, 19 host-descriptor tests, badge
consistency, 21 historical Codex documentation/proof tests, 125 provenance tests,
core synchronization, surface generation, root package generation, and whitespace.
The candidate-intent check deliberately did not claim the pre-tag suite passed.
Separate local runs against the same metadata tree passed the 15 installed-shell
release regressions and the 677-test release library suite (one expected skip).

### Remaining qualification

Version/changelog/provenance preparation is complete for this slice. The normal
CI aggregate must still assess the new committed PR head. The unchanged rendered
release skill still needs a fresh independent agent exercise against SHA-256
`55d91f619fb23de12e5d5439b79e457a216596e3d7347fa67bb09b6be44da445`.
Codex's exact `0.13.12` CI-assembled package needs its own live-host qualification;
the retained `0.13.11` marker is historical evidence and was not relabeled.
Ordinary historical documentation tests passing does not satisfy
`test_public_codex_docs.py --require-current-candidate`.

No independent actor, live model turn, authority receipt, approval, or proof hash
was invented to clear either boundary. Keep the PR draft until those actual
observations and the exact-head merge-readiness gate succeed. No merge,
publication, issue closure, or tag mutation is included in this slice.

## Slice 3: origin integration and committed-payload qualification

Date: 2026-09-24. User authorization: update this PR to origin, fix failed CI,
and add the next slice. The starting PR head was
`7fe42851182ac4a231ee2a4c43322d0fd35489e8`; the inspected origin/main commit is
`cf90ce4d79c5d87cb88f163535c1035da2315815`. Preserve both histories with a merge
commit rather than force-pushing or reconstructing a single-parent replacement.

### Changed upstream authority

PR #853 (`786a1db5713adc16cdee58e6903fd16099039ccd`) explicitly moved live
Codex model-turn verification after publication. Retain that implementation,
its historical-proof validation, and all static package/provenance gates. The
slice-2 statement that a current Codex live turn blocks merge/release is now
historical and superseded by #853; it must not be reintroduced on this branch.
PR #850 supplied the newer sprint/approval and command-owner implementation;
those upstream changes are retained without modification.

Main now owns the `.12` payload versions and their release sections. Resolve the
three changelog conflicts by preserving origin's `.12` sections byte-for-byte
and placing this PR's release work under candidate CA `2.21.13`, Codex
`0.13.13`, and Pi `0.14.13`. Keep the generated package, runtime identities,
badge, and only the affected provenance entries synchronized. No published
version identity is reused, and no prior release note is overwritten.

### Added qualification slice

`plugins/ca/hooks/tests/test_release_distribution_followup.py` adds four test
methods with explicit host/merge-method subcases. It archives the exact
committed Claude, Codex and Pi payloads into separate temporary installations,
checks their helper/skill identities against that commit, and executes the
archived shell definitions and helper CLIs. No canonical `core/` or repository
state is copied into those installations. It covers nine host-by-merge-method
first-release re-entries, retained footer/ledger refusal, and actual clean-tree
and commit-prerequisite guards ahead of controlled write attempts.

The shared consumer fixture now accepts an explicit installed plugin root;
all of its helper calls use that root. Its subprocess environment excludes
ambient Python import overrides as well as the existing Git/shell overrides.
The default fixture behavior and production release instructions are unchanged.

The new tests first failed because the fixture could not bind a selected
installed payload. After adding that binding, all four methods passed locally.
These are deterministic, committed-payload tests, not a blind agent exercise,
a production host session, or an inspection of a published release asset.

### Remaining red gate

The inspected final slice-2 CI run `35942517509` failed candidate readiness at
`check_skill_proof_fresh.py`: the record still covers the older rendered skill.
This slice does not replace independent judgment with passing tests or change
that gate. A distinct reviewer must actually exercise the final rendered skill
before its receipt can be updated. No independent actor, approval, result, or
replacement proof hash is manufactured. A requested review is not a completed
exercise, and ordinary CodeRabbit diff review alone is not this proof.

Normal CI must run on the new merged head. Codex live verification belongs to
post-publication under #853, not to the merge blockers listed in slice 2. The
remaining pre-release human/agent-judgment requirement is the release-skill
exercise; deterministic source and package checks do not waive it.
