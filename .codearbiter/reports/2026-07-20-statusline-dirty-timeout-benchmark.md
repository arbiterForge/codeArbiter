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
