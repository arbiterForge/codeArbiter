---
entity: commands/create-context
related: [decompose, init, skills/context-creation]
gates:
  - gate: brownfield check
    when: before scouts are dispatched
    effect: meaningful source code must already exist; a project with none redirects to decompose instead
  - gate: parallel scout dispatch
    when: after the pre-flight check
    effect: several read-only scouts each cover one slice of the codebase, returning file paths, line numbers, and named values only — never raw code or secret values
  - gate: initialization lock
    when: after the gap interview
    effect: the completion marker is written only once every gap is either resolved or explicitly deferred
---

## What it does

This is the populator for a project that already has code to read. Instead of interviewing you about
architecture that's already decided, it dispatches several scouts in parallel to read different
slices of the repository — dependencies, infrastructure, and so on — and each one reports back
structured findings rather than raw excerpts. Those findings get synthesized into a draft of the
project's state documents, and whatever the scouts couldn't determine on their own becomes a short,
targeted set of questions instead of a full interview. Once every gap is answered or explicitly
deferred, the documents are finalized and the project is marked initialized.

## Usage

```
/ca:create-context
```

No arguments — the skill reads the repository itself and only asks about what it can't determine
from the code.

## Example

```text
> /ca:create-context

Existing source detected (Express API + React frontend). Beginning scout-based extraction.
Dispatching 6 scouts in parallel: tech stack, infrastructure, domain vocabulary, testing conventions,
security surface, existing conventions...
[scouts report back: file paths, line numbers, named values]

Synthesis complete. Two gaps the scouts couldn't resolve from code alone:
  1. Is there a staging environment, or just local and prod?
  2. Who are the two user roles referenced in permissions.ts — admin and... ?
> staging exists at staging.example.com; the second role is "billing-admin"

Writing tech-stack.md, security-controls.md, coding-standards.md, CONTEXT.md...
CONTEXT.md marked initialized.
```

## When to reach for it

Reach for `/ca:create-context` on an existing codebase with `.codearbiter/` already scaffolded by
`/ca:init`. For a project with no meaningful source yet, `/ca:decompose` is the right populator.
