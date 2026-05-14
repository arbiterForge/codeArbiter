<!--
Copyright (c) 2026 suadtl
Author: suadtl
Created: 2026-05-10
File: COMMANDS.md
-->

# codeArbiter Commands

All user intent flows through these commands. No direct instructions accepted outside a command channel.

## Read-on-invocation guarantee

This Quick Reference table is the surface scan for commands. Command body specs (`${FRAMEWORK_ROOT}/.agents/commands/*.md`) are read ONLY when the corresponding `/command` is invoked. Routine flows MUST NOT bulk-read `${FRAMEWORK_ROOT}/.agents/commands/` (see AGENTS.md §3).

---

## Quick Reference

Row shape: `Command | Argument | One-line purpose | Body`. Open a body only when the user invokes the command.

| Command | Argument | One-line purpose | Body |
|---|---|---|---|
| `/feature` | `"description"` | Start a new feature; routes to TDD skill (6 phases) | [body](${FRAMEWORK_ROOT}/.agents/commands/feature.md) |
| `/fix` | `"bug description"` | Fix a bug using the same TDD workflow, bug-framed | [body](${FRAMEWORK_ROOT}/.agents/commands/fix.md) |
| `/refactor` | `"surface and motivation"` | Behavior-preserving change; routes to refactor skill (6 phases) | [body](${FRAMEWORK_ROOT}/.agents/commands/refactor.md) |
| `/debug` | `"symptom description"` | Investigate-then-decide RCA; outcomes: /fix, /ticket, or close | [body](${FRAMEWORK_ROOT}/.agents/commands/debug.md) |
| `/commit` | _(none)_ | Commit staged changes; routes to commit-gate skill | [body](${FRAMEWORK_ROOT}/.agents/commands/commit.md) |
| `/pr` | `["title"]` | Open a pull request after all gates pass | [body](${FRAMEWORK_ROOT}/.agents/commands/pr.md) |
| `/review` | `[path or scope]` | Security + code review of a path or scope | [body](${FRAMEWORK_ROOT}/.agents/commands/review.md) |
| `/threat-model` | `"scope"` | Pre-implementation threat model for a proposed change | [body](${FRAMEWORK_ROOT}/.agents/commands/threat-model.md) |
| `/adr` | `"decision title"` | Record a new architectural decision with user attribution | [body](${FRAMEWORK_ROOT}/.agents/commands/adr.md) |
| `/adr-status` | `[--adr N]` | Check ADR health — aged, unchallenged, unresolved CONFIRM-NN | [body](${FRAMEWORK_ROOT}/.agents/commands/adr-status.md) |
| `/checkpoint` | `[focus]` | Full checkpoint review — all 7 reviewers in parallel | [body](${FRAMEWORK_ROOT}/.agents/commands/checkpoint.md) |
| `/stage` | `[target]` | Report current stage or promote to target stage | [body](${FRAMEWORK_ROOT}/.agents/commands/stage.md) |
| `/release` | `["version" \| --auto \| --dry-run]` | SemVer bump, changelog, tag; deployment readiness gate | [body](${FRAMEWORK_ROOT}/.agents/commands/release.md) |
| `/add-dep` | `"package"` | Add a dependency with full vetting before install | [body](${FRAMEWORK_ROOT}/.agents/commands/add-dep.md) |
| `/rotate` | `"artifact-id"` | Rotate a secret/key with cadence + audit + archival gates | [body](${FRAMEWORK_ROOT}/.agents/commands/rotate.md) |
| `/surface-conflict` | `"description"` | Stop all work and surface a rule conflict | [body](${FRAMEWORK_ROOT}/.agents/commands/surface-conflict.md) |
| `/ticket` | `"title" \| <sub>` | Optional scope-overflow inbox; in-repo or Plane variant | [body](${FRAMEWORK_ROOT}/.agents/commands/ticket.md) |
| `/btw` | `"question"` | Ask a quick question; no state change, lightweight | [body](${FRAMEWORK_ROOT}/.agents/commands/btw.md) |
| `/status` | _(none)_ | Show open tasks and unresolved decisions | [body](${FRAMEWORK_ROOT}/.agents/commands/status.md) |
| `/decompose` | _(none)_ | Bootstrap projectContext for a green-field project (no source code yet) | [body](${FRAMEWORK_ROOT}/.agents/commands/decompose.md) |
| `/create-context` | _(none)_ | Bootstrap projectContext for an existing codebase (brownfield init) | [body](${FRAMEWORK_ROOT}/.agents/commands/create-context.md) |
| `/init` | _(none)_ | Re-run initialization detection (repair only) | [body](${FRAMEWORK_ROOT}/.agents/commands/init.md) |
| `/override` | `"reason"` | Bypass a gate with auto-identity audit log entry | [body](${FRAMEWORK_ROOT}/.agents/commands/override.md) |
| `/hotfix` | `"reason" --severity --escalation-tier --auto-revert-window` | Emergency bypass with two-identity audit + post-hoc ADR | [body](${FRAMEWORK_ROOT}/.agents/commands/hotfix.md) |
| `/onboard` | `["scope"]` | Engineer onboarding tour, full or targeted | [body](${FRAMEWORK_ROOT}/.agents/commands/onboard.md) |
| `/new-skill` | `"gap description"` | Author a new skill after rigorous gap validation | [body](${FRAMEWORK_ROOT}/.agents/commands/new-skill.md) |
| `/commands` | _(none)_ | Show this quick-reference table | [body](${FRAMEWORK_ROOT}/.agents/commands/commands.md) |

