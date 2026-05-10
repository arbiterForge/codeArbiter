# codeArbiter v2 — Portable, Defense-Grade AI Orchestration System
<!-- CORE PURPOSE: This repository's sole mission is to build codeArbiter v2 as described below.
     Every file, commit, and decision in this repo serves this plan.
     If you pick this up mid-session: read this file first, then check CODEARBITER_PROGRESS.md
     for what has been done and where each artifact lives. -->

## Implementation Progress
See `CODEARBITER_PROGRESS.md` for a running log of what has been completed and where.

---

## Context

The FUSION `.claude/` system was built tightly coupled to one project: FUSION's trust zones,
FIPS 140-3, Z-AUDIT event names, Gitea CI, AWS Secrets Manager, `docs/` paths, `.fusion/stage`,
Fastify/Drizzle/Zod, node/adapter domain vocabulary. Every skill says "read `docs/stack.md`"
or "check `.fusion/stage`" — none of it ports to another codebase without rewriting.

**Goal:** Redesign codeArbiter so the orchestration layer (AGENTS.md + `.agents/skills|commands|agents`)
is completely project-agnostic. All project-specific context lives in `.agents/projectContext/` —
an isolated adapter that skills read instead of hardcoded paths. Drop the kit into any repo and it
works after projectContext is populated, either by the decomposition skill (green-field) or the
context-creation skill (existing codebase).

codeArbiter is an orchestrator, never a coder. The user ONLY interacts via slash commands.

---

## What Changes (High-Level)

```
BEFORE (FUSION-specific)                    AFTER (codeArbiter v2)
──────────────────────────────────          ──────────────────────────────────
CLAUDE.md → fusion-core persona             AGENTS.md → canonical provider-agnostic persona
                                            CLAUDE.md → shim: @AGENTS.md (one line)
.claude/skills/fusion-*/SKILL.md            .claude/skills/<generic>/SKILL.md
  ↳ hardcoded docs/, .fusion/stage            ↳ reads .agents/projectContext/* instead
  ↳ FIPS 140-3, AWS SM, Z-AUDIT              ↳ reads projectContext/security-controls.md
  ↳ Fastify/Drizzle/Zod refs                 ↳ reads projectContext/tech-stack.md
  ↳ fusion-node-author (domain-specific)     ↳ moved to projectContext/plugins/
.claude/commands/*.md → FUSION-named         .claude/commands/*.md → generic verbs
(no initialization logic)                   codeArbiter.md §1 → 3-phase init protocol
(no projectContext concept)                 .agents/projectContext/ → project adapter dir
.claude/ holds all AI config               .agents/ holds canonical; .claude/ = shims only
(user talks directly to Claude)             User ONLY via /command → escalating redirect
(no bypass mechanism)                       /override → bypass + append-only audit log
```

---

## Architecture: codeArbiter Installation Layout

**Multi-provider naming strategy:** All canonical AI configuration lives in `.agents/` — a provider-agnostic directory. The persona lives in `AGENTS.md` at repo root (OpenAI Codex auto-loads it). Claude Code gets shim files in `.claude/` that `@`-import the real content from `.agents/`. No canonical definition ever lives in `.claude/` — that directory is shims-only.

**Shim mechanism:** Claude Code supports `@path` imports (relative to project root) in CLAUDE.md and in `.claude/commands/*.md` and `.claude/agents/*.md` files. Each shim file is one line: `@.agents/<category>/<filename>.md`. When Claude Code loads the shim, it inlines the full content from `.agents/`. Paths inside `.agents/` files use project-root-relative `@` references so they resolve correctly regardless of whether they're loaded via shim or directly.

**Skills** live in `.agents/skills/` — they're plain Markdown, not a Claude Code native feature. Commands and agents invoke them by referencing their path via `@`. No shims needed for skills since they're not in a Claude Code discovery directory.

