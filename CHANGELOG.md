# Changelog

All notable changes to codeArbiter are recorded here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

The plugin is the contents of `plugins/ca/`. Project state under a consumer's `.codearbiter/` is consumer-owned and out of scope for this log. Entries below `2.0.0` predate the plugin rewrite and are grouped by date.

---

## [2.6.1] — 2026-07-01

A security-hardening release. Five P1 reports (thanks to @tg12) showed the enforcement layer being enforced against a forgeable or lexical surface (a writable activation file, writable gate markers, raw path strings, a literal command string, an env-controlled delete root) rather than the real underlying operation. Each is closed, and the rest of the repo was swept for the same class in every case. Also fixes a task-id parsing gap and finishes two stale AGPLv3 relicense surfaces.

### Security
- **The activation switch can no longer be flipped off from inside the repo it governs (#159).** Every enforcement hook stays dormant unless `.codearbiter/CONTEXT.md` frontmatter reads `arbiter: enabled`, yet nothing protected that file, so writing `arbiter: disabled` (or corrupting the frontmatter) silenced every gate. The Write/Edit guards (H-18) now block a CONTEXT.md change whose resulting content drops `arbiter: enabled` or breaks the frontmatter, and the Bash pre-hook blocks the shell flank. A legitimate `stage:` change that keeps the flag enabled still passes.
- **Gate-pass markers can no longer be forged by a direct write (#160).** The `.codearbiter/.markers/` tokens that turn a hard BLOCK into an allow were ordinary writable repo files, so a hand-written marker forged a security, migration, or ADR gate pass. The Write/Edit guards (H-19) now block tool writes to any marker, and the Bash pre-hook blocks shell redirects and file verbs naming `security-gate-passed` or `migration-gate-passed`. The sanctioned recorder scripts and the `/ca:adr` authoring marker still work.
- **Symlink aliases no longer bypass the audit-log and ADR guards (#162).** The Write and Edit guards classified the raw `file_path`, so a symlink whose visible path lacked `.codearbiter/` slipped a write onto an append-only audit log or an immutable ADR. Every protected-path check now resolves the real path (the approach the Read and post-write hooks already used) and matches both the raw and resolved forms. `NotebookEdit`, previously wired to no hook, is now covered too.
- **Git mutations are enforced below the command spelling (#161).** The Bash pre-hook gates `git commit`, `push`, and `add` by matching the literal command string, so shell indirection such as `g=git; c=commit; $g $c` built a real commit the hook never saw, with no enforcement beneath it. codeArbiter now installs repo-level `pre-commit` and `pre-push` hooks that enforce the protected-branch, force-push, and crypto/secret/migration gates at the git operation itself, where spelling no longer matters. They reuse the same detection primitives as the Bash hook so the two cannot drift, never overwrite a pre-existing hook, and install idempotently at init and on session start.
- **Farm worktree deletes are contained to the repo-scoped farm root (#163).** The dispatcher resolved a worktree path from the env-controlled `FARM_WORKTREE_ROOT` plus a plan-controlled task id and recursively force-deleted it before git validated it, so a broad or misconfigured root plus a plausible id could delete an unrelated directory. The resolved root must now live inside the repository unless `FARM_ALLOW_EXTERNAL_WORKTREE_ROOT=1` is set, every worktree path is asserted strictly inside that root before deletion, and the reserved ids `.` and `..` are rejected.

### Fixed
- **A mistyped multi-part `--id` no longer strands a task (#158).** `/ca:task add --id` accepted a value with more than two dot-separated parts and minted an un-targetable four-segment id that start/done could not reach and the board linter could not see. The id is now validated as a single `GROUP.TYPE` pair and rejected with a clear message otherwise, and the board reader recognizes an over-segmented id so it can be surfaced and repaired.
- **Release-skill changelog heading and license declarations aligned (#151).** The `/ca:release` skill now documents the Keep-a-Changelog `## [X.Y.Z]` heading the repo and its release guards use, replacing the last reference to the bare `## vX.Y.Z` form. The plugin manifest now declares `AGPL-3.0-only` (correcting a stale `MIT`), and the README license notice no longer implies a commercial license is currently on offer, completing the AGPLv3 relicense across those surfaces.

---

## [2.6.0] — 2026-06-27

codeArbiter 2.6.0 spans several tracks. The headline additions are context-drift provenance (passive drift detection, a coarse code map, and commit-gate auto-heal) and file-scoped just-in-time context injection, which surfaces the governing decision, control, or spec at the moment an agent reads a file. The `--farm` preview gains best-of-N sampling and iterative retries for first-time-go accuracy, and commit-gate now lands task-board transitions atomically with the work (ADR-0008). This release also relicenses the project from MIT to AGPLv3 with a proprietary dual-licensing path; see the License note under Changed.

### Added
- **Best-of-N sampling against the gate (`FARM_SAMPLES`, default 1).** Because the gate is a deterministic pass/fail oracle and each task runs in an isolated worktree, N candidates are drawn in parallel and the first to pass the gate is accepted. Each sample runs in its own scratch worktree cut from the integration HEAD; the winner's files are taken into the task worktree and merged, the losers discarded. Total in-flight worker calls never exceed `FARM_CONCURRENCY` — a shared limiter, so sampling shares the budget rather than multiplying it. `FARM_SAMPLES=1` is byte-for-byte today's single-candidate path (pinned by a regression test). (report F1)
- **Sampling parameters on the worker call (`FARM_TEMPERATURE`, `FARM_MAX_TOKENS`).** The chat body now carries `temperature` (default 0; auto-bumped to 0.7 when `FARM_SAMPLES>1` so samples diversify) and an optional `max_tokens` cap (default unset = provider default, today's behavior). (report F4)
- **Best-of-N cost transparency.** `farm-report.json` records both the summed sample-token spend and the accepted candidate's own tokens (`acceptedPromptTokens`/`acceptedCompletionTokens`), so the N×-tokens trade-off is visible rather than hidden. (report F1)
- **Task-board transitions land atomically with the work (ADR-0008, #142).** commit-gate is now the single board-sync chokepoint. A done-flip `[~]`→`[x]`, start-flip `[ ]`→`[~]`, or a single queued add to `open-tasks.md` is recognized by a new `_taskboardlib.classify_board_diff` classifier, retained by commit-gate Phase 6 (not flagged as scope creep), and staged by Phase 7 into the same commit as the work — so the flip is invisible on `main` until merge, then lands atomically, and an abandoned PR abandons the flip with it. No more lagging `chore(board)` PR or cross-session board drift. A new `/ca:standup` advisory drift sweep (`hooks/boardsync.py reconcile`, read-only and best-effort) surfaces any merged-but-not-flipped task; the fix still routes through `/ca:task`.
- **Context-drift detection, a code map, and commit-gate auto-heal (#145).** codeArbiter records which source files back each derived `.codearbiter/` doc. When a tracked source changes, a single SessionStart line flags the drift, `.codearbiter/code-map.md` gives a coarse orientation map, commit-gate auto-heal re-baselines the provenance or proposes a doc update with the work commit, and `/ca:context-check` runs the audit on demand. A drifted claim is suppressed rather than surfaced as if it were fresh.
- **File-scoped just-in-time context injection (#146).** A `PreToolUse:Read` hook injects a budgeted (≤150-token), freshness-gated pointer to the security control, accepted ADR, approved spec, or fresh provenance claim that governs the file being read, in that priority order, then always allows the Read. A non-governed Read injects nothing and makes no git call. A spec opts in with an optional `**Governs:**` header line.

### Changed
- **Retries are now iterative.** On a retry — a failed gate, or a sampling round with no green — the worker is shown its own previous in-scope output, not just the gate-failure tail, so it refines rather than restarts blind. The prior output rides the same `FARM_ENRICH_MAX_BYTES` byte-cap and secret-redaction chokepoint as all injected context; out-of-scope drift is never carried forward. (report F2)
- **The follow-up harvest runs pre-commit.** commit-gate's raise-new harvest moved from after-the-commit to Phase 7 before staging, so a discovered follow-up task rides the work commit as a contingent default; a follow-up that must survive PR abandonment is filed as a GitHub issue instead of the board. (ADR-0008, #142)
- **Relicensed from MIT to AGPLv3 with proprietary dual-licensing (#147, ADR-0009).** The open-source distribution moves to the GNU AGPLv3, whose network-use clause closes the hosted-fork loophole that MIT leaves open. Copyright is held solely by the owner, who reserves a proprietary dual-licensing path for a planned closed-source SaaS; future contributions require a CLA (see `CLA.md`). The change is forward-only, so code already published under MIT stays available under MIT. This supersedes ADR-0006's broad-adoption posture. See `LICENSE` and the README for the full terms.

### Fixed
- **Mutation-hook least privilege (#143).** The pluggable mutation hook (`FARM_MUTATION_CMD`) no longer inherits the dispatcher's API key or OAuth token, giving it least-privilege parity with every other child command.
- **Heredoc commit messages (#139).** The commit gate no longer false-blocks a multi-line `git commit -F - <<EOF` commit message (H-09b).
- **`/ca:release` hardening (#138).** The release skill resolves the baseline tag, the notes heading, release-date consistency, and half-finished-publish recovery through tested helpers, and rebuilds `farm.js` unconditionally on every release.

---

## [2.5.2] — 2026-06-25

Deep-review (`docs/reports/2026-06-24-root/`) remediation, in two parts. The quick-kill batch is mechanical robustness, diagnosability, and hot-path hardening with no enforcement-behavior change (guard matrix, cold-install, and statusline render verified unchanged or byte-identical). The HARD-GATE batch closes real gaps in the crypto/secret commit gate and the append-only audit guards; each enforcement change shipped test-first (a RED test proving the gap, then the fix), with the full guard matrix, cold-install, migration backstop, and hook unit suites green.

### Security
- **Commit-time gates can no longer be bypassed by `git commit <pathspec>`.** A `git commit <path>` records the *worktree* content of the named paths (bypassing the index), but the H-09b/H-10b crypto-secret gate and the H-14 migration gate scanned only the staged (`--cached`) diff — so an unstaged crypto/secret/migration change named as a pathspec committed with no recorded review. Both gates now union the worktree diff **scoped to the named pathspecs** (an unrelated worktree change elsewhere is not dragged in). The crypto/secret scan and the H-14 file-list read now also **fail closed** when `git diff` cannot be read (timeout/error) instead of silently passing. (appsec-001/002, reliability-003)
- **Farm child commands no longer inherit dispatcher secrets.** `run()` scrubs `FARM_API_KEY` and `CLAUDE_CODE_OAUTH_TOKEN` from the environment passed to every child (git, operator gate/setup/test, mutation) — the API key is used only by the in-process `fetch`. Least-privilege defense-in-depth; shrinks the blast radius of the operator-authored gate-command shell boundary (CodeQL `js/shell-command-injection-from-environment` #5, traced non-exploitable and dismissed).
- **Two detection blind spots in the crypto/secret commit gate are closed.** `CRYPTO_RE` did not match RC2 or Blowfish (both forbidden by `security-controls.md`), so a commit adding either passed the H-09b gate with no crypto-compliance review. `SECRET_RE`'s leading word-boundary never fired when a secret keyword was the trailing segment of a compound identifier, so a hardcoded `FARM_API_KEY = "..."` committed clean past H-10b. Both now match. The outbound farm redactor and the commit-gate secret pattern are also pinned to a shared, CI-checked corpus (`secret-detection-corpus.json`) asserted against both, so they can no longer silently drift apart. (secrets-001/002, architecture-001, #132)
- **The H-05 append-only audit-log guard no longer accepts an empty-`old_string` Edit.** Because `new.startswith("")` is always true, an Edit with an empty `old_string` on `overrides.log` / `triage.log` / `sprint-log.md` slipped the append-only check entirely; it now blocks outright. The variable-indirection residual risk and the known truncation-spelling gaps (`exec N>`, `>>>`, process substitution) are now documented in `security-controls.md` so the policy matches the enforced scope. (migration-003, appsec-003, observability-005, #132)
- **A session-boundary `/ca:dev` exit now closes the audit pair.** When SessionStart clears a live dev marker (a prior session entered `/ca:dev` and ended without `/ca:arbiter`), it appends a synthetic `DEV: exit` line to `overrides.log` before removing the marker, so the audit trail no longer keeps an orphaned `DEV: enter` with no matching close. (observability-001, #133)

### Fixed
- **The task board can't be lost to a crashed write.** `taskwrite.py` writes `open-tasks.md` atomically (temp file in the board's own directory + `os.replace`), so an interrupted write leaves the prior board intact. (migration-001)
- **Farm dispatcher robustness + diagnosability.** A per-command wall-clock timeout (`FARM_GATE_TIMEOUT_MS`, default 5m; git stays unbounded) kills a hung gate/setup/mutation child so a stuck command can no longer wedge a run and stall the final report; the worktree-cleanup `finally` is guarded against an early failure; plan validation emits named field errors instead of an opaque crash; a run-id correlates `farm-results.jsonl` lines and the report header. Response/parse shape guards turn malformed API or mutation-hook output into actionable errors instead of silent empties. (reliability-001/004, migration-004, observability-003, dx-001/002/003)
- **ca-sandbox surfaces real failure causes.** `docker create`/`cp` exit codes are checked and the failed-clone path captures a bounded slice of git stderr into the thrown error, so a failed sandbox build/clone no longer reports only a bare exit code. (reliability-002, observability-004)
- **Task-board lib input guards.** `_taskboardlib.set_state`/`promote` no longer raise or silently mutate state on an unexpected value; valid value sets are documented. (dx-004/005)
- **Gate-pass markers are written atomically.** `migration-pass.py` and `security-pass.py` write their pass markers through a temp file plus `os.replace` (shared `_hooklib.write_text_atomic`), so a crash mid-write can no longer leave a half-written marker that the backstop reads as an unrecognized digest and spuriously re-blocks the next commit. Fail-closed behavior is unchanged. (migration-002, #133)

### Changed
- **Hook hot-path and statusline render cost reduced (behavior-preserving).** `_hooklib` caches the controls read (mtime-keyed, per ephemeral hook process) and precompiles its default path-globs at import; the statusline caches per-render state reads and its cost-ledger subsystem moved into a dedicated `_ledgerlib.py`. Verified: guard matrix 79/0, cold-install 134/0, and the statusline render byte-identical. (performance-001..005, architecture-005/007)
- Public-API header blocks added to `_hooklib.py` and `_sloplib.py` per the coding standard. (dx-007)
- **Audit-guard path sets centralized in `_hooklib` (behavior-preserving).** The append-only-log and ADR-decisions path patterns, previously triplicated inline across `pre-write` / `pre-edit` / `pre-bash`, now have a single definition (`is_audit_log` / `AUDIT_LOG_NAMES`, `is_decisions_path` / `DECISIONS_DIR_RE`), so adding an audit artifact touches one file instead of three. The detached-HEAD protected-tip check also resolves in one `git show-ref` spawn instead of three sequential `git rev-parse` calls, with the same block/allow decisions. (architecture-004, performance-006, #132, #133)

### Tests
- Added integration/coverage for existing behavior with no source change: custom CI/deploy scope grammar, the H-12 governed-path reminder (incl. superseded-ADR), and `validateRepoUrl` scp double-colon rejection; plus a `_ledgerlib` suite. (coverage-003/004/005)

### Documentation
- **Full pre-release docs pass.** Tightened the always-loaded orchestrator core (collapsed the duplicated non-negotiables, trimmed the register, made the lazy-load routers state one deterministic trigger-to-route surface) and reconciled the governance docs to the now-merged enforcement (the forbidden-crypto list, the secret-sweep pattern, and the audit-trail section that now names the automated `session-cleanup` `DEV: exit` write). Corrected stale references (`/ca:arbiter` no longer instructs a manual dev-exit line the hook already writes; `auth-crypto-reviewer` and the post-write reminder now list rc2/blowfish). The docs site gains an **Enforcement & Security** page and a complete **Hooks reference** documenting every hook (event, location, controls, and fail posture).

## [2.5.1] — 2026-06-23

### Fixed
- **Scope-touch reminders now fire on macOS and Windows** (`H-12`/`H-15`/`H-16`/`H-13`).
  `post-write-edit.py` derived its repo-relative path with a lexical `os.path.relpath`. When
  the hook payload's `file_path` and `git rev-parse --show-toplevel` named the same repo via
  divergent forms (a symlinked `/var` vs `/private/var` on macOS, an 8.3 short name on
  Windows), the path came out `..`-prefixed and every path-scoped reminder was silently
  dropped. A new `_hooklib.repo_rel()` canonicalizes both sides with `realpath` first. (#125)
- **`/ca:release` is now scoped to the `ca` plugin** (ADR-0007). The skill assumed a
  single-plugin repo: `LAST_TAG` resolved via bare `git describe` (returning a `ca-sandbox`
  tag), the bump and commit window spanned the whole repo, the derived version was never
  asserted against `plugin.json`, and the README/catalog surfaces had no sync step. All are
  now scoped to `plugins/ca/` and enforced, including a read-back of the published Release. (#125)

## [2.5.0] — 2026-06-22

### Added
- **Advisory scope-touch detection for CI, deploy/IaC, and auth** (`H-15`/`H-16`/`H-17`). After a
  write/edit, `post-write-edit.py` now reminds when a CI/CD workflow (`H-15`), a deployment/IaC
  manifest (`H-16`), or narrow high-signal auth logic (`H-17`) is touched, pointing at
  `security-reviewer`. These are **advisory only — no commit block**: a workflow runs only once merged
  and IaC bites only on apply, so a hard per-commit gate would impede iterative infra work while the PR
  review still catches the change (the irreversible-once-committed harms — secret/migration/crypto —
  keep their blocking gates). commit-gate now dispatches `security-reviewer` on a staged CI/deploy touch
  even on bare `/commit` / the small lane, closing the same lane-skip gap `H-14` closed for migrations.
  CI and deploy paths are detected by default glob sets, extendable/narrowable via `ci-paths` /
  `deploy-paths` blocks in `security-controls.md` (same grammar as `migration-paths`); the migration,
  CI, and deploy detectors now share one `path_in_globs` matcher in `_hooklib.py`. Resolves the
  scope-touch half of #73. (#73)
- **`/ca:metrics` — governance trend glance** (issue #79). Read-only command computing override rate,
  small-lane rate, and sprint low-confidence ratio over 20-commit windows, each with a direction arrow
  (↑/↓/→) vs. the prior window. Optional `--window N` to adjust the window size. Bare numbers only —
  not a second `/ca:audit` packet; writes nothing.
- **Task-board lifecycle + `/ca:task` writer and follow-up harvest** (#118). `open-tasks.md` gains a
  kanban-style lifecycle (`[ ]` queued, `[~]` in-progress, `[x]` done) with content-bearing IDs, so
  the in-flight count and stale-task nudge read real state instead of counting every bullet. The board
  now surfaces malformed or undated entries at SessionStart rather than letting work silently drop off.
  New `/ca:task add|start|done` is the sanctioned board mutator, and each gated workflow's terminal
  step harvests its un-actioned residue (NEEDS-TRIAGE markers, the checkpoint DEFERRABLE table,
  low-confidence sprint decisions) into the durable backlog.

### Fixed
- **`--farm` setup-doc error messages now point at the file that actually ships** (#119). The no-model
  and no-API-key guards cited a never-scaffolded `.codearbiter/farm.md`; they now point at
  `${CLAUDE_PLUGIN_ROOT}/includes/farm.md`, which is part of the plugin payload.
- **The crypto and secret commit gates now catch the Node/TS forms** (#120). `CRYPTO_RE` detects the
  TypeScript TLS-verification-disable patterns (the `rejectUnauthorized` bypass and the Node TLS-reject
  env override), not only the Python form; and `SECRET_RE` matches object-literal secrets
  (`"api_key": "…"`) plus high-entropy key prefixes (`AKIA`, `ghp_`, `sk-ant-`), not only `=`-style
  assignments. The `farm.ts` outbound redactor is aligned so the gate and the redactor never disagree.

## [2.4.6] — 2026-06-19

### Changed
- **Trimmed the always-on `ORCHESTRATOR.md` kernel.** The verbose `/dev` maintainer-override body
  moved to a new on-demand `includes/dev-mode.md` (loaded only on `/ca:dev` or `/ca:arbiter`), and the
  `--farm` summary compressed to a one-line pointer at `SPRINT.md` / `includes/farm.md`. The kernel
  retains the `/dev` security invariant (env-gated on `CODEARBITER_DEV=1`, entry/exit logged
  append-only, load the detail before suspending any gate) as a stub; the `§0.1` terminology lock and
  `§7` Override stay in-kernel, and `§3`/`§5`/`§6`/`§7` heading numbers are unchanged so hook citations
  stay accurate. Behavior-preserving — reduces the per-session SessionStart injection by ~21 lines. (#75)

### Security
- **Cleared 17 Dependabot alerts and hardened the farm test harness.** Bumped the vulnerable
  dev-dependency pins under `plugins/ca/tools/` (`package.json` / `package-lock.json`) and tightened
  process spawning in `farm.test.ts` so the test harness no longer shells out unsafely. Dev/test-only —
  no change to runtime plugin behavior. (#106)

## [2.4.5] — 2026-06-19

### Added
- **Migration commit-time backstop** (`H-14`): a `git commit` that stages a database migration is
  blocked until a migration-review pass is recorded for that file. commit-gate dispatches the
  `migration-reviewer` agent on a staged migration and, on PASS, records a content-digest marker
  (`.codearbiter/.markers/migration-gate-passed`) via the new `hooks/migration-pass.py`; `pre-bash.py`
  H-14 then admits the commit only when every staged migration is covered. Binding is by file-content
  digest with no freshness window — an edit to a reviewed migration re-blocks (closing TOCTOU and
  enforcing migration immutability at commit time). Migration paths are detected by a default glob set,
  extendable/narrowable via a `migration-paths` block in `security-controls.md`. Closes the bare-`/commit`
  / `/feature` small-lane gap where no lane dispatched the reviewer and no hook fired. (#77)

## [2.4.4] — 2026-06-18

### Added
- **Cold-miss nudge** [Feature Forge — `preview`]: an opt-in `UserPromptSubmit` speed bump that
  blocks once, with an advisory on stderr, when a large banked prune delta is about to re-cache on
  bloated in-memory context (idle ≥ 240 s, freed tokens ≥ 80k, `CODEARBITER_PRUNE_NUDGE=on`).
  Returns exit code 2 once; a resubmit proceeds. The once-per-cold-window `cold_nudged` marker is
  persisted in `prune-state.json` and reset on any warm submit. Strictly fail-open: any internal
  error returns 0 and never blocks the session. This is the first non-zero exit path in `hook_run`.
  Advisory content is derived from state numbers only (no transcript text). (#69)

## [2.4.2] — 2026-06-16

### Fixed
- **Closed six confirmed hook-enforcement bypasses** surfaced by the 2026-06-15 repo review, each
  with a red→green test: `git push --all`/`--mirror` could publish protected refs from any branch
  (H-01); `>|` force-clobber slipped the log-truncation and ADR-redirect guards (H-05/H-11); the
  Write/Edit ADR gate matched only numeric-prefixed names, so drafts and nested `decisions/*.md`
  slipped (H-11); `sprint-log.md` was not in the append-only set (H-05); `hooks.json` matched only
  `Edit`, letting `MultiEdit` sidestep the audit-log/ADR guards; and a detached-HEAD / case-sensitive
  branch check let a commit onto `main`'s tip slip. Adds direct tests for `pre-write.py` and
  `security-pass.py` plus a self-heal characterization test. (#68)

### Changed
- **Deduped skill overlap and unified the ADR format** (behavior-preserving skill-prose cleanups from
  the 2026-06-15 review). ADRs now share one `references/adr-template.md`, and `decompose` emits
  parseable `status:` frontmatter so `/ca:adr-status` reads every ADR uniformly. Five duplications
  were extracted to shared leaves (`--farm` plan extension, fresh-run verification, maturity→coverage
  table, crypto/secret on-pass block, cut-doc list). The `finishing-a-development-branch` open-PR path
  now executes the `/ca:pr` steps inline instead of re-routing (which looped under `/sprint`), and the
  stale inline command catalog was removed in favor of rendering from `COMMANDS.md`. (#68)

## [2.4.1] — 2026-06-14

### Fixed
- **Anti-slop copy pass now runs on the `/ca:chore` docs lane.** User-facing docs authored through the
  docs lane previously got no copy-law pass, so the core §3.A em/en dash prose-separator tell (the
  highest-signal AI text marker) could ship unflagged. The docs lane now applies the
  `anti-slop-design` pass before `commit-gate`, and a new advisory `H-13` PostToolUse reminder surfaces
  separator dashes in user-facing docs (repo-root community docs and `docs/**`) as you write, exempting
  code, URLs, numeric/date ranges, and lone table-cell dashes. (#60)

### Added
- **`PRIVACY.md`.** Records the no-data-by-default posture (no telemetry, no network calls in default
  operation, all state local to the repo) and the two opt-in flows that touch data: the `--farm`
  provider calls and the prune dry-mode local metrics. Supplies the Privacy Policy URL for the
  Claude Community Marketplace listing. (#63)

### Changed
- **Clarified that `/ca:dev` is the gates-off escape hatch**, not the required lane for editing
  codeArbiter's own command, hook, or persona bodies. Normal development of those files flows through
  the ordinary gated lanes and ships via PR + release. (#64)

## [2.4.0] — 2026-06-14

### Changed
- **Reframed `farm` as a pluggable execution backend (cheap / premium / agentic).** The dispatcher now
  runs every task through a `Worker` interface seam rather than calling the HTTP chat endpoint directly;
  the HTTP-chat author is one implementation. The worker owns the apply step, and a task-level
  containment sweep runs post-apply for any worker type, so path-traversal and read-only-test guards
  hold regardless of backend. Behavior-preserving for the existing flow. The name `farm` and its
  `preview` (Feature Forge) status are unchanged.

### Added
- **Prompt enrichment for workers.** Outgoing requests now include the read-only source of the task's
  failing test and the current contents of existing in-scope files, so a worker sees the contract it
  must satisfy. The injected context is byte-capped (configurable, mindful of `FARM_REQUEST_TIMEOUT_MS`)
  with a visible truncation marker, and is run through a redaction pass over the `security-controls.md`
  secret-pattern set — planted secrets, including multi-line PEM keys, are never transmitted.
- **Optional per-task `model`.** `task.model` is accepted in the plan schema (`additionalProperties:false`
  honored) and resolves as `task.model ?? meta.model`, enabling design-for cross-model execution.
- **Scope-aware scheduling.** A task overlapping an unfinished sibling's `filesInScope` is removed from
  readiness (not merely merge-serialized) until that sibling is green and merged; ordering is derived
  and id-tiebroken.
- **Regenerate-on-conflict.** A merge conflict now resets to the new integration HEAD and re-runs the
  worker once (the post-loop merge moved into the attempt loop) before escalating, instead of escalating
  instantly.
- **Streaming results rail.** Each settled task is appended to `.farm/farm-results.jsonl` in completion
  order as it settles, alongside the final `farm-report.json`.

---

## [2.3.1] — 2026-06-14

### Changed
- **Moved the `--farm` (OpenCode Zen) cost-arbitrage backend under Feature Forge.** It is labeled
  `preview` in the command catalog and the sprint body, documented in both READMEs' Feature Forge
  section, and carries a preview banner in its setup doc. `CONFIRM-05` records the promotion bar (the
  evidence that moves the farm from preview to stable). No behavior change to the farm itself.

---

## [2.3.0] — 2026-06-14

### Added
- **`/ca:release` now publishes the GitHub Release.** A new Phase 3 creates the GitHub Release via
  `gh release create` under the same explicit authorization that pushes the tag, reusing the changelog
  section composed in Phase 1 as the release notes. Closes the gap where the skill cut and pushed a tag
  but left the Releases page empty until someone ran `gh` by hand.

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
