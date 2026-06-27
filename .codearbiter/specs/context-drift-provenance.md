# Spec — context drift + scout provenance + coarse code map

**Slug:** `context-drift-provenance` · **Lane:** full · **Status:** approved 2026-06-26 by brennonhuff@gmail.com

> Source of truth: `docs/reports/deepdive-2026-06-26-project-context/README.md`
> (branch `research-project-context-improvements`) — recommendation items #1, #2, and
> archetype-A idea "concern-split codebase map." Implements those three on **one shared
> engine**. Recommendation #3 (file-scoped JIT injection) is the **committed next feature**
> and consumes the provenance map built here (see Follow-ups).

## Problem

The `.codearbiter/` derived docs — `tech-stack.md`, `coding-standards.md`,
`security-controls.md`, and the scout-derived portion of `CONTEXT.md` — are synthesized
**once** from scout evidence, then the evidence is **discarded**. Nothing links a doc to
the source it was derived from, and nothing detects when that source changes. At ~200k LOC
over a long life the docs silently drift — and wrong context is *worse* than none, because
every skill's pre-flight **trusts** them. Separately, an agent starting a task has no
high-level "concern → where it lives" map, so it burns turns globbing/grepping/reading just
to *locate* the code before doing work.

Both problems are the same shape — durable, low-churn knowledge about the codebase that must
**stay true as the code moves**. This feature captures the discarded scout evidence as
per-doc **provenance** (source files + content hashes + `file:line → claim`), detects
**drift** when a tracked source changes, ships a coarse **code map** for navigation, and —
critically — keeps both fresh **passively**, by riding `commit-gate`, so the maintenance
never becomes a command the user runs.

## Design pillars

1. **Content hash = `git hash-object`**, never mtime, never raw byte sha256. It honors
   `.gitattributes` EOL normalization, so a pure LF↔CRLF flip (a documented Edit hazard on
   Windows in this repo) does **not** false-flag as drift. All tracked paths hash in **one**
   subprocess via `git hash-object --stdin-paths`.

2. **Only low-churn, high-signal sources fire drift.** Each provenance entry carries
   `drift_trigger`. It is `true` only for config/manifest/schema/security-entry sources
   (`package.json`, lockfiles, CI yaml, `*.prisma`/`*.sql`/migrations, `.env.example`,
   auth/middleware/jwt entry files) — where the claims that matter live *and* the file
   rarely changes. General architecture source (Scout C citations) is stored with
   `drift_trigger: false`: it feeds the code map, the audit trail, and future line-anchors,
   but **never rings the alarm.** This is what keeps the signal trustworthy instead of noisy.

3. **Maintenance rides `commit-gate`, not a command** (the `board-done-flip-rides-with-work`
   / ADR-0008 pattern). When a staged file is a `drift_trigger` source whose hash diverged
   from baseline, commit-gate dispatches an **incremental re-scout of just that one file**:
   - scout says *claim still holds* → **silently re-baseline the hash.** Nothing surfaced.
   - scout says *claim changed* → the doc/map edit is **proposed in commit-gate's existing
     diff-review phase**, accepted as part of the commit the user was already making.
   The LLM judgment that a python hook can't make happens here, automatically, at the one
   moment an LLM is already in the loop. The map heals exactly when the source moves.

4. **Read-on-demand, never auto-injected.** The code map and provenance are **not** loaded
   at SessionStart. Task-authoring skills read the code map in pre-flight — paid only in work
   sessions, only when orientation helps. The single passive cost at SessionStart is one
   drift line, emitted **only when drift > 0**.

## Scope

**In:**

- **Provenance store** — `.codearbiter/.provenance/<doc>.json`, one git-committed file per
  derived doc (`tech-stack`, `coding-standards`, `security-controls`, `context`, `code-map`).
  Schema: `{ schema, doc, created, interview_derived, entries:[{ path, hash, drift_trigger,
  claims:[{lines, claim, confidence}] }] }`. Per-doc files give drift, git diffs, and
  incremental re-scout **per-doc locality**. JSON because the consumer is a python hook;
  still plain-text, git-diffable, auditable.

