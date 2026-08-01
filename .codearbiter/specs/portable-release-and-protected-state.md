# Sprint spec — portable release + protected-state machinery

**Date:** 2026-07-31
**Slug:** `portable-release-and-protected-state`
**Issues:** #563 (release portability, workstream A); #564 (protected-state machinery, workstream B)
**Companion spec:** `specs/release-portable-fixture.md` (rev 4, three adversarial passes, cleared)
**Decisions:** DECISION-0034; sprint-log D-1/D-2 closure 2026-07-31

## Goal

Two workstreams that share one piece of machinery. `/ca:release` becomes a portable fixture whose
repo-specific facts live in project state — and the guard that makes those facts trustworthy is built
as **generic marker-gated protected-state infrastructure**, with the release file as one of three
consumers rather than its reason.

## Standing steers (use these to break SMARTS ties)

Stated by the user across the design session. A `tied` or `moderate` SMARTS call resolves toward
these before falling back to the §2 conflict hierarchy.

1. **Context economy.** Minimize what is loaded into context on every turn while keeping it available
   when relevant. This is why the release rows live outside `CONTEXT.md` and why JIT surfacing is
   preferred over always-on inclusion.
2. **Helpers write; inference does not.** The project is moving toward project-state files mutated by
   sanctioned helpers rather than by an agent composing markdown. The guard exists to make the helper
   the only path.
3. **Generic over special-case.** The protected-state class is parameterized over a registry. A
   one-off for a single file would have to be torn out at the first second consumer.
4. **Reliability and testability over convenience.** The observed pattern across prior decisions
   (mutation-testing directive, dry-run-the-path, no-silent-reconcile) and the one applied in
   DECISION-0034.
5. **No repo-local variant of a shipped skill**, and no behavior change to this repo's four-plugin
   release.
6. **Never drop adversarial verification to save budget.** Sequence lanes instead; push WIP early so
   interrupted work is recoverable.
7. **Determinism over suggestion — weight `Scalable` heavier than usual.** The project is moving work
   out of prose "suggestions" that an agent may or may not honor, and into deterministic helpers and
   hooks. Two reasons, both load-bearing: it cuts tokens, and it turns process rules into things that
   are *enforced* rather than *advised*. When a SMARTS call is between adding skill prose and building
   a helper or hook, `Scalable` carries extra weight and the deterministic option wins ties.

## Review and completion standards

- **Adversarial passes** run one pass with an **Opus** model at **medium** effort. (The Agent tool
  pins the model but has no effort parameter; effort inherits the session setting.)
- **All HIGH findings must be remediated.** MEDIUM findings are fixed or filed at discretion.
- **The advisor is a maintainer proxy.** Questions that would otherwise stop the run for the user may
  be put to the standing adversarial advisor and answered as if it were them — except the hard gates,
  which remain true stops.
- **Completion bar: the replacement must be proven to work AND to port.** The sprint is not done when
  the tasks are `ACCEPTED`; it is done when the new lane is demonstrated working in this repo and in a
  clean consumer repo. Verifying against this repo's hand-built `.codearbiter/` state is exactly the
  condition that hides consumer-facing bugs.

## Workstream A — release portability

Fully specified in `specs/release-portable-fixture.md` rev 4: 42 acceptance criteria across six
slices, cleared by three adversarial passes. Not restated here. Its dependency on this sprint is
narrow and explicit: **AC-2.6 and AC-2.7 are satisfied by workstream B's class**, with
`release-targets.md` registered as its first consumer.

## Workstream B — generic protected-state machinery

### B1 — The class

A registry-based protected-write class over project-state files. **Each registry entry carries a
policy**, because the three consumers need materially different write semantics and a flat
marker-gated registry is wrong for two of them:

| policy | semantics | consumer |
|---|---|---|
| `marker-gated` | Write/Edit/shell admitted only under a fresh authoring marker | `release-targets.md` |
| `helper-only` | Write/Edit/shell naming the file are **hard-blocked with no marker path**; the sanctioned helper's own file I/O is the only route | `open-tasks.md` |
| `append-only` | mutation only via the helper's append verb | `done-tasks.md` |

**The policy enum is built in slice 1** even though only `marker-gated` is exercised then. Shipping a
marker-only schema would force a breaking rebuild at step 6.

