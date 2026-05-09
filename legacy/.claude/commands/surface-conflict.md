---
description: Stop work and surface a conflict between CLAUDE.md (or docs/) and on-disk code or instructions
argument-hint: "<short description of conflict>"
---

You have detected a conflict that you MUST NOT silently resolve. Surface it
now — do not write code, do not commit, do not refactor.

Produce a structured report:

1. **Conflict description.** What rule says one thing; what code (or what other rule, or what user instruction) says the opposite. Quote both verbatim with file paths and line numbers.
2. **Conflict-resolution hierarchy attempt.** Walk CLAUDE.md §0 levels in order. Identify the level at which the conflict resolves, OR state that it does not resolve within the hierarchy.
3. **Affected control families.** From `docs/security-controls.md` and `docs/agent-policy.md`, list which control families are implicated (e.g., SC-13, AU-9, IA-5).
4. **Required human decision.** A single yes/no or pick-from-options question for the human reviewer.
5. **Reversibility.** Note whether any code already on disk needs to be reverted, or whether this is purely a forward-decision question.

Then STOP. Do not proceed with the original task. Wait for human input via PR
comment with the literal text `Approved by <name> for <action>`.