```
any-project/
├── AGENTS.md                           ← CANONICAL PERSONA (OpenAI Codex auto-loads; load directly for any provider)
├── CLAUDE.md                           ← SHIM: "@AGENTS.md" (one line; Claude Code auto-loads → imports AGENTS.md)
├── COMMANDS.md                         ← USER-FACING reference: quick-ref table + per-command detail (no impl depth)
├── .agents/                            ← ALL CANONICAL AI CONFIG (provider-agnostic)
│   ├── agents/                         ← Agent definitions (canonical; see Agent Inventory section)
│   │   ├── backend-author.md           ← reads projectContext/tech-stack.md for stack-specific behavior
│   │   ├── frontend-author.md          ← NEW (FUSION had none); reads projectContext/tech-stack.md
│   │   ├── infra-author.md             ← NEW (IaC/Ansible/containers); reads projectContext/tech-stack.md
│   │   ├── security-reviewer.md
│   │   ├── auth-crypto-reviewer.md     ← reads projectContext/security-controls.md (not hardcoded FIPS)
│   │   ├── migration-reviewer.md
│   │   ├── audit-emitter.md
│   │   ├── dependency-reviewer.md      ← reads projectContext/dependency-policy.md
│   │   ├── trust-zone-reviewer.md      ← reads projectContext/trust-zones.md
│   │   ├── test-audit-reviewer.md      ← reads projectContext/audit-spec.md
│   │   ├── standards-compliance-reviewer.md ← reads projectContext/coding-standards.md
│   │   ├── architecture-drift-reviewer.md ← reads projectContext/decisions/
│   │   ├── scaffold-completeness-reviewer.md
│   │   ├── decision-challenger.md
│   │   ├── finding-triage.md
│   │   ├── checkpoint-aggregator.md    ← writes to projectContext/checkpoints/ (not docs/checkpoints/)
│   │   ├── grader.md                   ← INTERNAL subagent of arbiter skill (no user-facing trigger)
│   │   └── scout.md                    ← INTERNAL subagent of arbiter skill (no user-facing trigger)
│   ├── commands/                       ← Slash command definitions (canonical; see Command Set section)
│   │   ├── feature.md
│   │   ├── fix.md
│   │   ├── commit.md
│   │   ├── pr.md
│   │   ├── review.md
│   │   ├── threat-model.md
│   │   ├── adr.md
│   │   ├── adr-status.md
│   │   ├── checkpoint.md
│   │   ├── stage.md
│   │   ├── btw.md
│   │   ├── status.md
│   │   ├── surface-conflict.md
│   │   ├── add-dep.md
│   │   ├── override.md
│   │   ├── onboard.md                  ← NEW — engineer onboarding / re-explain
│   │   ├── new-skill.md                ← NEW — extend the skill set
│   │   └── commands.md                 ← NEW — display quick-ref command list
│   ├── skills/                         ← Process skills (canonical; no shims needed)
│   │   ├── tdd/SKILL.md                ← 6-phase TDD gate
│   │   ├── commit-gate/SKILL.md
│   │   ├── audit-emit/SKILL.md
│   │   ├── decision-lifecycle/SKILL.md
│   │   ├── doc-governance/SKILL.md
│   │   ├── crypto-compliance/SKILL.md
│   │   ├── secret-handling/SKILL.md
│   │   ├── security-architecture/SKILL.md
│   │   ├── stage-gating/SKILL.md
│   │   ├── arbiter/
│   │   │   ├── SKILL.md
│   │   │   └── references/
│   │   │       ├── decision-categories.md
│   │   │       ├── decision-log-format.md
│   │   │       ├── downstream-artifacts.md
│   │   │       ├── known-open-decisions.md
│   │   │       └── smarts-framework.md
│   │   ├── decompose/SKILL.md
│   │   ├── context-creation/SKILL.md
│   │   ├── onboard/SKILL.md            ← NEW
│   │   └── skill-author/SKILL.md       ← NEW
│   └── projectContext/                 ← PROJECT-SPECIFIC — isolated adapter
│       ├── CONTEXT.md                  ← Project identity, purpose, scope, what it IS NOT
│       ├── tech-stack.md
│       ├── trust-zones.md
│       ├── coding-standards.md
│       ├── audit-spec.md
│       ├── secrets-policy.md
│       ├── security-controls.md
│       ├── dependency-policy.md
│       ├── stage                       ← Integer 1–4
│       ├── open-tasks.md
│       ├── open-questions.md
│       ├── overrides.log               ← APPEND-ONLY override audit trail
│       ├── decisions/
│       │   └── README.md
│       └── plugins/
│           └── .gitkeep
└── .claude/                            ← SHIMS ONLY
    ├── agents/                         ← One shim per agent: "@.agents/agents/<name>.md"
    └── commands/                       ← One shim per command: "@.agents/commands/<name>.md"
```