Why `open-tasks.md` must NOT be marker-gated: `taskwrite.py` already exists and its header states it
is "the ONLY blessed way to write `.codearbiter/open-tasks.md`". It is Python file I/O invoked via
Bash whose argv never lexically names the file, so it is **invisible to all three flanks by
construction**. A marker would therefore add nothing for the helper while *admitting* an agent that
composes board markdown under that marker — exactly what steer 2 forbids. The correct enrolment is a
hard block with no marker path at all.

For the `marker-gated` policy only, the mechanism is the H-11 pattern
(`decision-lifecycle/SKILL.md:37,55` — mint immediately before the write, `rm -f` at lane exit;
`_hooklib.marker_fresh` is a 30-minute mtime window).

**Registered on all three flanks**, using CONTEXT.md's existing guards as the template:

- `pre-write.py` — the Write door
- `pre-edit.py` — the Edit door, via `classify_protected` per-class dispatch
- `_bashguardlib` — a redirect and write-verb regex pair mirroring `CONTEXT_REDIRECT_RE` /
  `CONTEXT_WRITE_RE` (lines 355-356, checked at 1011)

A one-flank implementation is a non-fix: it passes a Write-door test while
`echo '…' >> <protected file>` still lands. The shell-indirection residual (`f=…; sed -i "$f"`, novel
`python -c` spellings) is the same accepted ADR-0010 cooperative-attestation residual CONTEXT.md
already carries, and must be **named** in the new ADR rather than left implied. The marker's value is
audit friction, not authorization.

**The registry is the deliverable, not the entries.** Adding a fourth protected file later must be a
registry entry with a policy, never a new hook branch.

**Two flank regressions are B1 obligations, not enrolment-time discoveries.** `commit-gate` Phase 7
runs `git add open-tasks.md` (`commit-gate/SKILL.md:113`) — a Bash argv naming a protected file — and
`/ca:task add -- "fix open-tasks.md schema"` puts the filename in argv as data. If the mirrored
verb-set drifts to include git verbs, **commit-gate blocks itself on every retained board flip**.
Pinned tests: `git add open-tasks.md` passes, a filename-in-description helper call passes,
`tee open-tasks.md` and `>> open-tasks.md` block.

### B2 — Consumers

| file | policy | write route |
|---|---|---|
| `release-targets.md` | `marker-gated` | `context-creation`, the back-fill lane, `/ca:release`'s row-edit path |
| `open-tasks.md` | `helper-only` | `taskwrite.py` exclusively; lands **last** per sequencing |
| `done-tasks.md` | `append-only` | the B4 archive verb exclusively |

`done-tasks.md` is `helper-only`/`append-only` rather than joining the H-05 audit set. The audit set
would supply Write-block, tail-anchored append, and a shell flank for free, but it permits *any*
cooperative append — weaker than routing through the archive verb this sprint must build regardless.

### B3 — Writer inventory (corrected; verified, not heuristic)

The earlier "seven or eight writers" estimate was wrong in both directions. Verified inventory:

**Already helper-routed — no conversion needed.** `harvest.md:51-52` promotes work via
`{{CMD:task}} add`, so every harvest-invoking surface (`commit-gate` Phases 7/151, `tdd`,
`brainstorming:75`, `writing-plans:102`) already writes through the helper.

**Not writers at all.** `using-git-worktrees:34` explicitly says *not* the backlog;
`standup.md:44` states "the board is never mutated here" (it becomes a writer only via B4);
`reference-map.md` is routing. `commit-gate`'s apparent four paths overcount — line 97 is diff
retention and line 113 is `git add`.

**Hook-layer writers the surface scan cannot see.** `init-codearbiter.py:96` *creates*
`open-tasks.md`, and `taskwrite.py` itself. Both are helper-path and flank-invisible. Verified
read-only: `boardsync.py` (its header says "Writes nothing"), `session-start.py:1123`,
`statusline.py`, `_arbiterstatelib.py`.

**The only two surfaces needing real work:**

1. `debug/SKILL.md:80` instructs a **direct append** carrying an indented `- Desc:` rationale
   sub-bullet. `taskwrite add` has no sub-bullet support, so this is a conversion *plus a helper
   extension*, not a prose swap.
2. `context-creation/SKILL.md:103` **populates** `open-tasks.md` via the Write tool during
   doc-writing — blocked under `helper-only`. Needs either repeated `taskwrite add` seeding or a
   scaffold-time exemption while the file is uninitialized.

