# codeArbiter Commands

All user intent flows through these commands. No direct instructions accepted outside a command channel.

## Read-on-invocation guarantee

This Quick Reference table is the surface scan for commands. Command body specs (`.agents/commands/*.md`) are read ONLY when the corresponding `/command` is invoked. Routine flows MUST NOT bulk-read `.agents/commands/` (see AGENTS.md §3).

---

## Quick Reference

Row shape: `Command | Argument | One-line purpose | Body`. Open a body only when the user invokes the command.

| Command | Argument | One-line purpose | Body |
|---|---|---|---|
| `/feature` | `"description"` | Start a new feature; runs full TDD skill (6 phases) | [body](.agents/commands/feature.md) |
| `/fix` | `"bug description"` | Fix a bug using the same TDD workflow, bug-framed | [body](.agents/commands/fix.md) |
| `/commit` | _(none)_ | Commit staged changes; runs full commit-gate skill | [body](.agents/commands/commit.md) |
| `/pr` | `["title"]` | Open a pull request after all gates pass | [body](.agents/commands/pr.md) |
| `/review` | `[path or scope]` | Security + code review of a path or scope | [body](.agents/commands/review.md) |
| `/threat-model` | `"scope"` | Pre-implementation threat model for a proposed change | [body](.agents/commands/threat-model.md) |
| `/adr` | `"decision title"` | Record a new architectural decision with user attribution | [body](.agents/commands/adr.md) |
| `/adr-status` | `[--adr N]` | Check ADR health — aged, unchallenged, unresolved CONFIRM-NN | [body](.agents/commands/adr-status.md) |
| `/checkpoint` | `[focus]` | Full checkpoint review — all 7 reviewers in parallel | [body](.agents/commands/checkpoint.md) |
| `/stage` | `[target]` | Report current stage or promote to target stage | [body](.agents/commands/stage.md) |
| `/add-dep` | `"package"` | Add a dependency with full vetting before install | [body](.agents/commands/add-dep.md) |
| `/surface-conflict` | `"description"` | Stop all work and surface a rule conflict | [body](.agents/commands/surface-conflict.md) |
| `/ticket` | `"title" \| <sub>` | Optional scope-overflow inbox; in-repo or Plane variant | [body](.agents/commands/ticket.md) |
| `/btw` | `"question"` | Ask a quick question; no state change, lightweight | [body](.agents/commands/btw.md) |
| `/status` | _(none)_ | Show open tasks and unresolved decisions | [body](.agents/commands/status.md) |
| `/init` | _(none)_ | Re-run initialization detection (repair only) | [body](.agents/commands/init.md) |
| `/override` | `"reason"` | Bypass a gate with auto-identity audit log entry | [body](.agents/commands/override.md) |
| `/onboard` | `["scope"]` | Engineer onboarding tour, full or targeted | [body](.agents/commands/onboard.md) |
| `/new-skill` | `"gap description"` | Author a new skill after rigorous gap validation | [body](.agents/commands/new-skill.md) |
| `/commands` | _(none)_ | Show this quick-reference table | [body](.agents/commands/commands.md) |

---

## Command Details

### `/feature "description"`

**Purpose:** Start any new feature. This is the only way to begin implementation work.

**What triggers:** `tdd` skill (`.agents/skills/tdd/SKILL.md`) Phases 1–6, then routes to `backend-author`, `frontend-author`, or `infra-author` agent based on scope.

**Hard gate:** No implementation code before Phase 1 (obligation checklist) is complete.

**When to use:** Any new capability, UI component, API endpoint, infrastructure change, or configuration feature.

**What NOT to use for:** Bug fixes (use `/fix`); questions (use `/btw`); commits (use `/commit`).

---

### `/fix "bug description"`

**Purpose:** Fix a bug with the same rigor as a feature — test written first, root cause confirmed.

**What triggers:** `tdd` skill (bug variant) — same 6-phase workflow, framed around confirming the bug with a failing regression test before touching implementation.

**Hard gate:** Regression test must fail before fix is written (proof the test covers the actual bug).

**When to use:** Any defect, regression, or incorrect behavior confirmed to exist.

---

### `/commit`

**Purpose:** The only permitted path to creating a commit.

**What triggers:** `commit-gate` skill (`.agents/skills/commit-gate/SKILL.md`) — 8 phases including permission gate, branch gate, classification, verification, diff review, selective staging, message, and commit.

**Hard gates:**
- Explicit user instruction required (no speculative commits)
- Current branch MUST NOT be `main`
- All applicable verification gates (test + lint) must exit 0
- `make secrets-scan` runs on every commit regardless of type

