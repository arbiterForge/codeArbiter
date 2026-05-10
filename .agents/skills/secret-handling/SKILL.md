# secret-handling Skill

## Identity
Claude IS a secrets lifecycle enforcer who treats any secret outside the project-approved secret store as an active exfiltration risk.

## Trigger
- Code reads, generates, stores, or passes an API key, token, password, or passphrase
- Code handles platform credentials or session tokens
- Code references a database connection string
- Code uses an OIDC client secret
- Code handles a signing key or certificate private key
- Code references any value that grants access to a resource
- Any variable, parameter, or field name matches: `password`, `secret`, `token`, `key`, `credential`, `api_key`, `apikey`, `private`, `cert`, `passphrase`

If uncertain whether a value is a secret, treat it as a secret.

---

## Phases

### Phase 1 — Secret Identification
Grep changed code for: `password`, `secret`, `token`, `key`, `credential`, `api_key`, `apikey`, `private`, `cert`, `passphrase`.

For each match, record:
- The variable/field name
- Its current source (where the value comes from)
- Its current sink(s) (where the value flows to)

Output: list of identified secrets with source and sink for each. No candidate may remain unclassified.

**Gate:** All candidate secrets identified and listed with source and sink.

---

### Phase 2 — Source Verification
Read `projectContext/secrets-policy.md` to determine the approved secret store for this project. Secrets MUST originate from the store specified there.

Access MUST use the authentication method specified in `projectContext/secrets-policy.md` (e.g., IAM role, workload identity, service account token) — never long-lived static credential keys.

**BLOCK conditions at all stages (regardless of project):**

| Source | Status |
|---|---|
| `process.env` for secret values | BLOCK — permitted only for non-sensitive config (ports, log levels) |
| `.env` files for secrets | BLOCK — `.env` is for non-sensitive local-dev config only |
| Hardcoded string literal | BLOCK — caught by secrets scanner |
| Database column value (non-reference) | BLOCK |
| Any secret store endpoint not specified in `projectContext/secrets-policy.md` | BLOCK |
| Container env var on long-lived process [S2+] | BLOCK |

`.env` files MUST be in `.gitignore` AND scanned by the project's secrets scanner on every PR.

**Gate:** All secrets sourced from the store specified in `projectContext/secrets-policy.md` via the approved authentication method.

---

### Phase 3 — Sink Audit
Trace each identified secret from source to all sinks. The following sinks are prohibited at all stages with no project-specific exceptions:

| Sink | Rule |
|---|---|
| Application logger (any level) | MUST NOT — no secret in any log call |
| Error messages returned to clients | MUST NOT — no secret in HTTP 4xx/5xx response body |
| Telemetry / metrics / tracing | MUST NOT — no `span.setAttribute(key, secretValue)` |
| LLM prompts or context | MUST NOT — treat the LLM provider as out-of-boundary. Use `len()`, `startsWith()`, or a hash to verify token shape — never the value |
| Database columns (non-reference value) | MUST NOT — see Phase 4 for reference-only exception |
| Audit event payload | MUST NOT include the secret value — the audit event records that a secret was read and the store reference (path, ID, ARN), never the value |
| Serialized state, session storage, JWT payload | MUST NOT |

Note: if the project uses a log redaction backstop, that backstop is not an excuse to pass secrets to the logger — the MUST NOT rule applies regardless.

**Gate:** No secret flows to any prohibited sink.

---

### Phase 4 — DB Storage Check
If a secret reference must be persisted in the database, only the store reference (path, ID, ARN, or whatever identifier format the approved store uses) may be stored — never the secret value itself.

The reference-storing column MUST have a check constraint verifying the reference format. Read the expected reference format from `projectContext/secrets-policy.md`. The constraint must verify that the stored value matches the format of the approved store's reference (e.g., a path prefix, an ARN pattern, a UUID prefix).

If a migration adds a column that stores a secret reference without this constraint, that is a BLOCK condition.

**Gate:** Database columns store the store reference only. Check constraint present, verified against the format from `projectContext/secrets-policy.md`.

---

### Phase 5 — Lifecycle Check
Secrets MUST NOT persist beyond the request boundary in which they are used. Check all of the following:

| Anti-pattern | Rule |
|---|---|
| Module-level variable holding secret | MUST NOT |
| Class instance field outliving the request | MUST NOT |
| In-memory cache across requests (even with TTL) | MUST NOT without explicit CODEOWNER approval |
| Serialized state / session storage / JWT payload | MUST NOT |
| Worker job credential persisted across deployments | MUST NOT — worker credentials MUST be one-time scoped tokens generated at deploy start, expired at deploy end [S2+] |
| Signing keys or OIDC client secrets unrotated > 1 year | MUST NOT — rotation MUST emit a `key.rotate` audit event |

Rotation MUST emit an audit event per `projectContext/audit-spec.md` — route to the `audit-emit` skill for that event's test obligation.

**Gate:** Secret lifetime is bounded to request scope. No cross-request persistence without CODEOWNER approval.

---

### Phase 6 — Audit Emit
Every `read.secret` action MUST emit an audit event. The event MUST include:
- `action: 'read.secret'`
- `subject.type: 'secret_ref'`
- `subject.id`: the store reference from the approved store (path, ID, ARN — never the secret value)
- `actor.id`: the service identity or authenticated identity claim
- `outcome`: `success` or `failure`

Route to the `audit-emit` skill and complete through Phase 5 (Test Obligation) for this event. The audit event schema is defined in `projectContext/audit-spec.md`.

**Gate:** `read.secret` audit event emitted with store reference in `subject.id`. `audit-emit` skill Phase 5 complete.

---

## Decision Gates

| Gate | Condition | Action |
|---|---|---|
| Bad source | Secret read from `process.env`, `.env` file, or hardcoded literal | BLOCK |
| Long-lived env var [S2+] | Secret in container env var on long-lived process | BLOCK |
| Sink leak — logger | Secret flows to any logger call | BLOCK |
| Sink leak — error | Secret flows to client-facing error message | BLOCK |
| Sink leak — telemetry | Secret flows to metrics, tracing, or spans | BLOCK |
| Sink leak — LLM | Secret flows to any LLM prompt or context | BLOCK |
| DB value | Secret value (not store reference) stored in database column | BLOCK |
| No reference constraint | DB column stores reference but lacks check constraint | BLOCK |
| Cross-request persist | Secret stored in module var, class field, or cross-request cache | BLOCK |
| No audit emit | `read.secret` action with no emit call | BLOCK |
| Secret in audit event | Secret value (not store reference) appears in audit event payload | BLOCK |

---

## Hard Rules
- MUST read `projectContext/secrets-policy.md` before Phase 2 to identify the approved secret store. BLOCK if the file cannot be read and no cached policy exists.
- MUST NOT read secrets from `process.env`, `.env` files, or hardcoded values.
- MUST NOT allow secrets to flow to loggers, error messages, telemetry, tracing, or LLM prompts.
- MUST NOT store secret values in the database — store reference only, with check constraint.
- MUST NOT persist secrets beyond the request boundary without explicit CODEOWNER approval.
- MUST NOT omit the `read.secret` audit event.
- MUST NOT include the secret value in the audit event — record the store reference only.
- MUST NOT include secrets in any LLM prompt or agent context — treat the LLM provider as out-of-boundary.
