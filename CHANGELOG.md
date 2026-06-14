# Changelog

All notable changes to codeArbiter are recorded here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

The plugin is the contents of `plugins/ca/`. Project state under a consumer's `.codearbiter/` is consumer-owned and out of scope for this log. Entries below `2.0.0` predate the plugin rewrite and are grouped by date.

---

## [2.2.0] — 2026-06-14

### Added
- **`anti-slop-design` reference and `design-quality-reviewer` agent.** A lazy-loaded include bundle
  (`includes/anti-slop-design/`: an INDEX router, an always-loaded core, craft leaves, and per-medium
  leaves for documents, dataviz, slides, web, CLI, and diagrams) that keeps generated user-facing
  output from defaulting to generic AI-slop. A read-only `design-quality-reviewer` enforces it,
  dispatched by `frontend-author` on UI changes; `/ca:pr` and `release` apply the reference inline to
  PR-body and CHANGELOG prose. Governs generated artifacts only, not the framework's own docs.
- **`docs/patterns/lazy-load-bundles.md`** documenting the lazy-load reference-bundle pattern.

### Fixed
- **Statusline subagent rows** show a wider, more useful label: it fills the available row width
  instead of a fixed 22 columns, and is derived from a title-like first line with reminder and
  role-assignment preambles stripped.
- **Statusline honors the `NO_COLOR` environment variable**, and an expired rate-limit reset now reads
  `--` instead of a bare dash.

### Changed
- Unified the five blocking reviewer agents (security, auth-crypto, migration, dependency, coverage)
  onto one output grammar: `CRITICAL`/`HIGH`/`MEDIUM`/`LOW` buckets plus a single gate-status line.
- Tightened public-facing copy: purged em-dash prose separators from the README, plugin README, and
  demo-script, and corrected the agent count to 15.

---

## [2.1.1] — 2026-06-13

### Changed
- **Project moved to the `arbiterForge` GitHub organization.** Canonical home is now
  `github.com/arbiterForge/codeArbiter`. Plugin metadata (`homepage`, `repository`, `author`),
  the self-hosted marketplace `owner`, install instructions, and all doc links point at the new
  org. The old `SUaDtL/codeArbiter` URLs continue to redirect. No behavior, gate, or payload logic
  changed — metadata and documentation only.

---

## [2.1.0] — 2026-06-13

First stable minor since the 2.0 plugin rewrite. Consolidates the `2.1.0-beta.1`…`beta.6`
pre-releases into one release. Everything here ships **stable and dormant-by-default** (inert in a
repo without `arbiter: enabled`). Per-feature maturity is governed by the **Feature Forge**, not by
the version string: the session-transcript pruner is the lone **`preview`** feature — opt-in via
`CODEARBITER_PRUNE`, promoted by real-world data, never on by default. See *Feature Forge* in the
README. The per-beta history remains in the git tag log.

### Added
- **`/ca:standup` + SessionStart morning briefing** — read-only hygiene briefing on the first session
  of each local day (a one-line offer thereafter): branch divergence, merged-but-unpruned branches,
  stale worktrees, stashes/dirty state. The hook only reports; `/ca:standup` performs cleanups under
  per-action confirmation (ff-only pull on a clean tree, prune of merged branches — never current or
  default, stale-worktree removal, report-only stashes). Remote `git fetch` is detached and
  non-blocking. New `hooks/_standuplib.py` with full `unittest` coverage.
- **`/ca:watch <PR>` — PR CI babysitter** — watches a PR's checks to completion via server-side
  `gh pr checks --watch` (zero model tokens while CI runs). On red it diagnoses
  (`CODEARBITER_BABYSIT_ONRED`: `propose` default | `branch`); on green it notifies and offers the
  merge — **never** auto-merges, and a default-branch merge still routes through the hard gate. Global
  `CODEARBITER_BABYSIT` (default off) auto-attaches a watcher when `/ca:pr` opens a PR; never set on
  the user's behalf. New `hooks/_babysitlib.py` with `unittest` coverage.