**Isolation rule (hard):** No canonical file in `.agents/` may reference any path outside `.agents/projectContext/` for project-specific information.

---

## `AGENTS.md` (canonical persona) + `CLAUDE.md` (shim)

`CLAUDE.md` contains exactly one line: `@AGENTS.md`

`AGENTS.md` sections in startup order:
```
§0 Identity & Non-Negotiables
§1 Initialization Protocol   ← THREE-PHASE STARTUP
§2 Conflict Resolution Hierarchy
§3 Hard Rules (generic)
§4 Reference Map (all paths → .agents/projectContext/* paths)
§5 Routing Table (abstract verbs → abstract skills in .agents/skills/)
§6 User Interaction Protocol (slash commands only; Direct-Speech rules)
§7 Override Protocol         ← /override behavior + overrides.log format
```

No FUSION vocabulary anywhere in AGENTS.md. No hardcoded paths outside `.agents/projectContext/`.
No Claude-specific syntax in AGENTS.md — it must read coherently as plain text for any provider.

---

## Three-Phase Initialization Protocol

On every startup, codeArbiter runs this detection sequence BEFORE doing anything else:

```
1. Does .agents/projectContext/CONTEXT.md exist?
   AND does it contain the sentinel <!--INITIALIZED--> marker?
        ↓ YES                                   ↓ NO
   2. Load all projectContext files        3. Does meaningful source code exist?
      (silently, no user prompt)              (files outside .agents/, AGENTS.md, CLAUDE.md,
      Check open-tasks.md                     README.md, .gitignore)
      Present status + skill menu                  ↓ YES            ↓ NO
      → PHASE 3: NORMAL OPERATION          PHASE 2: CONTEXT    PHASE 1: DECOMPOSE
                                           CREATION SKILL      SKILL
```

### Phase 1 — Green-Field: `/decompose`

Invoked when: no projectContext AND no meaningful source code.

Runs the `decompose` skill — codeArbiter steps OUT of orchestrator persona and INTO the
"senior software architect / ruthlessly precise technical lead / decomposition partner"
persona for the duration of the interview.

**Rules of engagement:**
- **Pacing**: ONE LAYER AT A TIME. One focused question at a time within a layer.
- **Three lenses applied to every answer:**
  1. *Vague requirements* — challenge hand-wavy language; force concrete numbers and verbs.
  2. *Hidden complexity* — surface what the user assumes is easy that is actually hard.
  3. *Trade-off forcing* — frame architectural decisions explicitly; do not let the user have it both ways.
- **Integration suggestions** calibrated to confidence (HIGH/MEDIUM/LOW).

**Six interview layers** (run in order):
1. **Vision & Problem** — problem, evidence, primary user, definition of "working", what NOT to build.
2. **Users & Flows** — core journey, non-human actors, failure-mode UX, admin/ops users.
3. **Functional Scope** — every capability challenged, MVP vs v1 vs later, forced closures.
4. **Technical Shape** — components, data entities, state, hard constraints, forced trade-offs.
5. **Integrations & Infrastructure** — every external dependency, existing-system contracts, risks.
6. **Risks & Unknowns** — top 3 build-killing risks, lowest-confidence areas, spikes needed.

