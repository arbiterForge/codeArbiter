# Reference map

Loaded on a scope-touch — before acting on code in one of these rows, read the governing
`.codearbiter/*.md` doc first, then route to the owning skill or agent. All paths are under
`${CLAUDE_PROJECT_DIR}/.codearbiter/`.

| If the change touches… | Read first | Route to |
|---|---|---|
| Any code change | `coding-standards.md` | `tdd` skill |
| Stack / dependencies | `tech-stack.md`, `security-controls.md` | `dependency-reviewer` agent |
| Auth, crypto, secrets | `security-controls.md` | `crypto-compliance` / `secret-handling` skill; `auth-crypto-reviewer` agent |
| Data model / migrations | `tech-stack.md` | `migration-reviewer` agent |
| Networking / deployment / attack surface | `security-controls.md` | `security-architecture` skill (`/threat-model`, optional) |
| New domain concept or component | `CONTEXT.md` | update the vocabulary in `CONTEXT.md` |
| Failure / retry, CI/CD, branch settings | `tech-stack.md` | — |
| Risks / ADRs | `open-questions.md`, `decisions/` | `decision-lifecycle` skill (`/adr`) |
| Architectural reconciliation | `plans/` (the three artifacts), `decisions/decision-log.md` | `decision-variance` skill (`/reconcile`) |
| Out-of-scope finding | — | inline `[NEEDS-TRIAGE]` marker (never an ADR) |
