# Statusline dirty timeout benchmark - 2026-07-20

Scope: read-only timing of the exact `_gitlib.git_dirty` probe and its
`git status --porcelain` equivalent on the largest available local checkouts.
Repository identities, paths, porcelain output, and filenames are excluded.

## Environment and protocol

- Host: Windows, Python 3.14.6, Git 2.54.0.windows.1.
- Breadth sample: five distinct repositories with 98 to 1,587 tracked files,
  including both clean and dirty worktrees. Each received a 5-second control
  probe followed by 40 probes at the production 100 ms timeout.
- Focus sample: four primary or linked-worktree cases with 834 to 1,589 tracked
  files, including clean and dirty states. Each received 100 calls through the
  shipped `_gitlib.git_dirty` function.
- A mismatch means the bounded probe returned a different dirty boolean from
  the successful 5-second control. Timed-out probes fail soft to clean and
  therefore count as mismatches whenever the control is dirty.

### Reproduction contract

Run from the repository root with `core/pysrc` prepended to `sys.path`, then
import `_gitlib`. Resolve Git through `_gitlib.git_executable()` rather than an
independent PATH lookup. For each checkout:

1. Count tracked files with `[git, "-C", root, "ls-files", "-z"]` and count NUL
   separators in successful stdout.
2. Establish the control with
   `[git, "-C", root, "status", "--porcelain"]`, `capture_output=True`, and a
   5-second timeout. Dirty is `returncode == 0 and bool(stdout.strip())`.
3. For the breadth sample, run the same status argv 40 times with a 0.1-second
   timeout. Time each call with `time.perf_counter()`. Record `TimeoutExpired`
   separately and treat it as the helper's fail-soft `False` result.
4. For the focus sample, call `_gitlib.git_dirty(root)` 100 times and time each
   call with `time.perf_counter()`. Compare every boolean to the control.
5. Sort elapsed milliseconds and select p95/p99 with nearest-rank indexing:
   `ceil(percentile * sample_count) - 1`. Report the median as p50.

The checkout paths are operator inputs and must not be printed or persisted.
The case label, primary-or-linked kind, tracked-file count, control state,
latencies, timeout count, and mismatch count are the complete retained output.

## Evaluation rule

Record latency percentiles, timeout counts, and dirty-state mismatches without
retaining porcelain content. Retain the 100 ms policy only if normal clean and
dirty checkouts complete with practical headroom and no false-clean results.
If a representative checkout times out or disagrees with its control, route a
regression-first fix before changing the constant.

## Evidence

| Sample | Probes | p50 range | p95 range | p99 range | Maximum | Timeouts | Mismatches |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Breadth | 200 | 24.36-31.45 ms | 28.32-35.21 ms | not recorded | 73.91 ms | 0 | 0 |
| Focus | 400 | 28.91-31.70 ms | 31.73-35.03 ms | 73.88-79.11 ms | 81.25 ms | 0 | 0 |

### Anonymous case receipts

| Case | Probe | Kind | Tracked | Control | Runs | p50 | p95 | p99 | Maximum | Timeouts | Mismatches |
| --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B1 | exact argv | primary | 1,587 | dirty | 40 | 31.45 ms | 35.21 ms | not recorded | 73.91 ms | 0 | 0 |
| B2 | exact argv | primary | 274 | dirty | 40 | 25.86 ms | 28.32 ms | not recorded | 71.88 ms | 0 | 0 |
| B3 | exact argv | primary | 834 | dirty | 40 | 28.55 ms | 30.99 ms | not recorded | 72.62 ms | 0 | 0 |
| B4 | exact argv | primary | 334 | clean | 40 | 25.59 ms | 29.77 ms | not recorded | 70.14 ms | 0 | 0 |
| B5 | exact argv | primary | 98 | clean | 40 | 24.36 ms | 28.85 ms | not recorded | 71.80 ms | 0 | 0 |
| F1 | shipped helper | primary | 1,587 | dirty | 100 | 31.51 ms | 34.18 ms | 79.11 ms | 81.25 ms | 0 | 0 |
| F2 | shipped helper | linked | 1,589 | clean | 100 | 31.70 ms | 34.69 ms | 76.54 ms | 76.86 ms | 0 | 0 |
| F3 | shipped helper | primary | 834 | dirty | 100 | 28.91 ms | 31.73 ms | 73.88 ms | 77.17 ms | 0 | 0 |
| F4 | shipped helper | linked | 917 | dirty | 100 | 31.49 ms | 35.03 ms | 77.78 ms | 81.20 ms | 0 | 0 |

The largest observed checkout had 1,589 tracked files. Its p95 was 34.69 ms,
p99 was 76.54 ms, and maximum was 76.86 ms. Across all 600 production-budget
probes, none timed out and none hid dirty state.

## SMARTS decision

- **Secure:** unchanged. The probe remains stdlib-only, read-only, bounded, and
  fail-soft.
- **Maintainable:** retain one documented constant and the existing regression
  contract; no adaptive policy or cache is justified by this evidence.
- **Reliable:** zero false-clean results were observed, including dirty primary
  checkouts and linked worktrees. The largest sample retained about 2.9 times
  its p95 latency before the deadline.
- **Testable:** the benchmark exercised both the exact subprocess shape and the
  shipped helper against a generous control.
- **Scalable:** the available portfolio tops out at 1,589 tracked files. The
  evidence supports that range, not an unlimited repository-size claim.

Decision: retain the 100 ms timeout and full tracked-plus-untracked porcelain
semantics. Reopen the question only if a real checkout produces a timeout or a
false-clean result, or if materially larger representative repositories become
available. No implementation adjustment is warranted by the current evidence.