**Three canonical artifacts** (saved to `.agents/projectContext/decomposition/`):
1. `01-architecture-breakdown.md`
2. `02-phased-build-plan.md`
3. `03-task-backlog.md`

**Skill phases:**
- Phase 1 — Pre-flight
- Phase 2 — Persona Adoption
- Phase 3 — Layered Interview (Layers 1–6, draft ADRs inline)
- Phase 4 — Synthesis (produce 3 artifacts, user review)
- Phase 5 — projectContext Population (artifact → projectContext mapping)
- Phase 6 — Initialization Lock (write `<!--INITIALIZED-->` sentinel)

**Artifact → projectContext mapping:**

| Source | Destination |
|---|---|
| Layer 1 problem + users + NOT-building | `.agents/projectContext/CONTEXT.md` |
| Layer 4 components + boundaries | `.agents/projectContext/trust-zones.md` |
| Layer 4 stack + hard constraints | `.agents/projectContext/tech-stack.md` |
| Layer 4 compliance + crypto requirements | `.agents/projectContext/security-controls.md` |
| Layer 4 state-change actions | `.agents/projectContext/audit-spec.md` |
| Layer 4 lint/format/naming choices | `.agents/projectContext/coding-standards.md` |
| Layer 5 secret-bearing integrations | `.agents/projectContext/secrets-policy.md` |
| Layer 5 dependency strategy + license stance | `.agents/projectContext/dependency-policy.md` |
| Each Layer 4 major decision | `.agents/projectContext/decisions/000N-*.md` |
| Layer 6 unknowns + spikes | `.agents/projectContext/open-questions.md` |
| Phased Build Plan stage 1 | `projectContext/stage` = 1 |
| Task Backlog | `.agents/projectContext/open-tasks.md` |
| All three artifacts | `.agents/projectContext/decomposition/0{1,2,3}-*.md` |

### Phase 2 — Existing Codebase: `/create-context`

Invoked when: no projectContext AND source code exists.

Dispatches 6 parallel scout subagents (never scans source itself):
- Scout A: package.json / lock files / pyproject.toml / go.mod → tech stack + dependencies
- Scout B: CI/CD configs, Dockerfiles, Makefile, deployment manifests → infra + environments
- Scout C: Source file tree, entry points, module structure → components + architecture
- Scout D: Auth patterns, crypto imports, secrets handling → security posture
- Scout E: Test files, coverage config, test framework → testing conventions
- Scout F: Migration files, schema definitions, ORM usage → data model

Synthesis phase: reads scout reports only (not raw source), synthesizes projectContext.
Gap interview: targeted questions for low-confidence areas.
Same output as Phase 1: complete `.agents/projectContext/`, `<!--INITIALIZED-->` sentinel.

### Phase 3 — Normal Operation

Startup sequence:
1. Silently load all `.agents/projectContext/` files
2. Read `open-tasks.md` for in-flight items
3. Read `open-questions.md` for unresolved CONFIRM-NN items
4. Present: current stage, blocking open questions, in-flight tasks, available /commands

---

## Skill Transformation Map

| Old FUSION Skill | New Generic Name | Key Changes |
|---|---|---|
| `fusion-tdd` | `tdd` | Remove Vitest/Fastify/Z-API/Z-AUDIT refs; read from projectContext |
| `fusion-commit-gate` | `commit-gate` | Remove vitest hardcoding; read test runner from projectContext/tech-stack.md |
| `fusion-audit-emit` | `audit-emit` | Remove Z-AUDIT event names; read audit shape from projectContext/audit-spec.md |
| `fusion-decision-lifecycle` | `decision-lifecycle` | Change docs/decisions/ → .agents/projectContext/decisions/ |
| `fusion-doc-governance` | `doc-governance` | Reads projectContext reference map from AGENTS.md §4 |
| `fusion-fips-crypto` | `crypto-compliance` | Remove FIPS 140-3 hardcoding; read from projectContext/security-controls.md |
| `fusion-secret-handling` | `secret-handling` | Remove AWS SM hardcoding; read from projectContext/secrets-policy.md |
| `fusion-security-architecture` | `security-architecture` | Change docs/architecture/trust-zones.md → projectContext/trust-zones.md |
| `fusion-stage-gating` | `stage-gating` | Change cat .fusion/stage → cat .agents/projectContext/stage |
| `fusion-arbiter` | `arbiter` | Remove FUSION artifact names; generalize to projectContext decomposition artifacts |
| _(new)_ | `decompose` | Green-field project decomposition; produces projectContext |
| _(new)_ | `context-creation` | Reverse-engineers projectContext from existing codebase |
| `fusion-node-author` | _(moved to plugin)_ | .agents/projectContext/plugins/node-author/ |
| _(new)_ | `onboard` | Engineer onboarding + re-explain; two modes |
| _(new)_ | `skill-author` | Gap-challenge → author new skill → routing integration; 5-phase meta-skill |

