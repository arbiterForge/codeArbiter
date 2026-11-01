---
description: "Build an authorized feature from a maintained specification, testable criteria and useful plan, without duplicating user approval."
argument-hint: "<what you want to build>"
---

# {{CMD:feature}} — spec-driven feature

The feature entry maintains a useful spec and plan before full-lane implementation. The user request supplies the intended authorization; the artifact engine does not require another permission code. Check criteria and applicable tests before claiming completion.

## Durable work outcome

Use the installed `hooks/work.py` facade through `{{PLUGIN_ROOT}}/includes/helper-invocation.md`
from the intended project worktree. An actionable feature has one `WORK-ID`
through authoring, implementation and delivery. If the request names a work ID,
read `work.py context <WORK-ID>` first and retain its exact bindings. Never
equate two outcomes by title. If selection is ambiguous, list the bounded
candidates and ask for an exact ID before changing either item.

For a full lane, resolve or create the canonical spec first. If an explicit
`WORK-ID` was already selected, retain it and attach the actual spec ID there
with `work.py attach <WORK-ID> --spec-id <SPEC-ID> --operation-id <stable-id>`.
Otherwise search its stable origin with `work.py origins --origin
feature-spec#<SPEC-ID>`. Reuse the returned work ID, or create once with
`work.py create --title <outcome> --intent <outcome> --type feature --spec-id
<SPEC-ID> --origin feature-spec#<SPEC-ID>` and a stable operation ID. A lost
response is retried with the same operation ID or resolved by that exact
origin; it is not a reason to create another item. Once the real
plan exists, attach its `PLAN-ID` with `work.py attach <WORK-ID> --plan-id
<PLAN-ID> --operation-id <stable-id>`. Recheck the selected work context after
an uncertain attachment. A mismatched existing binding is a scoped conflict;
do not hide it by opening another work item.

For a small lane, keep the mini-spec inline. Create a work item when the
authorized change becomes actionable, without creating an HTML spec or plan for
bookkeeping. Use a durable external source key as `--origin` when one exists;
otherwise pass a stable `--operation-id` and reuse it for an uncertain retry.
Retain and report the returned work ID for exact resume. On a later
session, select that ID via `work.py list`/`get`, never a title-only match.
For native-owned work, run `work.py view <WORK-ID> --save` after changes and report its returned
local page path. The page is a replaceable snapshot; the work record remains
canonical. `work.py view <WORK-ID>` still prints HTML when a native caller needs it.
Legacy board work has no native derived view; use its selected board owner.
Local `complete` records implementation progress, not passing checks, PR merge,
release or provider synchronization. Preserve the existing test, host, commit
and PR boundaries.
In a native project with an explicit transition map, the ordinary lifecycle
call also saves the configured issue and Project intent, or a waiting reason,
in that same local transaction. Keep remote synchronization explicit through
`work.py sync-mapped <WORK-ID>` after the selected timing condition. Do not
make each model call stage both targets separately.

## Structured-artifact boundary

For new full-lane work or an existing `.html` spec/plan match, load
`{{PLUGIN_ROOT}}/includes/artifacts.md` before resume classification or artifact
I/O. After lane classification, call
`_select_authoring_route` with the trusted project root, slug, `workflow: feature`,
and the selected lane. Use only its returned mode, format, and paths. For a
selected HTML route it
checks the installed capability before writing; a missing or invalid helper is
a STOP and the workflow must not fall back to Markdown.
Its typed identity, binding, and task-progress operations replace rendered-label and Markdown status-cell assumptions for that pipeline.
New full-lane specs use the installed structured-artifact engine and default to
canonical `.html`. An existing `.md` pair remains on the legacy path. Discovery requires a
complete same-extension spec/plan pair: select that exact pair as authoritative. A
mixed-extension or duplicate match is a STOP. A lone spec resumes in its exact format,
and the next plan must use the same extension. The workflow must not create, rename, or convert its counterpart to repair ambiguity. HTML `--farm` dispatch stays
blocked. Small-lane behavior is unchanged: its confirmed mini-spec remains inline
and does not create a spec artifact.

**Orientation:** if the code map is present (`.codearbiter/code-map.md`, or its HTML knowledge document), read it first — a coarse concern→path→role map that orients task authoring. Absent is fine; it is read-on-demand, populated by context-creation or commit-gate heal. At each actual author or independent reviewer dispatch, use the private `_artifactpromptlib.compose_feature_actor_input` contract described in `tdd` and `subagent-driven-development`; send the bounded relevant input to that actor. Host permissions still apply to commands; delivery records do not independently grant or deny execution.

## Resume — an interrupted pipeline is re-entered, never restarted

Before triage, scan `{{PROJECT_DIR}}/.codearbiter/specs/` and `plans/` for artifacts
whose slug matches `$ARGUMENTS` (invoked bare, list every resumable pipeline and
ask which). Call the private bridge resolver `_resolve_workflow_pair` with the
trusted project root and selected slug; its returned paths and format own this
resume. Select a complete same-extension pair as authoritative. A lone spec
resumes in its exact format, and the next plan must use the same extension. A
mixed-extension or duplicate match is a STOP. A crash, compaction,
or closed session mid-pipeline loses nothing — the spec, the plan, and each task's
state are on disk. For an HTML pair, obtain state only through the installed
engine `identity`, `index`, and symbol-scoped `read` operations; do not scrape
rendered labels or embedded JSON. For a Markdown pair, use the
existing Markdown status ledger. Resume either exact format
without creating or consulting a shadow artifact; the workflow must not create,
rename, or convert its counterpart. On a match,
summarize the resume point without requesting an additional permission reply, then re-enter at the furthest useful stage:

