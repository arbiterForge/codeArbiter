# Audit log line formats — `.codearbiter/overrides.log`

The one schema for every audit line; no other shape is valid. Append-only: append with `>>`;
never edit, rewrite, or delete an existing line — the log is committed as a permanent audit
artifact, with no dev-mode exception. `BY:` is the identity from `git config user.email`; if
unset, ask the user once to state an identity — never an empty, `codeArbiter`, or `automated`
attribution.

- **Override:** `[ISO-8601] | BY: <email> | GATE: <gate bypassed> | REASON: <reason>`
- **Security override:** `[ISO-8601] | BY: <email> | SECURITY-OVERRIDE | FINDING: <specific finding> | REASON: <reason>`
- **Dev-mode entry:** `[ISO-8601] | BY: <email> | DEV: enter | NOTE: <note or —>`
- **Dev-mode exit:** `[ISO-8601] | BY: <email> | DEV: exit` — SessionStart appends the synthetic
  `BY: session-cleanup | DEV: exit` close when a session ended mid-dev.
