# Tests, fault injection and exact-artifact qualification

## Meaning of this file

These are implementation acceptance instructions. The handoff did not execute new product changes. Existing audit probes/results stay under `audit/` with their original limits. A test command written here is not an executed result. All new scenario records begin NOT_RUN.

## Required layers

1. **Contract and local behavior:** exact input/state/event/guard/effect results, valid and invalid cases, protocol/serialization compatibility and owner registry closure.
2. **Composed sequences:** writer → reader, permission → effect → receipt, commit → response loss → readback, cancel → cleanup → late callback, and upgrade/retirement with historical records.
3. **Generation/build:** shared Python and host surface equality, rebuilt JavaScript bundles, generated root metadata, complete native build identity and package member/digest checks.
4. **Installed behavior:** actual supported hosts and platforms using the exact candidate packages, including real delegated Pi authorship and actual Docker lifecycle where claimed.
5. **Release settlement:** observed immutable tag, correct artifact/registry/marketplace identity and required publication receipt, followed by truthful site/route observation.

Use ordinary assertions about effects and retained state. One discriminating sequence can cover many transition rows. Do not write 1,748 tautological tests that restate the table. Do not accept a grep/keyword check as proof of a permission boundary, semantic comparison, process containment or installed capability.

## Source-owned command entry points

Run from the repository root unless a working directory is named. Install the reviewed dependencies and environment declared in the workflow; do not copy a bare command without its setup. The exact current CI job/step inventory is in `evidence/ci-job-inventory.json`; refresh it from the execution source.

| Purpose | Existing entry point / owner | Important qualification limit |
|---|---|---|
| Generated host surfaces | `python3 tools/build-surface.py --check` | Equality proves the projection, not host execution. |
| Shared Python copies | `python3 tools/sync-core.py --check` | `_host.py` and bespoke adapters remain owner-specific. |
| Package metadata | `python3 tools/build-host-packages.py --check` | Exact native-bearing package assembly/cold checks also need their CI inputs and identities. |
| Native complete population | `python3 tools/go_test_parallel.py --module core/artifacts` | Current module declares Go 1.27.1. Preserve complete test population and supported platform behavior. |
| Native race paths | `python3 tools/go_test_parallel.py --module core/artifacts --build-flag=-race` | Current CI scopes this to supported Linux race execution; do not claim every cross-platform race cell. |
| Native generated types | `python3 tools/generate-artifact-types.py --check` | Add contracts through actual generators, not hand-edited generated files. |
| Native bridge/contracts | Current `artifact-native-default`, `artifact-native-bridges`, `artifact-authority`, `artifact-browser` jobs | Use actual named suites and installed candidate identities; honor unsupported cells. |
| Prompt delivery | `python3 .github/scripts/test_prompt_submit.py` | Existing audit ran 33 tests; add mode revisitation and failure settlement cases. |
| Farm | In `plugins/ca/tools`: `npm ci --ignore-scripts`, then `npm run typecheck`, `npm test`, `npm run build` | Verify committed farm.js equality and actual containment/recovery tests. |
| Sandbox | In `plugins/ca-sandbox/tools`: reviewed install, typecheck, test and build scripts | Required Docker evidence uses `CA_SANDBOX_REQUIRE_DOCKER=1` plus the current layer sentinel check. A no-Docker self-skip is not qualification. |
| Pi | In `plugins/ca-pi/tools`: reviewed host graph, toolchain install, typecheck, test and build scripts | Derive supported Pi versions from current policy; use disposable homes and actual supported-host qualification. |
| Release | `.github/scripts/test_release_target.py`, `test_release_workflow.py`, `test_auto_release_candidate.py`, `test_command_route_release_state.py` | Pure planners do not prove registry or hosted publication effects. Add failure/receipt compositions. |
| Site | In `site`: `npm run typecheck`, `npm test`, `npm run test:browser`, `npm run link-audit` | Follow the reviewed lock, pinned Academy source and installed Chrome workflow requirements. No arbitrary browser download substituted as exact hosted proof. |

The captured CI matrix currently includes native/cold-package `linux/amd64`, `linux/arm64`, `windows/amd64`, `windows/arm64`, `darwin/amd64` and `darwin/arm64`. Pi adapter jobs use Linux/Windows/macOS and policy-derived runtime versions. Codex install jobs currently name 0.143.0 and 0.145.0. Re-read current descriptors and qualification policy before execution; do not convert these into a broader support promise.

The routine Codex install lane is different from firing hooks in a real model turn. The major program must qualify the specific newly changed advertised behavior before publication, while retaining any separately documented general advisory/follow-up policy. No model-provider credential is granted to untrusted PR code.

## Cross-owner sequence catalogue

`contracts/scenarios.json` contains 31 concrete acceptance sequences with expected effects. Domain tasks add their own focused cases. The full task/row mapping remains in the structured corpus.

