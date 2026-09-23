---
title: Project Knowledge and Change Artifacts
description: "Understand the different jobs of project plans, feature specifications, execution plans, task boards, decisions and evidence."
journey:
  level: Foundation
  time: "8 min"
  outcome: "Find the record that answers the question instead of treating every file called a plan as the same thing."
  prerequisites: []
  proof: "You can distinguish project direction, agreed behavior, execution state, accepted decisions and verification evidence."
---

codeArbiter's durable records have different jobs. Their shared directory does not make them
interchangeable. For example, checking an item on a task board does not approve requirements,
and accepting an architectural choice does not establish that code implements it.

| Record | Question it answers | Owning path |
|---|---|---|
| Project context and policy | What is this repository, and which constraints apply? | Initialization and source-backed context maintenance |
| Greenfield architecture breakdown | What components and integrations should exist, and who owns them? | Decompose's `01-architecture-breakdown.md` |
| Greenfield phased build plan | What useful outcomes belong in each phase? | Decompose's `02-phased-build-plan.md` |
| Greenfield task backlog | How is project-level work prioritized and dependent? | Decompose's `03-task-backlog.md` |
| Feature specification | What observable behavior is being agreed to? | The feature/sprint specification |
| Execution plan | Which tasks, paths, dependencies and verification advance those criteria? | The plan derived from that specification |
| Task board | What work is queued, started or done at the board level? | The task command and its protected writer |
| ADR and decision ledger | Which durable choice was accepted, by whom, and what supersedes it? | The decision lane |
| Verification, review and audit records | What was observed or recorded, against which work? | The relevant verifier, reviewer or audit-producing lane |

## One example at two scales

A saved-search application might have a project roadmap covering local search, export and later
sharing. Its project backlog can allocate days to each capability. Selecting export for a feature
produces a much narrower specification: output rows, quoting behavior and the empty case.
Its execution plan maps those criteria to concrete implementation and tests.

Changing the project roadmap is not the same action as accepting a feature task. Likewise, the
three greenfield Markdown files are not old feature documents to convert automatically.
[Plan a new project](/guides/plan-a-new-project/) explains their review and reconciliation role.

## Format and authority are separate

New full-lane feature/sprint work uses typed HTML when the installed package has its qualified
native capability. Existing Markdown pairs stay authoritative in their own format, and small-lane
work remains inline with a triage record. The [review guide](/guides/review-artifacts/) explains
how to inspect each without creating a second authority.

The native engine is not a substitute for a host authority adapter. Prompt approval, verification
and review have different [per-host capability boundaries](/guides/review-artifacts/#check-your-hosts-authority-capability).
Shared files and entry syntax do not establish that a host can complete the whole typed workflow.

The typed model is authoritative; the visible HTML is its generated view. Stable criterion IDs
belong to the specification and are referenced by the plan. A browser view, matching hash, valid
schema, approval record, passing test and completed PR establish different things. None should
be silently substituted for another.

Use [Return to a project](/guides/return-to-a-project/) to locate the next action and
[Resume and recover](/guides/resume-and-recover/) when current state is uncertain.
For file-by-file ownership, see [the directory reference](/codearbiter-directory/).
