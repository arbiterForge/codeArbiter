# Brownfield prerequisite fixes: execution and engineering sign-off

Date: 2026-09-25. Product: codeArbiter. Scope: three bounded prerequisite corrections and one test-fixture correction.

## Decision and authority

The maintainer approved proceeding after a final review, including reasonable corrections and a pull request. The map-first campaign direction remains sound. I sign off on this bounded source patch for review based on the failing regression controls, passing corrected suites, source inspection and recorded compatibility checks. This is the authoring assistant's engineering assessment, not a fabricated independent review or native authority receipt. Merge and release remain separate.

The single campaign specification and plan remain in [PR #872](https://github.com/arbiterForge/codeArbiter/pull/872), at commit `4decde20df14cf4dfcd1e2762723772d1d5c8b53`. They are not copied, rewritten or marked completed here. This independent prerequisite-fix branch is based on `arbiterForge/codeArbiter@4187f1e22dc7da3cf755a2654bbf7ec268236126:/`. Its runtime baseline equals the campaign branch's runtime baseline.

The existing regression-first fix route owns these reproduced defects. No full-plan completion exemption was added. User authorization is recorded, but native spec/plan approval and task-acceptance receipts were not minted, and the 60-task campaign is not called complete. No further conceptual approval of this bounded patch is requested. Full campaign execution must retain its genuine native workflow authority rather than converting this note into a receipt.

## Implemented corrections

### HTML intent checking

`core/pysrc/_intentlib.py` now accepts the native validator's documented null/empty diagnostic result. It requires the selected artifact, ready gate, real Boolean validity and a valid model digest; malformed diagnostics remain errors. A changed or wrong final artifact identity still prevents success. Existing issue-checkbox checks and retired-criterion behavior remain. Ready validation of a draft never becomes approval. This advances campaign T-004 and its capability/claim obligations.

### Shared-source healing

`core/pysrc/_provenancelib.py::heal_worklist` retains every enabled dependent baseline until it evaluates divergence. One fresh document can no longer hide another stale document citing the same file. The existing ordered, deduplicated staged-path API is preserved. `compute_drift` and `changed_scope` retain document-level detail; disabled triggers, unrelated paths and all-fresh no-ops remain unchanged. No hash method, source classifier, schema, writer or automatic rebaseline policy is changed. This addresses the reproduced AC-013 selection defect, not the entire future provenance contract.

### Code-map size diagnosis

The existing map linter warns above 20 KiB of UTF-8 text, including a single enormous role and multibyte text. Entry-count and multiline-role checks still run. Invalid Unicode is diagnosed. This is advisory: no map is truncated, rewritten, adopted or globally blocked. It implements the byte-budget portion of AC-016; path lifecycle and task-delivery obligations remain.

### Actual native cell in the corruption fixture

The existing bridge test selected the first binary in a release manifest. In the six-platform published package that was not necessarily the running host's binary, so the fixture left the native executable intact and failed at unrelated missing workflow resources. The test now corrupts the actual OS/architecture cell. Its expected capability error and repository-preservation assertions are unchanged. This was reproduced on the unchanged source with the exact released package, not dismissed as a flake.

## Ownership and propagation

The two behavioral modules are authored in `core/pysrc/`. `tools/sync-core.py` generated all three host copies. The shared fallback and host-specific adapter version identities were synchronized, and the Pi root package manifest was generated with `tools/build-host-packages.py`.

Candidate versions are ca 2.21.17, ca-codex 0.13.18 and ca-pi 0.14.17, derived as patch advances from the inspected main. They are not release claims or globally reserved numbers. The three changelogs describe only these fixes. The provenance helper updated three code-map manifest claims and six release-target source identities after inspecting the owned manifests/changelogs and target declarations. Other provenance entries were preserved.

## Interaction with other work

PR #854 was tested as an isolated source overlay at `0aa030b33789d57fc23cbe864469f50923ce6ce8`. The two implementation modules and four test files were unchanged there before this overlay. The new intent, provenance and native-authoring tests passed; the corrected native bridge suite also passed. This is targeted compatibility evidence, not a merge, release, or qualification of every #854 change.

A later observed #854 head, `21ba930102c9fa3a1068c45f88cb83b02c2147e2`, changes only `.github/scripts/test_build_surface.py` relative to the tested head. Keep that UTF-8 fixture correction and #854's context-check, ADR, debug, PR, cleanup and other ownership work. None is replaced here.

The real overlapping paths are package/version identities, three changelogs, the shared fallback identity and two provenance files. Both branches currently propose the same next versions. Whichever lands second must reconcile with current main: preserve both sets of notes, advance a spent version as required, synchronize all owning/derived identities, refresh only revalidated provenance and run exact-head gates. Do not resolve these files by selecting one side wholesale.

PR #871 at `2b6e5a5bcfdb5d4713ba6d8f655d9cc99bfd4827` remains separate debug preparation. No debug source, diagnostic contract, authority adapter or planning record is modified by this patch.

## Verification and limitations

Thirty tests were added to existing suites: 13 intent-response cases, 15 healing/map cases and two native intent-CLI cases. Positive controls and failing unchanged-baseline cases are retained. Final checks include 33 intent, 140 provenance, 202 read-injection, 46 artifact-authoring, 12 bridge, 21 host-descriptor and 16 artifact-consumer tests; 34 version-contract tests and eight existing provenance-wiring checks also passed. Generator parity and Python compilation passed. Exact commands, outcomes, file identities and failures are in the [execution evidence](2026-09-25-brownfield-prerequisites-evidence.json).

Native tests use the exact published ca 2.21.16 artifact payload, SHA-256 `32588a10eb5070b408443e5a0ef23453128725d33574c49a93f5edf5edf22fb8`, with candidate resources copied into disposable fixtures. They are native integration tests, not a new cold marketplace installation or real-model exercise contribution. No credentials, global settings or installed plugin were changed.

Initial generated-test escaping errors were corrected before meaningful baseline runs and are not regression proof. Initial descriptor checks exposed missing scratch Git metadata and an unsynchronized fallback version; both were corrected. Version-gate calls before committing reported no changed committed payload and are not counted as candidate-version qualification. Exact committed-head gates and hosted CI remain required before merge. No assertions, thresholds, workflows or safety gates were weakened.

## Remaining campaign work and rollback

The schema-owned content writer, truthful initialization and partial recovery, bounded isolated scout contract, provenance membership/version transitions, portable task handoff, complete installed-host journey and conditional guidance pilot remain unimplemented. Do not label the exercise ready from these fixes. Continue from the existing campaign plan, reconciling these source corrections into its task evidence through the normal owner.

Rollback the coupled two modules, generated copies and tests together. Preserve #854's unrelated changes, valid initialized consumer state, human instruction files and historical campaign records. A later rollback release must advance versions normally rather than reuse a distributed version. No organization canon or cross-product claim registry changed.
