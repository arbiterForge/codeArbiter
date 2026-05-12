# /btw "question"

## Purpose

Lightweight Q&A about the project, codebase, architecture, or decisions. No skill is invoked. No routing table entry applies. No state changes. No side effects. Answer directly and conversationally.

## Usage

```
/btw "what does the audit-spec say about role changes?"
/btw "which trust zone does the frontend live in?"
/btw "why did we choose X over Y?"
/btw "what is the coverage threshold at Stage 1?"
```

The question can be anything about the project that doesn't require implementation or state change.

## What Happens

1. codeArbiter reads from `projectContext/` as needed to answer the question accurately
2. Answer delivered directly in the conversation
3. No skill invoked, no agent dispatched, no file written, no routing table entry applies
4. If the question reveals a gap in `projectContext/` (a question that can't be answered from existing docs): note the gap and suggest using `/adr` or `/status` as appropriate

## Key Behaviors

- **Conversational** — responses are direct and human-readable, not formatted as reports
- **Read-only** — `/btw` never modifies a file
- **No gates** — no hard gates apply; this command is always safe to invoke
- **Honest about gaps** — if the answer isn't in `projectContext/`, say so rather than guessing
- **Does not start implementation** — if the question sounds like it might be leading toward code, confirm with the user before routing to `/feature` or `/fix`

## What It Does NOT Do

- Does NOT invoke any skill
- Does NOT write or modify any file
- Does NOT run any tests or linters
- Does NOT engage any routing table entry
- Does NOT open a PR or commit anything
- Does NOT resolve `[CONFIRM-NN]` placeholders — those require `/adr` or `/surface-conflict`

## When NOT to Use

- To start implementing something: use `/feature` or `/fix`
- To check overall project status: use `/status`
- To check ADR health: use `/adr-status`
- To surface a conflict: use `/surface-conflict`
