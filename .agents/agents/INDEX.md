# Agents Index

<!-- Auto-maintained surface scan. Agent bodies are read ONLY when dispatched. -->
<!-- See AGENTS.md §3 and §6: bulk reads of `.agents/agents/*.md` are prohibited. -->
<!-- Use this index for routing decisions; open bodies on invocation. -->

## Read-on-invocation guarantee

This `INDEX.md` is the only sanctioned surface scan of `.agents/agents/`. Routing decisions in AGENTS.md §4 and §5 reference agents by name; their bodies are loaded only when the named agent is dispatched.

## Index

| Agent | One-line role | BLOCKs on | Body |
|---|---|---|---|
| architecture-drift-reviewer | Surfaces drift from ADRs and documented patterns | — (read-only) | [body](architecture-drift-reviewer.md) |
| audit-emitter | Verifies audit event emission for new auditable actions | missing emit, missing required fields | [body](audit-emitter.md) |
| auth-crypto-reviewer | Reviews authn, crypto, secrets handling against security controls | banned primitives, exposed secrets, shell injection | [body](auth-crypto-reviewer.md) |
| backend-author | Implements backend/API code via TDD workflow | failing tests, lint errors, missing audit emit | [body](backend-author.md) |
| checkpoint-aggregator | Writes dated checkpoint doc from triage + challenger output | — (aggregator, not a blocker) | [body](checkpoint-aggregator.md) |
| decision-challenger | Adversarial red-team review of ADRs (SMARTS, confidence 1–5) | — (surfaces, does not block) | [body](decision-challenger.md) |
| dependency-reviewer | Reviews package.json / lockfile / base image changes | denied license, supply-chain concerns | [body](dependency-reviewer.md) |
| finding-triage | Assigns stage promotion impact to checkpoint findings | — (sequential post-processor) | [body](finding-triage.md) |
| frontend-author | Implements UI code via TDD workflow | failing tests, lint errors, missing UI security checks | [body](frontend-author.md) |
| grader | INTERNAL: SMARTS analysis for decision-variance skill — never invoke directly | — | [body](grader.md) |
| infra-author | Implements IaC, containers, CI/CD manifests, deploy config | missing threat model on zone-crossing change | [body](infra-author.md) |
| migration-reviewer | Reviews DB migration files for safety and classification | classification annotation missing, irreversible destructive op | [body](migration-reviewer.md) |
| scaffold-completeness-reviewer | Identifies planned-but-missing artifacts | — (read-only checkpoint reviewer) | [body](scaffold-completeness-reviewer.md) |
| scout | INTERNAL: scans codebase sections for decision-variance / context-creation skills — never invoke directly | — | [body](scout.md) |
| security-reviewer | PROACTIVE diff review for security-sensitive paths | any CRITICAL or HIGH finding | [body](security-reviewer.md) |
| standards-compliance-reviewer | Reviews against coding standards, lint, type safety | — (read-only checkpoint reviewer) | [body](standards-compliance-reviewer.md) |
| coverage-auditor | Audits test coverage vs. TDD obligations | untested source files, missing audit emit tests | [body](coverage-auditor.md) |
| trust-zone-reviewer | Reviews zone boundary enforcement and HTTP client usage | undeclared zone crossings | [body](trust-zone-reviewer.md) |