---

## Command Details

### `/feature "description"`

**Purpose:** Start any new feature. This is the only way to begin implementation work.

**What it routes to:** `tdd` skill (`${FRAMEWORK_ROOT}/.agents/skills/tdd/SKILL.md`) Phases 1–6, which then dispatches `backend-author`, `frontend-author`, or `infra-author` agent based on scope.

**Hard gate:** No implementation code before Phase 1 (obligation checklist) is complete.

**When to use:** Any new capability, UI component, API endpoint, infrastructure change, or configuration feature.

**What NOT to use for:** Bug fixes (use `/fix`); questions (use `/btw`); commits (use `/commit`).

---

### `/fix "bug description"`

**Purpose:** Fix a bug with the same rigor as a feature — test written first, root cause confirmed.

**What it routes to:** `tdd` skill (bug variant) — same 6-phase workflow, framed around confirming the bug with a failing regression test before touching implementation.

**Hard gate:** Regression test must fail before fix is written (proof the test covers the actual bug).

**When to use:** Any defect, regression, or incorrect behavior confirmed to exist.

---

### `/refactor "surface and motivation"`

**Purpose:** Restructure existing code without changing observable behavior. The only permitted path to begin a refactor.

**What it routes to:** `refactor` skill (`${FRAMEWORK_ROOT}/.agents/skills/refactor/SKILL.md`) — Phases 1–6: surface identification, behavioral-parity coverage proof, red parity tests (conditional), implementation, parity verification, lint/coverage gate.

**Hard gate:** No refactor proceeds without behavioral-parity coverage proof in Phase 2. If the named surface is below the stage coverage threshold or any public method has zero direct tests, the skill halts and routes to `tdd` Phase 1 to backfill. A Phase 4 diff that classifies as `feat` or a Phase 5 verification that depends on edits to a pre-existing test re-routes to `/feature` or `/fix`.

**Args:** `"surface and motivation"` — two required parts. The surface MUST name exact files/symbols (a reader can grep and arrive at the same set). The motivation MUST state why the restructure is worth doing.

**When NOT to use:** New behavior, branches, or error paths → `/feature`. A change motivated by "the current behavior is wrong" → `/fix`. Questions → `/btw`.

**Example invocations:**
- `/refactor "extract signToken, verifyToken, rotateKey from src/auth/index.ts into src/auth/tokens.ts so the next rotation feature has a clean seam"`
- `/refactor "collapse duplicated retry-with-backoff in src/http/client.ts and src/ws/client.ts into a shared src/net/retry.ts"`
- `/refactor "split src/payments/processor.ts into processor.ts, validation.ts, settlement.ts without changing the exported Processor signature"`

**See also:** `/feature`, `/fix`, `/commit`.

---

### `/debug "symptom description"`

**Purpose:** Investigate-then-decide root-cause analysis for situations where the cause of a defect is **not yet known**. Distinct from `/fix`, which assumes a known bug with a named regression test obligation.

**What it routes to:** `debug` skill (`${FRAMEWORK_ROOT}/.agents/skills/debug/SKILL.md`) — Phases 1–5: symptom capture, hypothesis generation, evidence gathering, exit decision, handoff.

