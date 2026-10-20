# CI20-01: current-source reconciliation and reproducible timing baseline

**Status:** CI20-01 discovery and benchmark implementation; **no CI execution
pipeline or release behavior has changed.**

**Inspected current development source:** `arbiterForge/codeArbiter@9bf8b69ec21114f829f8745606d8da25a8f89a15:/`.
**Current-source CI:** `arbiterForge/codeArbiter@9bf8b69ec21114f829f8745606d8da25a8f89a15:.github/workflows/ci.yml`.
**Historical prototype:** [PR #993](https://github.com/arbiterForge/codeArbiter/pull/993),
head `16983f5017b39e35de2f90994e30fcd60730e82c`, base
`5f25ba840f8e86908980d994f629398b1747fd37`. Its referenced
reusable workflow at the recorded PR merge ref was
`eb790e383fb0e792913db219ff8c3dbcc8e0585a`. This reference
does **not** establish the state of current `main`.

**Plan:** [PR #1011](https://github.com/arbiterForge/codeArbiter/pull/1011),
`docs/plans/ci-under20.md` at
`88a692efd21197cc1294bced3b16cd223d3fe8ec`.
This report is the first execution slice of that plan, independently based on
the newer main commit above; the implementation does not incorporate the old
PR's workflow.

## 1. Replayed full-run measurements

| Source and run | Actual elapsed, including waiting | Zero-queue replay | Jobs | Observation |
| --- | ---: | ---: | ---: | --- |
| Historical #993, `39088746696` at `16983f50` | **59m43s** | **21m11s** | 113 successes | Complete prototype DAG |
| Preceding main, `39345028289` at `849a3cf6` | **47m09s** | **45m32s** | 74 successes, 9 skips | Unrestructured native DAG |

The newer source `9bf8b69e` added a control-byte gate after the preceding
`849a3cf6` main run. Its own full CI run had **not yet completed at this
source-inventory freeze**. The 47m09s run is therefore deliberately labeled
a **preceding-main baseline**, not proof of execution time at `9bf8b69e`.

Queue-free replay is a dependency counterfactual using the observed durations
of every job, including setup and cleanup. It assumes unlimited instantly
available runners. It is not achieved CI performance. Actual elapsed begins
at GitHub's workflow `created_at` timestamp and ends at the completed run's
`updated_at`; upstream webhook delivery latency cannot be inferred from
those fields.

The preceding-main no-queue determining chain contains impact selection
(**7s**), the Windows ARM64 structured-artifact job (**2,472s**),
package assembly (**52s**), a macOS Intel Pi cold-package cell (**198s**)
and final gate (**3s**). The sum is **2,732s**; do not compare it directly
with the prototype graph without accounting for changed job dependencies,
verification owners and source code.

### Immutable reproduction artifacts

Each numbered directory contains:

- `run.json.gz`: unpruned GitHub workflow-run API object.
- `jobs-pages.json.gz`: all unpruned API page **objects**, compressed as
  normalized JSON with a stable gzip header; every field is retained. This
  is not a claim to preserve exact HTTP response bytes.
- `ci.yml.gz` and, where applicable, `ci-native-platform.yml.gz`: the exact
  source-commit workflow bytes fetched from GitHub.
- `manifest.json`: file-level SHA-256 hashes, repository, run ID and source
  commit; `replay.json.gz`: deterministic dependency/observation result.

The replay tool checks every page's total, unique job IDs, terminal state,
source/run identity, job-name ownership, declared dependencies, timestamp
ordering, and source-file digests. It derives macOS consumption from actual
runner labels rather than platform words in a job name. Missing pages,
duplicates, stale source, unrecognized jobs, incorrect run identity or an
impossible dependency schedule cause an explicit refusal. The complete job
responses are retained so future analyses need not trust a summary alone.

To rerun without contacting GitHub:

```sh
python tools/ci_critical_path.py replay --directory docs/reports/ci20-01/39088746696
python tools/ci_critical_path.py replay --directory docs/reports/ci20-01/39345028289
python -m unittest discover -s tests -p 'test_ci_critical_path.py' -v
```

For the next completed full run, create a fresh directory (never overwrite
an earlier receipt):

```sh
python tools/ci_critical_path.py capture --run-id RUN_ID --directory docs/reports/ci20-01/RUN_ID
```

Capture needs the authenticated `gh` CLI with access to the public
`arbiterForge/codeArbiter` repository. Replay and all tests use Python
stdlib only. This diagnostic does not deploy, mutate GitHub, trigger a new
workflow, or alter any benchmarked code.

## 2. Source-to-job ownership map, current main

`current-main-ci.yml.gz` is the exact archived `9bf8b69e` workflow.
`current-main-obligations.json.gz` records **all 42** current root job
definitions, their actual commands, dependencies, selection predicates, OS
matrices, artifact inputs/outputs and timeout values, with hashes for the
canonical code and test sources. The stored 41-job graph in the earlier
run's `replay.json.gz` belongs to `849a3cf6`; the difference is material.

| Current owner | Selected instances / obligation | Owning requirement |
| --- | --- | --- |
| `changes` | One impact selector | Paths, required suites and no-work cases must remain correctly selected |
| `artifact-engine` | Six native cells | Go default test/vet, instrumented CLI/profile, context checks, CGO-disabled tested binary, installation/adapters and exact per-host qualification |
| `artifact-authority` | Two exhaustive shards per native cell, **12** total | All discovered authority adapter tests with independent candidate identity |
| `artifact-coverage` | One six-platform merge | Complete native Go profiles, integration requirements and **70% statement floor** |
| `artifact-browser` | One required browser check | Actual review output rendered in browser against native candidate |
| `artifact-package-assembly` | One exact-head assembly | Assemble only qualified six-platform candidates with promotion identity |
| `artifact-package-cold` | **18** cells | Six platforms × Claude, Codex and Pi cold-package admission |
| `hooks` | **Five** actual cells | Ubuntu/macOS all suites and three Windows partitions, including hermeticity and leak detection |
| `control-bytes` | New at `9bf8b69e` | Reject forbidden control bytes in tracked text files; this owner must not disappear in future restructurings |
| `ci-passed` | One protected final result | Await and enforce all required results, preserving legitimate explicit exceptions |

Native platform/runner pairs are Linux x64 (`ubuntu-24.04`), Linux ARM64
(`ubuntu-24.04-arm`), Windows x64 (`windows-2025`), Windows ARM64
(`windows-11-arm`), macOS x64 (`macos-15-intel`) and macOS ARM64
(`macos-26`). The complete exact matrix—including host variants, authority
shards and platform-specific conditions—is in the machine inventory; the
table is a summary, not an allowlist.

**Preserve the latest code and current timeout decisions.** At this
snapshot the direct native Go test runs `go test -buildvcs=false
-timeout=20m ./...`; the ordinary candidate builder runs fresh tests
with `-count=1 -timeout=30m` and then vet. The Go coverage command uses
`--minimum-statements 70` and the integration profile requirement.
Linux-only `-race`, SMARTS-specific tests, ship-set evidence-input tests,
Windows storage/readonly regressions and the new control-byte gate are
current obligations. A previous CI20 prototype's flags do not supersede them.

The core sources, settings and tests inspected were
`tools/build-artifacts.py`, `tools/artifact-coverage.py`,
`core/pysrc/_artifactlib.py`, `.github/ci-impact-map.json`,
`.github/scripts/test_ci_impact.py`, the native/hook and ship-set test
scripts, and `.github/workflows/ci.yml`, all at `9bf8b69e`.
Their exact hashes are in `current-main-obligations.json.gz`.

## 3. A material merge-registration contradiction to resolve

The `ci-passed` job at this current source contains **41** awaited
dependencies but only **35** entries in its `required_results` string.
The six awaited-but-not-directly-enforced identities are:

```text
ca-pi-latest
codex-host-latest
coverage-union
coverage-union-merge
coverage-union-pi
coverage-union-pi-merge
```

The gate's adjacent comment says the **only** sanctioned divergence is
`ca-pi-latest`. The other five differ from that stated contract.
Merely awaiting a job does not by itself enforce a successful outcome.
Some may be deliberately advisory or enforced elsewhere; this inventory
does **not** infer their security/release consequences without validating
their effective guards. The next implementation must classify each
explicitly and either add the required verdict check or document and
test a legitimate exception. It must never silently remove an obligation
to make CI green.

The preceding-main run already contained the five non-Pi omissions; the
new control-byte job is independently included in both the current gate
needs and result string. Thus this report does not blame the new guard
for the pre-existing discrepancy.

## 4. Reuse policy for historical PR #993

The old branch is useful **evidence and design reference**, not a source
file to cherry-pick over newer main. Its useful, commit-bound ideas are:

- Same-commit native platform workflow and exact tested-candidate binding.
- Complete duration-balanced authority partitions with fixture isolation.
- Parallel bounded conformance and resilient Windows worker cleanup.
- Paginated, completeness-checked hosted status queries.
- Explicit artifact naming for retries and diagnostics, including nested
  failed coverage logs, plus fail-closed qualification checks.

Only CI20-02 and later may implement adaptations. They must preserve the
newer native timeout flags, current SMARTS, ship-set, Windows and
control-byte tests, source selectors, publication contracts and all
legitimate cross-platform exceptions. `ci-native-platform.yml.gz` and
`artifact_ci.py` exist on #993 but are not current-main authorities.
Do **not** mark a compile-only input as `native_tested: true`, or
treat a historical green run as release proof for a different commit.

## 5. CI20-01 completion evidence and remaining work

This slice delivers a machine-readable source-to-job map and exact workflow
snapshot, complete two-run job API evidence, an offline deterministic
critical-path model and negative tests. The benchmark can be refreshed
for future commits without silently conflating histories.

CI20-01 does **not** implement the modeled 16m27s route, reduce runtime,
change any current CI job or release behavior, or claim capacity approval.
CI20-02 must start with an explicit CI-only unqualified binary contract
and admission/negative tests; CI20-03/04 then make verification independent
and replace late native setup with an exact proof-bound join. CI20-05
addresses separately approved capacity. Only measured full green runs,
including scheduling, can qualify under-20-minute performance.

**Rollback:** Revert these diagnostic tests, CLI and historical
evidence together. No workflow, product runtime, user-state migration
or published artifact requires rollback. Newer changes to main require
a fresh source snapshot rather than editing older captured runs.
