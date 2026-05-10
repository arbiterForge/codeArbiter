# /override "description of what is being overridden and why"

## Purpose

Explicitly override a codeArbiter gate or hard rule. Overrides are always logged, always visible, and never silent. This command implements the full override protocol from `AGENTS.md` §7. It does not bypass logging — using `/override` is a deliberate, traceable act.

## Usage

```
/override "skipping security-reviewer on ADR-0003 — reviewed manually by J. Smith on 2024-01-15"
```

The description MUST include:
- What gate or rule is being overridden
- Why the override is justified
- Who is authorizing it (a person, not "codeArbiter")

Vague overrides ("just skip it") are rejected — codeArbiter will ask for a specific justification.

## What Happens Step by Step

1. **Identity detection** — codeArbiter auto-detects the authorizing identity in this order:
   - `git config user.name` / `git config user.email`
   - Environment variable (e.g., `$OVERRIDE_IDENTITY` or `$USER`)
   - CLI session identity if available
   - Prompt: asks the user to confirm their name if none of the above resolves
2. **Override record written** — appended to `projectContext/overrides.log`:
   ```
   [YYYY-MM-DD HH:MM] <identity> — override: <what was overridden> — reason: <justification>
   ```
3. **Overridden action proceeds** — the specified gate or check is bypassed for this action only
4. **User notified** — codeArbiter confirms the override is logged and visible to reviewers

## Override Log Format

Each entry in `projectContext/overrides.log`:

```
[2024-01-15 14:32] Jane Smith (jane@example.com) — override: security-reviewer gate on /pr — reason: reviewed manually, see PR comment thread — authorized by: Jane Smith
```

## Hard Gates

- MUST write to `projectContext/overrides.log` before proceeding — the log entry is not optional
- MUST include an authorizing identity — "codeArbiter" or "automated" are not valid identities
- MUST include a justification — "because I said so" is not accepted
- The override is scoped to the immediate action only — it does not create a standing exception
- If the override involves a security-critical gate (auth, crypto, secrets): codeArbiter surfaces a warning before proceeding and asks for confirmation a second time

## Visibility

Override log entries are:
- Visible to all reviewers at the next `/checkpoint`
- Included in PR descriptions when the override affects a gate that `/pr` would normally enforce
- Permanent — entries are never deleted from `projectContext/overrides.log`

## When NOT to Use

- For routine work that passes all gates: never needed — gates exist for a reason
- For stage promotion: use `/stage N` (which has its own approval flow)
- For resolving a conflict between two sources: use `/surface-conflict` instead