**Hard gate:** The skill MUST NOT modify code. Code edits belong to `/fix` and `/fix` is only reached after `debug` has named a confirmed bug and a regression test obligation. Phase 1 BLOCKS on missing minimal repro.

**Phase 4 exits (one of three):**
- **Confirmed bug** — handoff to `/fix` with named regression test obligation
- **Design/behavior ambiguity** — escalation to `/ticket` or `/adr`
- **No-action close** — recorded findings, no further work

**Args:** `"symptom description"` — at minimum one sentence stating what the system did. Causes are recorded in Phase 2, not in the invocation.

**When NOT to use:** Known bug with named regression test → `/fix` directly. Design discussion with no failing behavior → `/adr` or `/ticket`. New feature → `/feature`.

**Example invocations:**
- `/debug "auth endpoints returning 500 intermittently since yesterday's deploy — repro unclear"`
- `/debug "payment settlement totals drift by cents under load; off-by-one suspected but unverified"`
- `/debug "users report they cannot log in after password reset, but staging passes end-to-end"`

**See also:** `/fix`, `/ticket`, `/adr`.

---

### `/commit`

**Purpose:** The only permitted path to creating a commit.

**What it routes to:** `commit-gate` skill (`${FRAMEWORK_ROOT}/.agents/skills/commit-gate/SKILL.md`) — 8 phases including permission gate, branch gate, classification, verification, diff review, selective staging, message, and commit.

**Hard gates:**
- Explicit user instruction required (no speculative commits)
- Current branch MUST NOT be `main`
- All applicable verification gates (test + lint) must exit 0
- `make secrets-scan` runs on every commit regardless of type

**When NOT to use:** There is no alternative commit path. `/commit` is the only way.

---

### `/pr ["title"]`

**Purpose:** Open a pull request after all gates pass.

**What it routes to:** pr-ready sequence — dispatches all BLOCK-level reviewer agents, confirms no open findings, then creates the PR.

**Hard gate:** No PR draft until all BLOCK-level review findings are cleared.

**When to use:** Work is committed on a branch and ready for merge review.

---

### `/review [path or scope]`

**Purpose:** Security and compliance review of existing code at a given path or scope.

**What it routes to:** `security-architecture` skill, which dispatches the applicable reviewer agents (`security-reviewer`, `auth-crypto-reviewer`, `standards-compliance-reviewer`, `coverage-auditor`).

**When to use:** Before merging any security-sensitive change; when a reviewer requests a specific area be checked; as part of checkpoint preparation.

---

### `/threat-model "scope"`

**Purpose:** Pre-implementation security architecture review for a proposed zone crossing, feature, or attack surface change.

**What it routes to:** `security-architecture` skill (`${FRAMEWORK_ROOT}/.agents/skills/security-architecture/SKILL.md`).

**When to use:** Before writing code for any change that crosses a trust zone boundary, adds a new external dependency, or modifies authentication/cryptographic behavior. Run BEFORE implementation, not after.

---

### `/adr "decision title"`

**Purpose:** Record a new architectural decision.

**What it routes to:** `decision-lifecycle` skill — creates a new ADR file in `${PROJECT_ROOT}/.agents/projectContext/decisions/`, writes frontmatter, queues for challenge.

**When to use:** Any time a significant architectural, technology, security, or process decision is made that should be durable and auditable.

---

### `/adr-status [--adr N]`

**Purpose:** Check the health of all ADRs or a specific one.

**What it routes to:** `decision-lifecycle` skill — scans for aged ADRs (>12 weeks since challenge), unchallenged ADRs, supersession candidates, and unresolved `CONFIRM-NN` items.

**When to use:** Before any stage promotion; at start of a checkpoint; when a `CONFIRM-NN` is encountered.

---

### `/checkpoint [focus]`

**Purpose:** Full checkpoint review of the codebase — all 7 reviewer agents run in parallel.

**What it dispatches:** All checkpoint agents simultaneously:
1. `architecture-drift-reviewer`
2. `coverage-auditor`
3. `security-reviewer`
4. `standards-compliance-reviewer`
5. `scaffold-completeness-reviewer`
6. `decision-challenger`
7. `finding-triage` → `checkpoint-aggregator`

**Hard gate:** All 7 reviewers must complete. No skipping. `checkpoint-aggregator` writes a dated checkpoint document to `${PROJECT_ROOT}/.agents/projectContext/checkpoints/`.

