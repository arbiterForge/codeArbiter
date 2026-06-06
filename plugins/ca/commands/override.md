---
description: Sanctioned, logged bypass of a gate or hard rule — one audit line, then proceed.
argument-hint: "<reason>"
---

# /ca:override — logged bypass

The sanctioned escape hatch. Bypass is permitted only with an audit log entry. Overrides are always
logged, always visible, never silent. Single identity, single confirm.

## Flow

1. Validate `$ARGUMENTS` — the reason MUST name the gate being bypassed and a justification. Reject a
   vague reason ("just skip it") and ask for a specific one.
2. Detect the operator identity from `git config user.email` only. If it is unset, ask the user once
   to state their identity for the log. (No platform ladder, no second confirmation.)
3. Append one line to `${CLAUDE_PROJECT_DIR}/.codearbiter/overrides.log`:

   ```
   [ISO-8601 timestamp] | BY: <email> | GATE: <gate bypassed> | REASON: <reason>
   ```

   The log is append-only — never edited or deleted, committed as a permanent audit artifact.
4. Proceed with the overridden action. Note in the response that the override is logged.

## Hard gate

MUST write the log line before proceeding — it is not optional. MUST capture an operator identity —
"codeArbiter" or "automated" are not valid. MUST include a justification. The override is scoped to
the immediate action only; it creates no standing exception. MUST NOT edit or delete an existing
`overrides.log` entry.

## When NOT to use

- Routine work that passes all gates — never needed.
- Reconciling two conflicting sources → `/ca:surface-conflict`.