- **Session-transcript pruner** (`/ca:prune`) — *Feature Forge preview, ships off.* Trims clutter from
  Claude Code JSONL transcripts at safe quiescence boundaries. Ten strategies across `gentle` /
  `standard` / `aggressive` tiers; protected tail keeps the K most recent tool turns verbatim; unknown
  line types pass through byte-identical; 7-check validation battery with rollback; live-race-safe
  write protocol. After-each-turn service mode (`UserPromptSubmit` / `PreCompact`, gains land at
  resume/compaction, off by default), a `✂ N% · Xs ago` statusline segment, and a `/ca:doctor` payload
  check. Dry mode (`CODEARBITER_PRUNE=dry`) records every would-be prune to an append-only JSONL log
  (`~/.codearbiter/metrics/prune-dry.jsonl`) — sizes/savings/verdicts only, **no transcript content** —
  the evidence base for the `dry → on` go/no-go. Backed by `hooks/_prunelib.py`; 40+ unit tests.
- **Feature Forge** (README) — a section with its own hero (`docs/feature-forge.svg`) framing preview
  features as opt-in, dormant, and promoted by real-world data; plus a `Feature Forge: prune data`
  issue form and chooser config so returning a `dry` log is drag-attach-submit. Demo shot list
  (`docs/demo-script.md`) and a README placeholder for an in-motion GIF.
- **Spinner verbs** wired during plugin install/uninstall.
- **`pre-edit.py` hook test suite** (`tests/test_pre_edit.py`) — H-05 append-only guard and H-11
  ADR-marker paths, including stale-marker and Windows-path variants.
- **CVE gate in CI** — `npm audit --omit=dev --audit-level=critical` in the `tools` job.
- **Architecture decision records** — `.codearbiter/decisions/` with ADR-0001..0004 and a decision log.

### Changed
- **Plugin storefront** (`plugins/ca/README.md`) and the README **configuration table** split so
  preview opt-ins (prune) sit under Feature Forge, not beside blessed flags. A collapsible README
  worked-example now *shows* a real `/ca:fix → commit → pr` flow.
- **Catalog & routing** — `COMMANDS.md`, `README.md` (counts 32→34), and the routing table gain
  `/ca:standup` and `/ca:watch`.
- **security-controls.md** — TLS section rewritten around resolved-URL validation; boundary-crossings
  table gains plan.json/`FARM_MUTATION_CMD` shell-exec and the loopback `http://` exception rows.
- **Babysitter flag resolution is executed, not eyeballed** — `_babysitlib.py` gains a fail-safe CLI;
  `/ca:pr` and `/ca:watch` invoke it instead of restating spellings in prose.
- **SH-6 ff-pull gate wired into the live briefing** — `assemble_summary` computes `ff_pull_eligible`
  via the pure helper rather than re-deriving the condition.

### Fixed
- **Statusline self-heals across plugin updates** — the SessionStart hook refreshes a
  codeArbiter-owned pin to the current renderer path each session, persisting only on a real change,
  leaving third-party statuslines untouched, and degrading silently on any error. New `refresh` action
  on `wire-statusline.py` and `heal_statusline_wiring()` in `session-start.py`, both `unittest`-covered.
- **Cold-install hook test no longer clobbers the developer's global statusline** — `scenario_env` now
  sandboxes `HOME`/`USERPROFILE` so a hook's `~/.claude/settings.json` write cannot escape into real
  user state.
- **Pruner robustness** — startup self-heal for the write/truncate crash window; rollback no longer
  eats a concurrent append; `CODEARBITER_PRUNE_KEEP_RECENT` counts turns as documented.
- **Audit remediation (pre-tag sweep)** — catalog drift in `COMMANDS.md`/`init.md`, the §6
  repeat-redirect command list completed, `prune.md` Windows interpreter fallback, `/sprint`→`/ca:sprint`
  normalization; `session-start.py` briefing comment/upstream-line/base-branch-namespace fixes; a
  textual `[DEV]` statusline badge for where color is stripped.

### Security
- **Validate the resolved API base URL before every fetch** — `farm.ts` now checks the resolved base
  URL (env → plan.meta → default) via `assertSecureBaseUrl` (HTTPS-only, documented loopback `http://`
  exception, WHATWG `URL` parsing), closing a path where a `FARM_API_BASE_URL` override could send the
  `Authorization: Bearer` header over cleartext. Error messages never include the key.

---

## [2.0.1] — 2026-06-10