1. **Plan exists with remaining, blocked, or unverified work** → `executing-plans` for actual outstanding tasks. HTML `REVIEW` and `DONE` are implementation progress, not proof of passing checks.
2. **Plan work complete with applicable checks recorded** → the authorized `commit-gate` handoff, without making a proof receipt another permission.
3. **Spec exists, no plan** → `writing-plans`.
4. **Spec exists but is incomplete** → inspect the missing actual requirements with `brainstorming`, rather than restarting the interview.

Re-running `brainstorming` against a usable existing spec discards decisions and re-asks answered questions. Only an explicit user
request ("start over") restarts an existing slug — and that is logged to `triage.log` like any
classification.

## Step 0 — change-class triage (logged)

Before routing, classify the request. The **small lane** applies only when ALL of these hold —
judged against `$ARGUMENTS` and a quick look at the code, never assumed:

- the change touches ≤ 2 implementation files (plus their tests);
- no §4 reference-map scope-touch: auth/crypto/secrets, dependencies, migrations/schema, telemetry,
  public API surface, domain vocabulary;
- no new dependency, endpoint, command, or configuration surface;
- the behavior change is expressible as 1–3 concrete, individually testable acceptance criteria.

**Small-lane SMARTS.** Only when the change involves a material solution choice — two or more
materially plausible ways to build it — run a SMARTS scan per `{{PLUGIN_ROOT}}/includes/smarts/core.md`,
inline with no grader or scout, and state its one-line result with the mini-spec. Otherwise state
`SMARTS: no material solution choice` and continue; that path adds no SMARTS table and no extra
artifact. If the scan shows that the better approach would violate any small-lane criterion above,
route to the **full lane**.

**Small lane:** state the mini-spec inline (the 1–3 criteria). Unless the user requested a pause or a real consequential question remains, proceed without a second permission reply. Append one line to `{{PROJECT_DIR}}/.codearbiter/triage.log`
(append-only, `>>`):

```
[ISO-8601 timestamp] | BY: <git user.email> | LANE: small | SCOPE: <one-line> | BASIS: <criteria met>
```

Then route directly to `tdd` (`{{PLUGIN_ROOT}}/skills/tdd/SKILL.md`) — the stated criteria are its obligations; run applicable TDD checks — and exit through the full `commit-gate` and `finishing-a-development-branch` exactly as
the full lane does. The lane trims ceremony, never gates.

Any criterion violated, or uncertain → **full lane** (below). Uncertainty is full-lane; the triage
never guesses.

## Flow — full lane

Route through the pipeline in order; each step gates the next:

1. **`brainstorming`** (`{{PLUGIN_ROOT}}/skills/brainstorming/SKILL.md`) — refine `$ARGUMENTS` into a concrete spec by Socratic questioning: challenge
   vague language, surface hidden complexity, force trade-offs. Writes the spec to
   route-selected spec path. New full-lane work writes
   `{{PROJECT_DIR}}/.codearbiter/specs/<slug>.html` through the installed engine.
   A missing consequential decision is asked once, not converted into a general spec-approval gate.
2. **`writing-plans`** (`{{PLUGIN_ROOT}}/skills/writing-plans/SKILL.md`) — turn the maintained spec into coherent tasks, each with relevant paths and a
   verification that maps to a `tdd` obligation (it does not replace one). Writes
   matching route-selected plan path with bijective criterion↔task coverage.
3. **`executing-plans`** (`{{PLUGIN_ROOT}}/skills/executing-plans/SKILL.md`) — runs coherent batches through `subagent-driven-development`, directly or with useful agents. Reports real progress and check results; pauses only for explicitly requested checkpoints or real missing decisions.
4. **`commit-gate`** — the only path to a commit; nine gates, including behavioral proof.
5. **`finishing-a-development-branch`** — terminal step: open-PR / merge-via-PR / discard. Every
   change lands through a PR; never a direct write to the default branch.

The autonomous counterpart (`{{CMD:sprint}}`) maintains the same spec→plan but passes the full plan to
`subagent-driven-development` directly, without per-batch checkpoints. That path is its own entry,
not `/feature`.

## Scope routing

Scope suggests useful author skills (`backend-author`, `frontend-author`, `infra-author`), not mandatory one-agent-per-task dispatch. Run the affected local checks and preserve failures; exhaustive cross-area and cross-platform proof remains exact-head hosted CI before merge under `{{PLUGIN_ROOT}}/includes/verification-boundary.md`.

## When NOT to use

- A known defect with a reproduction → `/fix`.
- A behavior-preserving restructure → `/refactor`.
- A question or quick discussion → ask it directly; no command needed.
- Persisting work already written → `/commit`.

## Hard gate

MUST preserve testable intent and perform applicable checks before claiming completion. An unapproved artifact is not a denial of an already-authorized feature. MUST NOT take the small lane
unless every Step 0 criterion holds, and MUST log the classification to
`.codearbiter/triage.log` before `tdd` begins. MUST NOT skip `writing-plans` in the full lane.
MUST NOT guess consequential unresolved user decisions; keep the affected task visibly waiting.
MUST NOT restart an interrupted pipeline whose artifacts exist on disk — resume at the furthest
checkpoint per the Resume ladder, unless the user explicitly asks to start over.
