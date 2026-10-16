---
title: Review Specifications and Plans
description: "Inspect the working specification and plan, request scoped changes, and distinguish implementation progress from verification and delivery."
journey:
  level: Practitioner
  time: "15 min reading; review depends on scope"
  outcome: "An informed review of the actual requirements, execution plan, observed results and remaining decisions."
  prerequisites:
    - A feature or sprint draft to inspect, or the read-only product example
  proof: "You can distinguish requirements, planned verification, recorded progress and actual evidence, and request a scoped revision safely."
---

A specification defines the behavior being agreed to. Its plan connects that definition to tasks,
paths, dependencies and verification. **A plan is not a second independent requirements list.**
Start with the [read-only artifact workbench](/product-tour/#artifact-workbench) to inspect a real
native-rendered draft pair without installing or approving anything.

## Identify which kind of work you have

| Work | Expected form | Important boundary |
|---|---|---|
| Greenfield project planning | Three exact named Markdown documents under `.codearbiter/plans/` | Architecture, roadmap and project backlog, not feature execution artifacts |
| New full-lane feature or sprint | `specs/<slug>.html` and `plans/<slug>.html` under `.codearbiter/` | Uses the installed manifest-owned native writer |
| An existing Markdown feature pair | Its existing matching `.md` specification and plan | Remains authoritative on that exact legacy path; no implicit conversion |
| A small-lane change | Stated inline mini-spec and triage record | Does not require a new full HTML pair solely for consistency |

See [Plan a new project](/guides/plan-a-new-project/) for the first row and
[Build a feature](/guides/feature-lane/) for full-versus-small classification.
An unavailable native capability is a capability error for new HTML work, not permission to
quietly substitute Markdown or an arbitrary executable.

## Check your host's authority capability

The installed native writer validates content, preserves identity and performs recoverable writes.
The workflow checks its declared capability before artifact I/O. Ordinary authoring and task
progress use the existing user request; they do not require approval codes, context tickets or
reviewer receipts. Native writer support includes Pi; that fact alone does not qualify every live
host workflow.

Keep these boundaries distinct:

| Boundary | What to inspect |
|---|---|
| Artifact integrity | The installed writer, selected pair, current revision and successful save/readback |
| Work authorization | The user's requested scope, actual unresolved decisions, explicit stops and real host/tool permissions |
| Verification and review | What ran, the source and scope it examined, actual results, findings and missing evidence |
| Explicit attestation | The requested evidence claim and the exact host adapter and producer that support it |

Strict attestation is an on-demand evidence path, not a prerequisite for ordinary drafting or
implementation. If it is explicitly requested, use its supported host-owned producer and preserve
its actual limits; never manufacture a receipt or infer an event from a progress label. The owning
workflow loads that contract when needed. A writer installation or package inventory does not
prove a live approval capture, isolated review or verification run.

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

An incomplete draft can exist on disk. Readiness diagnostics expose missing structure or coverage;
they are not a second permission gate. A plan binding identifies the current specification, not
proof of implementation. Missing requirements remain visible while independent authorized work
can continue.

## Understand what your decision authorizes

Your feature or sprint request establishes the intended working scope. codeArbiter records the
requirements and plan, resolves consequential missing choices with their owner, and continues
without requesting separate artifact approval. Settled decisions remain settled after a session
restart or an in-scope plan revision.

Ask for a review pause when you want one: “Show me the revised empty-state behavior before
implementing it.” That pause is real. A change to the product outcome, unresolved architecture
decision or external side effect beyond the agreed scope needs the appropriate owner's decision.
A reversible implementation method or task decomposition can change with a recorded reason.

Requirements and plan agreement do not grant arbitrary spending, credential access, irreversible
changes, merge, publication or overrides. Existing host permissions and security controls still
apply. See the [sprint working agreement](/guides/autonomous-sprints/#inspect-the-durable-package)
and [owning sprint contract](/reference/commands/sprint/).

Academy lessons have their own declared review and verifier contract; do not substitute a
different ceremony into a pinned lesson.

A content hash establishes integrity, not the identity of a decision-maker. Record actual user
decisions honestly, keep the plan bound to the current specification, and inspect the affected
criteria when the definition changes. Agreement on requirements does not establish that code is
implemented, tests passed, a reviewer ran or a pull request was merged.

## Request changes, resume, or migrate

Ask the existing lane to revise the named artifact and explain its impact. Keep the old records
and IDs; retired items retain their reasons and are not silently recycled. Do not create a new
slug merely because a session ended. Use [Resume and recover](/guides/resume-and-recover/) when
execution or a transaction was interrupted.

Existing Markdown pairs stay in their original format. Explicit migration is a separate,
pair-aware operation: it creates drafts and retains exact legacy bytes for guarded rollback.
Migration does not establish new verification or review. Do not convert Academy fixtures for
visual consistency or edit one side of a pair independently. HTML plans cannot use `--farm`.

## Verify completion without guessing

Ask for current criterion coverage, task progress, checks actually run, required review results
and the commit/PR boundary. Typed `REVIEW` means implementation is ready; `DONE` means implementation
is reported complete. Neither proves passing tests, independent review or user acceptance.
Distinguish command-level results from named-test evidence, preserve failures and unrun checks,
and recheck results affected by changed source. A passing focused test does not replace the
required exact-head hosted CI before merge.

For protocol details, see the repository's
[format contract](https://github.com/arbiterForge/codeArbiter/blob/main/docs/artifacts/spec-and-plan-format.md)
and [migration/recovery contract](https://github.com/arbiterForge/codeArbiter/blob/main/docs/artifacts/migration-and-recovery.md).
Use the installed package's supported operations for writes and recovery; inspect uncertain
transaction state before retrying work.
