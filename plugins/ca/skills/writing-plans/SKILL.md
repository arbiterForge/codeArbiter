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

For a new full-lane HTML spec, use the installed structured-artifact engine and
load `${CLAUDE_PLUGIN_ROOT}/includes/artifacts.md`. Read the source through typed
`index`, `outline`, and symbol-scoped `read`, not rendered HTML. Retain the
source's exact artifact ID and normative digest. `_preflight_plan_authoring`
checks the current source identity, structural validity, and same-slug target.
It does not require spec approval, a reviewer adapter, or a source snapshot.
`draft_for_pair` is a compatibility keyword, not a separate permission mode.

Create `.codearbiter/plans/<slug>.html` as `draft_preview` and use `plan-bind`
when selecting or refreshing its source binding. A genuine existing approval may
remain historical provenance; do not manufacture one. This path must not create
`.codearbiter/plans/<slug>.md` or a second criterion ledger. An existing `.md`
source remains on its legacy path without automatic conversion. Use its same
format for the plan and preserve human edits and references.

Check the installed capability before writing. A missing or invalid payload
means the artifact write did not happen; it must not fall back to Markdown.
Report the repair needed and continue safe, already-authorized investigation
where useful. Never report a failed or unsaved artifact as saved. A duplicate,
mixed-format, or missing source needs reconciliation, not an invented substitute.
HTML `--farm` dispatch remains disabled.

Read relevant project context and the build/test commands in
`${CLAUDE_PROJECT_DIR}/.codearbiter/tech-stack.md`; use
`${CLAUDE_PROJECT_DIR}/.codearbiter/coding-standards.md` for applicable conventions.
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

Do not call `_approvallib._preflight_plan_verification`, `arm-sprint`, or any
approval/prerequisite adapter merely to author or maintain this plan. Do not
freeze every test invocation, task boundary, or method as a new user decision.
Changes within the agreed outcome can update steps, task decomposition, checks,
and dependency-valid order with a concise reason. A material outcome change must
remain visible and goes to its actual decision owner.

Read back the saved identity and affected symbols. Return the plan location,
useful next work, actual unresolved choices, and outstanding checks to the active
caller. Distinguish implemented progress from verified behavior; a plan or a
`DONE` label is not test, review, or release evidence. Keep unrelated progress
when correcting the plan, and do not restart brainstorming after an interruption.

For legacy Markdown, retain its single task/status ledger and state verification
separately in that document. Do not reinterpret old `ACCEPTED` text as fresh
verification or convert formats as a shortcut. Preserve genuinely requested
checkpoints while removing duplicate artifact permission ceremonies.

## Explicit legacy farm requests

For a requested Markdown `--farm` workflow only, retain the existing backend
boundary in `${CLAUDE_PLUGIN_ROOT}/includes/farm.md` and the package contract in
`${CLAUDE_PLUGIN_ROOT}/skills/writing-plans/references/farm-plan.md`. Confirm its actual
prerequisites, including the required provider credential, without reading or
printing credential contents. No farm canary, model dispatch, or new spending
is implied by ordinary plan authoring. HTML farm remains disabled; do not
silently select another backend. Preserve the requested provider and budget.

Retain real out-of-scope follow-ups using `${CLAUDE_PLUGIN_ROOT}/includes/harvest.md`
when relevant. Do not turn routine drafting into an additional audit program,
mandatory reviewer chain, or repeated approval interview.
