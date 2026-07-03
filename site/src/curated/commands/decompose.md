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
    when: at the end of the interview
    effect: the completion marker is written only once every required doc is present and non-empty
---

## What it does

This is the populator for a project that has no code yet to read. Rather than guessing at
architecture, it runs a long, structured interview — six layers covering purpose, scope, users,
vocabulary, and constraints — pushing back on vague answers and naming the complexity a quick answer
tends to hide. Because a real interview like this can span multiple sessions, every layer is saved as
it's completed rather than held in memory until the end, so a context reset or a closed terminal
doesn't cost you the earlier answers. Once all six layers are solid, the surviving documents get
written to the project's state directory and the project is marked initialized — only then does
normal operation resume.

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
[layers 2-6 continue across the session; each answer lands on disk as it's given]

All six layers complete. Writing tech-stack.md, coding-standards.md, security-controls.md, and the
rest of the doc set... CONTEXT.md marked initialized.
```

## When to reach for it

Reach for `/ca:decompose` on a genuinely greenfield project with `.codearbiter/` already scaffolded
by `/ca:init`. If source code already exists, `/ca:create-context` is the right populator instead.
