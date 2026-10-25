---
name: writing-plans
description: Turn the selected specification into a maintained implementation plan with clear outcomes, useful tasks, dependencies, and verification steps. Drafting uses the existing authorization and does not require artifact approval codes, reviewer receipts, or a frozen implementation script.
disable-model-invocation: true
---

# writing-plans

Produce the plan for the active feature or sprint, then return it to that caller.
Do not execute implementation from this skill. Use the user's existing direction;
ask only about a consequential unresolved outcome, not permission to maintain the
plan. An explicitly requested human checkpoint still belongs to the caller.

## Select the source and representation

Load `<plugin-root>/includes/artifacts.md` for artifact I/O. Read the selected
specification's criterion records and retain its artifact ID and normative digest.
For HTML, `_preflight_plan_authoring` checks that identity, structural validity,
and the same-slug target. Create the matching plan as `draft_preview`; use
`plan-bind` when selecting or refreshing its specification binding. Preserve human
edits and stable references in the selected representation.

Read relevant project context and the build/test commands in
`<project-root>/.codearbiter/tech-stack.md`; use
`<project-root>/.codearbiter/coding-standards.md` for applicable conventions. In an
HTML-knowledge repository `knowledge.py relevant <paths>` returns both
(`<plugin-root>/includes/knowledge.md`).
Missing optional orientation is not a new permission gate. Identify a genuinely
missing requirement or command contract instead of guessing it.

## Build useful tasks

Start with the specification's intended outcome and criterion IDs. Check coverage
in both directions: each required criterion has planned work, and each task serves
the agreed outcome. Agreement between a plan and its criterion list does not
prove that either captures every part of the user's intent. Inspect relevant
source and ask what would still be wrong if all listed criteria passed. Record
actual gaps; do not repeat an interview the caller has already resolved.

Each task should describe a coherent unit of work: stable ID, intended result,
relevant paths, referenced criteria, an implementation approach, dependencies,
and the appropriate check or observable completion condition. Choose task size
for useful implementation and review, not a compulsory two-to-five-minute limit.
A small related change does not need its own author/reviewer lifecycle. Split
work when it has separate outcomes, dependencies, or independently useful progress.

**Design-drift guard.** Decomposition splits decided work; it never designs. If splitting surfaces a
material solution choice the spec does not decide — two or more materially plausible approaches the
spec leaves open, or a step that would contradict the spec's recorded SMARTS rationale — STOP and
never pick, score or SMARTS-evaluate it here. Route the undecided choice back to the owning design
workflow, `brainstorming` (`<plugin-root>/routines/brainstorming/SKILL.md`), and resume planning only
once the spec records the decision. A choice the spec already decides, or a trivial local
implementation detail with no material solution choice, is not drift.

Use real repository commands or an explicitly described observable check. A test
file or case that this task will create may not exist yet. An unsupported named
result parser is not a reason to reject the plan or invent test outcomes; a
command-level result must not be claimed as proof of individual named tests.
Read relevant command definitions without executing anything merely to author a
plan. Runner support and actual execution are checked when that check is needed.

Separate prerequisites that can be observed from choices only the user can make.
For typed prerequisites, use `kind: fact` or `kind: decision` and explicit
`task_refs` for affected tasks. Do not guess that an old unscoped prerequisite
applies to every task, or narrow a real shared dependency to hide it. Observable
facts use ordinary authorized tools and the engine's reported-observation path.
A consequential unresolved choice gets a clear normal-language question, not an
approval digest or a certification code.

For source impact without a repository-wide dependency analysis, record
`shared_inputs` only where the task genuinely depends on a common source
interface, fixture, schema or unusual build configuration. These must be
portable repository-relative paths to actual source, not generated artifact
state; a directory path includes its bounded descendants. A known shared
input change should refresh the affected check, not every unrelated review.
Do not invent references or claim an exhaustive dependency graph; missing
or unbounded inputs remain honestly `unassessed` in task context.

Order tasks by their actual dependencies. Remove cycles by fixing the plan, not
by pretending a required predecessor is complete. Group meaningful batches with
clear outcomes; checkpoints organize implementation and do not independently
create user approval requests. Keep genuinely blocked work visible while allowing
independent work to proceed. Identify the smallest useful delivery outcome without
splitting a promised atomic migration or compatibility change across releases.

## Save, inspect, and maintain

For HTML, use typed `create` and `apply` operations with current identity and CAS.
Preserve the specification's criterion IDs, task references, reasons, and history.
Drafts may be incomplete. Use `validate` with `gate: ready` to discover omissions;
its diagnostics describe the plan, not whether an already-authorized agent may
continue useful work. Structural errors or a conflicting write remain actual
operation failures. Do not fill missing fields with fabricated evidence to make
validation green.

Maintain the plan under existing authorization without extra artifact approvals
or freezing each method or check as another decision. Update in-scope steps,
tasks, checks and valid dependencies with a reason; material outcome changes
go to their actual decision owner.

Read back the saved identity and affected symbols. Return the plan location,
useful next work, actual unresolved choices, and outstanding checks to the active
caller. Distinguish implemented progress from verified behavior; a plan or a
`DONE` label is not test, review, or release evidence. Keep unrelated progress
when correcting the plan, and do not restart brainstorming after an interruption.

Existing Markdown retains one ledger and its original representation.
Never infer a passing check from an old status or duplicate approval prompts.

## Explicit farm requests only

For a user-selected Markdown `--farm` workflow, use
`<plugin-root>/includes/farm.md` and
`<plugin-root>/routines/writing-plans/references/farm-plan.md`. Preserve the
requested provider/budget and actual credential boundaries. Do not read
credential contents or trigger model spending during ordinary authoring.
HTML farm is disabled; never silently change backends.

Retain real out-of-scope follow-ups using `<plugin-root>/includes/harvest.md`
when relevant. Do not turn routine drafting into an additional audit program,
mandatory reviewer chain, or repeated approval interview.
