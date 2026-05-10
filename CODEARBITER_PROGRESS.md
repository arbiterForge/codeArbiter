# codeArbiter v2 — Implementation Progress

<!-- Updated as work completes. Each entry: artifact path + status + brief note. -->

## Status Legend
- ✅ Complete
- 🔄 In Progress
- ⬜ Pending

---

## Phase 1 — Foundation Files

| Artifact | Status | Notes |
|---|---|---|
| `CODEARBITER_PLAN.md` | ✅ | Full plan saved at repo root |
| `CODEARBITER_PROGRESS.md` | ✅ | This file |
| `CLAUDE.md` | ⬜ | Needs to become one-line shim: `@AGENTS.md` |
| `AGENTS.md` | ⬜ | Canonical persona §0–§7 |
| `COMMANDS.md` | ⬜ | User-facing quick-ref + detail |

## Phase 2 — projectContext Scaffold

| Artifact | Status | Notes |
|---|---|---|
| `.agents/projectContext/CONTEXT.md` | ⬜ | Stub with PLACEHOLDER sentinel |
| `.agents/projectContext/tech-stack.md` | ⬜ | |
| `.agents/projectContext/trust-zones.md` | ⬜ | |
| `.agents/projectContext/coding-standards.md` | ⬜ | |
| `.agents/projectContext/audit-spec.md` | ⬜ | |
| `.agents/projectContext/secrets-policy.md` | ⬜ | |
| `.agents/projectContext/security-controls.md` | ⬜ | |
| `.agents/projectContext/dependency-policy.md` | ⬜ | |
| `.agents/projectContext/stage` | ⬜ | File containing integer 1 |
| `.agents/projectContext/open-tasks.md` | ⬜ | |
| `.agents/projectContext/open-questions.md` | ⬜ | |
| `.agents/projectContext/overrides.log` | ⬜ | Append-only; format header only |
| `.agents/projectContext/decisions/README.md` | ⬜ | |
| `.agents/projectContext/plugins/.gitkeep` | ⬜ | |
| `.agents/projectContext/checkpoints/` | ⬜ | Empty dir with .gitkeep |
| `.agents/projectContext/decomposition/` | ⬜ | Empty dir with .gitkeep |

## Phase 3 — New Skills

| Artifact | Status | Notes |
|---|---|---|
| `.agents/skills/decompose/SKILL.md` | ⬜ | 6-phase green-field interview |
| `.agents/skills/context-creation/SKILL.md` | ⬜ | 6-scout subagent approach |
| `.agents/skills/onboard/SKILL.md` | ⬜ | Two-mode conversational |
| `.agents/skills/skill-author/SKILL.md` | ⬜ | 5-phase meta-skill |

## Phase 4 — Abstract Skills (from FUSION originals)

| Artifact | Status | Source |
|---|---|---|
| `.agents/skills/tdd/SKILL.md` | ⬜ | `.claude/skills/fusion-tdd/SKILL.md` |
| `.agents/skills/commit-gate/SKILL.md` | ⬜ | `.claude/skills/fusion-commit-gate/SKILL.md` |
| `.agents/skills/audit-emit/SKILL.md` | ⬜ | `.claude/skills/fusion-audit-emit/SKILL.md` |
| `.agents/skills/decision-lifecycle/SKILL.md` | ⬜ | `.claude/skills/fusion-decision-lifecycle/SKILL.md` |
| `.agents/skills/doc-governance/SKILL.md` | ⬜ | `.claude/skills/fusion-doc-governance/SKILL.md` |
| `.agents/skills/crypto-compliance/SKILL.md` | ⬜ | `.claude/skills/fusion-fips-crypto/SKILL.md` |
| `.agents/skills/secret-handling/SKILL.md` | ⬜ | `.claude/skills/fusion-secret-handling/SKILL.md` |
| `.agents/skills/security-architecture/SKILL.md` | ⬜ | `.claude/skills/fusion-security-architecture/SKILL.md` |
| `.agents/skills/stage-gating/SKILL.md` | ⬜ | `.claude/skills/fusion-stage-gating/SKILL.md` |
| `.agents/skills/arbiter/SKILL.md` | ⬜ | `.claude/skills/fusion-arbiter/SKILL.md` |
| `.agents/skills/arbiter/references/decision-categories.md` | ⬜ | |
| `.agents/skills/arbiter/references/decision-log-format.md` | ⬜ | |
| `.agents/skills/arbiter/references/downstream-artifacts.md` | ⬜ | |
| `.agents/skills/arbiter/references/known-open-decisions.md` | ⬜ | |
| `.agents/skills/arbiter/references/smarts-framework.md` | ⬜ | |

## Phase 5 — Command Definitions (.agents/commands/)

