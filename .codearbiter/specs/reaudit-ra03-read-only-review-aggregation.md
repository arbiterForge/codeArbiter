# RA-03 read-only review aggregation

**Status:** APPROVED — 2026-09-01 (explicit user approval recorded in campaign revision 13)
**Goal:** Separate read-only review verdict composition from checkpoint persistence so `/review` and generic parallel batches cannot route through a writer charter.
**Baseline:** `origin/main` merge commit `12ca6392209c81bea9aa2bf32f049887cac757f2` after PR #728.

## Locked design

1. Add `verdict-aggregator` as a read-only reviewer charter. It consumes the complete `finding-triage` report and returns exactly one structured verdict without writing repository files.
2. Route `/review` and the generic `dispatching-parallel-agents` funnel through `finding-triage` then `verdict-aggregator`.
3. Keep `checkpoint-aggregator` as the bounded writer used only when `/checkpoint` explicitly persists a dated checkpoint document.
4. Generalize `finding-triage` so its output is suitable for both read-only verdicts and explicitly persisted checkpoints.
5. Regenerate the Claude, Codex, and Pi surfaces from `core/surface`; rendered files are never edited directly.

## Acceptance criteria

1. Working-diff and inbound-PR review routes terminate at `verdict-aggregator`, whose declared tools contain no execution or write capability; a byte snapshot taken before and after static route verification is identical.
2. Generic parallel batches expose only the triage-to-verdict result to callers and do not route to `checkpoint-aggregator`.
3. `/checkpoint` explicitly receives the read-only verdict and separately invokes `checkpoint-aggregator`; its existing dated suffix and MUST-NOT-overwrite contract remains intact.
4. Agent catalogs, Codex dispatch policy, route receipts, reference closure, and all three generated host surfaces agree with the canonical templates.

## Out of scope

- Changing reviewer selection, severity semantics, PR posting authority, checkpoint document format, or harvest behavior.
- Implementing unrelated findings from the re-audit ledger.
- Merging, releasing, publishing, installing, or cleaning unrelated worktrees without the separate authority required by the campaign.

## Validation

- `python .github/scripts/test_review_funnel.py`
- `python .github/scripts/test_build_surface.py`
- `python .github/scripts/check-plugin-refs.py`
- `python tools/build-surface.py --check`
- Whole-surface and project gates required by `$ca-commit` and `$ca-pr` before delivery.
