---
title: Project Knowledge and Change Artifacts
description: "Understand what each project record owns, how a specification binds its plan, and why readable HTML, approval, verification and delivery are different claims."
journey:
  level: Foundation
  time: "Read and inspect an example"
  outcome: "Find the authoritative record for a question and distinguish project direction, requirements, execution state and evidence."
  prerequisites:
    - Read the Concept Map
  proof: "You can locate a governing definition, its planned verification and its actual evidence without treating a filename or checkbox as approval."
---

A conversation can say that a feature is finished without leaving enough information to resume it,
review it, or explain the decision later. codeArbiter uses durable records so that project knowledge,
agreed behavior, planned work and observed results have identifiable owners.

An **artifact** is a retained work product. Some artifacts define intended behavior; others record
decisions or observations. Their shared directory does not make them interchangeable. A task-board
status does not approve requirements, and an accepted architecture decision does not establish that
code implements it.

## Start with the question, not the extension

**Project context and policy answer “what repository is this?”** They describe the domain, stack,
commands, conventions and security constraints the work must respect. Source-derived knowledge can
become stale; [provenance and drift](/concepts/provenance-drift/) explains how that is surfaced.

**Project architecture and roadmap answer “what are we building over time?”** Greenfield
decomposition produces three deliberately different guiding documents, described below. They are
not a feature specification split into three files.

**A feature specification answers “what behavior is agreed?”** Its acceptance criteria should make
correct and incorrect behavior distinguishable. Exclusions and failure cases prevent an author from
filling a gap with an attractive but unauthorized design.

**An execution plan answers “which work advances that behavior?”** It owns tasks, paths,
dependencies, checkpoints and verification definitions. Its criteria references point back to the
specification. A plan is not a second independent requirements ledger.

**The task board answers “what work is queued or assigned?”** The task command owns its transitions.
A board item can refer to a feature or follow-up without establishing current plan acceptance.

**Decisions and evidence answer different historical questions.** An ADR records a durable choice
and its attribution. Verification records describe an actual observation against specific work.
Review records describe what was inspected and found. Audit output assembles available records for
a window; it does not retroactively manufacture missing evidence.

## The three greenfield documents

The [decompose procedure](/guides/plan-a-new-project/) writes these exact files under
`.codearbiter/plans/` before requesting their review:

### `01-architecture-breakdown.md`

This describes components, responsibilities, integrations and unresolved architectural questions.
The human review asks whether the boundaries represent the intended system. For a saved-search
application, it might distinguish the interface, search storage and export boundary. Omitting the
export boundary here is a project-design issue, not a failed CSV unit test.

### `02-phased-build-plan.md`

This organizes useful outcomes into MVP, v1 and v2 phases, with included and deferred work,
risks and measurable definitions of done. A reader should be able to challenge why export is in one
phase and sharing is deferred. A phase is broader than an implementation task.

### `03-task-backlog.md`

This turns project direction into prioritized work with dependencies, roles and bounded
investigations. It helps decide what to undertake next. It is not the authoritative task-state
model of every feature subsequently implemented.

The user reviews all three before context population proceeds. Later reconciliation matches their
exact filenames against project context and prior decisions. Renaming them for visual consistency
or converting them to HTML would change that contract. Brownfield context creation follows a
different source-inspection path; it does not require inventing these three greenfield records.

## One example at two scales

At the project scale, “export saved searches” is one capability among search, export and sharing.
The architectural breakdown identifies its place, the phased plan identifies when it matters,
and the project backlog identifies dependencies and uncertainty.

At the change scale, the export specification makes the actual behavior reviewable: `name,query`
headers, input-order preservation, correct round-tripping of unusual text, and a deliberate empty
case. Its execution plan maps those criteria to concrete implementation and verification. Several
tasks can contribute to one criterion; one task can advance several criteria.

Inspect the [native-rendered draft example](/product-tour/#artifact-workbench) and
[worked feature](/guides/first-feature/). They show the artifacts at change scale. Their illustrative
project story and local fixture tests are not approval or execution evidence for your own project.

## Format and authority are separate

**New full-lane feature/sprint work uses typed HTML when the installed package has the qualified
native capability.** Each document contains an authoritative typed model and a deterministic
readable view. Normal machine reads validate their agreement. The file can be opened offline
without JavaScript; opening it does not approve or execute anything.

**Existing Markdown pairs stay on their exact legacy path.** Their continued use is a deliberate
compatibility boundary, not a reason to silently migrate them. A mixed or duplicate pair requires
resolution, not a guessed authority.

**Small-lane work uses a confirmed inline mini-spec and triage record.** It does not need a full
HTML pair solely to make the folder look uniform. The classification conditions, not aesthetic
preference, determine that path.

**Greenfield Markdown remains project-level planning.** It is not an old typed feature pair awaiting
conversion. These four cases differ in scope and lifecycle as well as file format.

The native engine validates structure, identity, relationships and allowed transitions. The
installed host authority observes the applicable approval, review or verification events.
**The native engine is not a substitute for a host authority adapter.** Shared paths or command
spellings do not establish equal support. Check the
[host-authority boundary](/guides/review-artifacts/#check-your-hosts-authority-capability)
for the exact installed adapter; this concept explanation is not a release qualification.

## Six claims that should never collapse into “done”

A **readable document** can be inspected. A **valid model and matching view** have the required
structure and integrity. Neither claim decides whether the requirements are adequate.

An **approved normative definition** has the applicable current approval bound to that content.
Changing its normative content can stale approval and downstream plan bindings. A hash supports
integrity; it does not authenticate the human actor by itself.

A **verification definition** says what should be run. A **verification result** records what was
actually observed. Planned commands and copied successful output are not interchangeable.

**Task review and scope acceptance** have different boundaries. On the typed path, task `REVIEW`
is provisional until the required current task evidence and combined quality review support
whole-scope acceptance. A displayed status is not permission to hand-edit the transition.

An **open PR** proposes integration. A **merged PR** and a **published release** require additional
independent facts. None follows merely because a browser view or task board looks complete.

## Inspect the relationship in a real repository

Find the exact selected specification and plan through the owning lane. Ask which criterion IDs
the next task advances, which paths it changes, which test would distinguish failure from success,
and which dependencies or approvals currently permit it to run.

Then compare planned verification with actual evidence. A command in a plan is not a past run.
An observation from an earlier source revision is not automatically current. An incomplete draft
is useful to review, but it must not be presented as executable work.

Request changes through the existing artifact-owning procedure instead of editing the generated
HTML or embedded JSON. Preserve IDs and the actual selected pair. After an interruption, use
[Resume and recover](/guides/resume-and-recover/); uncertain transaction state requires inspection,
not a new slug that hides the old work.

The [artifact review guide](/guides/review-artifacts/) makes these checks executable.
[Return to a project](/guides/return-to-a-project/) connects the records to the next action, and
[the directory reference](/codearbiter-directory/) identifies file-by-file ownership.
