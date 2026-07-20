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
