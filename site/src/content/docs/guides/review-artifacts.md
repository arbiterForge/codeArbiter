---
title: Review Specifications and Plans
description: "Find, inspect, request changes to, and approve the right specification and plan without confusing a browser view with workflow authority."
journey:
  level: Practitioner
  time: "15 min reading; review depends on scope"
  outcome: "An informed review of the actual requirements and execution plan, with the right format and authority boundary."
  prerequisites:
    - A feature or sprint draft to inspect, or the read-only product example
  proof: "You can distinguish requirements, planned verification, recorded evidence and current approval, and request a scoped revision safely."
---

A specification defines the behavior being agreed to. Its plan connects that definition to tasks,
paths, dependencies and verification. **A plan is not a second independent requirements list.**
Start with the [read-only artifact workbench](/product-tour/#artifact-workbench) to inspect a real
native-rendered draft pair without installing or approving anything.

## Identify which kind of work you have

| Work | Expected form | Important boundary |
|---|---|---|
| Greenfield project planning | Three exact named Markdown documents under `.codearbiter/plans/` | Architecture, roadmap and project backlog, not feature execution artifacts |
| New full-lane feature or sprint | `specs/<slug>.html` and `plans/<slug>.html` under `.codearbiter/` | Requires the installed adapter's qualified native artifact capability |
| An existing Markdown feature pair | Its existing matching `.md` specification and plan | Remains authoritative on that exact legacy path; no implicit conversion |
| A small-lane change | Confirmed inline mini-spec and triage record | Does not require a new full HTML pair solely for consistency |

See [Plan a new project](/guides/plan-a-new-project/) for the first row and
[Build a feature](/guides/feature-lane/) for full-versus-small classification.
An unavailable native capability is a capability error for new HTML work, not permission to
quietly substitute Markdown or an arbitrary executable.

## Check your host's authority capability

A native artifact engine and a host authority adapter do different jobs. The engine validates
content and transitions; the host adapter records an actual user prompt, verification run or
review event. Installing the engine alone does not provide every authority adapter.

The [current source contract](https://github.com/arbiterForge/codeArbiter/blob/d0a247f3a78d10b1fc2d0b2b823a58ec5c2a2e3f/core/surface/includes/artifacts.md)
distinguishes these implemented boundaries. This is not a release-to-release support guarantee:
check your exact installed adapter and its qualification evidence before execution.

| Host | Typed spec/plan approval | Typed verification and review authority |
|---|---|---|
| Claude Code | Host-observed prompt approval | Not supported; stop at this boundary |
| Codex | Host-observed prompt approval | Codex-only production adapters; exact installed capability still required |
| Pi | Not supported | Not supported; do not arm the prompt adapter |

These limits concern the typed HTML path, not every operation on those hosts. Existing Markdown
pairs retain their legacy workflow, and small-lane work remains inline. Do not change the lane
classification or replace a new HTML pair with Markdown to evade an unsupported boundary.

## Open the actual files

Ask codeArbiter to report the repository root, existing slug, exact file paths, format and current
workflow state. Open the reported HTML in your browser using the file manager. The standalone
document needs no JavaScript or network to be read. The visible document is generated from its
authoritative embedded typed model; normal machine reads validate the model and view together.

Opening a file does not approve, execute or mutate it. Do not edit the HTML or embedded JSON in a
text editor. Ask the existing feature/sprint workflow to make a typed revision, then review it
again. The internal artifact engine is not an additional public command to memorize.

## Review the specification before the implementation

For each acceptance criterion, check the caller, trigger, preconditions, observable outcome,
exclusions and failure behavior. Inspect the proposed verification oracle: what observation
would distinguish correct behavior from a plausible but wrong implementation?

| Weak requirement | More reviewable example |
|---|---|
| “Export saved searches correctly.” | “For a nonempty ordered collection, export a CSV with `name,query` headers and one row per saved search in input order.” |
| “Support unusual text.” | “Round-trip commas, quotes, embedded newlines and Unicode through a CSV reader without altering either field.” |
| “Handle empty state.” | “For an empty collection, return no export payload; do not create a header-only file.” |

These are illustrative requirements from the product-tour fixture, not an approval of your
project. Decide whether they fit your real caller and constraints. A valid schema cannot decide
whether requirements are true, sufficient or desirable.

A useful revision request is: “Keep the CSV scope. Make the empty-case behavior explicit, preserve
the existing criterion IDs, and return the changed criteria for review before implementation.”
Genuine unknowns should remain explicit, not be filled with invented results or requirements.

## Review the plan's relationship to those criteria

The specification owns stable acceptance-criterion IDs. The plan references them and owns tasks,
paths, checkpoints, dependencies and verification definitions. Coverage can be many-to-many:
one criterion can need several tasks, and one task can advance several criteria.

Check that every required criterion is covered and every task advances an agreed criterion.
A test command should name its working directory, expected outcome and required test, rather
than merely saying “run tests.” Ask what existing code or prerequisite it depends on, and whether
a failure would actually detect the intended defect.

An incomplete draft can exist on disk. Structural validity, readiness, approval and permission to
execute are different checks. A plan's `draft_preview` relationship does not authorize execution.

## Understand what your decision authorizes

Use the approval boundary presented by the owning workflow. A feature has spec and plan review
gates; a sprint reviews the linked pair as one package. For typed HTML, the current adapter arms
one artifact at a time. Review the named artifact, return the exact reply supplied by the host,
and require a fresh approved-gate check before the next transition. A generic “yes” or a reply
for another artifact does not approve this one. After spec approval, the plan must bind to that
approved definition and obtain its own current approval. One review package is not a promise of
one prompt or a receipt covering both documents.

Academy lessons have their own declared review and verifier contract; do not substitute a
different ceremony into a pinned lesson.

The trusted host observes the decision and binds it to exact content. The coordinator must not
manufacture a successful event or receipt. Generic editing cannot make an artifact approved. A displayed approval is not proof of authenticated actor identity, and a
hash is integrity evidence, not an identity check. Changing the normative definition can stale
its approval and downstream bindings; re-review the actual changed definition.

Approval of requirements is not a claim that code is implemented, tests passed, a reviewer ran,
or a pull request was merged. Look for each kind of evidence separately.

## Request changes, resume, or migrate

Ask the existing lane to revise the named artifact and explain its impact. Keep the old records
and IDs; retired items retain their reasons and are not silently recycled. Do not create a new
slug merely because a session ended. Use [Resume and recover](/guides/resume-and-recover/) when
execution or a transaction was interrupted.

Existing Markdown pairs stay in their original format. Explicit migration is a separate,
pair-aware operation: it creates drafts, transfers no old approvals, and retains exact legacy
bytes for guarded rollback. Do not convert Academy fixtures for visual consistency or edit one
side of a pair independently. HTML plans cannot use `--farm` while that qualification remains
closed.

## Verify completion without guessing

Ask for current criterion coverage, plan task and scope state, named-test evidence, required
review results, and the commit/PR boundary. A passing focused test or an `ACCEPTED` label alone
does not establish that all current evidence and bindings remain valid.

For protocol details, see the repository's
[format contract](https://github.com/arbiterForge/codeArbiter/blob/main/docs/artifacts/spec-and-plan-format.md)
and [migration/recovery contract](https://github.com/arbiterForge/codeArbiter/blob/main/docs/artifacts/migration-and-recovery.md).
They describe current source. Confirm the installed package's capability and release evidence
before applying a source-only feature to a deployed adapter.
