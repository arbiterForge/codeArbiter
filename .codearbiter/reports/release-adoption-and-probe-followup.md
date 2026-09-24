# Release follow-up: implementation and verification boundary

Date: 2026-09-23 (America/New_York)
Repository: arbiterForge/codeArbiter
Inspected source base: 75b4d442ea42bdd19241608647419a390e1ee360
Scope: the three remaining findings from the post-#845 review. This does not reopen the deferred product decisions in #570.

## Implemented

- RR-01: replace the adoption-commit-equals-HEAD fallback with an executable, read-only window decision. A confirmed, reachable adoption boundary with an empty first-release payload window proposes an explicit confirm-or-replace decision across fast-forward, squash, and ordinary merge commits. It never widens silently. Tagged empty windows, missing payload arguments, invalid/unreachable revisions, and a failed history read cannot take that proposal path.
- RR-02: centralize the direct clean-tree predicate in an executable shell guard: the existing target-aware probe must exit zero AND print no porcelain output. Dirty, failed, and timed-out inspection stop the invoking lane before its following operation. Wire the guard through preparation, post-commit, hosted-build, and recovery call sites without changing the underlying helper exit-code contract.
- RR-03: execute installed shell definitions in real temporary consumer repositories. The new tests create a local bare origin, publish application history, validate the declaration's reconciliation ledger, land it using three merge methods, fetch it, and re-enter from a new release branch. Refusal tests place an actual guard invocation before a controlled write attempt. Existing partial ancestry/tag fixtures are now labeled as partial; their useful assertions are retained, while a consecutive-snapshot no-op assertion is removed.

Canonical source owns the change. tools/build-surface.py regenerated the Claude, Codex, and Pi release instructions. No public command, hosted publisher, confirmation authority, release-target schema, published tag, or repository setting was changed.

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

## Not qualified for merge or release yet

This is source-candidate evidence, not installed-host, publication, or independent agent-judgment proof. The archive portions of test_consumer_smoke.py read committed HEAD, which was the base during preparation; rerun them on the final committed PR candidate.

check_skill_proof_fresh.py correctly failed because the rendered Claude skill changed: its current candidate SHA-256 is 55d91f619fb23de12e5d5439b79e457a216596e3d7347fa67bb09b6be44da445, while the recorded independent exercise covers older bytes. No exercise, reviewer, approval, or replacement proof hash was fabricated. The historical proof record was not rewritten.

Before merge: prepare the required affected-host version/changelog/provenance updates against then-current main, obtain the required fresh independent release-skill exercise and exact-candidate qualification, rerun the committed consumer checks, and require the normal exact-head CI aggregate. Keep the PR draft until those obligations are satisfied. Source-test success is not permission to bypass any of them.

## Rollback and issue disposition

Before merge, retain or revise the PR rather than changing main. After an authorized merge, any rollback must use a reviewed revert and the repository's required new release identities; never move or delete a published tag. The original #570 deferred modes and policy questions remain open. This follow-up supplies no blanket closure for #570 or automatic issue-state changes.
