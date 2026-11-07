# 03. Evidence snapshot and owning source map

## Snapshot and observed issue state

Reviewed `main`: `94d901899a5f5c0a2a6040ca74cd904db0c5793c`, recorded 2026-11-07. This is a **development snapshot**. Freeze a fresh head before coding.

- [#1084](https://github.com/arbiterForge/codeArbiter/issues/1084): open at handoff; current board has 19 rows across six shared `(from ...)` origins; migration preview rejects shared origins.
- [#1087](https://github.com/arbiterForge/codeArbiter/issues/1087): open; 45 current one-line titles exceed the native 240-character limit (range 241 to 1,176); whole-board adoption refuses.
- [#1089](https://github.com/arbiterForge/codeArbiter/issues/1089): open; legitimate selected legacy-board attach/compound transitions cause the commit-gate board classifier to return false.
- [#1088](https://github.com/arbiterForge/codeArbiter/issues/1088): open; separate H-20 variable-command recognition and approved-bypass recovery defect. Security-sensitive: do not use its accidental bypass as a workaround.
- [PR #1091](https://github.com/arbiterForge/codeArbiter/pull/1091): merged as of this baseline; do not resurrect closed hook cleanup work.

The source-level reproduction and present-test results stated in this packet come from the immediately preceding ChatGPT review and issue/source inspection. They are **baseline observations**, not tests run by the receiving agent or a passing integration gate.

## Source references at frozen codeArbiter HEAD

| Owner or contract | Exact pinned source | What to inspect |
|---|---|---|
| Accepted assistive direction | `arbiterForge/codeArbiter@94d901899a5f5c0a2a6040ca74cd904db0c5793c:.codearbiter/decisions/0043-assistive-state-engine.md` | State engine assists rather than authorizes ordinary work |
| Native adoption preview | `arbiterForge/codeArbiter@94d901899a5f5c0a2a6040ca74cd904db0c5793c:core/pysrc/_workadopt.py` | `_rows` derives IDs from origin and rejects long titles; `_inventory` checks global duplicate origin |
| Native adoption writer | `arbiterForge/codeArbiter@94d901899a5f5c0a2a6040ca74cd904db0c5793c:core/artifacts/internal/operations/work_adopt.go` | `canonicalAdoptionRow` independently reconstructs ID/origin/title, `workAdopt` checks unique origin and exact block digests |
| Existing legacy work reader | `arbiterForge/codeArbiter@94d901899a5f5c0a2a6040ca74cd904db0c5793c:core/pysrc/_worklib.py` | Shared-origin rows treated as unkeyed for selected adoption, one legacy writer |
| Work façade | `arbiterForge/codeArbiter@94d901899a5f5c0a2a6040ca74cd904db0c5793c:core/pysrc/work.py` | Public `adopt-preview`, `adopt`, selected work operations |
| Native work owner | `arbiterForge/codeArbiter@94d901899a5f5c0a2a6040ca74cd904db0c5793c:core/artifacts/internal/operations/work.go` | Unique origin correlation, work ID behavior, create/lookup |
| Work schema | `arbiterForge/codeArbiter@94d901899a5f5c0a2a6040ca74cd904db0c5793c:core/artifacts/schemas/work.schema.json` | Title max 240; summary max 4000; `legacy_source` pointer; origin grammar |
| Legacy task writer | `arbiterForge/codeArbiter@94d901899a5f5c0a2a6040ca74cd904db0c5793c:core/pysrc/taskwrite.py` | Selected-owner and revision checks; serialized board mutation |
| Legacy board classifier | `arbiterForge/codeArbiter@94d901899a5f5c0a2a6040ca74cd904db0c5793c:core/pysrc/_taskboardlib.py` | `classify_board_diff` around baseline lines 498 to 554 |
| Commit gate owner | `arbiterForge/codeArbiter@94d901899a5f5c0a2a6040ca74cd904db0c5793c:core/surface/skills/commit-gate/SKILL.md` | Scope decision, selected board diff, protected paths |
| Feature owner | `arbiterForge/codeArbiter@94d901899a5f5c0a2a6040ca74cd904db0c5793c:core/surface/commands/feature.md` | Normal work binding to spec/plan |
| Human work view | `arbiterForge/codeArbiter@94d901899a5f5c0a2a6040ca74cd904db0c5793c:core/artifacts/internal/render/work_view.go` | Current situation, change, obstacle, next action, checks vs delivery |
| Project view | `arbiterForge/codeArbiter@94d901899a5f5c0a2a6040ca74cd904db0c5793c:core/artifacts/internal/render/project_view.go` | Inventory currently, no aggregated release/tracker evidence |
| Native-first plan | `arbiterForge/codeArbiter@94d901899a5f5c0a2a6040ca74cd904db0c5793c:.codearbiter/plans/native-first-workflow.html` | Eight plan task states recorded `PENDING` at baseline |
| Work-system plan | `arbiterForge/codeArbiter@94d901899a5f5c0a2a6040ca74cd904db0c5793c:.codearbiter/plans/project-work-system.html` | Older `IN_PROGRESS`/`REVIEW`/`PENDING` and source-scoped reported checks |

## Release and cross-surface boundaries

At the review:
- Claude source release [`v3.8.4`](https://github.com/arbiterForge/codeArbiter/releases/tag/v3.8.4) published.
- Codex [`ca-codex-v0.26.4`](https://github.com/arbiterForge/codeArbiter/releases/tag/ca-codex-v0.26.4) published. Marketplace branch `ca-codex-marketplace@b3d8d11ca6c1fa0312f4c93254eb3b777916273e` points to `ca-codex-dist-v0.26.4`.
- Pi `ca-pi-v0.27.4` release was a draft after publisher failure at observed time; latest public GitHub Release was `ca-pi-v0.27.3`. Recheck rather than assuming still blocked.
- Academy [`preview-0.33`](https://github.com/arbiterForge/arbiter-academy/releases/tag/preview-0.33) is published. Its manifest binds Claude `3.8.3`, Codex `0.26.3` and Pi `0.27.3` at release-and-command-contract evidence level, not automatically to the latest cohort.
- IDE remains a separate product. Its source links/relationship copy contain stale drift, but that is a separate surface and does not authorize wholesale content transfer.

Published release metadata was inspected but fresh installed-package/marketplace and complete model-backed live journeys were not independently qualified during the review. Do not equate current `main`, source tests or release metadata with installed user behavior.

## Known source mismatch and why order matters

Python `_workadopt.py` derives a default ID from `legacy_origin or origin` and disallows duplicate `origin`. Native Go `canonicalAdoptionRow` separately reconstructs the same logic and `workAdopt` insists on exact field equality and unique IDs/origins. An earlier partial change to one side was withdrawn after preview succeeded but Go refused. The new migration must be designed as a paired contract.

`_taskboardlib.classify_board_diff` accepts one-line state flips and one new queued block, not full selected-item attach/compound transitions. Its `False` is currently surfaced as scope creep by commit-gate even when the owning lane wrote the data.

The native-first plan's all-PENDING task labels are not proof nothing shipped; they are a durable planning-data reconciliation problem. Treat history/current source/checks independently.

## Source boundaries outside this PR

ArbiterForge system operates only on the seven authorized `arbiterForge` repositories. This implementation PR targets `arbiterForge/codeArbiter` only. No downstream forks or employer material are valid inputs. The full Project operating contract is `00-ARBITERFORGE-OPERATING-CONTRACT.md`; dated claim/decision registries are working evidence, not replacements for fresh GitHub source.
