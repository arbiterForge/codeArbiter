# agents — catalog (surface scan)

Agent bodies load on dispatch only. This index is the surface scan; never bulk-read `agents/*.md`.
An agent is a reviewer or author **dispatched** by a skill — never routed to, never "triggered."

| Agent | Dispatched by | Role | BLOCKs on |
|---|---|---|---|
| [backend-author](backend-author.md) | `tdd` (after Phase 1) | Writes backend/API/service code test-first; validates input; dispatches reviewers for security/migration/dependency changes. | failing tests, lint errors |
| [frontend-author](frontend-author.md) | `tdd` (after Phase 1) | Writes UI code test-first; component + state conventions; UI security. | failing tests, lint errors, missing UI security checks |
| [infra-author](infra-author.md) | `tdd` (after Phase 1) | Writes IaC, containers, CI/CD manifests, deploy config; security boundaries from `security-controls.md`. | failing tests, lint errors |
| [security-reviewer](security-reviewer.md) | proactively on security-sensitive paths; `commit-gate`, `/review` | Read-only diff review against `security-controls.md` — authn/authz/crypto/secrets/deploy/CI. | any CRITICAL or HIGH finding |
| [auth-crypto-reviewer](auth-crypto-reviewer.md) | author agents + reviewers on auth/crypto/key/secret changes | Read-only review of authn, crypto, key handling, and secrets against `security-controls.md`. | banned primitives, exposed secrets, disabled TLS verification, shell injection |
| [dependency-reviewer](dependency-reviewer.md) | on `package.json` / lockfile / base-image change | Verifies license, provenance, maintenance signal, supply-chain posture before merge. | denied license, supply-chain concern |
| [migration-reviewer](migration-reviewer.md) | on a DB migration file add/modify | Reviews migration safety, data-classification tagging, immutability. | missing classification annotation, irreversible destructive op |
| [coverage-auditor](coverage-auditor.md) | `tdd` (Phase 4) | Audits test coverage vs. TDD obligations; flags untested source and logical gaps. | untested source files, coverage below the maturity threshold |
| [architecture-drift-reviewer](architecture-drift-reviewer.md) | `/checkpoint` sweep | Read-only; surfaces drift between the codebase and accepted ADRs in `.codearbiter/decisions/`. | — (informational, never blocks) |
| [finding-triage](finding-triage.md) | `/checkpoint` sweep (sequential) | Consolidates reviewer reports; classifies each finding by severity and whether it blocks the current change. | — (post-processor) |
| [checkpoint-aggregator](checkpoint-aggregator.md) | `/checkpoint` sweep (terminal) | Composes triage + challenger output into a dated `.codearbiter/checkpoints/` doc. | — (aggregator) |
| [decision-challenger](decision-challenger.md) | `decision-variance` (optional) | Adversarial red-team of ADRs; confidence 1–5; surfaces disproving evidence. Read-only. | — (surfaces, does not block) |
| [scout](scout.md) | `decision-variance`, `context-creation` (INTERNAL) | Scans an assigned code scope, reports decision evidence — paths + line numbers only, no excerpts. Never dispatch directly. | — (internal) |
| [grader](grader.md) | `decision-variance` (INTERNAL) | Produces a SMARTS analysis + strength-labeled recommendation for one variance. Never decides. Never dispatch directly. | — (internal) |
| [design-quality-reviewer](design-quality-reviewer.md) | `frontend-author` on UI changes (Tier 2 `/pr`, `release` apply the reference inline, not via this agent) | Read-only review of generated user-facing output (UI, reports, slides, charts, diagrams, CLI) against the lazy-loaded `anti-slop-design` reference. Loads only the medium leaf needed. | fabricated/unmarked numbers where provenance is assessable; em/en-dash used as a prose sentence-separator (3.A exemptions excluded) |

## Cut in v2

`audit-emitter`, `trust-zone-reviewer`, `standards-compliance-reviewer`, and
`scaffold-completeness-reviewer` were removed in the v2 rewrite (their parent compliance skills were
cut, or their checks are now covered by `tdd`/`commit-gate`/the kept reviewers).
