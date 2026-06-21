# Spec — /ca:metrics (issue #79)

**Slug:** `metrics` · **Lane:** full · **Source:** GitHub issue #79 (market-eval, enhancement)

## Problem

codeArbiter captures rich, append-only audit data and never analyzes it. `/ca:audit`,
`/ca:status`, and `/ca:adr-status` only **list or snapshot** — none computes a trend. A
maintainer/lead cannot tell at a glance whether governance discipline is **holding or
eroding**.

## Scope

**In:** a new read-only command `/ca:metrics` that computes a small fixed set of
single-number governance trends from the existing append-only sources, each shown as a
current-window value plus a direction arrow (↑ / ↓ / →) versus the immediately prior
window. The arithmetic lives in a Python stdlib helper `_metricslib.py` (sibling of
`_previewlib.py`), unit-tested by `test_metrics_lib.py` against fixture logs — the
`/ca:preview` precedent. The command is prose that calls the helper and renders its
result. Writes nothing.

**Window model:** history is tiled into **commit-count windows of N=20 commits** (default;
overridable via `--window N`). Each append-only log entry is mapped into a window by its
ISO-8601 timestamp falling in that window's commit-date span. A metric compares the current
(most recent) window against the immediately prior window. Requires `git log` (already a
sanctioned read in `/ca:audit`); no network, no writes.

**The fixed metric set (3):**

1. **Override rate** — count of `overrides.log` entries in the window. ↑ = worse.
2. **Small-lane rate** — count of `LANE: small` entries in `triage.log` per window.
3. **Sprint low-confidence ratio** — `low / (low + high)` over the SMARTS confidence markers
   (`**low**` / `**high**`) in `sprint-log.md` entries in the window. ↑ = worse.

Each metric renders value + arrow (↑ / ↓ / →) vs. the immediately prior window.

**Out of scope (the guardrail, issue #79):** NOT a second `/ca:audit` packet. Emits bare
numbers/arrows only — no verbatim override lines, no commit list, no compliance dump, no
file write. Captures no new data. No network. Does not modify any log, decision, or
checkpoint. The `decisions/` source is **not** mined for a trend in this version (ADR
cadence is too sparse to trend; it stays an `/ca:audit` / `/ca:adr-status` concern).

**Deferred (`[NEEDS-TRIAGE]`, future features, not this one):**
- A true small-lane *share* (small ÷ total triaged) would require `/ca:feature` to also log
  full-lane classifications to `triage.log` — a producer change in another command's routing.
- A **"where does arbiter stop bad things" / caught-by-gate trend** (issue #79's original
  metric #2) is **not buildable on existing data**: nothing logs a gate catching-and-holding
  (a failed `tdd` Phase 1, a `commit-gate` block, a reviewer `BLOCK`). It needs a new
  append-only gate-catch event log — new instrumentation deliberately absent today. Dropped
  from this read-only feature and recorded for a future instrumentation feature.

## Acceptance criteria

Each criterion is verifiable by a single fixture-driven test against `_metricslib.py`
(one `tdd` Phase 1 obligation per criterion).

1. **Window tiling.** Given a git history of M commits and window size N, the tiler produces
   windows over the correct commit boundaries, and an ISO-8601 timestamp maps to the window
   whose commit-date span `[commit[i].date, commit[i+N].date)` contains it. Boundary case:
   a timestamp on a window edge maps to the higher-index (more recent) window.
2. **Override rate.** Given a fixture `overrides.log` with C entries timestamped inside the
   current window and P inside the prior window, the result reports `override_rate.current == C`,
   `.prior == P`, and `arrow` = ↑ if C>P, ↓ if C<P, → if C==P. Comment lines (`#`) are excluded.
3. **Small-lane rate.** Given a fixture `triage.log`, `small_lane.current` equals the count of
   `LANE: small` entries in the current window and `.prior` the count in the prior window, with
   the correct arrow; comment lines excluded.
4. **Sprint low-confidence ratio.** Given a fixture `sprint-log.md` with H `**high**` and L
   `**low**` confidence markers in the current window, `ratio.current == round(L/(L+H), 2)`;
   when `L+H == 0` the value is the sentinel `"n/a"`; the arrow compares current vs. prior, and
   any window with a sentinel value yields a `→` (no spurious arrow).
5. **Empty / missing source.** When a source file is absent or a window contains no relevant
   entries, the corresponding metric returns its defined sentinel (`0` for counts, `"n/a"` for
   the ratio) and the helper never raises and never divides by zero.
6. **Read-only.** Invoking the helper's public compute API over a fixture project directory
   leaves every file in `.codearbiter/` byte-for-byte unchanged (no writes, no log appends).
7. **Fixed output surface.** The helper's structured result contains exactly the three metric
   keys (`override_rate`, `small_lane_rate`, `sprint_low_conf_ratio`) and no verbatim
   source-log line is present in any value — enforcing the "not a second audit packet" guardrail.

## Open questions

None blocking. No `[CONFIRM-NN]` raised — the four delegated decisions were resolved by SMARTS
recommendation and user choice during brainstorming (window = commit-count N=20; small-lane =
rate not share; most-overridden/caught-by-gate metric dropped as un-instrumented; surface =
new `/ca:metrics` command). The default
N=20 and the prior-window-only comparison are deliberate simplicity calls, overridable later.

## Implementation notes (for writing-plans, not gating criteria)

- New helper `plugins/ca/hooks/_metricslib.py` (Python 3, stdlib only) + `.github/scripts/test_metrics_lib.py`; register the test in `tech-stack.md` and CI parity.
- New command `plugins/ca/commands/metrics.md`; add to the `/ca:commands` catalog and the README/docs command list; ensure `check-plugin-refs.py` resolves.
- This is a `plugins/ca/**` change on a tagged version → `plugin.json` version bump required (CI `version-bump` job), plus README badge + dated `CHANGELOG.md` section.
- Canonical EOL is LF for the new `.py`/`.md` files.
