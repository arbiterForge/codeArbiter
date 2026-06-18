# tools/ — repo-level utilities

Standalone helper scripts (not part of the shipped `ca` plugin runtime). Read-only
unless noted.

## Token-efficiency investigation aids

Two analysis scripts that turn arbiter's own persisted artifacts into the metrics the
subscription-efficiency investigation needs. Both are stdlib-only Python 3, read-only,
and print a human table by default or `--json` for machine use.

### `reviewer-yield.py` — per-reviewer dispatch-to-finding yield
```
python3 tools/reviewer-yield.py [CHECKPOINT_DIR ...]      # default ./.codearbiter/checkpoints
python3 tools/reviewer-yield.py --json
```
Parses the `## Finding summary` table in each `.codearbiter/checkpoints/*.md` and reports,
per reviewer, how often it was dispatched vs. actually returned a finding. Lowest-yield
reviewers (dispatched a lot, find little) are the candidates for a tighter dispatch
trigger and/or a cheaper model tier. Coverage is persisted checkpoint docs only — sprint
Phase-4 reviews that don't write a checkpoint are undercounted, so treat it as a pointer.

### `farm-first-pass.py` — first-pass / escalation rate for `--farm` runs
```
python3 tools/farm-first-pass.py [PATH]                   # default .farm/farm-report.json
python3 tools/farm-first-pass.py --json
```
Parses `.farm/farm-report.json` (written by `tools/farm.ts`) and reports the
first-pass-through-gate rate, escalation rate, average attempts, gaming warnings, and
off-pool worker token spend. A low first-pass rate plus a nonzero escalation rate means
the cheap worker is offloading less than it appears — escalated tasks revert to the
premium (Max-pool) path. That is the revert signal for the farm experiment.

## Other

- `statusline-screenshot.py` — renders a sample of the codeArbiter statusline.