| Artifact | Status |
|---|---|
| `.agents/commands/feature.md` | ⬜ |
| `.agents/commands/fix.md` | ⬜ |
| `.agents/commands/commit.md` | ⬜ |
| `.agents/commands/pr.md` | ⬜ |
| `.agents/commands/review.md` | ⬜ |
| `.agents/commands/threat-model.md` | ⬜ |
| `.agents/commands/adr.md` | ⬜ |
| `.agents/commands/adr-status.md` | ⬜ |
| `.agents/commands/checkpoint.md` | ⬜ |
| `.agents/commands/stage.md` | ⬜ |
| `.agents/commands/btw.md` | ⬜ |
| `.agents/commands/status.md` | ⬜ |
| `.agents/commands/surface-conflict.md` | ⬜ |
| `.agents/commands/add-dep.md` | ⬜ |
| `.agents/commands/override.md` | ⬜ |
| `.agents/commands/onboard.md` | ⬜ |
| `.agents/commands/new-skill.md` | ⬜ |
| `.agents/commands/commands.md` | ⬜ |
| `.agents/commands/init.md` | ⬜ |

## Phase 6 — Agent Definitions (.agents/agents/)

| Artifact | Status | Notes |
|---|---|---|
| `.agents/agents/backend-author.md` | ⬜ | |
| `.agents/agents/frontend-author.md` | ⬜ | NEW — author fresh |
| `.agents/agents/infra-author.md` | ⬜ | NEW — author fresh |
| `.agents/agents/security-reviewer.md` | ⬜ | |
| `.agents/agents/auth-crypto-reviewer.md` | ⬜ | |
| `.agents/agents/migration-reviewer.md` | ⬜ | |
| `.agents/agents/audit-emitter.md` | ⬜ | |
| `.agents/agents/dependency-reviewer.md` | ⬜ | |
| `.agents/agents/trust-zone-reviewer.md` | ⬜ | |
| `.agents/agents/test-audit-reviewer.md` | ⬜ | |
| `.agents/agents/standards-compliance-reviewer.md` | ⬜ | |
| `.agents/agents/architecture-drift-reviewer.md` | ⬜ | |
| `.agents/agents/scaffold-completeness-reviewer.md` | ⬜ | |
| `.agents/agents/decision-challenger.md` | ⬜ | |
| `.agents/agents/finding-triage.md` | ⬜ | |
| `.agents/agents/checkpoint-aggregator.md` | ⬜ | |
| `.agents/agents/grader.md` | ⬜ | Add proper YAML frontmatter |
| `.agents/agents/scout.md` | ⬜ | Add proper YAML frontmatter |

## Phase 7 — Claude Shims

| Artifact | Status |
|---|---|
| `.claude/commands/feature.md` | ⬜ |
| `.claude/commands/fix.md` | ⬜ |
| `.claude/commands/commit.md` | ⬜ |
| `.claude/commands/pr.md` | ⬜ |
| `.claude/commands/review.md` | ⬜ |
| `.claude/commands/threat-model.md` | ⬜ |
| `.claude/commands/adr.md` | ⬜ |
| `.claude/commands/adr-status.md` | ⬜ |
| `.claude/commands/checkpoint.md` | ⬜ |
| `.claude/commands/stage.md` | ⬜ |
| `.claude/commands/btw.md` | ⬜ |
| `.claude/commands/status.md` | ⬜ |
| `.claude/commands/surface-conflict.md` | ⬜ |
| `.claude/commands/add-dep.md` | ⬜ |
| `.claude/commands/override.md` | ⬜ |
| `.claude/commands/onboard.md` | ⬜ |
| `.claude/commands/new-skill.md` | ⬜ |
| `.claude/commands/commands.md` | ⬜ |
| `.claude/commands/init.md` | ⬜ |
| `.claude/agents/backend-author.md` | ⬜ |
| `.claude/agents/frontend-author.md` | ⬜ |
| `.claude/agents/infra-author.md` | ⬜ |
| `.claude/agents/security-reviewer.md` | ⬜ |
| `.claude/agents/auth-crypto-reviewer.md` | ⬜ |
| `.claude/agents/migration-reviewer.md` | ⬜ |
| `.claude/agents/audit-emitter.md` | ⬜ |
| `.claude/agents/dependency-reviewer.md` | ⬜ |
| `.claude/agents/trust-zone-reviewer.md` | ⬜ |
| `.claude/agents/test-audit-reviewer.md` | ⬜ |
| `.claude/agents/standards-compliance-reviewer.md` | ⬜ |
| `.claude/agents/architecture-drift-reviewer.md` | ⬜ |
| `.claude/agents/scaffold-completeness-reviewer.md` | ⬜ |
| `.claude/agents/decision-challenger.md` | ⬜ |
| `.claude/agents/finding-triage.md` | ⬜ |
| `.claude/agents/checkpoint-aggregator.md` | ⬜ |
| `.claude/agents/grader.md` | ⬜ |
| `.claude/agents/scout.md` | ⬜ |

## Phase 8 — Cleanup

| Action | Status |
|---|---|
| Delete `.claude/skills/fusion-*/` | ⬜ |
| Delete old `.claude/commands/` (FUSION-named) | ⬜ |
| Remove old `.claude/agents/` FUSION content | ⬜ |
| Delete `.fusion/` directory (if exists) | ⬜ |
