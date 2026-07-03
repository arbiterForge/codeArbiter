---
entity: commands/init
related: [create-context, decompose]
gates:
  - gate: no overwrite
    when: every invocation
    effect: the scaffolder refuses to run if .codearbiter/CONTEXT.md already exists — it never overwrites existing state
  - gate: mandatory populator handoff
    when: right after scaffolding
    effect: the stub it creates is not usable on its own; it routes straight to create-context or decompose to actually fill it in
---

## What it does

This is how a repository opts into codeArbiter for the first time. It writes the root-level state
directory with the activation flag and a set of empty tracking files — nothing more. The `CONTEXT.md`
it creates is deliberately a stub, not a finished project doc, so the very next thing that has to
happen is populating it: an existing codebase routes to the brownfield scout that reads the code and
drafts the real docs, while a from-scratch project routes to the layered architect interview instead.
Until that populator runs and writes its own completion marker, the rest of the pipeline stays
blocked — `/ca:feature` and the other lanes need `tech-stack.md` and `security-controls.md` to exist
before they'll proceed.

## Usage

```
/ca:init | --stage N | --check
```

No arguments runs the scaffold at its default maturity stage; `--stage N` sets an initial maturity
value other than the default; `--check` reports the current state without writing anything.

## Example

```text
> /ca:init

Running the scaffolder against the repo root...
Created .codearbiter/CONTEXT.md (arbiter: enabled, stage: 1, stub body)
Created open-tasks.md, open-questions.md, overrides.log, last-checkpoint
Source code detected in this repo — routing to /ca:create-context to populate the stub.
```

## When to reach for it

Reach for `/ca:init` exactly once, on a repository that hasn't opted in yet. If `.codearbiter/`
already exists, this refuses and `/ca:status` shows the current state instead.