- **`_provenancelib.py`** — pure, stdlib-only, fixture-testable (the `_taskboardlib` pattern),
  injectable hasher: `write_provenance`, `read_provenance`, `write_stub`, `classify_source`
  (→ `drift_trigger`), `batch_hash`, `compute_drift`, `changed_scope`, `rebaseline`,
  `heal_worklist`, `startup_drift_line`, plus a `lint_code_map` for the cap.

- **Coarse code map** — `.codearbiter/code-map.md`: `concern → path → ≤1-line role`, **capped**
  (module/concern granularity only, one line each, bounded entry count). Its paths are
  provenance-tracked (`code-map.json`), so a moved/renamed/deleted module fires drift and
  heals via commit-gate. Read on demand in task-skill pre-flight; never SessionStart-injected.

- **Creation writes both, as ride-alongs:**
  - **Brownfield** (`context-creation`): scouts additionally emit a `git hash-object` per
    cited file (they already Read those files — no new pass, no raw content to the
    orchestrator). Phase 5 writes one provenance file per derived doc **and** synthesizes
    `code-map.md` from Scout C evidence. A small addition to Phase 2 + Phase 5, not a rebuild.
  - **Greenfield** (`decompose`): writes provenance **stubs** (`interview_derived: true`,
    empty `entries`) and a code-map stub. Real provenance/map populate on the first
    commit-gate heal (or `/ca:context-check`) once code exists.

