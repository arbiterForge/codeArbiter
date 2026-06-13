# Changelog

All notable changes to codeArbiter are recorded here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

The plugin is the contents of `plugins/ca/`. Project state under a consumer's `.codearbiter/` is consumer-owned and out of scope for this log. Entries below `2.0.0` predate the plugin rewrite and are grouped by date.

---

## [2.1.0-beta.4] — 2026-06-13 — preview

Session-hygiene sprint: two opt-in repo-hygiene features, built test-first under `subagent-driven-development`. No change to existing gates; both features are dormant in a repo without `arbiter: enabled`.

### Added
- **`/ca:standup` + SessionStart morning briefing** — the SessionStart hook now emits a read-only
  hygiene briefing on the first session of each local calendar day (a one-line offer on later
  sessions), surfacing branch divergence, merged-but-unpruned branches, stale worktrees, and
  stashes/dirty state. The hook only reports; `/ca:standup` performs the cleanups, each under
  per-action confirmation: ff-only pull on a clean tree (refuses on divergence/dirty), prune of
  merged branches (never the current or default branch), removal of stale worktrees, and report-only
  surfacing of stashes/un-pushed work. The remote `git fetch` is detached and non-blocking, so
  session start never awaits the network. New pure-logic module `hooks/_standuplib.py` (porcelain /
  ahead-behind / merged-branch / worktree / stash parsers) with full `unittest` coverage.
- **`/ca:watch <PR>` — PR CI babysitter** — watches a pull request's checks to completion via the
  server-side `gh pr checks --watch` block (zero model tokens while CI runs; not a polling loop). On
  red it diagnoses at a configurable depth (`CODEARBITER_BABYSIT_ONRED`: `propose` (default, no
  tracked-file edit) | `branch` (an unmergeable `spike/fix-*`)). On green it notifies and offers the
  merge — it **never** auto-merges, and a merge into the default branch still routes through the
  merge-to-default hard gate. A global flag `CODEARBITER_BABYSIT` (default off, mirrors
  `CODEARBITER_PRUNE`) auto-attaches a watcher when `/ca:pr` opens a PR; the flag is never set on the
  user's behalf. New `hooks/_babysitlib.py` flag reader with `unittest` coverage.
- **Pruner dry-mode data collection** — `CODEARBITER_PRUNE=dry` now records every would-be prune to
  a shared append-only JSONL log (`~/.codearbiter/metrics/prune-dry.jsonl`, overridable via
  `CODEARBITER_PRUNE_METRICS`): one row per decision across all sessions, each carrying the
  reduction, per-strategy savings, and the validation verdict. Previously the audit log was written
  only on execute, so dry mode left no track record — the evidence base for the `dry`→`on` go/no-go
  decision. Dry-only by design; executed prunes continue to log to `~/.codearbiter/prune.log`.
  Covered by new `unittest` cases in `tests/test_hook.py`.

### Changed
- **`/ca:pr`** — gains a step-6 auto-attach of the CI babysitter, gated on `CODEARBITER_BABYSIT`
  (off by default); a Hard-gate clause forbids auto-attaching a watcher or enabling the flag without
  the user's explicit opt-in.
- **Catalog & routing** — `COMMANDS.md`, `README.md` (catalog + counts 32→34), and the routing table
  gain `/ca:standup` and `/ca:watch` rows.
- **Babysitter flag resolution is now executed, not eyeballed** — `_babysitlib.py` gains a fail-safe
  CLI (`--root`, prints one JSON line, always exits 0); `/ca:pr` and `/ca:watch` invoke it to resolve
  `enabled`/`on_red` instead of re-stating the accepted `on|true|1` spellings and the dormancy gate in
  prose, removing a drift risk. New `unittest` coverage for the CLI path.
- **SH-6 ff-pull gate wired into the live briefing** — `assemble_summary` now computes the
  `ff_pull_eligible` flag via the pure `_standuplib.ff_pull_eligible` helper (clean tree AND behind
  upstream); the SessionStart briefing surfaces it and `/ca:standup` step 1 keys off it rather than
  re-deriving the condition. Previously the helper was tested but never invoked.