| ID | Sequence | Required observation |
|---|---|---|
| SEQ-01 | Mode revisitation: arbiter → dangerous → arbiter; repeat unchanged prompt; compaction; new session | The selected persona is delivered when selection changes, unchanged events deduplicate, compaction/session identity remains correct and deterministic guards stay active. |
| SEQ-02 | Partial mode persistence: Marker write succeeds → audit append fails → restart/retry | Raw/effective state and owed audit are truthful; replay/recovery neither loses debt nor invents success. |
| SEQ-03 | Native output closure: Ordinary preview → strict snapshot → completion consumer | Every supported generated output is recognized and validated; arbitrary unregistered output still rejects. |
| SEQ-04 | Native discovery closure: Capabilities/schema discovery → dispatch each declared operation; implemented operation enumeration | Names, schema, dispatch, lock/effect class and documentation agree, including repair-apply. |
| SEQ-05 | Qualified binding limits: Largest supported npm/OS launch binding → completion; one over limit; duplicates/unsafe files | Producer/consumer bounds agree for all supported cells without broad unsafe admission. |
| SEQ-06 | History-preserving retirement: Check task → retire → render/validate/history lookup; scope baseline → checkpoint retirement | Retired identity/history remains valid; current observations are not silently deleted to make validation pass. |
| SEQ-07 | Progress/evidence decision: Upstream block/change → independent task; dependent task; ordinary versus strict review | Apply the B-selected SMARTS semantics. Independent work continues; current evidence never overstates historical progress or authority. |
| SEQ-08 | Scoped conflicts: One artifact/policy conflict → dependent task and independent task; shared pending journal | Pause only actual dependencies. Preserve store-wide integrity dependency where pending multi-file recovery requires it. |
| SEQ-09 | Corrected resubmission: Malformed debug/review → corrected fresh attempt → later actual denial → replay old attempt | Corrected input is evaluated anew under proper identity/current bindings. Old rejection remains immutable; host/user denial is not bypassed. |
| SEQ-10 | Durable harvest interruption: Find eligible result → durable obligation → terminate before terminal step → reentry → reconcile → duplicate reentry | One logical target entry is settled or explicitly unresolved; duplicate delivery is detected; optional backlog never blocks independent ordinary work. |
| SEQ-11 | Harvest failure and retention: Storage failure; corrupt record; claimed worker crash; index rebuild; failed target observation; retention boundary | Bounded diagnostics, no false settlement, no data loss disguised as cleanup and no repeat remote effect without readback. |
| SEQ-12 | Functional Pi author: Supported parent → scoped child → read/write/edit → permitted verification execution | Actual mutations and verification succeed within a parent-admitted action scope; the final bridge and authority checks remain enforced. |
| SEQ-13 | Pi delegation abuse/refusal: Wrong child/session/run/generation; forged scope; path escape; plan mode; revoked/expired grant; replay changed request | All invalid attempts refuse before their side effects. Exact replay does not duplicate the effect; a child cannot mint or broaden its grant. |
| SEQ-14 | Pi delegation interruption: Grant admitted → parent cancels/session switches → child response late; effect commits then response/audit settlement lost | Ordinary authority is revoked, owned cleanup completes, uncertain effect is observed before retry and result truth is retained. |
| SEQ-15 | UI lifetime and readiness: Dispose while metrics pending; bridge ready then persona read fails then bridge refresh succeeds | No stale sidebar installation; readiness exposes independent persona/bridge state and retry. |
| SEQ-16 | Package identities: Build a qualified manifest → install → doctor → farm admission | One supported manifest shape and package identity works across producer/installer/bridge/farm/diagnostics; unsupported/malformed metadata still refuses. |
| SEQ-17 | Farm receipt-only recovery: Commit/merge tasks → report failure → resume/recover same run | Recover evidence from retained operation/commit identities without author redispatch, branch reset or log truncation. |
| SEQ-18 | Farm containment and observation: Gate timeout → failed cleanup; failed Git diff/listing → retry decision | No mutation/reset/retry while containment is unknown; unavailable observation is not clean. |
| SEQ-19 | Sandbox cache: Equal dependencies in different temporary paths; changed builder/dependencies/platform | Stable equal identity reuses the intended cache; relevant content/builder/platform changes invalidate it. |
| SEQ-20 | Sandbox overflow/cleanup: Output overflow/abort → container stop/removal fails → registry observation fails → targeted re-observation | Command failure, containment, removal and observation remain separate. No false destroyed/empty claim and no unrelated instance cleanup. |
| SEQ-21 | User setting ownership: Install → user edits spinner/status setting → uninstall | Uninstall restores only still-owned values; later user edits survive. |
| SEQ-22 | Release interruption: Tag/draft/registry/public Release → final publication receipt failure → rerun | Only missing effects run. Public-without-receipt remains recoverable; immutable source/payload identity holds. |
| SEQ-23 | Exact release source/readiness: Older successful main CI, newer failed head, candidate artifact rebuild, forged/absent readiness | Major publication binds the approved exact source/build/bytes; no first publication before required installed qualification. |
| SEQ-24 | Publication projection: Stable tag-only/draft/published/mismatch/API unavailable → site and route clock | Tag is not publication; exact observed state and uncertainty survive into visible claims and JSON. |
| SEQ-25 | Qualification truth: Empty measurements, unknown scenario, optional skip, unavailable host/protection API, invalid base version | No false PASS/first-introduction/verified claim; existing advisory exit behavior stays explicitly scoped. |
| SEQ-26 | Measurement identity: Dirty workflow at HEAD; failed SMARTS subprocess; lens-name-only output; failed statusline renderer | Evidence is bound to actual source/harness, material reasoning is checked, no success from failed/empty producers and cleanup settles. |
| SEQ-27 | Verifier liveness: Child never emits first line/ready; installer hangs; cancellation during collection | Deadline bounds every phase; partial diagnostics and process containment are preserved. |
| SEQ-28 | Site async controls: Search/load/data/expand reject and resolve out of order; drawer reconnect | Current generation controls visible results, finally/retry restores controls, listeners do not multiply. |
| SEQ-29 | Generated/source consistency: Change owner fact → regenerate hooks/surfaces/catalog/site/bundles → package → installed readback | Counts/grammar/identity/claims come from actual owners, while bytes and host behavior are verified separately. |
| SEQ-30 | Sandbox instruction usability: No Nixpacks but supported fallback; shell exit; named destroy; normal offline run; consumer lacks maintainer docs | Model-guided instructions select supported behavior and correct scope without inventing authority or promising unsupported confinement. |
| SEQ-31 | Fresh and upgraded installs: Each supported prior artifact/state → new candidate → actual host workflow → uninstall/rollback boundary | Installed artifacts, schema compatibility, state preservation and user settings survive supported upgrade paths; unsupported cells are explicit. |

