# Reviewer contract — findings format, output template, out-of-scope rule

Canonical for every gate reviewer agent (`security-reviewer`, `auth-crypto-reviewer`,
`dependency-reviewer`, `migration-reviewer`, `coverage-auditor`). Loaded via each agent's
Required Reading; the agent bodies do not restate these blocks. An agent body MAY narrow the
subject field or add fields and heading qualifiers — additions extend this contract, never
replace it.

## Findings format

```
**Severity:** CRITICAL | HIGH | MEDIUM | LOW
**File:** <path>:<line>
**Description:** <specific problem — no vague claims>
**Remediation:** <concrete fix>
```

Agent-specific deltas declared in the agent body (examples): `security-reviewer` and
`auth-crypto-reviewer` add a `**Control:**` line citing
`${CLAUDE_PROJECT_DIR}/.codearbiter/security-controls.md`; `dependency-reviewer` uses
`**Package:** <name@version>` as the subject field; `coverage-auditor` uses
`**File:** <source path> / <test path, if exists>`.

## Review output template

```
## <Role> Review — <date>

### CRITICAL findings (N)
[findings or "none"]

### HIGH findings (N)
[findings or "none"]

### MEDIUM findings (N)
[findings or "none"]

### LOW findings (N)
[findings or "none"]

### Gate status
PASS (no CRITICAL or HIGH) | BLOCK (N CRITICAL, N HIGH must resolve before merge)
```

`<Role>` is the reviewer's own review name (Security, Auth/Crypto, Dependency, Migration,
Coverage); an agent body may qualify the heading (e.g. the dependency review includes
`<package@version>`).

## Out-of-scope findings

**Out-of-scope finding:** do not act on it and do not author an ADR for it (ADRs are
user-attributed, via `/adr` only). Mark it inline with a `[NEEDS-TRIAGE]` marker; never
silently drop it.
