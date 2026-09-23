---
entity: commands/decompose
related: [create-context, init, skills/decompose]
gates:
  - gate: greenfield check
    when: before the interview starts
    effect: any meaningful source code already in the repo redirects to create-context instead
  - gate: layer-by-layer persistence
    when: throughout the interview
    effect: each of the six layers writes to disk as it's answered, so closing the session mid-interview loses nothing
  - gate: initialization lock
    when: after explicit approval and project-state population
    effect: the completion marker is written only after all three planning documents are approved and every required populated doc is present and non-empty
---

## What it does

This is the populator for a project that has no code yet to read. Rather than guessing at
architecture, it runs a long, structured interview — six layers covering purpose, scope, users,
vocabulary, and constraints — pushing back on vague answers and naming the complexity a quick answer
tends to hide. Because a real interview like this can span multiple sessions, every layer is saved as
it's completed rather than held in memory until the end, so a context reset or a closed terminal
doesn't cost you the earlier answers. Once all six layers are solid, all three planning documents are written, reviewed, and explicitly approved
before project-state population and the initialization lock. Completing the interview alone
does not mark the project initialized.

## What you receive and approve

Decomposition writes three project-planning deliverables under `.codearbiter/plans/`:

| File | Job |
|---|---|
| `01-architecture-breakdown.md` | Components, boundaries, integrations and unresolved architectural choices |
| `02-phased-build-plan.md` | MVP, v1 and v2 outcomes, deferrals, risks and measurable completion |
| `03-task-backlog.md` | Prioritized, phase-grouped tasks, roles, dependencies and time-boxed spikes |

Open and review all three. Explicit approval of the complete set precedes project-state
population and the initialization lock. Later reconciliation locates these exact filenames;
they remain Markdown and are distinct from typed feature execution plans.

Use [Plan a new project](/guides/plan-a-new-project/) for preparation, examples, review criteria
and safe resumption. `init --greenfield` is the canonical strategy selector; this command remains
its compatibility entry.

## Usage

```
/ca:decompose
```

No arguments — the interview itself elicits everything it needs; you can hand it a summary at any
point if you already have one written down.

## Example

```text
> /ca:decompose

Switching to decomposition mode. Six layers, one question at a time — typically 60-110 questions
total, all persisted so you can pick this back up later.

Layer 1 — Purpose. What problem does this project solve, in one sentence?
> a scheduling tool for community garden plot signups

"Scheduling tool" is broad — walk me through one signup, start to finish: who initiates it, what do
they choose, what confirms it?
...
[layers 2-6 continue; each completed layer is persisted before the next begins]

All six layers complete. Writing the architecture breakdown, phased build plan and task backlog
under .codearbiter/plans/. Open and review all three; population waits for your approval.
[after explicit approval] Populating project context and confirming the initialization lock.
```

## When to reach for it

Reach for `/ca:decompose` on a genuinely greenfield project with `.codearbiter/` already scaffolded
by `/ca:init`. If source code already exists, `/ca:create-context` is the right populator instead.
