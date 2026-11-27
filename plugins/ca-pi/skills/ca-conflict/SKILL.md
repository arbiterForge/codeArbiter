---
name: ca-conflict
description: Pause affected work and its actual dependents when rules conflict. Present both sources and the dependency scope; the user resolves. Continue independent authorized work.
argument-hint: (none)
---

# /ca-conflict — conflict protocol

Orchestrator protocol, not a skill route. When governing sources contradict each other,
pause work whose authority, data or decision depends on that conflict. Record the
affected scope and present both sources for the user to resolve. The orchestrator
never picks a side. Continue independent authorized work, including independent
authorized mutations within its existing scope.

## Flow

1. **Bound the pause** — identify the affected task and actual dependents from their
   authority, data or decision dependencies. A shared security or authority rule
   can expand the affected scope across tasks. When a dependency is unknown, say
   `unknown`, pause the work that may rely on it, and inspect or ask the smallest
   consequential question. Do not invent a dependency graph or a universal stop.
2. **Identify** the conflicting sources (A and B): which document, file, or rule each is.
3. **Quote** the exact passages side by side.
4. **Classify** the conflict against the §2 conflict-resolution hierarchy and name the level the
   tension sits at. Note which source was more recently updated — informational, not determinative.
5. **Present** the affected scope, dependency reasons and independent work that can
   continue. Affected work resumes after the user resolves the conflict. Pass the
   same scope to any child, pause or revoke its affected delegation, and inspect
   uncertain child effects before replaying. An explicit global user or host stop remains global.

## Output

```
## Conflict detected: affected work paused

### Source A
File: <path> · Last updated: <date>
> <exact quoted text>

### Source B
File: <path> · Last updated: <date>
> <exact quoted text>

### Nature of conflict
<what the two sources disagree about>

### Conflict-hierarchy level
Level N — <why the tension sits here>

### Affected scope
<paused tasks and actual dependents; authority, data or decision dependencies;
shared security/authority effects; unknown dependencies and missing observation>

### Independent continuation
<independent authorized work and mutations that can continue; child scope updates>

### To resolve
<options — update A, update B, or supersede one via an ADR>

---
Affected work is paused pending resolution. Independent authorized work continues
within its existing authority. An explicit global user or host stop remains global.
```

## When routed automatically

The orchestrator surfaces a conflict on its own when the persona and a `.codearbiter/` doc contradict
each other, two docs contradict, code contradicts an accepted ADR, a new ADR contradicts an accepted
one, or a task instruction contradicts a hard gate.

## After resolution

The orchestrator records the resolution; if the user authorized a doc update, it makes that update
and resumes the affected work from its suspension point. Resolution does not
authorize unrelated changes, override an actual denial, or erase prior history.

## Hard gate

MUST pause the affected scope and actual dependents. MUST NOT pick a side without explicit user instruction. MUST NOT decide by
recency alone. MUST NOT silently continue affected work past a detected conflict. Allow independent authorized mutations
when no actual boundary prevents them; an explicit global user or host stop remains global. If the conflict involves a guessed
or auto-resolved `[CONFIRM-NN]`, flag that as a separate critical finding.