### Fixed
- **Audit remediation (pre-tag sweep).** Catalog drift: `COMMANDS.md` advertised a non-existent
  `/ca:statusline [--check]` (actual `install | uninstall | status`) and an incomplete `/ca:init`
  hint; both corrected, and `init.md`'s `argument-hint` gains `--check`. The §6 repeat-redirect "Full
  list" was missing ~8 commands (incl. `/ca:standup`, `/ca:watch`) — now complete. `prune.md` gained
  the `python3 || python` Windows interpreter fallback the other commands already carried. Bare
  `/sprint` command references in `sprint.md`/`override.md` normalized to `/ca:sprint`; `arbiter.md`
  `argument-hint` normalized from `""` to `(none)`.
- **`session-start.py` briefing.** Removed a stale comment claiming the briefing summary is always
  empty (assembly is live); the upstream line no longer prints a misleading "behind 0, ahead 0 (as of
  last fetch)" when there is no tracking branch (now "upstream: none"); the standup default-branch
  override moved off the wrong `FARM_BASE_BRANCH` namespace to `CODEARBITER_BASE_BRANCH`.
- **Statusline `/dev` tell.** Dev mode now shows a textual `[DEV]` badge alongside the full-bar
  redshift, so it reads where color is stripped or unseen.

---

## [2.1.0-beta.3] — 2026-06-13 — preview

Remediation of the 2026-06-13 checkpoint sweep. One sprint, planned hard-gate stops; governance
decisions recorded as user-attributed ADRs.

### Security
- **Validate the resolved API base URL before every fetch** — `farm.ts` previously validated only
  `plan.meta.apiBaseUrl` at parse time, so a `FARM_API_BASE_URL` env override could resolve to
  `http://` and send the `Authorization: Bearer ${FARM_API_KEY}` header over cleartext. The resolved
  base URL (env → plan.meta → default) is now checked by `assertSecureBaseUrl` — HTTPS-only with a
  documented loopback `http://` exception (no userinfo), via WHATWG `URL` parsing (the same parser
  `fetch` uses, so no parser-differential bypass). Error messages never include the key.

### Added
- **`pre-edit.py` hook test suite** — `tests/test_pre_edit.py` covers the H-05 append-only guard
  (overrides.log / triage.log) and the H-11 ADR-marker block/allow paths, including stale-marker and
  Windows path variants.
- **CVE gate in CI** — `npm audit --omit=dev --audit-level=critical` runs in the `tools` job;
  referenced in `tech-stack.md`.
- **Architecture decision records** — `.codearbiter/decisions/` initialized with ADR-0001..0004
  (hybrid governance model, plan.json shell-exec trust boundary, HTTPS-only transport, database-free
  stdlib-only architecture) and a decision log. Status: proposed.

### Changed
- **security-controls.md** — TLS section rewritten around the resolved-URL validation; boundary-
  crossings table gains rows for plan.json/`FARM_MUTATION_CMD` shell execution and the loopback
  `http://` exception.

---

## [2.1.0-beta.2] — 2026-06-12 — preview

