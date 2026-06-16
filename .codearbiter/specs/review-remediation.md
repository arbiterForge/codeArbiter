# Sprint spec: review-remediation

**Status:** APPROVED — 2026-06-16 (Phase 1 gate cleared; autonomy begun)
**Goal:** Close the findings from the 6-pass repo review — enforcement-hook holes, skill scope/overlap, catalog drift, and the prune/engine gaps. One sprint, one PR.
**Source:** the 2026-06-15 review sweep (links · skill-scope ×3 · enforcement-coverage · logs+engine). Findings captured in session; this spec is the durable record.
**Branch:** `sprint/review-remediation` (new branch off `main` HEAD)
**Execution backend:** premium (NOT `--farm`) — so `[CONFIRM-05]` (farm promotion bar) does not gate this sprint.
**SMARTS pre-scoring:** A strong/fix-now (confirmed fail-open) · B moderate/decided (canonical = lifecycle YAML) · C moderate/behavior-preserving · D strong/mechanical · E moderate/test-debt

---

## Decisions locked at the Phase 1 gate (user-attributed)

1. **Scope:** one big sprint, all HIGH + MEDIUM findings (LOW folded where cheap).
2. **Canonical ADR format (#3):** `decision-lifecycle`'s YAML-frontmatter `NNNN-*.md` form wins; `decompose` is converted to emit it. Least downstream breakage (`/adr-status` + `governs-cache` already parse it).
3. **#6 deferred:** the "MUST NOT commit on a red suite" / "no commit without commit-gate" *mechanical* enforcement is OUT of this sprint — logged as its own open decision (see Out of scope). Its sibling, the secret-to-logger/prompt sink breadth, is deferred with it.

---

## Hard-gate map (read first)

**Workstream A is hard-gate-dense by design** — every task edits an enforcement hook (`pre-bash.py` / `pre-edit.py` / `pre-write.py` / `hooks.json`), which is a `security-controls` / trust-boundary change. Each A-task HALTS and surfaces for explicit user approval even mid-sprint. This is expected, not a planning miss — these are the highest-value fixes and the framework is right to stop on them.

| Workstream | Hard gate | Why it stops |
|------------|-----------|--------------|
| A (all tasks) | `security-controls` / trust-boundary | Edits the enforcement layer (protected-branch, append-only audit log, ADR gate) |
| B (ADR format) | none (skill-prose change) | Changes how `decompose` *authors* ADRs; not authoring one — auto with care |
| C / D / E | none (auto) | Behavior-preserving skill refactors, doc hygiene, and test-debt — auto + logged |

Meta-risk: this sprint edits the framework governing the live session. Workstream A is ordered first so later tasks run under the hardened hooks. Hooks do not guard their own source files, so editing them is unobstructed.

---

## Workstream A — Enforcement-hook holes  (HIGH · HARD GATE, test-first)

Two confirmed fail-open bypasses (empirically verified during review) plus the related gate gaps.

- **A-1/A-2 — `--all` / `--mirror` push bypass (H-01).** `pre-bash.py:172-181`: the token filter strips `--all`/`--mirror`, leaving `['origin']`, which matches no protected-dest pattern → a feature-branch `git push --all` publishes local `main`. Fix the filter so a push that can write a protected ref is blocked regardless of flag form. Tests in `test_hook_guards.py`.
- **A-3/A-4 — `>|` force-clobber bypass (H-05 + H-11).** `pre-bash.py:62` `LOG_TRUNC_RE`: `>| overrides.log` clobbers the audit log and `>| decisions/NNNN.md` clobbers an ADR, both ALLOW today. Extend the truncation regex to catch `>|`. (`exec 3>` FD-redirection remains a documented residual — out of scope, noted.)
- **A-5/A-6 — H-11 numeric-prefix gap.** `pre-write.py:34`/`pre-edit.py:42` match only `decisions/[0-9]+-.+\.md` → a Write to `decisions/draft.md` or a nested `decisions/sub/0001-x.md` slips the ADR gate. Broaden to any `.md` under `decisions/`.
- **A-7 — `sprint-log.md` unprotected (H-05).** The append-only guard hardcodes `overrides|triage` only; `/sprint` auto-decisions in `sprint-log.md` have no integrity protection. Add `sprint-log.md` (and the `decisions/` logs) to the H-05 protected set across all three hooks.
- **A-8 — `hooks.json` matcher gap.** PreToolUse matchers are `Bash|PowerShell|Write|Edit` only; confirm which edit tools the harness exposes and extend to `MultiEdit`/`NotebookEdit` (and any MCP file-writer) so H-05/H-11 can't be sidestepped by tool choice.
- **A-9 — detached-HEAD / case-sensitive branch check (LOW).** `pre-bash.py:156,179` compare `branch in ("main","master")` case-sensitively and treat `""` (detached/failed) as not-protected. Harden the comparison.

## Workstream B — ADR-format unification  (#3 · auto)

- **B-1:** rewrite `decompose` SKILL.md's ADR block to emit the canonical format — YAML frontmatter (`status/date/title/decided-by/supersedes/governs`), `NNNN-*.md` filenames, body `Status/Context/Decision/Alternatives considered/Consequences/Risks` — matching `decision-lifecycle`.
- **B-2:** extract the canonical ADR template to `skills/decision-lifecycle/references/adr-template.md`; point both `decompose` and `decision-lifecycle` at it (single source).

## Workstream C — Skill scope / overlap dedup  (behavior-preserving · auto)

- **C-1 (#4):** extract `writing-plans`' inline `--farm` extension into `skills/writing-plans/references/farm-plan.md`; main body references it (mirrors `subagent-driven-development`'s `farm-dispatch.md`).
- **C-2 (#5):** make the "fresh run, read the exit code" behavioral proof a single canonical description; `subagent-driven-development` Phase 5 and `commit-gate` Phase 5 both reference it instead of restating it.
- **C-3:** extract the duplicated `decompose` ↔ `context-creation` Phase 6 write/lock exit (lock sentinel, required-file checklist, "do NOT scaffold cut docs" list) into a shared `references/lock-contract.md`; both reference.
- **C-4:** extract the maturity→coverage table into a shared include referenced by `tdd` Phase 5 + `refactor` Phase 2.
- **C-5:** extract the verbatim crypto/secret "On pass — record the gate" block into a shared include referenced by `crypto-compliance` + `secret-handling`.
- **C-6:** consolidate `decision-lifecycle` ↔ `decision-variance` — formalize lifecycle as the authoring front-end over a shared decision-log reference; remove the triple-stated supersession / challenger-dispatch / same-level-escalation rules. *(Highest-risk C task — touches two governance skills; review carefully.)*
- **C-7:** fix the `finishing-a-development-branch` ⇄ `/pr` circular ownership — make `routing-table.md` and both skill bodies agree on who owns PR-body assembly (one direction only).

## Workstream D — Catalog & docs hygiene  (chore · auto)

- **D-1 (#8):** strip `new-skill.md`'s inline phase list (it contradicts `skill-author` and uses the banned word "trigger"); reduce to a faithful wrapper like `adr.md`/`reconcile.md`.
- **D-2:** render `commands.md` from `COMMANDS.md`; delete the stale hard-coded catalog table (missing ~11 commands).
- **D-3:** fix `agents`/`skills` `INDEX.md` — `release` is three phases, not two.
- **D-4:** add the missing `/spike` row to `routing-table.md`.
- **D-5:** add a `## Hard gate` to `arbiter.md` (enforce: write `DEV: exit`, remove the marker, never rewrite the log).
- **D-6:** fold the two dangling `[NEEDS-TRIAGE]` items (`SH-TRIAGE-2` missing `coding-standards.md`; `SD-02` host-normalization re-review) into `open-tasks.md`.
- **D-7:** annotate the 2026-06-12/13 checkpoints as superseded on the ADR claim (ADRs `0001-0004` landed afterward).

## Workstream E — Prune / engine gaps  (test-first · auto)

- **E-1:** guard the prune `self_heal` false-positive on a healthy *growing* live transcript (`_prunelib.py:874-887`); test the growing-transcript case, keep the crash-corpse test green.
- **E-2:** close the `security-pass.py` branch-coverage gap — tests for unborn-branch, untracked-file inclusion, `MAX_UNTRACKED_BYTES` skip, no-`.codearbiter` exit, empty-digest.
- **E-3 (LOW, optional):** disambiguate same-second prune backup filenames (`_prunelib.py:865`) with a counter suffix.

---

## Acceptance criteria

1. **A:** `git push --all`/`--mirror` on a feature branch → BLOCK; `>| overrides.log` and `>| decisions/NNNN.md` → BLOCK; `decisions/draft.md` Write → BLOCK; `sprint-log.md` non-append → BLOCK; new guard tests green; full Python suite no regressions. Each A-task surfaced and user-approved (hard gate).
2. **B:** `decompose` and `decision-lifecycle` emit one canonical ADR format from a shared `adr-template.md`; `/adr-status` parses a decompose-authored ADR.
3. **C:** farm-plan, fresh-verification, lock-contract, coverage-table, and crypto/secret on-pass duplications each have a single source; `check-plugin-refs.py` green; no routing contradiction for PR-body ownership.
4. **D:** `new-skill.md` is a wrapper with no "trigger" language; `commands.md` renders from `COMMANDS.md`; INDEX phase count, `/spike` routing row, `arbiter.md` Hard gate all corrected; NEEDS-TRIAGE items and checkpoint-staleness recorded.
5. **E:** prune self-heal false-positive guarded + tested; `security-pass.py` branches covered; full suite (Python + TS) green.
6. Full test suite green; `commit-gate` clean; PR opened (never merged autonomously).
7. Every non-hard-gate auto-decision logged to `sprint-log.md` with a confidence flag.

## Out of scope / deferred (logged)

- **#6 — red-suite / commit-gate mechanical enforcement** (and its sibling, the "compel a log write" half of audit logging, and secret-to-logger/prompt sink breadth): deferred to its own decision per the Phase 1 gate. To be recorded in `open-questions.md` as a tracked, non-blocking deferral — these are inherent prose/discipline limits whose mechanical enforcement is a separate design call (a test-running commit hook is slow and invasive).
- **`exec 3>` FD-redirection** audit-log bypass: documented residual in `pre-bash.py`; A-4 closes `>|` only.
- **The pure-discipline rules** (no-guessing-CONFIRM, no-silent-reconcile, domain-vocab, no-bulk-reads): irreducibly prose-only; no hook surface; not defects.
- **`sprint-log.md:123` old-org URL** (`SUaDtL`): valid historical record; no action.
