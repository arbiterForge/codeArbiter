# Reference map

For every security policy reference below, follow `{{PLUGIN_ROOT}}/includes/knowledge.md`
("Read security policy before a security decision"): select the repository's
context format, read the complete policy from exact `CTX-SECURITY-CONTROLS`
records in HTML mode or the full Markdown controls in Markdown mode, and read
operative scope blocks when applicable. Required policy that is missing or
unreadable blocks a security decision; scope blocks alone are not full policy.

Loaded on a scope-touch: before acting on code in one of these rows, read the governing doc first,
then route to the owning skill or agent. This map answers *what to read before touching a scope*; for
*what to invoke or route given a trigger*, use `routing-table.md`. "Read first" paths are under
`{{PROJECT_DIR}}/.codearbiter/` unless the row gives a `{{PLUGIN_ROOT}}/` path.

| If the change touches… | Read first | Route to |
|---|---|---|
| Any code change | `coding-standards.md` | `tdd` skill |
| Stack / dependencies | `tech-stack.md`, `security-controls.md` | `dependency-reviewer` agent |
| Auth, crypto, secrets | `security-controls.md` | `crypto-compliance` / `secret-handling` skill (`{{PLUGIN_ROOT}}/skills/<name>/SKILL.md`); `auth-crypto-reviewer` agent |
| Data model / migrations | `tech-stack.md` | `migration-reviewer` agent |
| Networking / deployment / attack surface | `security-controls.md` | `security-reviewer` agent (H-16 advisory); `security-architecture` skill (`/threat-model`, optional) |
| New domain concept or component | `CONTEXT.md` | update the vocabulary in `CONTEXT.md` |
| Failure / retry, CI/CD, branch settings | `tech-stack.md`, `security-controls.md` | `security-reviewer` agent (CI/CD: H-15 advisory) |
| Risks / ADRs | `open-questions.md`, `decisions/` | `decision-lifecycle` skill (`/adr`) |
| Architectural reconciliation | `plans/` (the three artifacts), `decisions/decision-log.md` | `decision-variance` skill (`/reconcile`) |
| Out-of-scope finding | — | inline `[NEEDS-TRIAGE]` marker (never an ADR); promoted to the selected work owner by the harvest at the workflow's terminal step |
| Following up on workflow residue / a backlog task | `{{PLUGIN_ROOT}}/includes/harvest.md`, selected `work.py` owner | `{{CMD:task}}` writer; harvest (`extract_*` → `promote`) at a terminal step. Legacy mode retains `open-tasks.md`. |
| Generating a user-facing deliverable (UI, report, PR/CHANGELOG prose, slide, chart) | `{{PLUGIN_ROOT}}/includes/anti-slop-design/INDEX.md` (then `core` + the medium leaf) | `design-quality-reviewer` agent |
| Provenance drift or requested refresh of initialized context | Selected documents + `.codearbiter/.provenance/` + `.codearbiter/code-map.md` | `context-check` skill (`{{CMD:context-check}}`); reuse the selected scope and existing authorization |