---

## Agent Inventory (18 total)

| Agent | Type | projectContext reads |
|---|---|---|
| `backend-author` | Implementation | tech-stack.md, audit-spec.md, coding-standards.md |
| `frontend-author` | Implementation (NEW) | tech-stack.md, coding-standards.md |
| `infra-author` | Implementation (NEW) | tech-stack.md, trust-zones.md |
| `security-reviewer` | Review | security-controls.md, trust-zones.md |
| `auth-crypto-reviewer` | Review | security-controls.md |
| `migration-reviewer` | Review | audit-spec.md, dependency-policy.md |
| `audit-emitter` | Review | audit-spec.md |
| `dependency-reviewer` | Review | dependency-policy.md |
| `trust-zone-reviewer` | Review | trust-zones.md |
| `test-audit-reviewer` | Review | audit-spec.md, tech-stack.md |
| `standards-compliance-reviewer` | Review | coding-standards.md |
| `architecture-drift-reviewer` | Review | decisions/ directory |
| `scaffold-completeness-reviewer` | Review | open-tasks.md |
| `decision-challenger` | Pipeline | decisions/ directory |
| `finding-triage` | Pipeline | (reads reviewer reports) |
| `checkpoint-aggregator` | Pipeline | Writes to projectContext/checkpoints/ |
| `grader` | Internal subagent | (invoked by arbiter skill only) |
| `scout` | Internal subagent | (invoked by arbiter/context-creation skills only) |

---

## Skill Structure Standard

Every `SKILL.md` MUST contain these sections:

```markdown
# <skill-name>

## Trigger
## Pre-Flight
## Phases
### Phase N — <Name>
**Goal:** One sentence.
**Inputs:** What the skill reads/receives.
**Actions:** What the skill does.
**Output:** What artifact/state change results.
**Gate:** Hard stop condition.
## Failure Modes
## Subagents Invoked
```

---

## Slash Command Set (18 total)

| Command | Argument | Routes To | Notes |
|---|---|---|---|
| `/feature` | `"description"` | `tdd` skill | Primary dev entry point |
| `/fix` | `"bug description"` | `tdd` skill (bug variant) | Same 6-phase workflow, bug framing |
| `/commit` | _(none)_ | `commit-gate` skill | Only valid commit path |
| `/pr` | `["title"]` | pr-ready sequence | Runs all gates first |
| `/review` | `[path or scope]` | `security-architecture` + reviewer agents | |
| `/threat-model` | `"scope"` | `security-architecture` skill | Pre-implementation |
| `/adr` | `"decision title"` | `decision-lifecycle` skill | Records a new ADR |
| `/adr-status` | `[--adr N]` | `decision-lifecycle` health scan | |
| `/checkpoint` | `[focus]` | All checkpoint agents in parallel | |
| `/stage` | `[target]` | `stage-gating` skill | Promote or report current stage |
| `/add-dep` | `"package"` | `dependency-reviewer` agent | Full vetting before install |
| `/surface-conflict` | `"desc"` | `surface-conflict` command | Stops all work |
| `/btw` | `"question"` | Lightweight Q&A | No state change |
| `/status` | _(none)_ | Reads open-tasks.md + open-questions.md | Read-only |
| `/init` | _(none)_ | Re-runs initialization detection | Repair only |
| `/override` | `"reason"` | Bypass with audit log | Auto-detects git identity |
| `/onboard` | `["scope"]` | `onboard` skill | Two modes: full / targeted |
| `/new-skill` | `"gap description"` | `skill-author` skill | Rigorous gap validation |
| `/commands` | _(none)_ | Reads COMMANDS.md quick-ref | No state change |

