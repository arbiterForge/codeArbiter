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
| `artifact-conformance` (called) | **Its own platform's** candidate | Complete cross-kind/reference conformance and debug handoff, with the locked reference interpreter. Runs alongside adapter and authority checks; its five independent native suites overlap with a three-process bound. |
| `artifact-authority` (called) | **Its own platform's** candidate | Four duration-balanced, fixture-preserving shards, executed as two jobs with two isolated child processes each. |
| `artifact-platform-passed` (called) | All four local stages | Rejects missing, failed, skipped, pending or cancelled local stages. |
| `artifact-native-checks` | Impact selection | Three isolated concurrent workers: default tests/vet and Linux-specific checks; instrumented CLI/module coverage; native storage/context workflows. |
| `artifact-coverage` | All six complete configuration groups | Complete statement union and the unchanged coverage floor. |
| `artifact-engine` | All platform calls, configuration groups and coverage | Strict global success join, exact candidate/context-observation verification, then the existing qualification receipt. |
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

## Grouped native configurations and runner contention

The default, instrumented and context configurations remain independent work,
but no longer request three separately provisioned runners per native platform.
`artifact-native-checks` uses three child interpreters on one runner, with at
most three active configurations, or two on Windows ARM64. This removes
**twelve runner startups** from a full six-platform run, including four macOS
requests, without putting tests into the candidate builder's dependency chain.

The versioned command plan `.github/ci-native-checks.json` owns all fourteen
original commands, working directories, context observation output and the five
existing Linux-only selections. The runner rejects missing or reordered commands
and unexpected platform exclusions. Default and race Go tests now explicitly use
`-count=1`: compiler work may be shared safely inside the runner, but successful
test results are never reused as fresh verification. The normal candidate
builder and coverage collector remain unchanged.

Every worker has a private home and temporary directory, configuration-specific
output paths and logs, and a complete named result. The parent requires all
three real child exits, matching plan/platform identities, exact command
membership, the expected selections and successful results. Missing, stale,
substituted or failed results refuse. Cleanup uses the existing bounded
Windows-sharing-error owner; no test is retried. Diagnostics exclude worker
homes, retain per-command timings, and include the workflow attempt in their
artifact names. Coverage and context outputs retain their existing artifact
names and qualification consumers.

This change addresses a measured scheduling bottleneck: successful run
`39071349661`, head `97bf20ff32c164f1134cffb5d7d467dce8e99dc6`, passed all
125 jobs but took **28m44s**. Its Intel macOS candidate did not start until
**11m27s** after run creation; its own execution was **5m17s**. That delayed its
consumers and the final qualification join. The result is not evidence of a
product regression or a configured account limit. Fewer runner requests reduce
avoidable competition; no account setting or paid runner is changed.

The complete new group passed locally on Windows/amd64 in **544.074 seconds**.
All selected default, coverage and context commands executed, including the full
module tests, actual instrumented CLI, complete native statement collection,
named context cases and all thirty context-workflow tests. The five Linux-only
commands were correctly unselected on that platform, not claimed as executed.
This is functional local evidence, not a hosted speedup or a successful
under-twenty-minute full CI run.

The first grouped hosted run, `39085371841` at `b91ec07b`, then exposed a
Windows ARM64 contention boundary. The default operations package reached its
unchanged Go **ten-minute suite-wide limit**; the currently starting test had
run for zero seconds, so the log does not establish a stuck test. Coverage and
context configurations both passed, while the parent retained the default
failure and prevented coverage/qualification promotion. This failed run is not
speedup evidence.

Windows ARM64 now starts at most **two** native configuration workers, with the
third still submitted and required after a slot becomes available. Other
platforms retain the three-worker schedule. This is a narrow scheduling repair,
not proof that every future ARM64 run will be fast: the next hosted run must
exercise it. Go's ten-minute package limit, the existing job budgets, every
command and every assertion remain unchanged. No failed test is retried, and no
partial successful configuration can stand in for the complete group.

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

`run_artifact_authority_group.py` schedules partitions `(0, 2)` and `(1, 3)`
as two jobs per platform. Each group uses two child interpreters with separate
homes, temporary paths, logs and observation files. Worker roots remain shallow
and separate from the diagnostic directory. The parent independently
rediscovers the partition and rejects missing reports, nonzero exits, wrong
membership, stale partition digests, duplicated observations and wholly
unexercised results. This retains all four partitions while removing twelve
runner startups from a full six-platform run. It does not claim twice the
available CPU or change a timeout.

Timing artifacts include platform, group and workflow attempt. A failed-test
attempt and its successful rerun therefore retain distinct diagnostics instead
of colliding on an immutable fixed-name artifact. Only the top-level JSON and
log files are uploaded, never worker home or temporary directories. Existing
candidate reuse across a failed-consumer retry remains independently verified.

