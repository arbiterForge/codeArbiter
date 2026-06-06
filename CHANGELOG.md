# Changelog

All notable changes to codeArbiter are recorded here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

The plugin is the contents of `plugins/ca/`. Project state under a consumer's `.codearbiter/` is consumer-owned and out of scope for this log. Entries below `2.0.0` predate the plugin rewrite and are grouped by date.

---

## [2.0.0] — Native Claude Code plugin

The big one. codeArbiter is rebuilt from a ~13,600-line `.agents/` + vendoring framework into a **native Claude Code plugin**. The soul is intact — orchestration, gates, SMARTS, the audit trail, hidden `/dev` — re-grounded on Claude Code's plugin primitives and made leaner and more autonomous. Install with `/plugin marketplace add SUaDtL/codeArbiter` then `/plugin install ca@codearbiter`; commands are namespaced `/ca:<name>`.

### Added
- **Native plugin packaging** — `.claude-plugin/marketplace.json` + the plugin under `plugins/ca/`. No clone-into-your-repo, no symlinks, no shims.
- **Per-repo activation** — a `SessionStart` hook injects the orchestrator persona only in a repo whose `.codearbiter/CONTEXT.md` sets `arbiter: enabled`, and exits silently everywhere else. This single mechanism replaces the entire `CLAUDE.md → AGENTS.md → _includes` chain **and** the monolith-vs-vendored dual mode.
- **Root-level `.codearbiter/` project state** — stage, specs, plans, ADRs, decision log, and the overrides audit trail live at the repo root so they commit with your code and survive uninstalling the plugin. The sole footprint codeArbiter adds to a consumer repo.
- **Spec-driven `/ca:feature`** — brainstorm a spec → plan → test-first build → commit → finish. The only path to implementation.
- **Dynamic-workflow skill layer** — `brainstorming`, `writing-plans`, `executing-plans`, `subagent-driven-development`, `dispatching-parallel-agents`, `finishing-a-development-branch`, `using-git-worktrees`, adapted from [obra/superpowers](https://github.com/obra/superpowers).
- **Hidden `/sprint`** — autonomous sprint mode: brainstorm a spec, then execute the plan deciding "as the user" via SMARTS on every non-hard-gate point, logging each call to `.codearbiter/sprint-log.md`. Hard gates remain true stops.
- **commit-gate behavioral-proof phase** (verification before completion) and a closed reproduce→fix→verify loop in `debug`.
- **Plugin statusline** — token/context/cost segment renders everywhere; the four arbiter segments (stage, open tasks, open questions, overrides-since-checkpoint) render only when `arbiter: enabled`. Wire it with `/ca:statusline`.

### Changed
- **`AGENTS.md` → `ORCHESTRATOR.md`** — terser, high-authority voice, single-source rules, `${CLAUDE_PLUGIN_ROOT}` paths. Persona is hook-injected, not `@import`-loaded.
- **Path model collapsed** — `${FRAMEWORK_ROOT}` → `${CLAUDE_PLUGIN_ROOT}`; `${PROJECT_ROOT}/.agents/projectContext/` → `.codearbiter/`.
- **SMARTS retained and trimmed** — 6 lenses + ADR/decision-log + audit trail kept; the 12-week aging clock and forced challenger dropped.
- **Maturity is a single `stage` value** — a rigor knob, not the old 4-stage promotion machinery.
- **Every skill/command/agent body re-grounded** — ~35–40% prose shrink per skill, every hard gate preserved.

### Removed
- **All portability/vendoring machinery** — `.agents/`↔`.claude/` symlinks, per-file `@import` shims, `/init-vendor`, the `${FRAMEWORK_ROOT}`/`${PROJECT_ROOT}` dual-root scheme, the `AGENTS-CODEARBITER-ROOT` sentinel, `_paths.md`, and `SELF-EDIT-MODE`.
- **Enterprise ceremony** — app-level audit/observability signal emission, the trust-zones doc (folded into `security-controls.md`), the 4-stage promotion model, and the commands `/hotfix`, `/rotate`, `/ticket`, `/stage`, `/onboard`. Two reviewer agents cut (`standards-compliance`, `scaffold-completeness`).
- **The legacy v1 tree** moved to `legacy/` for reference.

---

## [2026-05-13] — token efficiency pass, added missing slash commands, added local context caching to decompose 

Meta-review of the framework: a four-workstream pass on the decompose skill, skill↔command coupling, AGENTS.md preamble weight, and a sanctioned self-edit mode. Plus follow-up commits addressing an independent consistency review and a vendor-pollution cleanup.

### Added
- **`/decision-variance` command** — entry point to the previously orphan `decision-variance` skill. Dispatches `decision-challenger`; requires explicit user attribution for every arbitration choice.
- **`${FRAMEWORK_ROOT}/.agents/skills/INDEX.md`** — skills surface scan with invocation-class annotations (user-invoked / condition-triggered / internal), matching the existing `.agents/agents/INDEX.md` pattern.
- **`${FRAMEWORK_ROOT}/.agents/SELF-EDIT-MODE`** sentinel + AGENTS.md §1 Phase 0 detection — a per-developer toggle (gitignored) that suppresses the H-08 bootstrap nag when the framework is being edited as source rather than consumed. `session-start.sh` Phase 0 detection requires SELF-EDIT-MODE + AGENTS-CODEARBITER-ROOT + monolith layout.
- **`decompose` skill compaction resilience** — new Phase 2.5 init/resume + per-layer disk drafts (`${PROJECT_ROOT}/.agents/projectContext/.decompose-draft/layer-N-*.md`) + Layer 4 immediate `Status: DRAFT` ADR writes + Phase 4 disk-rehydrate clause + Phase 6 draft-directory cleanup gate. The interview now survives auto-compaction with no data loss for completed layers.
- **AGENTS.md §1 Phase 0 — Monolith Self-Edit Detection** documenting the suppression clause.

### Changed
- **AGENTS.md preamble slimmed** by ~75 lines. §0.1.1 Path Resolution, §4 Reference Map, and §5 Routing Table extracted to on-demand bodies (`.agents/commands/_paths.md`, `_reference-map.md`, `_routing-table.md`) following the existing `_redirect.md` pattern. Stubs remain in AGENTS.md with bolded "Loaded when:" callouts.
- **§5 row for `schema-validator`** strengthened to `[OPTIONAL PLUGIN]` — agent body is consumer-supplied, not framework core.
- **§5 condition-only skills** annotated `(condition-triggered, no command)` to disambiguate from user-invoked routes.
- **`decompose` Phase 1** reduced from a "re-do Pre-Flight checks" duplicate to a lightweight "Pre-Flight passed → announce + log entry" step. Pre-Flight section retained (framework structural standard per `skill-author`).
- **`decompose` Phase 5** clarified — DRAFT ADRs written in Layer 4 are now promoted in place to `Status: Accepted` rather than rewritten. Phase 5 source-to-destination mapping notes which files are already on disk from earlier phases.

### Fixed
- **HIGH consistency findings from independent review** — Phase 2 of decompose was asking the Layer 1 question both in Phase 2 AND Phase 2.5 (now Phase 2.5 only); AGENTS.md §4 stub said "twelve rows" but the body has thirteen (corrected); overrides.log entry from this work cycle contained two factual errors — corrected via an append-only audit-fix entry.
- **MEDIUM consistency findings** — three places in `decompose/SKILL.md` misattributed `.decompose-draft/` detection to Pre-Flight; corrected to Phase 2.5 only. Phase 2 Gate language updated from "No gate; this phase is declarative" to describe the actual gate.
- **LOW consistency findings** — Phase 5 ADR template split into two separate code blocks (DRAFT state, Accepted state) to avoid copy-paste hazard; `skills/INDEX.md` tdd row consolidated to `user → /feature, /fix`; "Workstream N" self-references in permanent docs replaced with stable language.

### Removed
- **`.agents/projectContext/decisions/001-ticketing-design.md`** — a real ADR about codeArbiter's own ticketing design was inadvertently shipping in the framework's projectContext, polluting any vendor consumer's submodule clone. Removed from `HEAD` (still present in git history; vendor consumers don't see it in their working tree unless they check out an old commit).
- **Two framework-edit `/override` entries** from `.agents/projectContext/overrides.log`. Log reset to header-only state with a new `FRAMEWORK-SOURCE INTENT` block declaring the framework's published log is intentionally empty.

