# Native CI critical path

The owning files are `.github/workflows/ci.yml` and its same-commit reusable
workflow `.github/workflows/ci-native-platform.yml`. This layout changes CI
execution, not product permissions, native support, coverage floors or release
qualification policy.

## Execution graph

| Job | Starts after | Owns |
|---|---|---|
| `artifact-platform` | Impact selection | Six independent calls to the native-platform workflow. Each call has its own build-to-consumer graph. |
| `artifact-candidate` (called) | Its platform call | One normal CGO-disabled native test/vet/build and same-run candidate binding. |
| `artifact-bridges` (called) | **Its own platform's** candidate | Greenfield, mixed-schema recovery, examples, approval, prerequisites, reconciliation and reply handling. |
| `artifact-conformance` (called) | **Its own platform's** candidate | Complete cross-kind/reference conformance and debug handoff, with the locked reference interpreter. Runs alongside adapter and authority checks. |
| `artifact-authority` (called) | **Its own platform's** candidate | Four duration-balanced, fixture-preserving authority shards. |
| `artifact-platform-passed` (called) | All four local stages | Rejects missing, failed, skipped, pending or cancelled local stages. |
| `artifact-native-default` | Impact selection | Default Go tests and vet; Linux race, generated-type, surface, consumer and ship-set checks. |
| `artifact-native-coverage` | Impact selection | Actual instrumented CLI exercise and full instrumented Go statement run, preserving both profiles. |
| `artifact-context` | Impact selection | Native storage, finite context cases, installed-input refusals and context workflow. |
| `artifact-coverage` | All six instrumented cells | Complete statement union and the unchanged coverage floor. |
| `artifact-engine` | All platform calls, default/context checks and coverage | Strict global success join, exact candidate/context-observation verification, then the existing qualification receipt. |
| Browser and package assembly | Native qualification | Existing browser evidence and exact package assembly. |
| Cold packages | Package assembly | Unchanged eighteen-cell host/platform installation matrix. |

The reusable workflow eliminates the **global candidate matrix barrier**. A
Linux or macOS consumer can start when its own binary is ready, without waiting
for a slow or queued Windows build. Four authority shards remain on each of the
six platforms. Matrix failures do not cancel sibling cells. No polling jobs
occupy runners while waiting for artifacts.

The global qualification and protected merge gates remain fail-closed. The
merge gate registers `artifact-platform` and the other required stage groups in
both `needs` and its required-results list. Each platform call has its own
strict join, so a skipped local stage cannot become a successful global result.
Impact-unselected runs retain their legitimate skips. The six final native
qualification check names remain unchanged for existing package verifiers.

The default Go configuration, the builder's CGO-disabled configuration and the
instrumented configuration are deliberately separate checks. Coverage is not
relabelled as an uninstrumented run. The removed work is the twelve extra normal
builders formerly executed by the two-per-platform authority jobs before this
PR. `tools/build-artifacts.py` and `tools/artifact-coverage.py` retain their normal
verification commands; there is no skip-tests fast path.

## Candidate and qualification boundary

The normal builder completes tests and vet before writing `native_tested: true`.
Its job then writes `artifact-candidate-ci.json`, binding the actual binary and
manifest to the checkout, module bytes, pinned native Go executable, source
commit, workflow run and producer attempt. Consumers download named artifacts
from the same run, validate those inputs before executing and recheck candidate
bytes afterward. They never rebuild or promote the manifest.

The caller invokes the reusable workflow by its local repository path, so both
files come from the same commit. The called workflow has read-only content
permissions, no external workflow reference and no inherited extra secrets.
GitHub's `github` context remains associated with the caller. The binding keeps
`.github/workflows/ci.yml` as the run owner and `artifact-candidate` as the
producer identity.

Only the existing global `artifact-engine` job may invoke `--qualify-existing`.
It verifies the same candidate and the exact-platform context observation,
retaining finite-case, module and Go-executable checks. Release assembly still
consumes `artifact-native-*` receipts, never intermediate candidate artifacts.