## Evidence record for every executed case

Record scenario/task IDs; exact repository commit; platform/architecture; actual host/runtime version; package/binary/manifest/member digests; input fixture identity; setup and command; selected and executed population; assertions and expected failures; observed return/side effects; timeout/cancellation/containment; raw diagnostic location; result; and limits. Include the producer/runner identity and workflow/run/job where relevant.

Allowed results are PASSED, FAILED, UNAVAILABLE, SKIPPED, NOT_APPLICABLE and NOT_RUN. They are not interchangeable. A required cell accepts PASSED only. A verified contract exception can make a cell NOT_APPLICABLE with its source/rationale. Missing credentials/runtime/permissions stays UNAVAILABLE. An expected negative test passes only when the expected refusal and absence/presence of effects were observed.

## Regression and mutation quality

First reproduce each relevant defect on the baseline or document why a safe native/host fixture is needed. Add tests that would fail when the producer/consumer bound, generation check, receipt eligibility, containment propagation or authority binding is intentionally removed. Use the repository's applicable coverage/maturity rules and targeted mutation testing where it demonstrates a real invariant; do not multiply duplicate tests for counts.

## Final readiness

Q-01 closes implementation, migration, documentation and candidate qualification on the integration branch. Actual publication/public readback remains Q-03 and is excluded from PREPUBLICATION_READY; DISTRIBUTION_SETTLED requires it afterward. Q-02 prevents automatic publication from outrunning exact final-byte qualification after promotion. Final program acceptance needs all task/finding dispositions, meaningful row coverage, updated ADR/docs, upgrade/rollback proof and exact artifact/installed evidence. The packet validator checks none of the product runtime claims; the implemented trusted readiness verifier must check them through actual evidence.

Sources: [current CI](https://github.com/arbiterForge/codeArbiter/blob/fd7eb34b2da439551443d09526ab48fd1d1bb9bf/.github/workflows/ci.yml), [native module](https://github.com/arbiterForge/codeArbiter/blob/fd7eb34b2da439551443d09526ab48fd1d1bb9bf/core/artifacts/go.mod), [host descriptors](https://github.com/arbiterForge/codeArbiter/blob/fd7eb34b2da439551443d09526ab48fd1d1bb9bf/core/hosts.json), [site package](https://github.com/arbiterForge/codeArbiter/blob/fd7eb34b2da439551443d09526ab48fd1d1bb9bf/site/package.json), [sandbox harness](https://github.com/arbiterForge/codeArbiter/blob/fd7eb34b2da439551443d09526ab48fd1d1bb9bf/plugins/ca-sandbox/tools/vitest.config.ts), [Pi test setup](https://github.com/arbiterForge/codeArbiter/blob/fd7eb34b2da439551443d09526ab48fd1d1bb9bf/plugins/ca-pi/tools/test/setup-disposable-home.ts).

Also test delayed readiness after main advancement: a new Pi npm publication must preserve the actual release-event SHA equality, or move to a freshly built and qualified eligible source under the existing provenance policy. Packet tests must detect a circular prepublication requirement on Q-03.
