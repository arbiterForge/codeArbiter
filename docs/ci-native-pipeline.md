# Native CI critical path

The owning implementation is `.github/workflows/ci.yml`. This is a CI execution
layout, not a change to product permissions, host support, coverage floors or
released-product qualification policy.

## Execution graph

| Job | Starts after | Owns |
|---|---|---|
| `artifact-candidate` | Impact selection | One normal module-tested, CGO-disabled candidate build and vet per native platform. |
| `artifact-native-default` | Impact selection | Default Go tests and vet; Linux race, generated-type, surface, consumer and ship-set checks. |
| `artifact-native-coverage` | Impact selection | The actual instrumented CLI exercise and full instrumented Go statement run, preserving both profiles. |
| `artifact-context` | Impact selection | Native storage checks, finite context cases, installed-input refusals and the context workflow. |
| `artifact-bridges` | Candidate builds | Greenfield, mixed-schema recovery, examples, approval, prerequisites, reconciliation, reply handling, complete conformance and debug handoff. |
| `artifact-authority` | Candidate builds | Four duration-balanced authority shards on each native platform. |
| `artifact-coverage` | Instrumented native checks | Complete six-platform statement union and the unchanged 70 percent statement floor. |
| `artifact-engine` | Every preceding stage | Strict success join, exact candidate and context-observation verification, then the existing native qualification receipt. |
| Browser and package assembly | Native qualification | Existing browser evidence and exact package assembly. |
| Cold packages | Package assembly | The unchanged host/platform installation matrix. |

All six native platforms remain. Matrix failures do not cancel sibling cells.
The merge gate registers every new stage both in `needs` and in the required
result list. The qualification join rejects missing, skipped, pending, failed or
cancelled stages when native verification was selected. Impact-unselected runs
retain their existing legitimate skips.

The default Go configuration, the builder's CGO-disabled configuration and the
instrumented configuration are deliberately separate checks. Each executes in
its owning platform job; coverage is not relabelled as an uninstrumented test.
The removed work is the twelve extra normal builders formerly run in the two
per-platform authority shards. Those tests now consume the single tested
candidate. `tools/build-artifacts.py` and `tools/artifact-coverage.py` retain their
normal verification commands; this layout does not add a skip-tests fast path.

## Candidate and qualification boundary

The normal builder completes tests and vet before writing `native_tested: true`.
The candidate job then writes `artifact-candidate-ci.json`, binding the actual
binary and manifest to the checkout, module bytes, native Go executable, source
commit, workflow run and producer attempt. Every consumer downloads the named
artifact from its own run, validates those inputs before execution, and never
rebuilds or promotes the manifest. Adapter and authority jobs also recheck the
candidate after their tests.

The final `artifact-engine` job is still the only job that may use the existing
`--qualify-existing` path. Its `artifact_ci.py gate` step must accept all required
stage results before any qualification is written. It verifies the same candidate
and consumes the exact-platform context observation, which retains the existing
finite-case, module and Go-executable checks. Release assembly still consumes
`artifact-native-*` receipts, not the intermediate candidate artifacts.

The CI binding is an unkeyed substitution check, not a signature or an
independent execution attestation. GitHub's same-run artifact transport and the
required execution graph supply the job boundary. A retry of failed consumers
may reuse a successful earlier producer attempt of the **same source and run**;
a later attempt, different run, changed source/tool or changed bytes is refused.

## Duration-balanced authority shards

`run_artifact_authority_shard.py` discovers the complete authority suite, including
imported regression classes. Test classes remain indivisible so their class-level
fixtures execute once. Longest measured fixture groups are assigned first to the
currently lightest shard, with deterministic tie-breaking. Unknown classes use a
positive default estimate, and added tests in existing classes scale that class's
weight. Missing timing data never removes a test.

The runner proves nonempty, complete, disjoint membership before executing any
shard. It checks actual execution counts, fails unsuccessful results, and rejects
a wholly skipped/expected-failure shard. Legitimate individual platform skips
remain reported as skips. It emits selected IDs, a common partition digest,
outcomes and actual per-case times in a same-run diagnostic artifact.

Initial hints come from completed Windows ARM64 authority jobs `117418643650`
and `117418643661` in run `39039950454`, source commit
`0312358ff7f84ade3855fdf670ba0b2117fb8e9b`. The old alphabetical halves selected
135 cases each, but their test steps took 979.883 and 235.621 seconds. The retained
270-case dataset produces four approximately 302 to 308 second scheduling
weights. These are log-derived hints, not measured times for the new workflow,
a cross-platform forecast or percentile estimates. New tests are always discovered.

## Evidence and acceptance

The baseline run `39039950454` succeeded in 49 minutes 21 seconds. Windows x64's
limiting native job took 38 minutes 34 seconds; its initial module tests,
statement collection and normal candidate builder took 664, 444 and 439 seconds
respectively. The earlier Windows ARM64 job was slightly longer, but finished
first. The eight-second impact selector also waited 386 seconds to start. Keep
execution time, dependency waits and runner queueing distinct, without removing
any of them from the end-to-end headline.

The engineering target is a full green run under 20 minutes, followed by repeated
comparable runs to establish the ordinary elapsed range. It is not a new hard CI
timeout or a claimed measured improvement. Acceptance requires every selected
native configuration, all authority shards, coverage, browser and cold-package
checks, and the protected merge gate. Native platform behavior and final runtime
must be checked on the hosted candidate, not inferred from local contract tests.

For each run, fetch all job pages, not just the first 100:

```sh
gh api --paginate --slurp \
  'repos/arbiterForge/codeArbiter/actions/runs/RUN_ID/jobs?per_page=100'
```

Record the exact source and merge revision, run and attempt, full run envelope,
queue delay, stage times and final gate. Compare successful runs against the
49m21s baseline; failed or cancelled runs are not speedup evidence. The Pi
hosted-check reader also paginates all check-run pages and refuses incomplete,
changing or duplicated results, so larger CI fan-out cannot hide a required
check beyond page one.

## Verification and rollback

`test_ci_native_pipeline.py` exercises the strict join, candidate substitution
and retry controls, real suite discovery, deterministic fixture-preserving
partitioning, complete platform matrices, single-builder ownership and check
pagination. Existing impact, context, coverage, package and release contracts
remain in place, with their assertions mapped to the actual new owners. Native
provenance for the changed workflow must be refreshed through the context writer;
do not silence a stale-source rejection or rewrite the human documents merely
to update its digest.

No repository setting or protected required-check name changes. No new package dependency,
paid runner, service, database or product state format. Rollback is a normal
revert of the coherent CI change and its matching provenance records. Intermediate
CI artifacts are not publication artifacts and do not migrate consumer state.
