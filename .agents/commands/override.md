# /override "reason"

## Purpose

Sanctioned escape hatch from a codeArbiter gate or hard rule. Bypass is permitted
only with mandatory audit logging. Overrides are always logged, always visible,
never silent. Using `/override` is a deliberate, traceable act.

## Usage

```
/override "skipping security-reviewer on ADR-0003 — reviewed manually by J. Smith on 2024-01-15"
```

The description MUST include:
- What gate or rule is being overridden
- Why the override is justified
- Who is authorizing it (a person, not "codeArbiter")

Vague overrides ("just skip it") are rejected — codeArbiter will ask for a specific
justification.

## Routes To

Override protocol implemented in this command body (no skill). Reads/writes
`.agents/projectContext/overrides.log`.

## Identity Detection (in priority order — never ask if any succeeds)

1. `git config user.email` and `git config user.name` — always try first
2. `GITHUB_ACTOR`, `GITEA_TOKEN`, `GITEA_ACTOR` environment variables
3. GitHub CLI: `gh auth status` — extract logged-in username
4. If ALL detection fails → ask: "Please state your name for the override log."

## Log Entry Format

Appends to `.agents/projectContext/overrides.log` (append-only, never modified):

```
[ISO-8601 timestamp] | BY: <git-user-name> <<git-user-email>> | PLATFORM: <github|gitea|unknown> | GATE: <gate bypassed> | REASON: <user's reason>
```

`overrides.log` is append-only. No entry is ever edited or deleted. This file is
committed to the repo — it is a permanent audit artifact.

## Hard Gates

- MUST write to `.agents/projectContext/overrides.log` before proceeding — the log
  entry is not optional
- MUST include an authorizing identity — "codeArbiter" or "automated" are not valid
  identities
- MUST include a justification — "because I said so" is not accepted
- The override is scoped to the immediate action only — it does not create a
  standing exception
- If the override involves a security-critical gate (auth, crypto, secrets):
  surface a warning before proceeding and ask for confirmation a second time

## After Appending

Proceed with the overridden action. Note in the response that the override is
logged and visible to all reviewers.

## Visibility

Override log entries are:
- Visible to all reviewers at the next `/checkpoint`
- Included in PR descriptions when the override affects a gate that `/pr` would
  normally enforce
- Permanent — entries are never deleted from `.agents/projectContext/overrides.log`

## When NOT to Use

- For routine work that passes all gates: never needed — gates exist for a reason
- For stage promotion: use `/stage N` (which has its own approval flow)
- For resolving a conflict between two sources: use `/surface-conflict` instead
