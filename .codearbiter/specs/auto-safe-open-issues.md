# Sprint spec — auto-safe open issues

**Status:** COMPLETE — final verification and review passed
**Branch:** `feat/auto-safe-open-issues`
**Landing:** ready PR to `main`; never merge autonomously.

## Goal

Clear the implementation-ready, auto-safe GitHub issue debt while preserving codeArbiter's enforcement boundaries, generated-source discipline, default statusline output, and user-owned main checkout.

## Included work

- **#296:** concurrent ledger updates and `persist_sess_start` must not lose another session's state; interrupted writes preserve valid data and totals remain correct.
- **#297:** branch resolution supports normal checkouts, linked-worktree gitdir pointers, detached HEAD, and malformed metadata without traceback.
- **#299:** statusline ownership recognizes current/stale codeArbiter paths without claiming third-party `statusline.py` commands; backup, refresh, and uninstall remain lossless.
- **#298:** dirty detection has a deterministic tested latency budget, fails softly, and preserves tracked/untracked semantics.
- **#278:** prune warm/cold tests use an injected/frozen clock rather than elapsed wall time; sibling timing cases are audited.
- **#293:** hook-gate extraction tests identify gates structurally rather than by exact source line.
- **#283:** docs show the `host=<host>` gate-event field and pass the site suite.
- **#259:** audit current Codex payload/bootstrap behavior; close with evidence if acceptance is already met, otherwise remediate only the remaining gap through canonical shared generation.
- **#300:** add five named palettes and bounded partial custom JSON while keeping violet byte-equivalent by default; add model identity to existing bounded subagent scans and preserve metrics under narrow widths.
- **Emergent audit regressions (user-approved 2026-07-12):** concurrent Windows gate-event writes must retain every same-process and dual-host event. These defects repeatedly blocked the sprint's full test gate and were approved for inclusion after final review surfaced the scope mismatch.

## Global constraints

- Python hook code remains stdlib-only, import-side-effect free, fail-soft on malformed user input, UTF-8/LF, and implemented in `core/pysrc/` before `tools/sync-core.py` materializes host copies.
- Existing violet rendering, layout, glyphs, content, semantic thresholds, explicit gradient arguments, and `NO_COLOR` precedence remain unchanged unless the user opts into a theme.
- Custom theme files are read-only, bounded before JSON parsing, accept six-digit `#RRGGBB`, ignore invalid/unknown values, inherit missing values from violet, and never cause a traceback or blank render.
- Model extraction occurs during the existing bounded JSONL scan with no subprocess or second pass; rows show one compact model, `model:mixed`, or `model:?`.
- Available implementation subagents may be used, but no lower-model guarantee is claimed. Sol owns specification, reviews, integration, and final verification.
- The modified `.codearbiter/gate-events.log` in the main checkout is user-owned and must not be overwritten or cleaned.

## Exclusions and hard gates

Issues #223, #265, #271, #237, and #270 remain excluded because they touch separate enforcement, audit-marker, security, or recorded-decision work. The approved gate-event append regressions above are the sole audit-integrity addition. External-human validation, telemetry records, and unscoped product concepts are excluded. Stop on a failing baseline, security-critical finding, irreversible operation, unresolved acceptance ambiguity, or gate weakening.

## Acceptance

All included issue criteria are covered by deterministic tests; canonical/generated sources are synchronized; focused and full repository gates pass; the feature branch is pushed and a ready PR is opened when credentials permit, but neither the task branches nor feature branch are merged to `main` autonomously.
