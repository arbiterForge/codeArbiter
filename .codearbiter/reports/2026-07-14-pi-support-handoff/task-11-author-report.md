# Task 11 author report - relative performance and cross-platform contract

Status: implementation complete and locally verified on Windows with installed Pi 0.80.6. The
Windows/macOS/Linux x Pi 0.80.5/0.80.6 evidence remains a hosted Task 13/14 promotion gate.

## Test-first evidence

- RED: `.github/scripts/test_pi_benchmark.py` failed because `pi_benchmark.py` did not exist.
- RED: `.github/scripts/test_pi_platform_contract.py --fixtures-only` failed at each unimplemented
  version, UTF-8 JSONL, executable-resolution, command-plan, and runner seam.
- GREEN: benchmark unit/CLI suite passes 6/6 and the platform fixture unit suite passes 4/4.
- A first integrated fixture run correctly exposed Task 9's in-progress descriptor/host-map drift for
  `codearbiter_farm_preview`. Task 11 did not overwrite that lane. After Task 9 completed the shared
  map, the same run passed, proving the platform aggregate catches real cross-task drift.

## Implemented benchmark

- Added `.github/scripts/pi_benchmark.py` with the exact relative limit:
  `slower_existing_p95 + max(slower_existing_p95 * 0.25, 10.0)`.
- Measures the same bounded read/exec/write semantic corpus through the real Claude, Codex, and Pi
  host adapters. It uses five warmup events followed by exactly 100 measured warm events.
- Uses `time.perf_counter_ns()` and records cold module startup once, shared-core activation time
  separately, and adapter-only p50/p95. Each host gets a fresh enabled temporary repo whose path has
  spaces and non-ASCII text.
- Emits exactly one compact JSON record per host with only `platform`, `host`, `sampleCount`,
  `startupMs`, `coreP50Ms`, `adapterP50Ms`, and `adapterP95Ms`. It does not start a provider, use the
  network, read host authentication, or print fixture payloads.
- Local Windows measurement from the final direct run:
  - Claude adapter p95: 0.0103 ms
  - Codex adapter p95: 0.0071 ms
  - Pi adapter p95: 0.0045 ms
  - Result: Pi is below the relative threshold.

## Implemented platform contract

- Added one cross-platform runner that accepts only `0.80.5`, `0.80.6`, or `latest`; both supported
  versions are blocking and only `latest` is classified nonblocking.
- Direct fixtures cover UTF-8 JSONL with LF/CRLF, space/non-ASCII paths, and real absolute executable
  resolution.
- The aggregate command plan runs package discovery and generated paths, canonical bridge and host
  parity, runner cancellation and process-tree fixtures, Pi compaction/prune parity, benchmark tests,
  and two consecutive clean surface/root-package generation checks for idempotency.
- Installed-version mode additionally verifies the actual Pi CLI version and runs live descendant
  cleanup, child isolation/cancellation, and the 100-event benchmark.
- CI reuses the existing exact six-cell Windows/macOS/Linux x 0.80.5/0.80.6 matrix with Node 22.19.0
  and Python 3. It runs the platform contract and benchmark in every cell. The already nonblocking
  npm-latest canary now installs Python and runs the same version-aware contract.
- All action versions remain reviewed commit-SHA pins and external Pi installation keeps
  `--ignore-scripts`.

## Verification

- `python .github/scripts/test_pi_benchmark.py` -> 6/6 passed.
- `python .github/scripts/pi_benchmark.py --samples 100` -> three records; relative threshold passed.
- `python .github/scripts/test_pi_platform_contract.py --fixtures-only` -> 11 aggregate steps and
  4/4 direct fixtures passed.
- `python .github/scripts/test_pi_platform_contract.py --pi-version 0.80.6` -> 14 aggregate steps and
  4/4 direct fixtures passed, including live child/process cleanup.
- `python -m py_compile` for all three Task 11 scripts -> passed.
- `git diff --check` for the Task 11 scripts and CI workflow -> passed.
- `.github/scripts/test_pi_package.py`, included in both aggregate runs, passed its CI matrix/static
  assertions after the Task 11 workflow edits.

## Files in this slice

- `.github/scripts/pi_benchmark.py`
- `.github/scripts/test_pi_benchmark.py`
- `.github/scripts/test_pi_platform_contract.py`
- `.github/workflows/ci.yml` (Task 11 filter/steps only; other Pi CI hunks are shared sprint work)
- `.codearbiter/reports/2026-07-14-pi-support-handoff/task-11-author-report.md`

## Remaining acceptance dependency

The implementation is locally green, but PI-AC-31 and PI-AC-32 cannot be finally promoted from one
Windows run. Task 13/14 must bind the committed SHA to all six blocking hosted matrix cells. The
latest canary remains separately visible and nonblocking by design.