- **Surfaces:**
  - **Passive SessionStart line** — backed by `startup_drift_line`; emits **exactly one**
    line iff drift > 0, nothing when clean.
  - **commit-gate auto-heal** — pillar 3, the maintenance engine.
  - **`/ca:context-check` (minimal)** — optional manual audit for bypass cases (a merge or
    external edit drifted a file you're not about to commit): report stale docs, then per doc
    offer **re-scout** / **re-baseline (acknowledge)** / **defer**. No machinery beyond the
    helper + the report.

**Out (explicit boundaries):**

- **Net-new-file coverage.** Drift sees *changed tracked* sources, not net-new files that
  *should* update a doc. Full `/ca:create-context` re-run owns that (D-2).
- **Line-anchor drift.** Per-file hash to start; line ranges are *stored* (free, feeds future
  precision + the JIT-injection follow-up) but drift is per-file (D-1).
- **File-scoped JIT injection** — the committed next feature; consumes this map (Follow-ups).
- **Per-task context manifest** — already produced by `writing-plans` (exact file paths per
  task) + the new code map; a separate artifact would duplicate it. Declined.
- No vector DB / embeddings / semantic index, no daemon/worker, no transcript-JSONL parsing,
  no call-graph/API-chain database (cannot be kept fresh passively). FTS5-in-one-SQLite remains
  the documented escape hatch **only if** the doc set ever outgrows grep — not now.

## Acceptance criteria

Each verifiable by a single test. Helper criteria → `test_provenancelib.py`; wiring criteria
→ structural SKILL.md/hook assertions (`test_board_sync.py` pattern) + `check-plugin-refs.py`.

**Hash & drift core**
1. **AC-01** `write_provenance` then `read_provenance` round-trips an equal record; on-disk
   file is valid JSON with `schema/doc/created/interview_derived/entries[]`.
2. **AC-02** `batch_hash(paths, runner)` issues a **single** `git hash-object --stdin-paths`
   call (asserted via injected `runner`) and returns `{path: oid}` preserving order.
3. **AC-03** An entry hashed by `git hash-object` vs a working-tree file differing **only** by
   LF↔CRLF under `eol=lf` is reported **unchanged** by `compute_drift`.
4. **AC-04** Given an injected current-hash map with one diverged path, `compute_drift` returns
   that path under its doc, and only it.
5. **AC-05** An entry whose path is absent from current hashes is reported as drift kind
   `missing`; `compute_drift` does not raise.
6. **AC-06** No diverged entry → `startup_drift_line` returns `""` (SessionStart silent).
7. **AC-07** Drift > 0 → `startup_drift_line` returns exactly one line naming stale-source and
   doc counts and pointing to `/ca:context-check`.
8. **AC-08** Missing/corrupt `.provenance/` → `compute_drift` empty, `startup_drift_line` `""`,
   hook never crashes (degrade-not-fail).

**Low-churn discipline (the anti-noise guarantee)**
9. **AC-09** `compute_drift` considers **only** entries with `drift_trigger: true`; entries
   with `drift_trigger: false` are stored but never reported as drift.
10. **AC-10** `classify_source(path)` returns `drift_trigger: true` for config/manifest/schema/
    security-entry patterns and `false` for general source, over a fixture path set.

**Incremental scope & acknowledge**
11. **AC-11** `changed_scope(doc_provenance, drift)` returns **only** the changed/missing paths
    of that doc — never the full repo, never another doc's paths.
12. **AC-12** `rebaseline(provenance, current_hashes)` updates each entry's `hash`, leaves
    `claims`/`doc` untouched; a subsequent `compute_drift` returns empty.

**commit-gate auto-heal engine**
13. **AC-13** `heal_worklist(staged_paths, provenance, current_hashes)` returns only staged
    paths that are `drift_trigger` entries with diverged hashes — **empty** when no staged file
    is tracked (most commits pay nothing).
14. **AC-14** (structural) `commit-gate/SKILL.md` gains a conditional phase: on a non-empty
    heal worklist, dispatch an incremental re-scout scoped to those paths only; claim-holds →
    silent re-baseline; claim-changed → doc/map edit proposed in the existing diff-review phase.

**Code map**
15. **AC-15** `lint_code_map` rejects/flags a map exceeding the entry cap or carrying a
    multi-line role — enforcing module/concern granularity.
16. **AC-16** (structural) task-authoring skills (`tdd`, `feature`, `fix`) read `code-map.md`
    in pre-flight; the SessionStart hook does **not** read or inject it (read-on-demand only).

**Creation**
17. **AC-17** (structural) `context-creation` Phase 2 scouts emit a `git hash-object` per cited
    file; Phase 5 writes one provenance file per derived doc **and** `code-map.md`;
    `agents/scout.md`'s output template carries the hash field.
18. **AC-18** (structural) `decompose` writes provenance stubs (`interview_derived: true`,
    empty `entries`) per derived doc + a code-map stub; `write_stub` produces exactly that shape.

**Surface**
19. **AC-19** (structural) `/ca:context-check` skill + command exist with the minimal flow
    (report → per-doc re-scout / re-baseline / defer), and routing-table + reference-map +
    command-catalog entries resolve under `check-plugin-refs.py`.

## Deferred decisions (non-blocking — not `CONFIRM-NN`, do not gate stage promotion)

- **D-1 — line-anchor precision.** Per-file hash ships; line ranges already stored. Add anchor
  drift only if per-file proves noisy in practice.
- **D-2 — net-new-file coverage.** Drift sees changed *tracked* files only; full `/create-context`
  re-run is the current answer for net-new sources.
- **D-3 — SessionStart cost guard.** The drift line runs one `git hash-object` subprocess per
  session. If latency is unacceptable on a huge tracked set, gate it (env flag or a periodic
  marker); ships ungated, tune if measured.
- **D-4 — heal-trigger breadth.** commit-gate owns the auto-heal. Whether `/ca:standup` or a
  sprint step should also *offer* a drift sweep is a later wiring decision.
- **Enforcement soft-spot (named, not solved).** Provenance/code-map *writes* are
  prompt-discipline backed by structural ACs (AC-17/18), not a runtime gate — the same class as
  open **CONFIRM-09** ("compel a log write"). v1 accepts prose-enforcement; a compelling hook
  rides whatever direction CONFIRM-09 resolves to.

## Open questions

None blocking. No new `[CONFIRM-NN]` raised — every fork (hash mechanism, schema, greenfield,
check scope, drift granularity, maintenance trigger, code-map inclusion) resolved in session.

## Follow-ups (harvest at exit)

- **NEXT FEATURE — file-scoped JIT injection** (deep-dive rec #3, kickoff-2). A `PreToolUse:Read`
  hook that injects the governing `.codearbiter/` knowledge about the file being opened, gated on
  this feature's provenance freshness. Committed as the immediate next step after this ships.
  → `open-tasks.md`.
- **`[NEEDS-TRIAGE]`** Doc inconsistency: `agents/scout.md` says the scout agent is dispatched by
  `context-creation`, but `context-creation/SKILL.md` Phase 2 dispatches **`general-purpose`**
  agents. Harmless here; the two docs disagree on which agent runs brownfield scouting.
  → `open-tasks.md`.
