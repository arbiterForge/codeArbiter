---
name: decompose
description: Develop greenfield intent or initialized brownfield target and delta in existing decomposition and knowledge records.
argument-hint: (none)
---

# decompose

<!-- catalog-compatibility-notice:start -->
> Compatibility route. Prefer `/ca-init --greenfield` for new usage. This installed route remains
> functional under the command-route compatibility policy at <plugin-root>/includes/command-compatibility.md;
> continue with the greenfield workflow below.
<!-- catalog-compatibility-notice:end -->

Develop the project specification before implementation. Keep actual user decisions,
planned architecture and observed repository facts distinct. Load
`<plugin-root>/includes/knowledge.md` for the record vocabulary and the
`knowledge.py` verbs used below.

## Initialized brownfield acquisition

When source already exists and the user selects project-model acquisition,
preserve `<!--INITIALIZED-->`, the current context documents, existing
decomposition records, question history, ADRs, and work identities. Read those
owners index-first before asking or writing. Use the selected `context-check`
refresh for source-backed changes to the code map and other observed knowledge;
do not invoke the initial-population route, rerun `initialize`, or invent the
original interview. A denied or incomplete source inspection leaves its claim
unknown and does not erase independent existing records.

After reading the relevant decomposition records and checking their cited
sources, run `knowledge.py stale decomposition`. If it reports no baseline,
run `knowledge.py rebaseline decomposition` once after the check. Leave
deferred or unresolved records in their existing states; a baseline records
the checked source revision and does not answer them.

Add observed capabilities and architecture to the existing decomposition
document with `basis: source-observed` and actual source references. Distinguish
the current implementation from the intended target and delta: target
capabilities, future phases, and possible work are `proposed` until the user
decides. Link to the existing global open-question and ADR owners by identity;
do not make a second writable answer or acceptance status. A source file does
not establish historical rationale, deployment, passing tests, or an accepted
decision. Ask only consequential choices still unresolved after the saved
answers and current user direction are considered.

Save discovered gaps as decomposition `work_item` candidates. Do not call
`knowledge.py promote` or create an external issue merely because a gap was
recorded. When the user selects promotion, check the candidate's stable origin
against the selected work owner, including archived work, and retain the actual
returned `work_id`; a retry repairs the same link. Reinspect only affected
records on later source changes through `context-check`. Continue with
independent useful work when a separate choice remains open. Report the
selected records and remaining unknowns, then return to the requested work;
the greenfield interview and initialization steps below do not run on this path.

For an initialized project that keeps Markdown format, use the initialized
acquisition section in `<plugin-root>/routines/decompose/references/markdown-format.md`.
Do not silently convert. The numbered procedure below remains the greenfield
route for projects that have not been initialized.

## 1. Inspect and resume

Read `.codearbiter/CONTEXT.md` frontmatter. An initialized project returns to normal
operation; context changes use `/ca-context-check`. Meaningful implementation
source routes to `/ca-create-context`. If the scaffold is absent, run
`/ca-init` first. If `knowledge.py format` reports `markdown`, this is an older
scaffold: offer `knowledge.py convert`; read every returned Markdown section,
record its meaning, map each section ID to its saved record or note references
(`[]` only for `content=false`), then run
`knowledge.py convert --finish <token> --coverage @checklist.json` (the
transaction retains the original bytes). If the
user keeps the Markdown format, load
`<plugin-root>/routines/decompose/references/markdown-format.md` and follow that
unchanged procedure instead of this one; never convert silently.

Run `knowledge.py create-missing`, then `knowledge.py read decomposition`. Existing
`question` records with `status: answered` are settled: do not ask them again or
require another approval of unchanged answers. Resume with the open question that
matters most for what the user wants to do next, not a fixed first-unfinished
step. An explicit restart retires earlier records with a reason; it never deletes
them.

## 2. Capture the interview

Explain briefly that you will establish scope, architecture and a build sequence.
Ask focused questions only where existing answers do not establish the needed facts
or choices. Cover these areas, in whatever order the conversation makes natural;
record an inapplicable area with its reason:

