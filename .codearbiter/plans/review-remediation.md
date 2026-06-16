# Plan: review-remediation

**Spec:** `.codearbiter/specs/review-remediation.md`
**Branch:** `sprint/review-remediation` (new branch off `main` HEAD)
**Status:** APPROVED — 2026-06-16 (executing)

Execution order: branch (0) → **A** enforcement hooks (hard-gate-dense, first so later tasks run hardened) → **B** ADR format → **C** skill dedup → **D** catalog/docs → **E** engine/test-debt → land. Every A-task HALTS for user approval (trust-boundary); B–E run autonomously and logged.

---

## Tasks

| # | Title | File(s) | Verification | Deps | Gate | Status |
|---|-------|---------|--------------|------|------|--------|
| 0 | Pre-flight: branch `sprint/review-remediation` off `main` HEAD | branch | New branch exists; tree clean | — | auto | DONE |
| 1 | A: failing tests — `git push --all`/`--mirror` on feature branch → BLOCK (H-01) | `.github/scripts/test_hook_guards.py` | Tests red before fix: both forms expect exit 2, `H-01` tag | 0 | auto | DONE |
| 2 | A: block `--all`/`--mirror` pushes (`PUSH_ALL_RE`) | `plugins/ca/hooks/pre-bash.py` | Task 1 green; existing H-01/H-02 matrix still green (71/0) | 1 | **HARD: trust-boundary** | DONE |
| 3 | A: failing tests — `>\| overrides.log` & `>\| decisions/NNNN.md` → BLOCK (H-05/H-11) | `.github/scripts/test_hook_guards.py` | Tests red: both expect exit 2 | 0 | auto | DONE |
| 4 | A: extend `LOG_TRUNC_RE` + `DECISIONS_REDIRECT_RE` to catch `>\|` | `plugins/ca/hooks/pre-bash.py` | Task 3 green; plain `>`/`>>` behavior unchanged (71/0) | 3 | **HARD: trust-boundary** | DONE |
| 5 | A: failing tests — Edit/Write to `decisions/draft.md` & nested `decisions/sub/0001-x.md` → BLOCK (H-11) | `.../tests/test_pre_edit.py`, `test_pre_write.py` (new) | Tests red: non-numeric / nested ADR path → exit 2 | 0 | auto | DONE |
| 6 | A: broaden H-11 regex to any `.md` under `decisions/` | `plugins/ca/hooks/pre-write.py`, `pre-edit.py` | Task 5 green; fresh-marker ALLOW still passes | 5 | **HARD: trust-boundary** | DONE |
| 7 | A: failing tests — non-append edit/redirect to `sprint-log.md` → BLOCK (H-05) | `.github/scripts/test_hook_guards.py`, `test_pre_edit.py`, `test_pre_write.py` | Test red: sprint-log truncation → exit 2 | 0 | auto | DONE |
| 8 | A: add `sprint-log.md` to the H-05 protected set in all three hooks | `pre-bash.py`, `pre-edit.py`, `pre-write.py` | Task 7 green; overrides/triage protection unchanged | 7 | **HARD: trust-boundary** | DONE |
| 9 | A: extend `hooks.json` Edit matcher to `MultiEdit`; teach `pre-edit.py` its shape (NotebookEdit N/A — can't target `.log`/`.md`-ADR) | `plugins/ca/hooks/hooks.json`, `pre-edit.py` | MultiEdit on an audit log/ADR blocks; existing matchers intact | 6,8 | **HARD: trust-boundary** | DONE |
| 10 | A: harden detached-HEAD / case-insensitive protected-branch check | `plugins/ca/hooks/pre-bash.py` | Test: detached HEAD at main tip + `Main` case → still blocked | 2 | **HARD: trust-boundary** | DONE |
| 11 | B: extract canonical ADR template (YAML `NNNN-`) to shared reference | `plugins/ca/skills/decision-lifecycle/references/adr-template.md` (new) | Reference exists; matches lifecycle's current format | 0 | auto | DONE |
| 12 | B: convert `decompose` ADR block to the canonical format; point at the shared template | `plugins/ca/skills/decompose/SKILL.md` | decompose emits YAML `NNNN-` w/ `status:` frontmatter; `/adr-status` would parse it | 11 | auto | DONE |
| 13 | B: point `decision-lifecycle` at the shared template (single source) | `plugins/ca/skills/decision-lifecycle/SKILL.md` | Both skills reference `adr-template.md`; no inline divergence | 11 | auto | DONE |
| 14 | C: extract `writing-plans` `--farm` extension to `references/farm-plan.md`; body references it | `plugins/ca/skills/writing-plans/SKILL.md`, `.../references/farm-plan.md` (new) | Farm path no longer inline; `check-plugin-refs.py` green | 0 | auto | DONE |
| 15 | C: dedup fresh-verification proof — shared `includes/fresh-verification.md` referenced by both Phase 5s | `subagent-driven-development/SKILL.md`, `commit-gate/SKILL.md`, `includes/fresh-verification.md` (new) | One canonical principle; both reference it, each keeps its target | 0 | auto | DONE |
| 16 | C: extract the verbatim cut-doc list to shared `includes/cut-docs.md` (lock-mechanics left per-skill — file sets genuinely differ) | `decompose/SKILL.md`, `context-creation/SKILL.md`, `includes/cut-docs.md` (new) | Cut-doc list defined once; both reference (×3 sites) | 0 | auto | DONE |
| 17 | C: extract maturity→coverage table to `includes/maturity-coverage.md` (tdd P5 + refactor P2) | `tdd/SKILL.md`, `refactor/SKILL.md`, `includes/maturity-coverage.md` (new) | Table defined once; both reference | 0 | auto | DONE |
| 18 | C: extract crypto/secret "On pass" block to `includes/security-gate-record.md` | `crypto-compliance/SKILL.md`, `secret-handling/SKILL.md`, `includes/security-gate-record.md` (new) | Block defined once; H-09b/H-10b ids preserved per skill | 0 | auto | DONE |
| 19 | C: `decision-lifecycle`↔`decision-variance` — boundary-clarified, NOT merged (SMARTS: shared log format already single-sourced in smarts.md; merge = parity risk for marginal gain) | `decision-lifecycle/SKILL.md` | Boundary note added; authoring vs arbitration split documented | 0 | auto | DONE |
| 20 | C: fix `finishing-a-development-branch` ⇄ `/pr` circular PR-body ownership | `finishing-a-development-branch/SKILL.md` | open-PR path executes pr.md steps, does not re-invoke `/pr`; no loop | 0 | auto | DONE |
| 21 | D: strip `new-skill.md` inline phases; wrapper form; remove "trigger" | `plugins/ca/commands/new-skill.md` | No inline phase list; no "trigger"; names skill-author's 5 phases incl. routing-integration | 0 | auto | DONE |
| 22 | D: render `commands.md` from `COMMANDS.md`; delete stale inline table | `plugins/ca/commands/commands.md` | No hard-coded catalog; renders from COMMANDS.md | 0 | auto | DONE |
| 23 | D: fix INDEX phase count for `release` (2→3); enrich `/spike` routing row (already existed — review finding was inaccurate); add `arbiter.md` Hard gate | `skills/INDEX.md`, `includes/routing-table.md`, `commands/arbiter.md` | release=3 phases; `/spike` row present+enriched; arbiter Hard gate present | 0 | auto | DONE |
| 24 | D: fold dangling `[NEEDS-TRIAGE]` items + checkpoint-staleness note into state docs | `.codearbiter/open-tasks.md`, `checkpoints/2026-06-12.md`, `2026-06-13.md` | SH-TRIAGE-2 + SD-02 tracked; both checkpoints note ADRs landed | 0 | auto | DONE |
| 25 | E: characterization test pinning `self_heal` does NOT heal a growing live transcript (existing guard already conservative — no production change) | `plugins/ca/hooks/tests/test_write.py` | Test: growing transcript not healed; crash-corpse tests still green | 0 | auto | DONE |
| 26 | E: cover `security-pass.py` branches (unborn/untracked/oversize-skip/no-.codearbiter/empty-digest/diff-HEAD) | `plugins/ca/hooks/tests/test_security_pass.py` (new) | 6 new tests exercise each branch; suite green | 0 | auto | DONE |
| 27 | E (LOW, optional): disambiguate same-second prune backup filenames | `plugins/ca/hooks/_prunelib.py` | DEFERRED — clean fix fights the lexicographic newest-backup sort for a very-unlikely case; logged | 25 | auto | DEFERRED |
| 28 | Log #6 deferral to `open-questions.md` as a tracked, non-blocking item | `.codearbiter/open-questions.md` | Deferral recorded with rationale; not marked BLOCKING | 0 | auto | TODO |
| 29 | Land: `commit-gate` → `finishing-a-development-branch` (auto open-PR) | — | Full suite green; PR opened; merge left to user | 1-28 | **HARD: merge-to-default deferred to user** | TODO |

---

## Notes

- **MVP slice:** tasks 0–10 (Workstream A) are the shippable core — the confirmed fail-open enforcement holes. B–E extend the same PR.
- **Hard-gate stops, in order:** tasks 2, 4, 6, 8, 9, 10 (every A code-fix is a trust-boundary edit) and task 29 (merge deferral). Each halts and surfaces — none auto-decided. The density is expected for an enforcement-layer sprint and is flagged in the spec, not a planning miss.
- **Test-first:** A (1→2, 3→4, 5→6, 7→8) and E (25, 26) author the failing test before the fix, per `tdd`. B/C/D are skill-prose/doc edits — no TDD demanded of prose (chore/refactor lane), but each carries a concrete verification.
- **Auto-decisions** (test shapes, regex form, reference-file naming, include placement, doc wording) are SMARTS-scored and logged to `sprint-log.md` with a confidence flag.
- **#6 and its siblings are out of scope** (task 28 logs the deferral); do not auto-expand into mechanical commit-gating.