### Added
- **Fable pricing in the statusline** — `API_PRICES` gains the Fable family ($10/$50 per MTok, standard 1.25×/2×/0.1× cache multipliers) so the `api≈` cost estimate prices Fable-model tokens correctly instead of falling back to Sonnet rates.
- **Fable model pill** — the statusline model pill recognizes the Fable family and renders it gold, the tier above Opus violet; previously an unrecognized Fable model fell through to the grey unknown-model pill.

---

## [2.0.0] — 2026-06-10 — Native Claude Code plugin

The big one. codeArbiter is rebuilt from a ~13,600-line `.agents/` + vendoring framework into a **native Claude Code plugin**. The soul is intact — orchestration, gates, SMARTS, the audit trail — re-grounded on Claude Code's plugin primitives and made leaner and more autonomous. Install with `/plugin marketplace add arbiterForge/codeArbiter` then `/plugin install ca@codearbiter`; commands are namespaced `/ca:<name>`. Pre-release, the whole plugin went through an eight-persona adversarial marketplace-readiness review; everything it surfaced is folded in below.

### Added
- **Native plugin packaging** — `.claude-plugin/marketplace.json` + the plugin under `plugins/ca/`. No clone-into-your-repo, no symlinks, no shims.
- **Per-repo activation** — a `SessionStart` hook injects the orchestrator persona only in a repo whose `.codearbiter/CONTEXT.md` sets `arbiter: enabled`, and exits silently everywhere else. This single mechanism replaces the entire `CLAUDE.md → AGENTS.md → _includes` chain **and** the monolith-vs-vendored dual mode.
- **Root-level `.codearbiter/` project state** — stage, specs, plans, ADRs, decision log, and the overrides audit trail live at the repo root so they commit with your code and survive uninstalling the plugin. The sole footprint codeArbiter adds to a consumer repo.
- **Spec-driven `/ca:feature`** — brainstorm a spec → plan → test-first build → commit → finish. The only path to implementation.
- **Dynamic-workflow skill layer** — `brainstorming`, `writing-plans`, `executing-plans`, `subagent-driven-development`, `dispatching-parallel-agents`, `finishing-a-development-branch`, `using-git-worktrees`, adapted from [obra/superpowers](https://github.com/obra/superpowers).
- **`/ca:sprint`** — the flagship autonomy mode: brainstorm a spec (the one interactive gate), then execute the plan deciding "as the user" via SMARTS on every non-hard-gate point, logging each call with a confidence flag to `.codearbiter/sprint-log.md`. Hard gates — security, crypto/secrets, irreversible ops, merge-to-default — remain true stops.
- **`/ca:dev` / `/ca:arbiter`** — maintainer override for editing codeArbiter itself, env-gated behind `CODEARBITER_DEV=1` with entry/exit logged to `overrides.log`. Fully documented; nothing in the plugin is hidden from its operator.
- **`/ca:chore` and `/ca:spike`** — sanctioned lanes for non-behavioral work (docs edits, dependency bumps, reverts — type-scaled gates) and for throwaway exploration (a `spike/*` branch that can never merge; exits to a findings note or `/ca:feature`).
- **`/ca:feature` small lane** — a logged change-class triage (Step 0): small changes meeting four mechanical criteria skip the brainstorm/plan ceremony and go straight to `tdd` after a one-reply mini-spec confirmation. Every classification is appended to `.codearbiter/triage.log`, which the hooks guard append-only like `overrides.log`.
- **`/ca:audit`** — the promotion packet: assembles commits, overrides (verbatim), triage classifications, ADRs with attribution, sprint auto-decisions, open `CONFIRM-NN`s, and open checkpoint findings for a window into `.codearbiter/audits/<date>.md`. Read-only; never overwrites a packet.
- **Live ADRs** — an optional `governs:` path-glob field on ADRs; the post-write hook surfaces "this file is governed by ADR-NNNN" on any matching Write/Edit, so accepted decisions push back at edit time instead of waiting for a checkpoint sweep.
- **SMARTS precedent row** — each variance table cites the 1–3 most-similar prior decisions from the project's own decision log and the observed lens pattern ("Precedent: none on record" on thin history).
- **Mechanical hook hardening** — every enforcement hook is gated on `arbiter: enabled` (the dormancy promise is now mechanically true); hooks match the PowerShell tool as well as Bash; a `python3`→`python` fallback chain keeps gates alive on stock Windows; UTF-8 stdout guards; Windows backslash-path normalization; git guards tolerate global flags and catch `commit -a`, `--force-with-lease`, forcing refspecs, and `git add --all`; the audit logs are protected against truncation, deletion, and non-append edits.
- **Enforcement layer red-teamed pre-release** — six verified bypasses closed: directory/glob/pathspec-magic staging (`git add src/`, `git add *`, `-u`); audit-log rewrites via `truncate`/`tee`/`cp`/`dd`/`sed -i`; shell-authored ADRs (`echo > .codearbiter/decisions/…`); pushes whose refspec lands on `main` (`git push origin HEAD:main`); a fail-open UTF-8 decode in the security diff scan; and the 30-minute TOCTOU window in the crypto/secret commit gate — the gate-pass marker is now **diff-bound** (`hooks/security-pass.py` records a digest of every sensitive line the gate approved; a pass for one diff cannot launder a different one). Proven by a 62-assertion guard-logic CI matrix on 3 OSes, alongside the 110-assertion cold-install interpreter matrix.
- **`/ca:doctor`** — install health, proven not assumed: interpreter resolution (including the Microsoft Store `python3` stub), payload integrity, stale plugin-cache siblings, repo activation state, git identity, statusline wiring — then a live-fire probe (`git add --all --dry-run` must come back `BLOCKED [H-03]`) that catches the silent-dormancy failure the static checks can't.
- **Pipeline resume** — plans carry a per-task `status` column; acceptance is recorded to the plan file, not just conversation context; an interrupted `/ca:feature` or `/ca:sprint` re-enters at the first unaccepted task (never re-brainstorms an approved spec); `/ca:status` lists every pipeline with its progress.
- **Version-bump CI guard** — a PR changing the plugin payload on an already-published version fails CI, because `claude plugin update` no-ops on an unchanged version string and installed users would silently keep the old payload.
- **commit-gate behavioral-proof phase** (verification before completion) and a closed reproduce→fix→verify loop in `debug`.
- **Plugin statusline** — token/context/cost segment renders everywhere; the four arbiter segments (stage, open tasks, open questions, overrides-since-checkpoint) render only when `arbiter: enabled`. Wire it with `/ca:statusline`.

### Changed
- **`AGENTS.md` → `ORCHESTRATOR.md`** — terser, high-authority voice, single-source rules, `${CLAUDE_PLUGIN_ROOT}` paths. Persona is hook-injected, not `@import`-loaded.
- **Path model collapsed** — `${FRAMEWORK_ROOT}` → `${CLAUDE_PLUGIN_ROOT}`; `${PROJECT_ROOT}/.agents/projectContext/` → `.codearbiter/`.
- **SMARTS retained and trimmed** — 6 lenses + ADR/decision-log + audit trail kept; the 12-week aging clock and forced challenger dropped.
- **Maturity is a single `stage` value** — a rigor knob, not the old 4-stage promotion machinery.
- **Every skill/command/agent body re-grounded** — ~35–40% prose shrink per skill, every hard gate preserved.
- **Tone pass on the user-facing surfaces** — the off-channel redirect now leads with routing help and a pre-filled command instead of a refusal ("Strike 1/2" is gone); the persona holds the gates without being adversarial toward the operator; a user-facing glossary (stage, gate, phase, `CONFIRM-NN`, SMARTS, …) ships in `COMMANDS.md`.
- **Review-stop economics** — `tdd` Phase 1 auto-passes obligations that map one-to-one onto the already-approved spec (user reviews only beyond-spec additions); `executing-plans` drops the redundant breakdown acknowledgment; quality review runs once per batch over the combined diff. Roughly 7 interactive stops → 4 for a small feature, with no gate weakened.
- **Crypto gate tuned** — benign `crypto.randomUUID`/`getRandomValues` no longer trip the commit gate; signing, key-derivation, `randomBytes`, `subtle`, and password-hashing changes still do.

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
- `[2.0.0]` froze when `v2.0.0` was tagged (2026-06-10). New work accumulates in a fresh section above it; any change to the shipped payload (`plugins/ca/**`) must ride a version bump — CI enforces this against published versions.
