# Reviewer-to-path matrix

The single source of truth for which reviewer is dispatched when the scope touches a given path.
Cited by `review.md`, `pr.md`, `checkpoint.md`, and `preview.md`: edit the matrix here, not in those
commands. Each matched reviewer is one read-only unit.

| Reviewer | Dispatched when scope touches |
|---|---|
| `security-reviewer` | auth, middleware, secrets, deploy/CI, any security-sensitive path |
| `auth-crypto-reviewer` | authn, crypto, key handling, secrets |
| `dependency-reviewer` | `package.json`, lockfiles, base images, dependency manifests |
| `migration-reviewer` | DB migration file add/modify |
| `coverage-auditor` | any source change (test coverage vs. obligations) |
| `architecture-drift-reviewer` | code that may diverge from accepted ADRs in `.codearbiter/decisions/` |
