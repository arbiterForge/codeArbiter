<!--PLACEHOLDER-->
<!-- Populated by decompose/context-creation skill. -->

# Secrets Policy

## Approved Secret Store

_Where secrets must be stored and retrieved from (e.g., AWS Secrets Manager, HashiCorp Vault, Kubernetes Secrets, Azure Key Vault)._

## Access Pattern

_How services access secrets (e.g., IAM role, service account, environment injection)._

## Prohibited Sources

_Sources from which secrets MUST NOT be read:_
- Hardcoded string literals
- Source-controlled `.env` files (unless explicitly scoped to non-sensitive local-dev config)
- Database columns (unless storing reference/ARN only)
- Container environment variables for long-lived processes (specify stage threshold if applicable)

## Prohibited Sinks

_Places where secrets MUST NOT flow:_
- Application logs (any level)
- Error messages returned to clients
- Telemetry / metrics / tracing
- LLM prompts or agent context
- Audit event payloads (record the reference/ARN, never the value)

## Rotation Requirements

_Rotation schedule and what events must be emitted on rotation._

## DB Storage Rule

_If secret references must be persisted in DB, only the store reference (ARN, path, etc.) is permitted — never the secret value._
