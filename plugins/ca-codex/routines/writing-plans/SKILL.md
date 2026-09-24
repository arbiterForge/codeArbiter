---
name: writing-plans
description: The spec-to-plan bridge. /feature supplies an approved spec; initial full-lane HTML sprint review may supply a ready draft only through draft_for_pair. Creates the same-format plan with exact paths, tests, dependencies and complete criterion coverage. The initial paired review has no execution authority until one real user reply approves both artifacts. Ordinary sequential planning retains approved-source binding and plan approval.
disable-model-invocation: true
---

# writing-plans

## Authoritative format boundary

For a new full-lane HTML spec, load [includes/artifacts.md](../../includes/artifacts.md) and
use the installed structured-artifact engine for every spec and plan read or
write. The resulting pair is `.codearbiter/specs/<slug>.html` and
`.codearbiter/plans/<slug>.html`. Missing or invalid HTML capability is a STOP
before writing and must not fall back to Markdown. An existing authoritative
Markdown spec continues through the legacy Markdown path without conversion.
HTML `--farm` dispatch remains blocked.


Turn an approved spec into an executable plan, or prepare a ready draft plan for initial combined
HTML sprint review. Draft preparation is not execution authority. Routed to by `/feature` (after
spec approval) and `/sprint` under its explicit call mode.

## Pre-flight

Read these, or STOP and surface the gap. Missing specs always block. Ordinary planning requires
approval; only initial full-lane HTML sprint-pair preparation accepts an exact ready draft:

- The authoritative approved spec selected by `/feature`: for HTML, resolve it
  through the installed engine and verify its ready approval and exact identity;
  for legacy Markdown, read `<project-root>/.codearbiter/specs/<slug>.md`.
  Absent → STOP. Unapproved → STOP except the explicit initial sprint `draft_for_pair` mode,
  which verifies ready/current draft identity through the private preflight and never grants execution.
  Route a genuine missing prerequisite back to the active caller, not an unrelated feature interview.
- `<project-root>/.codearbiter/CONTEXT.md` — the `stage:` frontmatter (the maturity value) and project context.
- `<project-root>/.codearbiter/tech-stack.md` — file layout, build/test/lint invocations. A verification step cites a real command from here, never a guess.
- `<project-root>/.codearbiter/coding-standards.md` — structure and naming, so a task names the right path.

**If `--farm` was requested:** check that `FARM_API_KEY` is set in the environment (or `.env` at `tools/.env`). If absent, BLOCK immediately — cite [includes/farm.md](../../includes/farm.md) for setup instructions. Do not proceed; the farm dispatcher cannot run without an API key. Model selection happens later (at dispatch time in `subagent-driven-development`), so no model research is needed here.

## Phase 1 — Criterion extraction · gate: BLOCK

Lift every acceptance criterion from the spec and retain its stable ID (`AC-01`,
`AC-02`, …). For HTML, obtain criterion records through typed engine reads and
retain their typed IDs; rendered document text is not an authority source. This
list is the coverage ledger for the whole plan — Phase 4 checks the task set
against it.

A criterion the spec leaves ambiguous is a `[CONFIRM-NN]` against
`<project-root>/.codearbiter/open-questions.md` — surface it, do not invent the intent.