---

## Escalating Direct-Speech Redirect

**Strike 1:**
```
Process required. I don't accept direct instructions or questions outside of a
skill channel — that path bypasses the gates that keep the project healthy.

What are you trying to do?
→ Start a feature:          /feature "describe it"
→ Ask a question:           /btw "your question"
→ Fix a bug:                /fix "describe it"
→ Bypass with audit trail:  /override "reason"
→ See everything open:      /status
```

**Strike 2:** Hard gate — command list only, no suggestions.

---

## Override Protocol

`/override "reason"` — permitted bypass with mandatory logging.

Auto-detects user identity in priority order (never asks if any succeeds):
1. `git config user.email` + `git config user.name`
2. `GITHUB_ACTOR` / `GITEA_TOKEN` / `GITEA_ACTOR` environment variables
3. GitHub CLI: `gh auth status` → extract logged-in username
4. If ALL fail → ask: "Please state your name for the override log."

Appends to `.agents/projectContext/overrides.log`:
```
[ISO-8601 timestamp] | BY: <git-user-name> <<git-user-email>> | PLATFORM: <github|gitea|unknown> | GATE: <gate bypassed> | REASON: <user's reason>
```

`overrides.log` is append-only. Never edited or deleted. Committed to repo.

---

## Implementation Order

1. `CLAUDE.md` — one line: `@AGENTS.md`
2. `AGENTS.md` — canonical persona §0–§7
3. `COMMANDS.md` (root) — 19 commands quick-ref + detail sections
4. `.agents/projectContext/` scaffold — stub files with `<!--PLACEHOLDER-->` sentinel
5. New skills (parallel): decompose, context-creation, onboard, skill-author
6. Abstract skills (parallel, read FUSION original first): tdd, commit-gate, audit-emit, decision-lifecycle, doc-governance, crypto-compliance, secret-handling, security-architecture, stage-gating, arbiter
7. `.agents/commands/` — 19 command definitions
8. `.agents/agents/` — 18 agent definitions (including frontend-author, infra-author fresh)
9. `.claude/commands/` shims — 19 files, one line each
10. `.claude/agents/` shims — 18 files, one line each
11. Cleanup — remove old .claude/skills/fusion-*/, old commands/agents, .fusion/ dir

---

## Verification Checklist

1. Empty repo: startup triggers Phase 1 (`/decompose`)
2. Repo with code, no projectContext: startup triggers Phase 2 (`/create-context`)
3. Populated projectContext (sentinel present): startup triggers Phase 3
4. `/feature "test"` → tdd skill invoked; no FUSION vocabulary in output
5. `/commit` → commit-gate reads `projectContext/tech-stack.md` for test runner
6. `/commands` → outputs COMMANDS.md quick-ref; no state change
7. `/onboard` → walks project overview from projectContext; conversational
8. `/new-skill "gap"` → challenge interview; only writes if gap is confirmed real
9. `/override "test"` → auto-detects git identity; appends to overrides.log
10. Direct message → Strike 1 redirect with command list
11. `AGENTS.md` contains no `@path` syntax, no Claude-specific markdown
12. No skill/agent file contains: "fusion", "Z-AUDIT", ".fusion/stage", "docs/stack.md",
    "FIPS 140-3" (except projectContext), "AWS Secrets Manager" (except projectContext),
    "Fastify", "Drizzle", "Vitest" (except projectContext)
13. `grader.md` and `scout.md` have proper YAML frontmatter
14. `frontend-author.md` and `infra-author.md` exist with no hardcoded framework references
