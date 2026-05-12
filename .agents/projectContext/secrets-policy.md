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

## External Ticketing Credentials (ticketing skill, Plane mode)

When the optional `ticketing` skill operates in `mode: plane` against an on-prem Plane instance, API keys live in shell environment variables only. Specifically:

- API key MUST be set as a shell env var (default name: `PLANE_API_KEY`). The variable name is configurable in `projectContext/ticketing-config.md`.
- The env var value MUST NEVER appear in any committed file, including:
  - `.claude/settings.json` or `.agents/settings.json` — the `mcpServers` entry references the env var by name (`${PLANE_API_KEY}`), not by value.
  - `ticketing-config.md` — stores only the env var NAME, never its value.
  - Any agent prompt, log, or ticket body.
- Approved storage locations for the env var value: the user's shell rc file (`.bashrc`, `.zshrc`) or a manually-sourced gitignored file at `~/.config/codeArbiter/plane.env`.
- The same rule applies to any other ticketing-related credentials (`PLANE_API_URL`, `PLANE_WORKSPACE_SLUG`): values are env-var-only.

Rotation: when the API key is rotated in Plane, export the new value in the shell and restart the MCP server. No repo change is required.