**Backstop the ledger against the spec's own stated intent, mechanically, before trusting it — this
runs even when `brainstorming` already ran the same check, because a hole that survived Phase 3
survives Phase 4's bijection too, silently** (#566): run `"$PY" "${PLUGIN_ROOT}/hooks/_intentlib.py"
uncovered-intent <spec-path> [--issue-body <scratch-file>]`, where `<spec-path>`
is the authoritative `.html` or legacy `.md` spec selected above —
`<scratch-file>` holds the linked issue's body when one exists (`gh issue view <N> --json body -q
.body > <scratch-file>`, written outside the working tree), omitted when none does. A non-empty
result names an in-scope bullet or an acceptance checkbox the criteria never cited — BLOCK and route
back to `brainstorming` ([routines/brainstorming/SKILL.md](../brainstorming/SKILL.md)) to add the missing criterion or record a `[CONFIRM-NN]`; never paper over a
missing criterion by authoring a task for it here instead. This is the LAST point before a hole gets
laundered through Phase 4's bijection, which only checks the ledger against itself and cannot see
past it.

Then ask the half this tool cannot mechanize: **if every `AC-NN` passed and nothing else changed,
what would still be broken?** A real answer names a criterion the ledger is missing even though
every scope bullet and checkbox is technically cited — judgment, not mechanizable, and not satisfied
by a rhetorical "nothing." Finding nothing broken is a reportable result, stated in one line, never a
silent skip.

Gate: every acceptance criterion in the spec captured as a numbered `AC-NN`; the `uncovered_intent`
backstop above returns empty or every finding is resolved; and the negative question has been asked
and answered. A partial ledger does not pass.

## Phase 2 — Task decomposition · gate: BLOCK

Break the work into the smallest honest units. Each **task** is ~2–5 minutes of work and carries:

- **id** — `T-01`, `T-02`, … stable.
- **path(s)** — the exact file(s) the task touches, resolved against `coding-standards.md`. "Some files" is not a path.
- **verification** — one concrete command or observable that proves the task done (e.g., `<test cmd> -k test_token_expiry passes`, `endpoint returns 401 on missing header`). It cites a real `tech-stack.md` invocation or a directly observable behavior — never "looks right".
- **maps-to** — the `tdd` obligation this verification corresponds to. The verification *maps to* a tdd obligation; it does NOT replace tdd's own gates. `tdd` Phase 1 still derives and Phase 4 still verifies obligations against passing tests.
- **covers** — the `AC-NN`(s) this task advances.

Split anything that won't fit ~5 minutes or touches unrelated paths. Reject the trap of one
monolithic "implement the feature" task — that defeats the plan.

Gate: every task has at least one path AND a verification AND a `maps-to`. A task missing any of the
three blocks the plan.

## Phase 3 — Order & MVP slice · gate: BLOCK

Order tasks so each runs only after what it depends on. Flag every dependency explicitly
(`T-07 depends on T-03`). A cycle is a decomposition error — return to Phase 2 and split.

Group the ordered tasks so the **MVP slice** is identifiable: the minimal contiguous task set that
satisfies the spec's core acceptance criteria and is shippable on its own. Everything past the slice
is incremental.

Gate: a complete dependency order with no cycle, and an explicitly marked MVP slice.

## Phase 4 — Bijection proof & write · gate: BLOCK

Cross the ledger against the task set, both directions. **This proves the plan and the ledger AGREE
with each other — it does not prove the ledger itself is COMPLETE relative to the spec's stated
intent.** A criterion missing from the ledger entirely was never a candidate for either check below;
that completeness gap is caught earlier, by Phase 1's `uncovered_intent` backstop (and by
`brainstorming` Phase 3 before that) — never re-derived here, and never implied by this phase's name
(#566: a prior version of this gate read "coverage proof", which a bijective check does not earn).

- Every `AC-NN` is covered by at least one task's `covers`. An uncovered criterion blocks — author the missing task.
- Every task advances at least one `AC-NN`. A task that covers nothing is scope creep — cut it or surface it.

For an HTML source, pass the selected route, installed client, and the spec
identity just read from the engine through `_preflight_plan_authoring`. Initial full-lane sprint
pair preparation alone sets `draft_for_pair: true`; the ordinary default still requires approval. Only its
returned same-slug `.codearbiter/plans/<slug>.html` target may be created. Create
that plan through the installed structured-artifact engine as `draft_preview`,
using the source spec's exact artifact ID and normative digest. For ordinary sequential planning,
this must be the approved spec's exact artifact ID and normative digest. Populate it only with typed operations
and validate it at the ready gate. For initial combined review, retain `draft_preview` and return
both ready identities to the caller: `sprint-approve` owns the binding and both approvals after one
actual host-observed reply. Do not separately `plan-bind` or approve that pair. On ordinary approved-spec
planning, use `plan-bind` to bind it to the approved spec before plan approval. This path must not create `.codearbiter/plans/<slug>.md`;
that would be a shadow authority.

For an existing authoritative Markdown source, write
`<project-root>/.codearbiter/plans/<slug>.md` — `<slug>` matching the spec —
with the `AC-NN` ledger, the ordered task table (id · path(s) · verification ·
maps-to · covers · depends-on · **status**, initialized `PENDING`), the marked
MVP slice, and any out-of-scope item tagged inline `[NEEDS-TRIAGE]`.

The status column is the pipeline's resume ledger: `subagent-driven-development` flips a task to
`ACCEPTED` the moment it accepts it, so an interrupted run (crash, compaction, closed session) is
re-entered by `/feature` at the first non-`ACCEPTED` task instead of restarted from brainstorming.

Gate: bijection proven between the plan and the ledger — no criterion without a task, no task without
a criterion — and the plan written to disk. This proves the two are mutually consistent, nothing more;
completeness of the ledger itself was Phase 1's gate, not this one. Initial combined-review drafts
return for `arm-sprint`, never execution. Only verified approved spec-and-plan authority clears execution:
`executing-plans` (checkpointed, via `/feature`) or `subagent-driven-development` (autonomous, via
`/sprint`) — each routes every task through `tdd`. The plan never hands off to `tdd` directly.

### Phase 4-farm extension (only when `--farm` was requested)

When `--farm` was requested for a legacy Markdown workflow, after the bijective coverage gate passes and the `.md` plan is written,
produce the farm artifact (`plan.json`) — **one MVP slice at a time** — per
[routines/writing-plans/references/farm-plan.md](references/farm-plan.md). Load that leaf and follow it;
it owns the per-task failing-test + schema-valid `plan.json` procedure.

Gate: all failing tests written and confirmed failing; `plan.json` written and schema-valid. Both
artifacts exist before handing off to `subagent-driven-development` ([routines/subagent-driven-development/SKILL.md](../subagent-driven-development/SKILL.md)).

## Hard rules

- MUST NOT execute or approve work against an absent or unapproved spec. Only explicit initial
  full-lane HTML `draft_for_pair` planning accepts a ready draft and must return for combined approval;
  other unapproved inputs route back to their actual caller.
- MUST NOT write or parse rendered HTML directly, create a Markdown shadow for
  an HTML spec, or bind a plan from a caller-supplied identity.
- MUST NOT emit a task without an exact path AND a concrete verification step.
- MUST NOT let a task's verification stand in for a `tdd` gate — it maps to a tdd obligation, it does not replace one.
- MUST NOT write the plan while any acceptance criterion is uncovered or any task covers nothing.
- MUST NOT guess a verification command — cite `tech-stack.md` or STOP.
- MUST NOT resolve an ambiguous criterion by guessing — raise a `[CONFIRM-NN]`.
- MUST run the `uncovered_intent` backstop and ask the negative-judgment question in Phase 1, and MUST NOT treat Phase 4's bijection proof as a substitute — bijection proves the plan and the ledger agree with each other, never that the ledger is complete (#566).
- MUST NOT emit `plan.json` in `--farm` mode without writing and confirming each failing test first.
- MUST NOT set `meta.model` or `meta.apiBaseUrl` in `plan.json` — these belong to the dispatch step.
- MUST NOT proceed with `--farm` if `FARM_API_KEY` is absent — cite [includes/farm.md](../../includes/farm.md) and BLOCK.
- MUST, at exit, run the follow-up harvest ([includes/harvest.md](../../includes/harvest.md)) over any `[NEEDS-TRIAGE]` out-of-scope items — batch-confirm promoting them to `open-tasks.md` (work) or `open-questions.md` (decisions) so they don't die in the plan file.