**When to use:** Before any stage promotion; periodically during development; when `finding-triage` identifies a `BLOCKS_S2` finding.

---

### `/stage [target]`

**Purpose:** Report the current project stage or run the promotion checklist to advance to the next stage.

**What it routes to:** `stage-gating` skill (`${FRAMEWORK_ROOT}/.agents/skills/stage-gating/SKILL.md`).

**Without argument:** Reports current stage and what gates are satisfied vs. outstanding for the next stage.

**With argument (e.g., `/stage 2`):** Runs the full stage promotion checklist. Requires named approver and all gates passing.

**Hard gate:** No `${PROJECT_ROOT}/.agents/projectContext/stage` value change without named approver and gate confirmation.

---

### `/release ["version" | --auto | --dry-run]`

**Purpose:** Compose a tagged, announceable release. The only permitted path to a version tag. A release is a deployment-readiness assertion: the codebase at this SHA satisfies every published threshold for shipping.

**What it routes to:** `release` skill (`${FRAMEWORK_ROOT}/.agents/skills/release/SKILL.md`) — Phases 1–7: pre-flight readiness, checkpoint gate, SemVer version bump, changelog generation, ADR currency check, stage threshold verification, tag and announce. The skill is a gate aggregator and routes to `/checkpoint`, `decision-lifecycle`, and `stage-gating`.

**Hard gate:** No tag is composed without all 7 phases recording PASS. DEFERRED is not PASS. MUST NOT silently downgrade or upgrade SemVer classification. MUST NOT push the tag to a remote without explicit user authorization. Any BLOCK is bypassable only via `/override`.

**Args:**
- `--auto` (default) — version is derived mechanically from `LAST_TAG..HEAD` via Conventional Commits
- `"X.Y.Z"` — explicit version; Phase 3 still classifies the commit log and BLOCKS on disagreement
- `--dry-run` — evaluates all gates, surfaces the readiness report, STOPS before tag composition

**Example invocations:**
- `/release` — default flow, auto-derive version, compose tag if all gates green
- `/release "2.0.0"` — explicit version; Phase 3 BLOCKS if commit log classifies differently
- `/release --dry-run` — full gate evaluation, no tag composed, useful as a pre-flight

**See also:** `/checkpoint`, `/stage`, `/adr-status`.

---

### `/add-dep "package"`

**Purpose:** Add a new dependency after full vetting.

**What it dispatches:** `dependency-reviewer` agent — checks license, provenance, maintenance signal, and supply-chain posture before any install command runs.

**Hard gate:** BLOCK on any denied license. BLOCK on supply-chain concerns. Package is not installed until the reviewer clears it.

**When to use:** Before running any package install command. Do not install first and review later.

---

### `/rotate "artifact-id"`

**Purpose:** Rotate a single rotation-bearing artifact — signing key, OIDC client secret, TLS certificate, API token, or service-account credential — through the full inventory → cadence → plan → audit-emit → archival lifecycle. A rotation without an archival record is treated as credential loss.

**What it routes to:** `rotation` skill (`${FRAMEWORK_ROOT}/.agents/skills/rotation/SKILL.md`) — Phases 1–5: inventory, cadence check, rotation plan, audit emit, archival. Phase 3 routes the proposed replacement primitive through `crypto-compliance` before issuance. Phase 4 routes the rotation event through `audit-emit` in full.

**Hard gates:**
- **Cadence** — past-cadence artifacts MUST enter the rotation plan or be recorded as a `CONFIRM-NN` exception. Silent reconciliation is prohibited.
- **Audit-emit** — `audit-emit` Phase 5 (Test Obligation) MUST complete before Phase 4 exits. Emit MUST route through the canonical sink in `audit-spec.md`.
- **Archival** — the four-fact record (which / when / what / who) MUST be written and the last-rotation timestamp updated before the rotation is marked complete.

**Args:** `"artifact-id"` — the artifact's store reference from `secrets-policy.md`. Never the credential value or a fingerprint of it.

**Default cadences** are defined in `${PROJECT_ROOT}/.agents/projectContext/secrets-policy.md` per artifact category (signing keys, OIDC client secrets, TLS certs, API tokens, service accounts).

**Example invocations:**
- `/rotate "jwt-signer-2025"`
- `/rotate "oidc-client-partner-portal"`
- `/rotate "CN=api.example.internal"`

