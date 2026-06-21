# Plan — /ca:metrics (issue #79)

**Slug:** `metrics` · **Spec:** `.codearbiter/specs/metrics.md` (approved) · **Lane:** full

Pre-flight note: `.codearbiter/coding-standards.md` is absent in this project; paths below are resolved
against the live repo layout and `tech-stack.md` (authoritative for build/test commands).

## AC ledger (verbatim from spec)

- **AC-01 — Window tiling.** Given M commits and window size N, the tiler produces windows over the
  correct commit boundaries; an ISO-8601 timestamp maps to the window whose commit-date span
  `[commit[i].date, commit[i+N].date)` contains it; an edge timestamp maps to the higher-index window.
- **AC-02 — Override rate.** `overrides.log` with C current / P prior entries → `override_rate.current==C`,
  `.prior==P`, arrow ↑/↓/→ by sign of C−P; `#` comment lines excluded.
- **AC-03 — Small-lane rate.** `triage.log` → `small_lane.current`/`.prior` count `LANE: small` entries
  in each window with correct arrow; comment lines excluded.
- **AC-04 — Sprint low-confidence ratio.** `sprint-log.md` with H `**high**`, L `**low**` in window →
  `ratio.current == round(L/(L+H), 2)`; `"n/a"` when `L+H==0`; arrow vs prior; sentinel window → `→`.
- **AC-05 — Empty / missing source.** Absent file or empty window → defined sentinel (`0` for counts,
  `"n/a"` for ratio); never raises, never divides by zero.
- **AC-06 — Read-only.** Compute over a fixture project dir leaves every `.codearbiter/` file
  byte-for-byte unchanged.
- **AC-07 — Fixed output surface.** Result holds exactly `override_rate`, `small_lane_rate`,
  `sprint_low_conf_ratio`; no verbatim source-log line in any value.

## Tasks

| id | path(s) | verification | maps-to (tdd obligation) | covers | depends-on | status |
|----|---------|--------------|--------------------------|--------|------------|--------|
| T-01 | `plugins/ca/hooks/_metricslib.py`, `.github/scripts/test_metrics_lib.py` | `python .github/scripts/test_metrics_lib.py WindowTest` passes (boundaries for M commits/size N; edge timestamp → higher-index window) | window-tiling | AC-01 | — | ACCEPTED |
| T-02 | `plugins/ca/hooks/_metricslib.py`, `.github/scripts/test_metrics_lib.py` | `… OverrideRateTest` passes (current==C, prior==P, arrow by sign, `#` excluded) | override-rate | AC-02 | T-01 | ACCEPTED |
| T-03 | `plugins/ca/hooks/_metricslib.py`, `.github/scripts/test_metrics_lib.py` | `… SmallLaneTest` passes (`LANE: small` counts current/prior, arrow, comments excluded) | small-lane-rate | AC-03 | T-01 | ACCEPTED |
| T-04 | `plugins/ca/hooks/_metricslib.py`, `.github/scripts/test_metrics_lib.py` | `… SprintRatioTest` passes (`round(L/(L+H),2)`; `"n/a"` at 0; arrow; sentinel→`→`) | sprint-low-conf-ratio | AC-04 | T-01 | ACCEPTED |
| T-05 | `plugins/ca/hooks/_metricslib.py`, `.github/scripts/test_metrics_lib.py` | `… EmptySourceTest` passes (missing file & empty window → sentinels; no raise; no div-by-zero) | empty/missing-safety | AC-05 | T-02, T-03, T-04 | ACCEPTED |
| T-06 | `plugins/ca/hooks/_metricslib.py`, `.github/scripts/test_metrics_lib.py` | `… ComputeApiTest` passes (`compute(dir, window=20)` returns exactly the 3 keys; no verbatim source line in any value) | fixed-output-surface | AC-07 | T-02, T-03, T-04 | ACCEPTED |
| T-07 | `.github/scripts/test_metrics_lib.py` | `… ReadOnlyTest` passes (fixture `.codearbiter/` byte-identical before/after compute) | read-only-invariant | AC-06 | T-06 | ACCEPTED |
| T-08 | `plugins/ca/commands/metrics.md` | Command file present; documents the `python3 … _metricslib … || python …` fallback call (per `preview.md`); running it on this repo renders the 3-metric block (value + arrow), writes nothing | _(prose — authoring gate, no tdd obligation)_ | AC-07 | T-06 | ACCEPTED |
| T-09 | `plugins/ca/COMMANDS.md` | `python3 .github/scripts/check-plugin-refs.py ca` passes (rule D: `/ca:metrics` cataloged, file↔catalog agree) | _(static CI check — no tdd obligation)_ | AC-07 | T-08 | ACCEPTED |
| T-10 | `.github/workflows/ci.yml`, `.codearbiter/tech-stack.md` | `ci.yml` runs `python .github/scripts/test_metrics_lib.py` in the hooks-test job (green); `tech-stack.md` test list mirrors it | _(CI registration — enforces AC-01–07; no new tdd obligation)_ | AC-01, AC-02, AC-03, AC-04, AC-05, AC-06, AC-07 | T-07 | ACCEPTED |
| T-11 | `README.md`, `CHANGELOG.md` | README shows a `/ca:metrics` command-table row and the commands-count badge reads `36`; `CHANGELOG.md` `[2.5.0]` **Added** lists `/ca:metrics` | _(docs hygiene — authoring gate)_ | AC-07 | T-08 | ACCEPTED |

## Order & MVP slice

Dependency order: **T-01 → {T-02, T-03, T-04} → {T-05, T-06} → {T-07, T-08} → {T-09, T-10, T-11}**.
No cycle.

- **MVP slice — T-01 … T-10:** the helper computing all three trends (AC-01–05, AC-07), proven
  read-only (AC-06), surfaced through an invocable `/ca:metrics` command that passes
  `check-plugin-refs` (T-09) and is CI-enforced (T-10). Shippable on its own: a working, reachable,
  test-gated command.
- **Incremental — T-11:** README/CHANGELOG discoverability hygiene. Not CI-enforced; lands in the
  same PR but after the MVP slice.

## Notes

- **Version:** `2.5.0` is the current **untagged** version (latest tag `v2.4.6`); per the release
  invariant a bump is required only on an *already-tagged* version, so `plugin.json` stays `2.5.0`
  and the CHANGELOG entry appends to the existing unreleased `[2.5.0]` section. No `version-bump` task.
- **No new skill/agent** — `/ca:metrics` is self-contained command prose calling `_metricslib.py`
  directly (the `/ca:preview` → `_previewlib.py` pattern), so `skills/INDEX.md` and `agents/INDEX.md`
  are untouched.
- **EOL:** new `.py`/`.md` files are LF.
- `[NEEDS-TRIAGE]` (future features, out of scope — carried from the spec): true small-lane *share*
  (needs `/ca:feature` to log full-lane classifications); a caught-by-gate "where arbiter stops bad
  things" trend (needs a new gate-catch event log — un-instrumented today).
