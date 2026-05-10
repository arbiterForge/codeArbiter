# fusion-secret-handling Skill

## Identity
Claude IS a secrets lifecycle enforcer who treats any secret outside AWS Secrets Manager as an active exfiltration risk.

## Trigger
- Code reads, generates, stores, or passes an API key, token, password, or passphrase
- Code handles AWS credentials or STS tokens
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
Every secret MUST originate from AWS Secrets Manager via the FIPS endpoint:
`secretsmanager-fips.<region>.amazonaws.com`

Access MUST use IAM instance role or IRSA — never long-lived AWS credential keys.

**BLOCK conditions at all stages:**

| Source | Status |
|---|---|
| `process.env` for secret values | BLOCK — permitted only for non-sensitive config (ports, log levels) |
| `.env` files for secrets | BLOCK — `.env` is for non-sensitive local-dev config only |
| Hardcoded string literal | BLOCK — caught by gitleaks |
| Database column value (non-ARN) | BLOCK |
| Any HTTP endpoint other than Secrets Manager FIPS | BLOCK |
| Container env var on long-lived process [S2+] | BLOCK |

`.env` files MUST be in `.gitignore` AND scanned by `make secrets-scan` (gitleaks). Run `make secrets-scan` on every PR.

**Gate:** All secrets sourced from Secrets Manager FIPS endpoint via IAM instance role or IRSA.

---

### Phase 3 — Sink Audit
Trace each identified secret from source to all sinks. The following sinks are prohibited at all stages:

| Sink | Rule |
|---|---|
| Application logger (any level) | MUST NOT — `console.log`, `logger.info`, `logger.error`, `request.log.*` |
| Error messages returned to clients | MUST NOT — no secret in HTTP 4xx/5xx response body |
| Telemetry / metrics / tracing | MUST NOT — no `span.set_attribute(key, secretValue)` |
| LLM prompts or context | MUST NOT — treat the LLM provider as out-of-boundary (AC-21). Use `len()`, `startsWith()`, or a hash to verify token shape — never the value |
| Database columns (non-ARN value) | MUST NOT — see Phase 4 for ARN-only exception |
| Audit event payload | MUST NOT include the secret value — the audit event records that a secret was read and the ARN, never the value |
| Serialized state, session storage, JWT payload | MUST NOT |

Note: the application logger uses a redaction backstop (`backend/src/common/log_redact`). That backstop is not an excuse to pass secrets to the logger — the MUST NOT rule applies regardless.

**Gate:** No secret flows to any prohibited sink.

---

### Phase 4 — DB Storage Check
If a secret reference must be persisted in the database, only the Secrets Manager ARN may be stored — never the secret value.

The ARN-storing column MUST have a Drizzle-level CHECK constraint verifying ARN format:
```
CHECK (col LIKE 'arn:aws:secretsmanager:%')
```

Verify the constraint exists in the Drizzle schema file. If adding a new column that stores a secret reference, copy the constraint pattern from `env_variables.value_ref`.

If a migration adds a similar column without this constraint, that is a BLOCK condition.

**Gate:** DB columns store ARN only. CHECK constraint present and verified in Drizzle schema.

---

### Phase 5 — Lifecycle Check
Secrets MUST NOT persist beyond the request boundary in which they are used. Check all of the following:

| Anti-pattern | Rule |
|---|---|
| Module-level variable holding secret | MUST NOT |
| Class instance field outliving the request | MUST NOT |
| In-memory cache across requests (even with TTL) | MUST NOT without explicit CODEOWNER approval |
| Serialized state / session storage / JWT payload | MUST NOT |
| Worker job credential persisted across deployments | MUST NOT — worker credentials MUST be one-time STS tokens scoped to that deployment's resources, generated at deploy start, expired at deploy end [S2+] |
| OIDC client secrets or signing keys unrotated > 1 year | MUST NOT — rotation MUST emit `key.rotate` audit event |

Rotation MUST emit `audit.emit({ action: 'key.rotate', ... })` — route to the `fusion-audit-emit` skill for that event's test obligation.

**Gate:** Secret lifetime is bounded to request scope. No cross-request persistence without CODEOWNER approval.

---

### Phase 6 — Audit Emit
Every `read.secret` action MUST emit an audit event. The event MUST include:
- `action: 'read.secret'`
- `subject.type: 'secret_ref'`
- `subject.id`: the Secrets Manager ARN (never the secret value)
- `actor.id`: the OIDC sub claim or service identity
- `outcome`: `success` or `failure`

Route to the `fusion-audit-emit` skill and complete through Phase 5 (Test Obligation) for this event.

**Gate:** `read.secret` audit event emitted with ARN in `subject.id`. `fusion-audit-emit` skill Phase 5 complete.

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
| DB value | Secret value (not ARN) stored in database column | BLOCK |
| No ARN constraint | DB column stores ARN but lacks CHECK constraint | BLOCK |
| Cross-request persist | Secret stored in module var, class field, or cross-request cache | BLOCK |
| No audit emit | `read.secret` action with no `emit()` call | BLOCK |
| Secret in audit event | Secret value (not ARN) appears in audit event payload | BLOCK |

---

## Hard Rules
- MUST NOT read secrets from `process.env`, `.env` files, or hardcoded values.
- MUST NOT allow secrets to flow to loggers, error messages, telemetry, tracing, or LLM prompts.
- MUST NOT store secret values in the database — ARN only, with CHECK constraint.
- MUST NOT persist secrets beyond the request boundary without explicit CODEOWNER approval.
- MUST NOT omit the `read.secret` audit event.
- MUST NOT include the secret value in the audit event — record the ARN only.
- MUST NOT include secrets in any LLM prompt or agent context — treat the LLM provider as out-of-boundary (AC-21).
- MUST NOT reference Python code, Python `get_secret` helpers, or Python examples — the Python stack was retired per ADR-0004.