**ADR-0008 composes cleanly — verified by trace.** `/ca:task done X` → `taskwrite.py` stamps
`(done YYYY-MM-DD)` (`_taskboardlib.py:761`) → the Bash flank sees no lexical filename and passes →
`commit-gate` Phase 6 `classify_board_diff` sees a clean done-flip (the stamp is *required* by the
classifier at line 406/453) → RETAINED → Phase 7 stages by explicit path. The write-time guard and the
commit-time classifier act on different objects — a tool call versus a staged diff — so they are
complementary, not double-gating.

**Circularity hazard — the structural mitigation, not the sequencing one.** Under `helper-only` the
guard *cannot* block `/ca:task`, because the lexical flanks never see the helper's write. That
construction, not "enrolment lands last," is what makes the hazard safe, and it gets a pinned test
(helper invocation succeeds with enrolment live). The residual is an overbroad flank regex blocking
unrelated Bash, where `/ca:override` is available and logged.

### B4 — Archival sweep (closes D-2)

**The sweep has no implementation path today and needs a new helper verb.** `taskwrite.py`'s verbs are
exactly `add`/`start`/`done` with no removal, and the routing table says "never delete to complete."
With `open-tasks.md` helper-only and `done-tasks.md` append-only, a model Edit performing the move is
blocked by this sprint's own guard.

- **New verb `taskwrite archive <ID> [--date]`** (or `sweep --cutoff N`): **per-item**
  append-to-`done-tasks` first, then remove from `open-tasks`, rerun-safe via dedup on dotted ID
  (exact text for ID-less entries). Batch ordering is unsafe — appending all N then removing all N
  duplicates every item if interrupted between phases, and the reverse order loses records. Per-item
  ordering also maps standup's per-item confirmation 1:1 onto helper calls.
- **Owner: `/ca:standup`** — the daily-hygiene lane with per-action confirmation and a
  never-destructive-without-a-yes contract, which is verbatim D-2's requirement. This holds
  *conditional on the archive verb existing*; without it the composition genuinely fails, which is
  why the arbitration was logged `confidence: low`.
- **Cutoff: done > 14 days**, a named constant per D-3's precedent, tested against an injected date.
- **Undated `[x]` items** archive only under explicit per-item confirmation. Both `taskwrite done` and
  the ADR-0008 classifier enforce `(done …)` stamps, so an undated entry is legacy or override-era.

**D-1 closes as fact, not decision** — verified: `taskwrite.py:2` literally says "resolves D-1". The
`open-questions.md` D-1 text predates the writer and is stale. What D-1 left open is that the
sanctioned path is not *enforced*, which is B1.

## Sequencing

1. **B1** — the class and registry **including the full policy enum**, with `release-targets.md` as
   its only live consumer. The enum is designed now, from B3's verified inventory, even though only
   `marker-gated` is exercised at this point; deferring it forces a breaking schema rebuild at step 6.
   The two flank regressions are obligations here.
2. **A slices 1–4** — mechanism ships, data loads, pre-tag execution, CI repointed.
3. **A slice 5** — onboarding and back-fill.
4. **B3 conversions** — `debug` and `context-creation` onto the helper path, plus the `taskwrite add`
   sub-bullet extension `debug` needs. The inventory itself is already verified, so this is bounded
   conversion work rather than discovery.
5. **B4** — the `taskwrite archive` verb, `done-tasks.md`, and the standup sweep. Runs
   sanctioned-but-unguarded in the gap before step 6, which is fine.
6. **B2 open-tasks enrolment** — last, once both conversions have landed.
7. **A slice 6** — surface reconciliation. The docs-site half (AC-6.5) is separable and carries its
   own verification regime (`npm test` over the generator suites).

## Expected hard gates

Named in advance so their tripping is a planned stop rather than a signal the spec was thin:

- **`security-controls.md` boundary entry** (A's AC-2.5) — a trust-boundary change, never auto-decided.
- **The protected-write class itself** — it modifies hook guards that run in every consumer repo.
- **The new ADR** for the executable-input boundary and the ADR-0010 residual — `/ca:adr` requires
  user attribution by hard rule.
- **Merge to the default branch** — `/ca:sprint` auto-selects open-PR and never merges.

Everything else is auto-decidable under SMARTS with the steers above.

## Out of scope

- Relocating `.github/published-tags.json` (D-6 stays deferred; the row field makes the lane coherent).
- Changing what any release gate *does*, beyond what rev 4 specifies.
- Enrolling project-state files beyond the three named consumers. The registry makes that a later
  one-line change, which is the point.

## Non-gating open question

`[CONFIRM-05]` (the `--farm` Feature Forge promotion bar) is open but unrelated: this sprint runs the
premium backend and does not touch the farm seam. It is not resolved here and does not block.
