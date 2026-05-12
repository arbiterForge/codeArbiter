# /review [path or diff]

## Purpose

Run a targeted review of a specific file, path, or the current diff. Routes to the appropriate reviewer agents based on what is being reviewed. Read-only — no code is modified. Produces findings with severity ratings.

## Usage

```
/review                        # reviews current staged diff
/review path/to/file.ts        # reviews a specific file
/review path/to/directory/     # reviews all files in a directory
```

## Routes To

`security-architecture` skill, plus reviewer agents determined by path matrix (see below).

Always invoked:
- `coverage-auditor` — audits test coverage and audit event emission for the reviewed scope

Path-conditional (invoked when the scope matches):
- `auth-crypto-reviewer` + `security-reviewer` — if path includes auth, crypto, middleware, secrets handling, or audit libraries
- `migration-reviewer` — if path includes database migration files
- `audit-emitter` — if path includes code that performs or should perform auditable actions
- `dependency-reviewer` — if path includes `package.json`, lock files, or dependency manifests
- `trust-zone-reviewer` — if path includes HTTP clients, network configuration, or zone-crossing code
- `standards-compliance-reviewer` — for all code paths (naming, conventions, banned patterns)

## What Happens Step by Step

1. codeArbiter inspects the scope to determine which reviewer agents apply
2. Reviewer agents run — in parallel where no dependency exists
3. All findings aggregated and presented with:
   - Severity: CRITICAL / HIGH / MEDIUM / LOW
   - Description
   - File and line
   - Remediation recommendation
   - Applicable control from `${PROJECT_ROOT}/.agents/projectContext/security-controls.md` (for security findings)
4. Findings summary presented to user
5. BLOCK-level findings (CRITICAL / HIGH) highlighted — these MUST be resolved before `/pr`

## Severity Definitions

- **CRITICAL** — exploitable vulnerability, secret exposure, banned primitive in use, or data integrity breach. Blocks PR.
- **HIGH** — significant compliance gap, missing audit event on auditable action, trust zone violation. Blocks PR.
- **MEDIUM** — standards deviation, coverage gap, improvement needed. Must appear in checkpoint report.
- **LOW** — informational, style, or minor suggestion. Does not block.

## Hard Gates

- Review is read-only — no file is modified during a `/review`
- CRITICAL and HIGH findings MUST be resolved before `/pr` is invoked
- MEDIUM findings MUST appear in the next `/checkpoint` report
- If `security-reviewer` raises CRITICAL: all work halts until user resolves

## When NOT to Use

- To open a PR (which dispatches reviewers automatically): use `/pr`
- For a full checkpoint across the entire codebase: use `/checkpoint`
- For a threat model before a new feature: use `/threat-model`
- For questions about the code: use `/btw`
