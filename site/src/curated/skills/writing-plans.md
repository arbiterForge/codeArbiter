---
entity: skills/writing-plans
related: [commands/feature, commands/sprint, brainstorming, executing-plans]
gates:
  - gate: criterion coverage
    when: before execution is authorized
    effect: every required criterion must be covered and every task must advance agreed criteria; readiness and approval are separate from draft existence
---

## What it does

Writing-plans connects a specification to executable work: tasks, exact paths, dependencies,
checkpoints and concrete verification. The existing feature or sprint coordinator owns the
handoff. This skill does not implement code.

## Draft, readiness and approval

For new full-lane typed work, the specification owns stable acceptance-criterion IDs. The plan
references those existing IDs rather than minting a second criterion list. Its `draft_preview`
binding allows a draft to be inspected; it is not authority to execute.

A structurally valid draft may still be incomplete. Readiness checks required content and
coverage; the owning workflow then establishes the required approval and exact-content binding.
Coverage is bidirectional and can be many-to-many, not a one-to-one mathematical bijection.

Existing Markdown pairs remain on their exact legacy route. Do not retroactively impose the
HTML lifecycle on an in-progress Markdown plan or migrate just one file.

## What to review

Check that every task names its affected paths, criterion references, dependencies and
verification. A verification definition should identify the command's working directory,
required test and expected observation. Reject a task that adds unrelated scope or relies on an
invented command or result. Ask for unresolved prerequisites to remain explicit.

## Exits

The coordinator advances only after the relevant readiness, approval and binding gates. It
selects the attended or autonomous execution path and retains the existing test and review
boundaries. An incomplete draft is not made executable merely by writing it to disk.

[Review specifications and plans](/guides/review-artifacts/) shows the human review procedure;
[Resume and recover](/guides/resume-and-recover/) covers stale bindings and interrupted work.
