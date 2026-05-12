# TASK-02: Skills sweep — all SKILL.md files
<!-- TASK-02: CLOSED -->
## Owner: SUBAGENT-A
## Files
All files under /home/user/arbiterRebuild/.agents/skills/ (recursive, all SKILL.md):
- .agents/skills/tdd/SKILL.md
- .agents/skills/commit-gate/SKILL.md
- .agents/skills/audit-emit/SKILL.md
- .agents/skills/secret-handling/SKILL.md
- .agents/skills/crypto-compliance/SKILL.md
- .agents/skills/security-architecture/SKILL.md
- .agents/skills/stage-gating/SKILL.md
- .agents/skills/doc-review-gate/SKILL.md
- .agents/skills/decision-lifecycle/SKILL.md
- .agents/skills/decision-variance/SKILL.md
- .agents/skills/decision-variance/references/*.md (5 files)
- .agents/skills/ticketing-router/SKILL.md
- .agents/skills/ticketing-router/in-repo/SKILL.md
- .agents/skills/ticketing-router/plane/SKILL.md
- .agents/skills/skill-author/SKILL.md
- .agents/skills/refactor/SKILL.md
- .agents/skills/debug/SKILL.md
- .agents/skills/release/SKILL.md
- .agents/skills/observability-emit/SKILL.md
- .agents/skills/observability-emit/templates/observability-spec.md.tmpl
- .agents/skills/rotation/SKILL.md
- .agents/skills/onboard/SKILL.md
- .agents/skills/decompose/SKILL.md
- .agents/skills/context-creation/SKILL.md

## Rule of Thumb
- `.agents/skills/X` → `${FRAMEWORK_ROOT}/.agents/skills/X`
- `.agents/agents/X` → `${FRAMEWORK_ROOT}/.agents/agents/X`
- `.agents/commands/X` → `${FRAMEWORK_ROOT}/.agents/commands/X`
- `.agents/projectContext/X` → `${PROJECT_ROOT}/.agents/projectContext/X`
- `projectContext/X` (bare, without leading .agents/) → `${PROJECT_ROOT}/.agents/projectContext/X`

## Done when
All path references in each file use ${FRAMEWORK_ROOT} or ${PROJECT_ROOT} prefix. No bare `.agents/...` paths remain.
Mark this task CLOSED by changing `<!-- TASK-02: OPEN -->` to `<!-- TASK-02: CLOSED -->`.