**See also:** `/add-dep`, `/checkpoint` (may auto-route to `/rotate` for aged artifacts).

---

### `/surface-conflict "description"`

**Purpose:** Stop all work and surface a conflict between AGENTS.md (or projectContext docs) and on-disk code or instructions.

**What it routes to:** Immediate STOP handler. Presents the conflicting sources, quoted passages, and which is more recently updated. All other work halts until the user resolves.

**Hard gate:** This command overrides all other active work. Nothing proceeds while a conflict is open.

**When to use:** Any time you observe a rule in AGENTS.md contradicted by code, by a projectContext doc, or by another rule. Do not silently resolve — always surface.

---

### `/ticket "title" | <subcommand>`

**Purpose:** Optional scope-overflow inbox for subagent findings (in-repo mode) OR project management bridge to Plane (Plane mode). Disabled by default; opt in by editing `${PROJECT_ROOT}/.agents/projectContext/ticketing-config.md`.

**What it routes to:** `ticketing-router` skill (`${FRAMEWORK_ROOT}/.agents/skills/ticketing-router/SKILL.md`) — reads `mode` from config and `@`-imports only the active variant (`in-repo/` or `plane/`).

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

**What it routes to:** Direct answer from projectContext context. No skill invoked. No state change. No routing table entries apply.

**When to use:** Clarifying questions, quick lookups, asking about a concept, checking a value. NOT for starting work, making decisions, or bypassing gates.

---

### `/status`

**Purpose:** Show everything currently open — in-flight tasks and unresolved decisions.

**What it routes to:** Reads `${PROJECT_ROOT}/.agents/projectContext/open-tasks.md` and `${PROJECT_ROOT}/.agents/projectContext/open-questions.md`. Read-only. No side effects.

**Output:**
- Current stage
- In-flight tasks (from `open-tasks.md`)
- Unresolved `CONFIRM-NN` items (from `open-questions.md`)
- Any override entries from `overrides.log` in the current session

---

### `/decompose`

**Purpose:** Green-field projectContext initialization. Conducts a layered interview (Layers 1–6) to elicit purpose, scope, primary users, domain vocabulary, and architectural constraints, then writes the full `${PROJECT_ROOT}/.agents/projectContext/` file set and the `<!--INITIALIZED-->` sentinel.

**What it routes to:** `decompose` skill (`${FRAMEWORK_ROOT}/.agents/skills/decompose/SKILL.md`) — Phases 1–6.

**Two blockers before it runs:** `<!--INITIALIZED-->` must be absent (context not yet created) AND no meaningful source code may be present (otherwise route to `/create-context`).

---

### `/create-context`

**Purpose:** Brownfield projectContext initialization. Dispatches six parallel scouts to read the codebase, synthesizes findings into the full `${PROJECT_ROOT}/.agents/projectContext/` file set, fills gaps via a targeted interview, and writes the `<!--INITIALIZED-->` sentinel.

**What it routes to:** `context-creation` skill (`${FRAMEWORK_ROOT}/.agents/skills/context-creation/SKILL.md`) — Phases 1–6.

**Two blockers before it runs:** `<!--INITIALIZED-->` must be absent (context not yet created) AND meaningful source code must be present (otherwise route to `/decompose`).

---

### `/init`

**Purpose:** Re-run the initialization detection sequence.