| Area | Outcomes to capture |
|---|---|
| Vision | Problem, primary users, demonstrable success and exclusions. |
| Flows | User journey, non-human actors, failure experience and privilege boundaries. |
| Functional scope | Capabilities with initiators, inputs and outputs; MVP/v1/later; hardest user-facing risk. |
| Technical shape | Components and ownership, entities, state/write paths, stack and hard constraints, technical risks, copyright holder, release intent. |
| Integrations | External dependencies, contracts and authentication, ownership, reliability, cost and fallback. |
| Risks | Material risks with mitigations, open questions, bounded spikes and architecture-change triggers. |

Record each question as a decomposition `question` record when you ask it
(`status: open`) and update it with the user's actual answer
(`status: answered`, `basis: user-reported`) as soon as it is given, so a closed
session loses nothing. A deferral is `status: deferred`, not an answer. Exclude
secret values.

Record a user-decided architectural choice through `decision-lifecycle` at
`<plugin-root>/routines/decision-lifecycle/SKILL.md`; it owns ADR numbering,
attribution and status. Link the ADR from a decomposition `decision` record. Keep
draft choices as `proposed` until the user actually decides; do not create an ADR
merely to fill a quota.

Release intent is elicited here: capture the **tag prefix** preference and
**changelog kept** yes/no under technical shape. No `.codearbiter/release-targets.md` row is ever written by this skill.
Greenfield runs before any manifest or tag exists. `/ca-release` or a subsequent
context refresh derives a target from the actual manifest and delivery structure.

An unresolved consequential choice blocks only the output that depends on it.
Continue with independent areas.

## 3. Synthesize and confirm

From the answered questions and linked ADRs, add decomposition records:
`capability` (what the product does), `component` (intended parts, responsibilities
and connections), `phase` (MVP and later phases with measurable completion) and
`work_item` (bounded tasks with roles, dependencies and time-boxed spikes). Link
each to the questions it rests on in `related_refs`. These describe intended
architecture; they never claim code exists.

Show the user the synthesized records. Apply corrections with `update`; a wording
or method refinement does not need a fresh confirmation. Record the user's actual
confirmation as an answered question. Proceed when the records match the user's
choices and every remaining gap is an open question.

## 4. Populate context

Add knowledge records for what is known now:

| Document | Content |
|---|---|
| `project` | Identity, purpose, users, scope and exclusions. |
| `tech-stack` | Intended runtime, frameworks and tooling. A command without a real manifest is a `command` record with `basis: proposed` and `run_state: unrun`. |
| `coding-standards` | Confirmed structural and style conventions; copyright holder. |
| `security-controls` | Trust boundaries, authentication requirements, secret handling and prohibited primitives. Scope blocks for migrations, CI and deploys stay in `security-controls.md`. |
| `code-map` | Leave it empty or state that no implementation paths exist yet: the code map records observed code, and intended components live in decomposition. |

Leave unknowns as `unknown` records rather than inventing facts. Preserve
`CONTEXT.md` frontmatter exactly; the scaffold owns activation and stage.

Promote each approved `work_item` with `knowledge.py promote <WORK-ID>`. It adds the
task through the task board's own writer and is safe to repeat. Never write task
rows directly or mark planned work done. Record unresolved questions that need the
user's later decision on `open-questions.md` as well, keeping its history. Preserve
`overrides.log`, `last-checkpoint` and all ADR history.

## 5. Initialize and return to work

Run `knowledge.py initialize`. It checks that the knowledge documents exist and
parse and that the task board is well formed, then adds the standalone
`<!--INITIALIZED-->` marker to `CONTEXT.md`. Open questions do not prevent it.
A refusal names the document to repair; never append the marker manually.

Report the populated context, open questions and any actual checks, then continue
authorized work. Initialization records population; it does not certify host
enforcement, semantic review or passing tests.

When source and manifests arrive, `/ca-context-check` adds what the code
actually contains to the code map and reconciles intended and implemented facts,
keeping the interview records.