---

## [2026-05-13] — copyright standards, /decompose, H-08 hook fix

### Added
- `/decompose` command file and registration ([#11](../../pull/11)) — closes a gap where the greenfield-interview skill had no slash-command entry point.
- Copyright header enforcement via checkpoint reviewer ([#9](../../pull/9)) — new files must carry the standard `<!-- Copyright ... -->` header; checkpoint blocks if missing.

### Changed
- Retrofit copyright headers onto all existing framework files ([#10](../../pull/10)).
- Shim file ordering — copyright block moved below the `@path` import line in every `.claude/commands/*.md` shim.

### Fixed
- H-08 source-code check now excludes the vendor tree and framework artifacts ([#13](../../pull/13)) — previously falsed-positive in vendored installs.

---

## [2026-05-12] — ticketing, statusline, perf, expansion

### Added
- **Ticketing skill** ([#3](../../pull/3)) — optional scope-overflow inbox with two variants: lightweight in-repo (`${PROJECT_ROOT}/.agents/projectContext/tickets/`) and Plane MCP integration (on-prem only, API-key auth via env vars). Ships disabled (`enabled: false`); consumers opt in by editing `ticketing-config.md`.
- **Custom Claude Code statusline** ([#4](../../pull/4)) — token-aware status bar surfacing stage / tasks / open questions / git branch / overrides count.
- **Project README and MIT LICENSE** ([#4](../../pull/4)) — first user-facing documentation surface.
- **5 new skills + 4 new commands** ([#6](../../pull/6)) — including `decision-variance`, `doc-review-gate`, `observability-emit`, and others, with a framework-wide terminology lock (§0.1 invariants on `skill` / `agent` / `phase` / `stage` / `layer` / `gate` / `severity` and the `invoke` / `route` / `dispatch` verb triple).
- **`/create-context` command** ([#7](../../pull/7)) — brownfield bootstrap for existing codebases (alongside `/decompose` for greenfield).

### Changed
- **Modular path conventions** ([#7](../../pull/7)) — formal `${FRAMEWORK_ROOT}` vs `${PROJECT_ROOT}` split; framework source uses the former, populated project state uses the latter. Vendored-vs-monolith modes documented in AGENTS.md §0.1.1 (later extracted to `_paths.md`).
- **Install docs added** ([#7](../../pull/7)) — `/init-vendor` command and submodule install instructions.
- **~250 lines cut from AGENTS.md / commands / agents** ([#5](../../pull/5)) — token-efficiency pass; surface-scan INDEX files introduced so routing decisions don't bulk-load `.agents/agents/*.md` or `.agents/commands/*.md`.

---

## [2026-05-10] — foundation

### Added
- **codeArbiter v2 foundation** — initial commit of `AGENTS.md`, `${PROJECT_ROOT}/.agents/projectContext/` scaffold (templates for CONTEXT, tech-stack, security-controls, audit-spec, coding-standards, secrets-policy, dependency-policy, observability-spec, trust-zones, open-questions, open-tasks, stage, decisions/, decomposition/, tickets/, plugins/, checkpoints/), abstract skills, and the `.claude/` shim layer.
- **FUSION `.claude/` system** — routing-table-driven orchestration: every user intent flows through a slash command that fans out to skills and reviewer agents.
- **18 reviewer / author agent definitions** — `auth-crypto-reviewer`, `backend-author`, `frontend-author`, `infra-author`, `migration-reviewer`, `dependency-reviewer`, `security-reviewer`, `trust-zone-reviewer`, `architecture-drift-reviewer`, `coverage-auditor`, `standards-compliance-reviewer`, `scaffold-completeness-reviewer`, `audit-emitter`, `decision-challenger`, `checkpoint-aggregator`, `finding-triage`, `scout`, `grader`.
- **Command catalog** — `/feature`, `/fix`, `/refactor`, `/debug`, `/commit`, `/pr`, `/review`, `/threat-model`, `/adr`, `/adr-status`, `/checkpoint`, `/stage`, `/release`, `/add-dep`, `/rotate`, `/surface-conflict`, `/ticket`, `/btw`, `/status`, `/init`, `/override`, `/hotfix`, `/onboard`, `/new-skill`, `/commands`.
- **`skill-author` skill** — meta-skill enforcing the Skill Structure Standard (Trigger, Pre-Flight, Phases with gates, Failure Modes, Subagents Invoked) for any new skill authored via `/new-skill`.
- **Claude Code hook scripts and `settings.json`** ([#2](../../pull/2)) — `pre-bash.sh`, `pre-edit.sh`, `pre-write.sh`, `post-write-edit.sh`, `session-start.sh`, `statusline.sh`, `statusline-tokens.py`.

### Removed
- `CODEARBITER_PLAN.md` and `CODEARBITER_PROGRESS.md` — superseded by `AGENTS.md` and the projectContext scaffold once v2 was complete.

---

## Maintenance notes

- This changelog is updated by the maintainer (or via `/release` once that workflow is in regular use), not auto-generated. Each entry should describe an outcome a user might notice, not every commit on the way there.
- Once the project cuts versioned releases (SemVer per `release` skill Phase 1), the date headers above will be reorganized under version headers (`## [0.1.0] - 2026-05-10`, etc.) with the trailing `[Unreleased]` section reserved for in-flight work.
- The `[Unreleased]` section currently reflects work on branch `claude/edit-arbiter-meta-pKkTP`. When that branch merges to `main`, the section heading should be promoted to a dated entry.