The conformance harness starts all five existing native suites with at most
three concurrent child processes. The measured longest package and workflow
suites are submitted first. Each child inherits the same candidate and pinned
reference interpreter but receives a separate home and temporary environment.
The original exact membership, no-unexpected-skip, exit-status and before/after
candidate-identity assertions remain. A failed child cannot be replaced by a
successful sibling, and the parent waits for submitted work before returning.

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
`artifact-native-checks` and its command plan, and also runs in the early platform-neutral
contract suite. Both `impact` and `artifacts` filters include every new pipeline
subject, including the reusable workflow and the contract suite itself. Filter
closure has a regression test rather than relying on a workflow edit happening
to trigger broad checks.

## Successful intermediate run and remaining scheduling work

Run `39060990810`, head `50ae5f148d3dd29a94a95b73f2bce823ce20111d`,
completed successfully in **31m05s** with all **137 CI jobs** successful. This
is a measured improvement over 49m21s, but it does not meet the under-20-minute
target. Its Intel macOS conformance job ran for 607 seconds, with 485 seconds
inside the conformance harness. The five native child suites still executed
sequentially; the package and workflow suites accounted for roughly 251 and
132 seconds respectively. The current bounded overlap addresses that serial
work without creating additional conformance runner jobs.

The run reached five simultaneous macOS runners and some macOS jobs waited
more than ten minutes to start. Those observations do not establish the account's
configured limit, but explain why simply adding more job shards is not a free
wall-clock improvement. The two-job/four-process authority layout reduces queued
runner requests and repeated setup. No account-concurrency setting or paid
runner is introduced. Queueing still counts in end-to-end acceptance.

Review identified an attempt-name collision in authority diagnostics. It is
corrected with the attempt-qualified artifact names above. A further source
review found that changing only the new reusable definition did not match the
main-push trigger; that path is now explicit and regression-tested, in addition
to its existing `impact` and `artifacts` filter registrations.

## Toolchain acquisition and measured local conformance

Run `39067340600` exposed an additional setup penalty: Windows ARM64 candidate
job `117497658867` spent about 402 seconds in Go setup, including two aborted
requests, before its normal module tests started. The explicit
`go-download-base-url: https://go.dev/dl` is a custom-source override, even
though it names the normal upstream domain. The pinned setup-go implementation
uses a separate custom cache namespace and skips its standard GitHub-hosted
Go distribution path in this mode.

Native CI now omits that override. The same SHA-pinned setup action first uses
its normal exact-version tool cache, then its official Actions Go distribution,
with its existing upstream fallback. The inspected manifest publishes Go 1.27.1
for all six selected native platforms, including Windows ARM64. This restores
the supported default acquisition route; it does not introduce an arbitrary
mirror, a floating Go version or test-result caching. Go remains exactly 1.27.1,
`check-latest: false`, `GOTOOLCHAIN: local`, and module/build caching remains
`cache: false`. Native tool and candidate identity verification is unchanged.
Whether this avoids a future network stall is a hosted measurement question,
not a guarantee inferred from one successful download.

A three-pair alternating-order local comparison independently tested the
conformance scheduling change on Windows/amd64 with the same native binary and
hash-locked reference interpreter. All six runs passed. Serial observations were
203.079, 190.622 and 190.577 seconds; parallel observations were 130.171, 121.360
and 121.327 seconds. The medians were 190.622 and 121.360 seconds respectively,
a 36.3 percent reduction for this harness. These small-sample warm-cache results
are neither hosted full-CI timing nor percentile claims. The raw observations
are retained with the PR verification record.

## Worker cleanup failure boundary

Both worker owners use the same bounded cleanup helper. A transient Windows
sharing violation (`PermissionError.winerror == 32`) is retried for at most two
seconds and 41 attempts, matching the existing native farm fixture's policy.
Only cleanup is retried, never the child test or its assertions. Persistent
sharing violations and every other cleanup error remain fatal. The owned root
is not ignored or deleted through an arbitrary path. A failed child remains a
failure even when a cleanup retry succeeds.

Regression tests inject sharing failures after actual worker entry, prove each
child executes once, and verify retry success, deadline exhaustion, persistent
failure and non-sharing errors for both authority and conformance boundaries.

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
wiring, grouped child verification, conformance concurrency, attempt-qualified diagnostics
and check pagination. Existing context, coverage, package and release
contracts remain. Refresh enrolled source evidence through the native context
writer; never silence stale-source refusals or change human documents just to
update a digest.

No account setting, protected required-check name, product state format or
packaged dependency changes. Rollback is a normal revert of this coherent CI
change and its matching provenance records. Intermediate artifacts are not
publication artifacts and do not migrate consumer state.
