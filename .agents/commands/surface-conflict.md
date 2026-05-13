<!--
Copyright (c) 2026 suadtl
Author: suadtl
Created: 2026-05-10
File: surface-conflict.md
-->

# /surface-conflict

## Purpose

Stop ALL other work immediately and surface a conflict between two sources of truth. Used when `AGENTS.md`, a `${PROJECT_ROOT}/.agents/projectContext/` document, and code contradict each other, or when two `${PROJECT_ROOT}/.agents/projectContext/` documents contradict each other. codeArbiter does not pick a side — it presents both positions and waits for the user to resolve.

## Usage

```
/surface-conflict
```

Typically invoked automatically by codeArbiter when it detects a conflict mid-task. Can also be invoked manually by the user when they spot a contradiction.

## What Happens

1. **All other work halts immediately** — the in-progress task is suspended
2. codeArbiter identifies the two (or more) conflicting sources:
   - Source A: which document, file, or rule
   - Source B: which document, file, or rule
3. Quoted passages from each source are presented side by side
4. Recency check: which source was more recently updated (file modification date or commit date)
5. Conflict presented to user in structured format (see below)
6. **Work does not resume until the user explicitly resolves the conflict**

## Output Structure

```
## Conflict Detected — work halted

### Source A
File: <path>
Last updated: <date or commit>
Relevant passage:
> <exact quoted text>

### Source B
File: <path>
Last updated: <date or commit>
Relevant passage:
> <exact quoted text>

### Nature of conflict
<One paragraph describing exactly what the two sources disagree about>

### Recency
<Source A / Source B> is more recently updated.

### What is needed to resolve
<Options the user has — e.g., update Source A, update Source B, or create an ADR that supersedes one of them>

---
Work is halted. Please resolve this conflict before codeArbiter proceeds.
```

## Hard Gates

- MUST stop ALL other work — no partial progress on the suspended task
- MUST NOT pick one source over the other without explicit user instruction
- MUST NOT guess which source is correct based on recency alone — recency is informational, not determinative
- MUST NOT silently continue if a conflict was detected — surface it every time
- If the conflict involves a `[CONFIRM-NN]` placeholder that has been guessed or auto-resolved: flag that as a separate critical finding

## When This Is Routed Automatically

codeArbiter invokes `/surface-conflict` automatically when:
- `AGENTS.md` and a `${PROJECT_ROOT}/.agents/projectContext/` document contradict each other
- Two `${PROJECT_ROOT}/.agents/projectContext/` documents contradict each other
- Code contradicts an accepted ADR
- A new ADR being authored contradicts an existing accepted ADR
- An instruction in the current task contradicts a hard gate in `AGENTS.md`

## After Resolution

Once the user explicitly resolves the conflict (e.g., "update Source A to match Source B" or "Source B is wrong, ignore it"):

1. codeArbiter records the resolution decision
2. If a document needs updating, that update is made (read: this is a side effect the user explicitly authorized)
3. Work resumes from where it was suspended
