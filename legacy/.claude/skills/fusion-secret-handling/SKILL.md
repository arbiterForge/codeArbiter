---
name: fusion-secret-handling
description: Use whenever code needs to read, write, or pass through any kind of secret — API keys, tokens, passwords, AWS credentials, database connection strings, OIDC client secrets, signing keys. Tells the agent how to source from AWS Secrets Manager, never persist, never log, and never include in LLM prompts.
---

# FUSION Secret Handling

Secrets in FUSION live in AWS Secrets Manager (FIPS endpoint), accessed via
IAM instance role or IRSA. Anything else is a finding.

## Sourcing

```python
# YES — short-lived fetch with TTL
from backend.common.secrets import get_secret

token = await get_secret("fusion/oidc/client-secret")  # cached for ≤ 5 min
# Use immediately. Do not store in a long-lived variable.
```

The `get_secret` helper:
- Uses the FIPS Secrets Manager endpoint (`secretsmanager-fips.<region>.amazonaws.com`).
- Caches per-process for ≤ 5 minutes (Stage 2+).
- Emits `audit.emit(action="secret.read", ...)` automatically.
- Marks the returned object with a `__sensitive__` flag the redactor recognizes.

## Banned Sources

- `os.environ["AWS_SECRET_ACCESS_KEY"]` for long-lived AWS keys → BANNED at all stages. Use IAM instance role/IRSA.
- `.env` for any secret → BANNED at all stages. `.env` is for non-sensitive local config only (ports, log levels).
- Hardcoded literals → BANNED. Caught by gitleaks.
- Reading from an unencrypted file → BANNED. Even tmpfs is a last resort.

## Banned Sinks

- App logger: `logger.info(f"token={token}")` → BANNED. The redactor catches `__sensitive__`-marked values, but you MUST NOT rely on it.
- Error message: `raise ValueError(f"bad token {token}")` → BANNED. Wrap in `RedactedValue`.
- Telemetry attribute: `span.set_attribute("token", token)` → BANNED.
- LLM prompt: passing a secret into any LLM call (including Claude in Claude Code, Cursor, etc.) → BANNED. Treat the LLM provider as out-of-boundary (AC-21). If the agent needs to verify a token shape, it MUST use `len()`, `startswith()`, or a hash — never the value.
- Container env var on a long-lived process → BANNED at S2+. Use per-request fetch.
- Database column → BANNED. Store the Secrets Manager ARN in `value_ref`.

## Storage in DB

Only the reference goes in Postgres:

```python
# YES
env_variables.value_ref = "arn:aws:secretsmanager:us-east-1:123:secret:fusion/oidc-abc123"

# BANNED — CHECK constraint will reject this
env_variables.value_ref = "actual-secret-value"
```

The `env_variables.value_ref` column has a Postgres CHECK constraint
enforcing the ARN format. If your migration adds a similar column, copy the
constraint pattern.

## Redaction

The application logger uses `backend/common/log_redact.py`, which is an
allow-list of safe field names — anything not on the list is redacted before
emission. This is a backstop, not an excuse:

```python
SAFE_FIELDS = {
    "ts", "level", "logger", "request_id", "user_id", "action",
    "resource_type", "resource_id", "outcome", "duration_ms",
    # ... explicit allow-list
}
# Any other field is replaced with "[REDACTED]" in the output.
```

If you need a new field on the safe list, add it via PR with justification.
The `security-reviewer` subagent reviews additions.

## Rotation

- Worker job credentials MUST be one-time STS tokens scoped to that deployment's resources, generated at deploy start, expired at deploy end. (IA-5(1)) [S2+]
- OIDC client secrets, signing keys: rotate at least annually. Rotation MUST emit `audit.emit(action="key.rotate", ...)`.

## When You're Unsure

If you're about to write code that holds a secret value in a Python variable
for more than the duration of one HTTP request — STOP. That's almost always
wrong. Either fetch lazily on each use, or hold the ARN and fetch.

If you're about to put a credential into a test fixture — STOP. Use:

```python
@pytest.fixture
def fake_oidc_token():
    return "test-token-not-a-real-secret"  # MUST contain "test" or "fake"; gitleaks allow-listed
```

Cite controls: IA-5, SC-12, SC-28, AU-9, AC-21.