The CI binding is an unkeyed substitution check, not a signature or independent
execution attestation. GitHub's same-run artifact transport and required job
graph supply the boundary. A retry of failed consumers may reuse a successful
earlier producer attempt of the **same source and run**; another run, a future
attempt, changed source/tool or changed candidate bytes is refused.

## Exhaustive duration-balanced authority shards

`run_artifact_authority_shard.py` discovers the complete authority module,
including imported regressions. Whole unittest classes remain together so their
class fixtures execute once. Longest measured groups go first to the lightest
shard, with deterministic tie-breaking. Unknown classes receive a positive
default estimate; added cases scale a known class's weight. Missing or stale
timing hints never remove a test.

The runner checks nonempty, complete and disjoint membership before execution,
then checks actual execution counts and outcomes. A wholly skipped or
expected-failure shard is not proof. Legitimate individual platform skips remain
reported. Each shard emits selected IDs, a common partition digest, outcomes and
actual per-case timings.

Initial hints are bound to Windows ARM64 jobs `117418643650` and `117418643661`
in run `39039950454`, source `0312358ff7f84ade3855fdf670ba0b2117fb8e9b`.
The old alphabetical halves contained 135 cases each but took 979.883 and 235.621
seconds. The 270-case dataset assigns four roughly 302–308-second scheduling
weights. These are log-derived hints, not a cross-platform runtime promise.

## Observed baseline and correction

Successful baseline run `39039950454` took **49m21s**. Windows x64's limiting job
took 38m34s; initial module tests, statement collection and the candidate builder
ran serially for 664, 444 and 439 seconds. The impact selector also waited 386
seconds before its eight seconds of execution. Queueing stays in the headline.

The first parallel attempt, `39052933204` at
`c399d3ecf2a318027fc6d137f3682c08bf07aa70`, failed after **27m20s**. All 24
authority shards and the candidate, context and instrumented groups passed.
One Linux ship-set wiring assertion still inspected the old job location. The
strict join correctly rejected it; browser/package work did not complete, so
this failed run is **not** speedup evidence.

That attempt also exposed avoidable waits: Intel macOS built its candidate by
6m01s but its consumers waited until roughly 10m28s for the global candidate
matrix. A late authority shard started at 20m40s. The Intel adapter/conformance
job took 12m44s, including 7m17s of conformance after its earlier adapter checks.
The per-platform call graph and separate conformance job remove those dependency
barriers. They do not promise to remove GitHub runner-capacity limits.

The missed ship-set wiring assertion is corrected to inspect its actual owner,
`artifact-native-default`, and now also runs in the early platform-neutral
contract suite. Both `impact` and `artifacts` filters include every new pipeline
subject, including the reusable workflow and the contract suite itself. Filter
closure has a regression test rather than relying on a workflow edit happening
to trigger broad checks.

## Acceptance and rollback

The engineering target remains a **full green run under 20 minutes**, followed
by repeated comparable successful runs to establish the ordinary elapsed range.
It is not a new hard timeout or a demonstrated performance claim. Acceptance
requires all selected native configurations, authority shards, complete coverage,
browser/cold-package checks and the protected merge gate.

Fetch every job page when measuring larger runs:

```sh
gh api --paginate --slurp \
  'repos/arbiterForge/codeArbiter/actions/runs/RUN_ID/jobs?per_page=100'
```

Record exact source/merge revisions, run and attempt, the full run envelope,
queue delays, stage durations and the final gate. Failed or cancelled envelopes
are not comparable green benchmarks. The Pi hosted-check reader likewise
paginates all check pages and refuses incomplete or duplicate results.

`test_ci_native_pipeline.py` covers both strict joins, substitution/retry cases,
actual discovery and fixture-preserving partitioning, platform completeness,
single-builder ownership, caller/callee dependencies, filter closure, ship-set
wiring and check pagination. Existing context, coverage, package and release
contracts remain. Refresh enrolled source evidence through the native context
writer; never silence stale-source refusals or change human documents just to
update a digest.

No account setting, protected required-check name, product state format or
packaged dependency changes. Rollback is a normal revert of this coherent CI
change and its matching provenance records. Intermediate artifacts are not
publication artifacts and do not migrate consumer state.