**When to use:** Only to repair a broken initialization state (e.g., `CONTEXT.md` was manually deleted, the sentinel was accidentally removed, or a new session doesn't detect the project correctly).

**What happens:** Runs the §1 detection sequence from the top. If projectContext is populated but sentinel is missing, asks the user whether to re-initialize (destructive) or just restore the sentinel.

---

### `/override "reason"`

**Purpose:** Bypass a gate or process requirement with a mandatory, append-only audit log entry.

**What it routes to:** Identity detection (git config → env vars → CLI → manual prompt), log append to `${PROJECT_ROOT}/.agents/projectContext/overrides.log`, then proceeds with the overridden action.

**Auto-detected identity:** `git config user.name` + `git config user.email` (tried first). Falls through to env vars, then CLI, then prompt only if all else fails.

**When to use:** When a process gate must be bypassed for a legitimate reason (time pressure, broken environment, explicit approval from a named approver). Every override is permanent, auditable, and visible to all reviewers.

**What NOT to use for:** Routine workarounds. If you find yourself using `/override` repeatedly for the same gate, that gate may need to be updated — use `/new-skill` or `/adr` to address the root cause.

---

### `/hotfix "reason" --severity --escalation-tier --auto-revert-window`

**Purpose:** Emergency-bypass channel for P0/P1 incidents where waiting on the full gate suite would extend production harm. Unlike `/override` (a per-action escape hatch), `/hotfix` is a **two-person, time-boxed, post-hoc-audited** bypass.

**What it dispatches (inline workflow — no backing skill):** identity detection → second-identity attestation check → log entry written to `${PROJECT_ROOT}/.agents/projectContext/hotfixes.log` (BEFORE bypass applied) → bypass applied → auto-revert deadline recorded → operator surfaced with deadline and post-hoc-ADR obligation.

**Hard gates:**
- **Two-identity** — `--escalation-tier` MUST differ from the auto-detected operator identity. BLOCK on match; there is no flag to disable.
- **Pre-bypass logging** — `hotfixes.log` append MUST precede the bypass action; no silent bypasses.
- **Post-hoc ADR within 72h** — independent of `--auto-revert-window`. `/checkpoint` BLOCKS stage promotion on any entry past `EXPIRES:` with `ADR: pending` or any entry past 72h without an authored ADR.
- **Severity gate** — anything lower than P1 MUST use `/override`, not `/hotfix`.

**Args:**
- `"reason"` — what gate is bypassed and why the incident justifies skipping; vague reasons rejected
- `--severity P0|P1` — required; P0 = customer-facing outage / data integrity event, P1 = severe degradation
- `--escalation-tier <identity>` — the attesting second human (email or username); MUST differ from operator
- `--auto-revert-window 24h|72h|7d` — wall-clock deadline after which `/checkpoint` flags expired-without-followup

**Differences from `/override`:** two identities required (not one); severity flag mandatory; time-boxed; post-hoc ADR mandatory within 72h; separate log file (`hotfixes.log` vs `overrides.log`); BLOCKS stage promotion if expired or ADR-missing.

**Example invocations:**
- `/hotfix "auth service returning 500 for all tenants — rollback blocked by failing migration-reviewer" --severity P0 --escalation-tier "j.smith@example.com" --auto-revert-window 72h`
- `/hotfix "payment webhook signature verification failing after dependency CVE patch — partner traffic dropping" --severity P1 --escalation-tier "ops-lead@example.com" --auto-revert-window 24h`
- `/hotfix "DB connection pool exhausted under unexpected load; need to ship raised limit without standard review window" --severity P1 --escalation-tier "dba@example.com" --auto-revert-window 7d`

**See also:** `/override`, `/adr` (authors the mandatory post-hoc decision record and updates the `hotfixes.log` entry's `ADR:` field), `/checkpoint` (enforces expiration and post-hoc-ADR gates).

---

### `/onboard ["scope"]`

**Purpose:** Engineer onboarding tour — walks a new team member (or re-explains to a returning one) through the project context, architecture, stage, key ADRs, open questions, and the codeArbiter skill system.

**What it routes to:** `onboard` skill (`${FRAMEWORK_ROOT}/.agents/skills/onboard/SKILL.md`).

**Two modes:**
- No scope argument: full tour — project overview, architecture, stage, key ADRs, open questions, command system.
- Scope argument (e.g., `/onboard "auth flow"`): deep-dive on a specific area.

**Conversational:** The skill stays in context for follow-up questions. Exit explicitly or start a new command to leave.

---

### `/new-skill "gap description"`

**Purpose:** Author a new skill after rigorous gap validation — ensures new skills address real, recurring gaps.

**What it routes to:** `skill-author` skill (`${FRAMEWORK_ROOT}/.agents/skills/skill-author/SKILL.md`) — 5-phase process: gap challenge, scope decision, skill authoring, routing integration, validation.

**Hard gate:** Gap must be confirmed real before any skill is written. "I want a skill that..." is not a confirmed gap.

**When to use:** When a recurring process need is not covered by any existing skill and the gap has blocked work at least 3 times (or once with significant impact).

---

### `/commands`

**Purpose:** Display the quick-reference command table (the section at the top of this file).

**What it routes to:** Reads `COMMANDS.md` and outputs the Quick Reference table only. No state change.

**When to use:** When you can't remember the exact command syntax or want to see all available commands at a glance.
