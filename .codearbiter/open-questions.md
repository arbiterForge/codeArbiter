# Open questions

Unresolved `[CONFIRM-NN]` items. Each blocks stage promotion until resolved.
The SessionStart hook and statusline count `CONFIRM-NN` occurrences here.

## [CONFIRM-05] Feature Forge promotion bar for the `--farm` (OpenCode Zen) backend

What evidence promotes `--farm` from `preview` to stable? Define the bar before promoting. Candidate
signals to choose among, with thresholds to set: number of successful `/ca:sprint --farm` runs across
how many distinct repos; per-task pass-rate and average attempts; measured cost saving vs. the premium
backend; zero gate escapes (no farm-produced code reaching a commit without clearing the full review
chain); no security or supply-chain incident from the third-party Zen API. The owner decides the metric
set and thresholds; until then the farm stays `preview`.

_Previously resolved: the four Phase 1 gate decisions, 2026-06-04 (see `legacy/ASSESSMENT.md` §10)._

## Deferred decisions (non-blocking — deliberately NOT a `CONFIRM-NN`, so it does not gate stage promotion)

- **Mechanical enforcement of "no commit on a red suite" / "no commit without commit-gate" (review finding #6).** The 2026-06-15 review confirmed these ORCHESTRATOR §3 rules are skill-discipline only — no hook runs or inspects test status, and `pre-bash.py` lets a raw `git commit` (no secrets, feature branch) through. The `review-remediation` sprint deferred this to its own decision per the user (2026-06-16): a test-running commit hook is slow and invasive, so whether to build one (vs. accept the rules as prose-enforced) is a separate design call. Its siblings ride along: the "compel a log write" half of audit logging (hooks protect logs once written but never force a write) and the secret-to-logger/prompt sink breadth (`SECRET_RE` only matches assignment literals). Pick a direction when enforcement strategy is next revisited.

### `task-board-lifecycle` feature deferrals (spec: `specs/task-board-lifecycle.md`, 2026-06-21)

- **D-1 — Task-board transition writer surface.** How `[ ]`→`[~]`→`[x]` transitions get written: a new `/ca:task` command (add/start/done), an extension to `/ca:standup` or `/ca:status`, or manual editing. MVP ships with the schema + fixed counters + stale nudge; transitions are hand-edited until this is decided. Gates the decompose-seeding criterion (AC-11). If a command lands, update `reference-map.md`, `routing-table.md`, and the command catalog in lockstep. **Priority when implemented:** the highest-value transition to automate is `[ ]`→`[~]` *with the `(started …)` date* — a task started-but-never-flipped is the one drop-off hole the MVP can't catch (the stale nudge only sees dated `[~]`), so the start-transition writer should stamp the date automatically.
- **D-2 — Archival sweep owner + cutoff.** Which command runs the deliberate, confirmed, append-only sweep of long-settled `[x]` items from `open-tasks.md` into `done-tasks.md`, and what "long-settled" means (e.g. done >14 days). Archival is post-MVP; done items stay in-place under `## Done` until then.
- **D-3 — Stale-in-progress threshold.** The age at which a `[~]` task triggers the SessionStart nudge. Default 3 days ships as a named constant; this only tunes the number (the mechanism is tested with an injected date, so the value is non-load-bearing).