### Fixed
- **Pruner: startup self-heal for the write/truncate crash window** — the in-place write protocol
  (deliberately same-inode, so the live CLI's open handle and appends survive) writes the shorter
  image and then truncates; a process death between the two left the file spliced mid-line.
  `self_heal()` now runs at the top of every execute-mode run (hook and CLI): it detects the exact
  splice signature (one unparseable line, file at least backup-sized, byte-identical tail vs. the
  newest session backup in `~/.codearbiter/prune-backups/`), restores the original, and preserves
  any lines the live session appended after the crash. Corruption that does not match the
  signature is left untouched for a human. Logged to `~/.codearbiter/prune.log`.
- **Pruner: rollback no longer eats a concurrent append** — the post-write-validation rollback
  rewrote the original prefix and truncated blindly, destroying a line a live appender added
  after the truncate. The rollback now captures any appended tail first, restores
  original + tail, and skips the truncate if newer bytes landed during the restore (mirroring
  the main path's growth guard).
- **Pruner: `CODEARBITER_PRUNE_KEEP_RECENT` now counts turns, as documented** — the protected
  tail counted tool-bearing *lines* (tool_use and tool_result separately), so `KEEP_RECENT=10`
  protected ~5 turns. Turn anchors are now the assistant tool_use lines, so the setting protects
  exactly the K most recent tool turns (each tool_use plus its results).

---

## [2.1.0-beta.1] — 2026-06-12 — preview

> **Preview release.** The session-transcript pruner ships **off** by default
> (`CODEARBITER_PRUNE=off`). Static analysis and the CLI (`/ca:prune dry/run/audit`) are stable.
> Service mode (`CODEARBITER_PRUNE=on`) is experimental — opt in explicitly and treat it as
> latest-channel until a `2.1.0` stable tag. The pruner never breaks a session (hook always exits 0,
> write protocol has a rollback floor); the experimental label is about signal-loss calibration
> at the aggressive tier, not safety.

### Added
- **Session-transcript pruner** (`/ca:prune`) — trims clutter from Claude Code JSONL transcripts
  at safe quiescence boundaries to extend session lifetime. Ten strategies across three tiers:
  `gentle` (`sidecar-collapse`, `oversize-result-clamp`), `standard` (+ `reasoning-fold`,
  `aged-result-condense`, `mcp-payload-condense`, `shell-tail-keep`), `aggressive`
  (+ `superseded-read-condense`, `repeat-reminder-fold`, `inline-image-evict`). The protected
  tail keeps the K most recent tool-bearing turns verbatim; unknown line types pass through
  byte-identical; 7-check validation battery with rollback; live-race-safe write protocol (re-stat
  abort, same-inode shrink-only, fstat append-check gates `ftruncate`). Typical reduction on a
  tool-heavy transcript: 50–80%; 20–40% on prose-dominated sessions. Backed by
  `hooks/_prunelib.py` + `hooks/prune-transcript.py`; 40+ unit tests across pipeline, validators,
  strategies, write safety, and hook mode.
- **After-each-turn service mode** — `UserPromptSubmit` and `PreCompact` hook entries prune at
  safe quiescence points and always exit 0. A stat short-circuit skips unchanged transcripts
  (`CODEARBITER_PRUNE_MIN_GROWTH` bytes of growth required). Gains land at `claude --resume` /
  restart / next compaction — not the current turn. Ships **off**; enabling is the user's explicit
  choice.
- **Statusline prune segment** — after the pruner runs, `statusline.py` renders `✂ N% · Xs ago`
  (cumulative session reduction, age of last run). Absent until the first prune; fail-soft (never
  makes statusline rendering fail).
- **`/ca:doctor` payload check** — `prune-transcript.py` added to the hook-script completeness
  check so a missing pruner shows as FAIL, not silent omission.

---

## [2.0.1] — 2026-06-10

### Added
- **Fable pricing in the statusline** — `API_PRICES` gains the Fable family ($10/$50 per MTok, standard 1.25×/2×/0.1× cache multipliers) so the `api≈` cost estimate prices Fable-model tokens correctly instead of falling back to Sonnet rates.
- **Fable model pill** — the statusline model pill recognizes the Fable family and renders it gold, the tier above Opus violet; previously an unrecognized Fable model fell through to the grey unknown-model pill.

---

## [2.0.0] — 2026-06-10 — Native Claude Code plugin

The big one. codeArbiter is rebuilt from a ~13,600-line `.agents/` + vendoring framework into a **native Claude Code plugin**. The soul is intact — orchestration, gates, SMARTS, the audit trail — re-grounded on Claude Code's plugin primitives and made leaner and more autonomous. Install with `/plugin marketplace add SUaDtL/codeArbiter` then `/plugin install ca@codearbiter`; commands are namespaced `/ca:<name>`. Pre-release, the whole plugin went through an eight-persona adversarial marketplace-readiness review; everything it surfaced is folded in below.

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
