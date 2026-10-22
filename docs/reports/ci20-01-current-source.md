# CI20-01 â€” Current-source and baseline inventory

**Status:** source discovery and baseline capture completed; implementation and under-20-minute qualification **not started**.
**Owning repository:** `arbiterForge/codeArbiter`.
**Inspected main:** `0badb588dc1179b06e13db1ca5322590962b586a` (2026-10-20).
**Benchmark:** completed successful GitHub Actions CI run `39357341801`, attempt 1, same commit.
**Historical prototype:** closed, unmerged [#993](https://github.com/arbiterForge/codeArbiter/pull/993) at `16983f5017b39e35de2f90994e30fcd60730e82c`.
**Plan:** [#1011](https://github.com/arbiterForge/codeArbiter/pull/1011), a separate documentation-only proposal.

## Reproducible evidence

- [Exact-head job, step, runner and replay receipt](ci20-baseline-0badb588.json). This preserves the observed job population and the workflow SHA-256.
- [Complete source-to-job inventory](ci20-source-map-0badb588.json). This records all job definitions, matrix selections, conditions, dependencies, commands, actions and observed outcomes, plus all current workflow-file digests and branch-protection check identities.
- `tools/ci20_baseline.py`: read-only, paginated `gh api` collection and group-level dependency replay. `tools/test_ci20_baseline.py` contains negative controls for source mismatch, unknown/ambiguous jobs, missing groups, cycles and matrix-name handling. `tools/ci20_inventory.py` regenerates the current-source map.

To reproduce with an authenticated GitHub CLI and Python with PyYAML installed, check out **exactly** the inspected main commit and run:

```sh
python tools/test_ci20_baseline.py
python tools/ci20_baseline.py --run-id 39357341801 --checkout . --output ci20-replay.json
python tools/ci20_inventory.py --baseline ci20-replay.json --output ci20-source-map.json
```

The baseline collector refuses a run from another commit, incomplete paginated results, duplicate job IDs, unknown job owners, missing required groups and cyclic dependencies. It refuses to overwrite its output. The inventory writer also refuses overwrite. Do not run the inventory generator again over its committed output; generate in a fresh exact-head checkout or remove the old generated output deliberately. The historical receipt remains immutable.

## Observed baseline

| Measure | Result | Interpretation |
|---|---:|---|
| Trigger to last completed job | **43m22s** (2,602 seconds) | Actual run, includes queueing |
| Zero-queue replay | **43m08s** (2,588 seconds) | Model retaining observed group durations and all `needs` edges |
| Observed jobs | **79** | 54 successful, 25 legitimately skipped, none failed |
| Workflow job groups | **42** | Full source inventory |
| Shell command definitions | **224** | Recorded with owning group and condition |
| Runner execution | **340m37s** | Capacity demand, not billed minutes |
| macOS execution | **87m02s** | Classified by actual runner labels |

The source is **not** the same as #993. Its `artifact-engine` still runs complete native tests, instrumentation, context, candidate construction, adapters and final qualification serially. The longest native platform job is Windows ARM64 (**40m45s**); Windows x64 is **36m14s**. Native authority shards build their own candidates, and the Windows ARM64 second authority shard took **26m05s**. The observed `artifact-engine` group finishes at 40m51s on the zero-queue replay; downstream browser, coverage, assembly and cold packages bring the critical dependency endpoint to 43m08s.

The replay is a **group-level lower-bound approximation**: each job group takes its slowest observed matrix-child duration and depends on completion of every declared prerequisite group. It preserves observed setup and cleanup. It does not model changed CPU contention, GitHub provisioning, independent required workflow settlement, or the true individual-job dependency chain. It is not proof that a redesigned pipeline will achieve the target.

## Current obligations to preserve

The exact current source owns these requirements:

| Property | Current source evidence | Preservation rule |
|---|---|---|
| Native targets | `.github/workflows/ci.yml`, `artifact-engine.strategy.matrix.include` | Six: Linux x64/ARM64, Windows x64/ARM64, macOS x64/ARM64 |
| Native configurations | `artifact-engine.steps` | Default Go tests/vet, CGO-disabled builder tests/vet, instrumented CLI and module coverage, context/storage, mixed-schema recovery, adapters, conformance, Linux race and generated/public-surface checks |
| Authority | `artifact-authority`; `.github/scripts/run_artifact_authority_shard.py` | Twelve matrix jobs: two exhaustive alphabetical halves on six platforms; **271 discovered cases** in the current Python source, not the historical 270 |
| Installed-host package tests | `artifact-package-cold` | Eighteen cold host/platform combinations (three hosts per platform) |
| Coverage | `artifact-coverage`, `tools/artifact-coverage.py` | Exact six-platform profile union, current statement floor and refusal tests |
| Hook checks | `hooks` | Linux/macOS full partitions plus three Windows partitions, including hermeticity and new SMARTS-related contracts |
| Qualification | `tools/build-artifacts.py`, `artifact-engine` | `native_tested` remains truthful; only real native evidence qualifies packages |
| Protected gate | `ci-passed`, GitHub branch protection | `[GATE ] \| [REPO] \| Merge readiness` is the protected required context; all 41 prerequisite groups remain registered |
| Other workflows | `.github/workflows/{codeql,docs,pi-promotion,release}.yml` | Keep their current triggers and separate required-workflow relevance; no implicit exclusion from acceptance |
| Newer main obligations | Current `artifact-engine` and `hooks` | Preserve SMARTS exact-test contract, ship-set evidence inputs, newer source and Windows safety checks; do not restore #993's older command definitions |

The complete command, action, condition and matrix inventory is in the machine-readable source map. Any implementation PR must compare the final required population against this source snapshot **and then-current main**, since this snapshot becomes historical as soon as main moves.

## Reconciliation with #993

The closed PR is a **reference, not a merge candidate**. Its potentially reusable ideas include shared immutable candidate inputs, conformance overlap, duration-aware fixture groups, bounded worker cleanup, paginated hosted-check reads and attempt-qualified diagnostics. Each must be reconsidered against current tests and tool versions.

Do not cherry-pick the old workflow wholesale. It predates the current main's SMARTS, ship-set, native safety and timeout choices. No prototype behavior is claimed as implemented on current main. CI20-02 must separately design the provisional CI test-input state and evidence ownership before any build-first restructuring.

## Decision and acceptance boundary

**Confirmed:** the current exact-head native path alone exceeds 20 minutes; the modeled queue-free path is also 43m08s. Reducing runner queue time cannot make this source pass the goal.

**Material contradictions:** the older #993 prototype, the October 19 timing model, and current main have different command inventories and durations. The 16m27s model is an unexecuted hypothesis. Unlimited public runner minutes do not establish concurrent capacity.

**Affected surfaces:** only the new CI20-01 evidence scripts and this report. No CI workflow, product runtime, qualification emitter, installed admission, release package, Project canon or claim registry is changed.

**Approvals:** no account quota, paid capacity, release or merge approval is implied.

**Still required:** CI20-02 contract and negative tests; CI20-03/04 build-first and evidence aggregation; CI20-05 actual capacity confirmation; CI20-06 measured follow-up; CI20-07 complete end-to-end hosted acceptance.

**Next action:** review this frozen inventory, then specify the explicit CI-only provisional artifact and strict qualification transition, with negative controls before workflow changes. Rollback for this slice is simply removing the three scripts and three evidence/report files; no migration is needed.