**When NOT to use:** There is no alternative commit path. `/commit` is the only way.

---

### `/pr ["title"]`

**Purpose:** Open a pull request after all gates pass.

**What triggers:** pr-ready sequence — runs all BLOCK-level reviews, confirms no open findings, then creates the PR.

**Hard gate:** No PR draft until all BLOCK-level review findings are cleared.

**When to use:** Work is committed on a branch and ready for merge review.

---

### `/review [path or scope]`

**Purpose:** Security and compliance review of existing code at a given path or scope.

**What triggers:** `security-architecture` skill + applicable reviewer agents (`security-reviewer`, `auth-crypto-reviewer`, `standards-compliance-reviewer`, `test-audit-reviewer`).

**When to use:** Before merging any security-sensitive change; when a reviewer requests a specific area be checked; as part of checkpoint preparation.

---

### `/threat-model "scope"`

**Purpose:** Pre-implementation security architecture review for a proposed zone crossing, feature, or attack surface change.

**What triggers:** `security-architecture` skill (`.agents/skills/security-architecture/SKILL.md`).

**When to use:** Before writing code for any change that crosses a trust zone boundary, adds a new external dependency, or modifies authentication/cryptographic behavior. Run BEFORE implementation, not after.

---

### `/adr "decision title"`

**Purpose:** Record a new architectural decision.

**What triggers:** `decision-lifecycle` skill — creates a new ADR file in `projectContext/decisions/`, writes frontmatter, queues for challenge.

**When to use:** Any time a significant architectural, technology, security, or process decision is made that should be durable and auditable.

---

### `/adr-status [--adr N]`

**Purpose:** Check the health of all ADRs or a specific one.

**What triggers:** `decision-lifecycle` skill — scans for aged ADRs (>12 weeks since challenge), unchallenged ADRs, supersession candidates, and unresolved `CONFIRM-NN` items.

**When to use:** Before any stage promotion; at start of a checkpoint; when a `CONFIRM-NN` is encountered.

---

### `/checkpoint [focus]`

**Purpose:** Full checkpoint review of the codebase — all 7 reviewer agents run in parallel.

**What triggers:** All checkpoint agents simultaneously:
1. `architecture-drift-reviewer`
2. `test-audit-reviewer`
3. `security-reviewer`
4. `standards-compliance-reviewer`
5. `scaffold-completeness-reviewer`
6. `decision-challenger`
7. `finding-triage` → `checkpoint-aggregator`

**Hard gate:** All 7 reviewers must complete. No skipping. `checkpoint-aggregator` writes a dated checkpoint document to `projectContext/checkpoints/`.

**When to use:** Before any stage promotion; periodically during development; when `finding-triage` identifies a `BLOCKS_S2` finding.

---

### `/stage [target]`

**Purpose:** Report the current project stage or run the promotion checklist to advance to the next stage.

**What triggers:** `stage-gating` skill (`.agents/skills/stage-gating/SKILL.md`).

**Without argument:** Reports current stage and what gates are satisfied vs. outstanding for the next stage.

**With argument (e.g., `/stage 2`):** Runs the full stage promotion checklist. Requires named approver and all gates passing.

**Hard gate:** No `projectContext/stage` value change without named approver and gate confirmation.

---

### `/add-dep "package"`

**Purpose:** Add a new dependency after full vetting.

**What triggers:** `dependency-reviewer` agent — checks license, provenance, maintenance signal, and supply-chain posture before any install command runs.

**Hard gate:** BLOCK on any denied license. BLOCK on supply-chain concerns. Package is not installed until the reviewer clears it.

**When to use:** Before running any package install command. Do not install first and review later.

---

### `/surface-conflict "description"`

**Purpose:** Stop all work and surface a conflict between AGENTS.md (or projectContext docs) and on-disk code or instructions.

**What triggers:** Immediate STOP. Presents the conflicting sources, quoted passages, and which is more recently updated. All other work halts until the user resolves.

**Hard gate:** This command overrides all other active work. Nothing proceeds while a conflict is open.

**When to use:** Any time you observe a rule in AGENTS.md contradicted by code, by a projectContext doc, or by another rule. Do not silently resolve — always surface.

---

### `/ticket "title" | <subcommand>`

**Purpose:** Optional scope-overflow inbox for subagent findings (in-repo mode) OR project management bridge to Plane (Plane mode). Disabled by default; opt in by editing `projectContext/ticketing-config.md`.

**What triggers:** `ticketing` skill router (`.agents/skills/ticketing/SKILL.md`) — reads `mode` from config and `@`-imports only the active variant (`in-repo/` or `plane/`).

**Subcommands:**
- `/ticket "title" -- "body"` — file a new ticket (subagent or user)
- `/ticket close <id>` — interactive close with disposition prompt
- `/ticket show <id>` — read a ticket body explicitly
- `/ticket list` — surface scan via INDEX (in-repo) or `mcp__plane__list_issues` (Plane)
- `/ticket move <id> <state>` — Plane-only manual transition
- `/ticket config` — edit `ticketing-config.md`

**Hard gates:**
- BLOCK on any `adr-*` disposition. ADRs require user attribution and are authored only via `/adr`.
- BLOCK if `incorporated-to:*` close is recorded without the target doc having been edited in the current session.
- Plane mode never falls back to direct REST. MCP failures append to `ticketing-sync-failures.md` and continue.

**When NOT to use:**
- Decision-worthy concerns: use `/adr` instead of filing a ticket
- Confirmed bugs: use `/fix` instead
- Quick questions: use `/btw`

---

### `/btw "question"`

**Purpose:** Lightweight Q&A channel for quick questions that don't require the full state machine.

**What triggers:** Direct answer from projectContext context. No skill invoked. No state change. No routing table entries fire.

**When to use:** Clarifying questions, quick lookups, asking about a concept, checking a value. NOT for starting work, making decisions, or bypassing gates.

---

### `/status`

**Purpose:** Show everything currently open — in-flight tasks and unresolved decisions.

**What triggers:** Reads `projectContext/open-tasks.md` and `projectContext/open-questions.md`. Read-only. No side effects.

**Output:**
- Current stage
- In-flight tasks (from `open-tasks.md`)
- Unresolved `CONFIRM-NN` items (from `open-questions.md`)
- Any override entries from `overrides.log` in the current session

---

### `/init`

**Purpose:** Re-run the initialization detection sequence.

**When to use:** Only to repair a broken initialization state (e.g., `CONTEXT.md` was manually deleted, the sentinel was accidentally removed, or a new session doesn't detect the project correctly).

**What happens:** Runs the §1 detection sequence from the top. If projectContext is populated but sentinel is missing, asks the user whether to re-initialize (destructive) or just restore the sentinel.

---

### `/override "reason"`

**Purpose:** Bypass a gate or process requirement with a mandatory, append-only audit log entry.

**What triggers:** Identity detection (git config → env vars → CLI → manual prompt), log append to `projectContext/overrides.log`, then proceeds with the overridden action.

**Auto-detected identity:** `git config user.name` + `git config user.email` (tried first). Falls through to env vars, then CLI, then prompt only if all else fails.

**When to use:** When a process gate must be bypassed for a legitimate reason (time pressure, broken environment, explicit approval from a named approver). Every override is permanent, auditable, and visible to all reviewers.

**What NOT to use for:** Routine workarounds. If you find yourself using `/override` repeatedly for the same gate, that gate may need to be updated — use `/new-skill` or `/adr` to address the root cause.

---

### `/onboard ["scope"]`

**Purpose:** Engineer onboarding tour — walks a new team member (or re-explains to a returning one) through the project context, architecture, stage, key ADRs, open questions, and the codeArbiter skill system.

**What triggers:** `onboard` skill (`.agents/skills/onboard/SKILL.md`).

**Two modes:**
- No scope argument: full tour — project overview, architecture, stage, key ADRs, open questions, command system.
- Scope argument (e.g., `/onboard "auth flow"`): deep-dive on a specific area.

**Conversational:** The skill stays in context for follow-up questions. Exit explicitly or start a new command to leave.

---

### `/new-skill "gap description"`

**Purpose:** Author a new skill after rigorous gap validation — ensures new skills address real, recurring gaps.

**What triggers:** `skill-author` skill (`.agents/skills/skill-author/SKILL.md`) — 5-phase process: gap challenge, scope decision, skill authoring, routing integration, validation.

**Hard gate:** Gap must be confirmed real before any skill is written. "I want a skill that..." is not a confirmed gap.

**When to use:** When a recurring process need is not covered by any existing skill and the gap has blocked work at least 3 times (or once with significant impact).

---

### `/commands`

**Purpose:** Display the quick-reference command table (the section at the top of this file).

**What triggers:** Reads `COMMANDS.md` and outputs the Quick Reference table only. No state change.

**When to use:** When you can't remember the exact command syntax or want to see all available commands at a glance.
