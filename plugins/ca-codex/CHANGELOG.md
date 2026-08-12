# Changelog — ca-codex

All notable changes to the **ca-codex** plugin are recorded here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/). ca-codex is the OpenAI Codex CLI sibling to `ca`; the two version and release independently (ADR-0011), sharing one `.codearbiter/` store via the host-abstraction seam in `core/pysrc/`.

---

## [Unreleased]

## [0.7.0] — 2026-08-12

### Added

- Orchestration **mode plane** (ADR-0030): `arbiter`, `dangerous`, and `ops`. The injected persona is
  now `safety-core.md` plus the active mode's body, composed per turn, and the mode is flipped by a
  whole-prompt-anchored control token intercepted at the prompt seam with no model turn.
- `ops` mode: an advisory carve-out permitting in-channel work that starts, observes, or exercises a
  running system, keyed on the durable artifact produced. Anything mutating tracked files, the index,
  git history, or published state stays routed and refused.

### Changed

- `ORCHESTRATOR.md` is renamed `arbiter.md` and reframed as the arbiter mode's body rather than an
  always-on kernel. Its header records the former name so historical citations stay resolvable.
- Persona injection moved off `SessionStart` to the per-turn prompt seam; a once-per-session event
  cannot express a mid-session posture change. The startup block is now per-mode composable emitters.
- `dev` mode becomes `dangerous`: a general gates-off posture for any repository, with no
  maintainer-only env gate. No enforcement hook reads the mode, so every gate fires in all modes.

### Removed

- The `dev` and `arbiter` mode-entry commands. The mode bodies are the surface; the catalog drops
  from 40 to 38.

### Fixed

- A compaction could silently clear a live mode, because the mode plane borrowed the legacy marker's
  owner record to decide whether it had seen a session before. It now keeps its own anchor.
- Mode and marker state resolved through two different roots in three places; in a linked worktree a
  transition pair could split across two audit logs, or a stale session go undetected.

## [0.6.1] — 2026-08-08

### Changed

- Routine frontmatter carries `disable-model-invocation: true` on the nine chain-internal routines (inert on this host — routines are path-loaded prose) and JSON-quoted scalars per `_yaml_safe_scalar`; route sites cite explicit routine paths.

## [0.6.0] — 2026-08-08

### Changed

- Tribunal roster consolidated (ADR-0027): the eleven per-lens tribunal reviewer personas
  are replaced by one generic `tribunal-lens-reviewer` routine role dispatched once per
  active lens; lens cards under `routines/tribunal/references/lenses/` carry the mandates.
- Shared reviewer/author contracts extracted to `includes/reviewer-contract.md` and
  `includes/author-tdd-workflow.md`.

## [0.5.2] — 2026-08-08

### Documentation

- Backfilled 11 CHANGELOG sections that were missing when the manifest passed through them (`0.4.1`-`0.4.9`, `0.4.12`, `0.4.13`) — each composed verbatim from that commit's own `CHANGELOG:` footer. No functional change; this entry documents the CHANGELOG.md edit itself, which is why it required its own version.

## [0.5.1] — 2026-08-07

### Fixed

- `/ca:release`'s `--dry-run` no longer executes a declared `rebuild`/`generate`
  command — it previously ran the row's rebuild unconditionally, overwriting a
  committed build artifact despite promising not to write anything. Found and
  fixed by a required pre-tag blind agent-judgment exercise against the shared
  release-lib core.
- Phase 3's `resume_publish` path can now reconstruct release notes from the
  committed CHANGELOG via a new `changelog-section` CLI subcommand, instead of
  depending on a scratch file that does not survive a session boundary.

## [0.5.0] — 2026-08-07

### Added

- Recorded intent precedes autonomous scoring and spec shaping (ADR-0025),
  projected from the shared core: SMARTS Step 0 (scoped; arbitration surfaces
  exempt by name), the `ca-sprint` pre-approval intent read with the
  contradiction hard gate and stale-record valve, the pinned `intent:`
  sprint-log field, and the `brainstorming` routine's deferral-resurrection
  and accepted-ADR conformance checks. Index-first and fail-soft throughout;
  a repository with no decomposition record proceeds untouched. Codex ships
  no separate `agents/` surface, so the grader line lands via prose routines
  only; the cross-host pins live in `test_recorded_intent_surface.py`.

## [0.4.16] — 2026-08-06

### Fixed

- Corrected the 2.11.0 changelog entry's protected-state-registry description
  to name its three enrolled consumers instead of claiming it ships empty;
  the same stale claim in `_protectedstatelib.py` and `_bashguardlib.py` is
  corrected to match (shared `core/pysrc/` kernel).
- The release skill's Phase 3 release-notes command used bracket notation
  (`--latest[=false]`), which is prose shorthand and not runnable shell;
  split into the two runnable commands the surrounding prose already
  describes.
- Pre-flight's clean-tree requirement and the later rebuild step read as
  contradictory in isolation; added a note distinguishing the entry
  condition from the later, deliberately-reconciled exception.
- `medium-documents` was cited by bare name in the release skill's changelog
  step while every sibling include in the same sentence carries a full
  path; pathed it to match.
- `load_targets()` folded every unreadable declared-targets file into
  "absent"; added `UnreadableTargetsFileError` so the two cases are
  distinguishable (shared `core/pysrc/` kernel).
- The context-creation skill's single-target template omitted
  `latest-eligible: true`, disagreeing with the release skill's own
  back-fill detector for the identical shape.
- `row_assertions()` reported a blank `rebuild: ""` string as a declared
  command instead of "not declared" (shared `core/pysrc/` kernel).
- `select_release_target_by_name()` returned the bare string `""` for a
  pair with a blank NAME, outside its own documented result vocabulary
  (shared `core/pysrc/` kernel).

## [0.4.15] — 2026-08-06

### Fixed

- `run-pre-tag` now resolves a POSIX-compatible shell (Git for Windows' own `bash.exe`) to dispatch a target's declared `pre-tag` commands, instead of always dispatching through `cmd.exe` on Windows — so a row spelled `"$PY" <script>` (the #601 convention) now runs correctly on every platform, not just POSIX. A Windows host with no POSIX shell reachable at all now reports a distinct "could not run" diagnosis (exit 9) rather than misreading the absence as drift. This repository's own `.codearbiter/release-targets.md` `pre-tag` rows are rewritten from hardcoded `python3` to `"$PY"` now that the fix makes it portable (#602).

## [0.4.14] — 2026-08-05

### Added

- INDEX.md / routing-table.md consistency is now a CI-checked invariant instead of an authoring discipline: `check_routing_index_parity.py` fails the build when a skill/routine/agent is missing its INDEX row, an INDEX row points at nothing, or `includes/routing-table.md` routes to a name that does not exist — across all four generated surfaces. `skill-author`'s routing-integration phase now cites the check instead of re-stating the hand-verification it replaces (#592).

## [0.4.13] — 2026-08-05

### Fixed

- `/ca:release --dry-run` now really previews a release (target, derived version, changelog-footer check, resolved row) with nothing written, and writing-plans/brainstorming gain a mechanical citation backstop plus an explicit negative-judgment question so a spec criterion missed by both sides can no longer pass bijection silently (Closes #565, #566; shared `core/surface/` kernel).

## [0.4.12] — 2026-08-05

### Fixed

- Six governance rules that pin load-bearing release-skill doctrine are re-anchored so deleting the sentence they guard is now detected instead of passing silently (shared `core/pysrc/` kernel).

## [0.4.11] — 2026-08-05

### Fixed

- The git-level hook backstop (#161) could run from an arbitrarily stale host plugin cache — this plugin's own `0.3.0` cache predating the #279 sensitive-scan exemption resurrected that exact false positive, blocking a commit whose only "sensitive" lines were the crypto/secret gate's own machine-written audit rows. Each live host's session now records a content-addressed freshness heartbeat (`.git/codearbiter-hooksd/<plugin>.seen`) alongside its registered enforcer entry; the generated shim skips a registered entry whose heartbeat is missing or stale relative to a fresher registered sibling. `/ca:doctor` now surfaces a stale drop-in entry before it can produce a false block (#556).

## [0.4.10] — 2026-08-05

### Fixed

- The H-11 authoring-marker freshness window is now declared exactly once (`_hooklib.MARKER_FRESHNESS_MINUTES`) and imported by every enforcement flank (`pre-write.py`, `pre-edit.py`, `_bashguardlib.py`, `git-enforce.py`, `_protectedstatelib.py`), instead of five independently hardcoded copies of the same literal (#567).
- `_releaselib.py`'s unreachable `_PRERELEASE_MARKERS` dead code is removed (#568).

## [0.4.9] — 2026-08-05

### Fixed

- Linked-worktree sessions no longer lose a recorded security/migration gate pass, and the statusline palette test suite no longer depends on the developer's own accumulated `.codearbiter/` audit trail (shared `core/pysrc/` kernel).

## [0.4.8] — 2026-08-05

### Fixed

- H-05/H-11/H-18/H-22 close interpreter and lexical shell-flank bypasses; the Codex PowerShell audit-log append recipe no longer risks UTF-16LE corruption (shared `core/pysrc/` kernel).

## [0.4.7] — 2026-08-05

### Fixed

- Command/skill surfaces resolve the Python interpreter once by presence instead of a python3-or-python exit-code fold that could discard a helper's real verdict (shared `core/pysrc/` kernel).

## [0.4.6] — 2026-08-05

### Added

- `tdd`'s red gate now names and rebuts the four known excuses for skipping the failing test, and `skill-author`'s self-review enforces the evidence-lens authoring doctrine (shared `core/surface/` kernel).

## [0.4.5] — 2026-08-05

### Added

- The orchestrator persona is restructured on measured evidence — hard rules lead the document, a rationalization guard and letter-vs-spirit rule intercept gate-skipping, every user-facing ask leads with a recommendation and its strongest counter-case, a suspicious gate is diagnosed before any bypass, and startup instructions moved into the SessionStart briefing (shared `core/surface/` kernel).

## [0.4.4] — 2026-08-04

### Added

- The brainstorming skill now splits bundled ideas before refining, shapes the approach with a recommendation, decides routine parameters while asking genuine forks in full, and adversarially reviews its own spec before approval (shared `core/surface/` kernel).

## [0.4.3] — 2026-08-04

### Fixed

- The orchestrator no longer asks "did you mean" when it has already resolved the exact command and its complete argument — fully-resolved, non-destructive intent routes directly (ADR-0022 tier 1; shared `core/surface/` kernel).

## [0.4.2] — 2026-08-04

### Fixed

- Post-merge cleanup now proves squash merges via the PR record instead of STOPping on them, fast-forwards a stale local default before checkout, and standup can clear stale worktrees as one named group (shared `core/surface/` kernel).

## [0.4.1] — 2026-08-04

### Fixed

- Release lane: back-fill first releases clear the footer check, run-pre-tag distinguishes could-not-run from drift, and the version bump is mechanized via apply-bump (shared `core/pysrc/` kernel).

## [0.4.0] — 2026-08-01

### Added

- Protected-state registry (hook `H-22`): `.codearbiter/` files can be enrolled as `marker-gated`, `helper-only`, or `append-only`, enforced across the Write, Edit, and shell flanks. `release-targets.md`, `open-tasks.md`, and `done-tasks.md` are enrolled, one per policy.
- `taskwrite archive` moves a long-done task to `done-tasks.md`, writing the permanent record before removing from the board so an interrupted run cannot lose it.

### Fixed

- The shell flank's interpreter leg missed `py` and PowerShell, leaving it bypassable on Windows, and matched on the interpreter token alone — which blocked the sanctioned helper's own invocation whenever a task description named an enrolled file. It now requires an inline-code switch.
- Archiving moved only a task's top line, orphaning its `Desc`/`Boundaries` sub-bullets onto the following task, and removed every line matching the target, collapsing two identical done entries into one.
- An unreadable `done-tasks.md` was treated as empty, so a transient read failure rewrote the append-only archive from scratch and discarded every record.

## [0.3.7] — 2026-07-30

### Changed

- **`_hooklib` sheds activation, completing the #321 partition (slice 4 of 4).**
  The hook core finishes at **557 lines, from 1,263** - a 56% reduction across
  four slices. `_activationlib` now owns which Host the process runs under, where
  the project root is, and whether the arbiter is switched on, together with the
  two process-lifetime caches those answers share.

  `_HOST` is deliberately **not** re-exported: importing a mutable global binds
  its *value*, so a later `set_host()` would rebind it in the owning module and
  leave a stale copy behind forever. The accessors are re-exported instead, and
  a test proves both modules share one cache in both directions.

  `_hooklib` re-exports every name with a consumer, so the public surface is
  unchanged and parity rests on 1,185 pre-existing hook tests that did not move.

  No behaviour change.

## [0.3.6] — 2026-07-30

### Changed

- **`_hooklib` sheds its path-scope detection (#321, slice 3 of 4).** The hook
  core drops from 880 to 663 lines - **1,263 before the partition began**, so
  three slices have taken nearly half off the god module. `_scopelib` now owns
  which repo paths are database migrations (H-14), CI/CD workflow files (H-15),
  and deployment / IaC manifests (H-16), plus the security-controls.md reader and
  glob compiler they share.

  The cleanest seam of the four: this cluster referenced NOTHING from the rest of
  `_hooklib`, and nothing referenced it. Its only dependency was `norm_path`,
  already on the `_pathnorm` floor.

  `_hooklib` re-exports every moved name - including the private ones, which have
  real consumers - so the public surface is unchanged and parity rests on 1,185
  pre-existing hook tests that did not move.

  No behaviour change.

## [0.3.5] — 2026-07-30

### Changed

- **`_hooklib` sheds its protected-path classifiers (#321, slice 2 of 4).** The
  hook core drops from 1,050 to 880 lines - 1,263 before the partition began.
  `_protectedlib` now owns which repo paths are append-only audit logs (H-05),
  ADR decision files (H-11), the activation manifest, and the gate-marker
  directory. `repo_rel` joined `norm_path` on the `_pathnorm` floor, because it
  references no module symbol and the remaining slices need it too.

  Measured the same way slice 1 was: one outward reference, zero inward.
  `_hooklib` re-exports every moved name, so all consumers are untouched and
  parity rests on 1,185 pre-existing hook tests that did not move. The public
  surface is preserved exactly - nothing lost, nothing gained.

  No behaviour change.

## [0.3.4] — 2026-07-30

### Changed

- **`_hooklib` sheds its H-09b/H-10b sensitive-scan concern (#321, slice 1 of 4).**
  The 1,263-line hook core drops to 1,051. `_sensitivelib` now owns the crypto and
  secret detectors, the pinned security diff argv, the path-aware diff walk, and
  the digests that bind a recorded gate pass to the lines it reviewed;
  `_pathnorm` holds `norm_path` as the dependency floor beneath every path
  classifier.

  The seam was measured rather than guessed: the cluster referenced exactly ONE
  symbol from the rest of `_hooklib`, and nothing in the rest of `_hooklib`
  referenced the cluster. `_hooklib` re-exports every moved name, so all 59
  consuming files are untouched and behavioural parity rests on 1,185
  pre-existing hook tests that did not move.

  No behaviour change.

## [0.3.3] — 2026-07-29

### Changed

- **The support claim now separates what CI verifies continuously from what a
  human verifies per release (#408 AC-2, closed by scoping).** Proving a hook
  *fires* needs a turn, a turn needs a model, and a provider credential cannot be
  a required check on fork pull requests — so that half is manual by decision.
  The manifest says so explicitly and names `docs/codex-parity-testing.md` as the
  record, instead of implying continuous coverage.

  The runbook states the division and carries a machine-findable baseline marker,
  because the failure mode of "manual per release" is that it quietly becomes
  "manual once" — and it already had: the recorded baseline sat at ca-codex 0.2.4
  across four minor versions, and is now marked stale rather than read as current.

  A contract pins the distinction so it cannot erode back into an unqualified
  promise: the description must disclose the manual half and name the runbook, and
  the runbook must record both a Codex and a ca-codex version so staleness can be
  judged at all.

## [0.3.2] — 2026-07-29

### Changed

- **The supported-Codex claim now names the versions CI continuously verifies
  (#408 AC-1).** The manifest advertised `Codex >= 0.143.0; live-verified on
  0.144.1` while CI installed exactly one version, so the LOWER BOUND of the
  supported range rested on a single manual check from July. The required
  real-host lane now runs at both ends of the window - 0.143.0 and 0.145.0 - and
  a contract test derives the claim from that matrix, so bumping one without the
  other fails.

### Added

- **The real-host check verifies every declared hook has a script to run
  (#408 AC-3).** The existing check compared the installed hook manifest to the
  source manifest - and the install is a copy of that same source, so the two
  agreed by construction for anything source declared. Measured: a hook added to
  source with no script behind it left that check passing. Every
  plugin-root-relative script the installed manifest points at must now exist in
  the install, which is what makes a declared-but-absent hook visible. Still
  credential-free.
- **An advisory upstream-compatibility lane** installs `@openai/codex@latest` and
  runs the same host check, so protocol or plugin-install drift is reported
  rather than discovered at the next pin bump. Never blocking - an upstream
  release must not be able to fail a merge. It is already useful: `latest` is
  0.146.0 while the required lane pins 0.145.0, and nothing reported that.

## [0.3.1] — 2026-07-28

### Changed

- Projection of the shared surface change in ca 2.10.2: coverage figures are the
  union across a tree's supported hosts, and `tdd` Phase 5 requires the
  measuring host to be named (#521). No Codex-specific behaviour changed.

## [0.3.0] — 2026-07-12 — Shared-state concurrency hardening

### Added
- The projected review routine accepts an inbound pull request as its argument,
  reviewing code the operator did not write through the existing fleet (#80).

- `$ca-cleanup` (`post-merge-cleanup`): the already-merged branch transition —
  prove ancestry of the fetched default branch, classify leftover artifacts as
  unique / redundant / superseded, resolve each under its own confirmation,
  `--ff-only` onto the default branch, then `branch -d` the merged local branch.
  The remote branch is never touched (issue #308).

### Changed
- The projected release routine takes the target plugin as an argument and
  covers all four series, instead of documenting `ca` and leaving the siblings
  undefined. Shared-core change, projected to this host unchanged (#382).

- The projected release routine named two independently-versioned plugins
  instead of four, and told the reader nothing about how a `ca-codex` release is
  actually cut. It now names every tag series and routes a sibling release to
  the hosted `release` workflow's own lane, which carries the changelog-heading
  guard, the existing-tag classifier, and the published-release read-back that a
  hand-cut tag has none of (#382).

- ORCHESTRATOR §6 routes on understood intent rather than asking the user to
  retype a command it has already named, in three tiers, with everything
  irreversible or gate-bypassing held at the ask-once tier regardless of how
  clear the intent is (ADR-0022).

### Fixed
- The projected release routine names the latest-badge trap directly: a sibling
  must pass `--latest=false`, because omitting the flag lets GitHub default the
  badge to the newest non-prerelease.

- The shared guard and anti-slop libraries pick up the `git commit-graph`
  mis-gating fix (#485) and the line-wrap-boundary detector fix (#484). Both are
  core changes projected to this host unchanged.

- A session started inside a linked worktree no longer repoints the main
  repository's git-level enforcement at a worktree path that is pruned out from
  under it. The enforcer entry is shared through the git common dir, so an
  ephemeral plugin root used to overwrite the main repo's registration and leave
  it silently ungated. Refused now in both the producer and the caller; a stale
  but durable path is still refreshed (issue #441).
- The guard layer now normalizes a non-object hook payload to an empty payload
  at `read_input()`, so the adapter's shape check below is no longer the only
  thing standing between a valid-JSON non-object and an `AttributeError` out of
  a guard. The adapter's own refusal is unchanged and deliberate: it is a
  router, so a payload it cannot route is one it cannot prove safe, while a
  guard that cannot parse its own input takes the documented warn-and-proceed
  path. ADR-0020 records the asymmetry.
- The PreToolUse adapter validates the hook payload's shape before routing it.
  A valid-JSON but non-object payload (`null`, an array, a string, a number, a
  bool) used to raise `AttributeError` out of the adapter — exit 1, a traceback,
  and no allow/block decision at all — and an empty or syntactically invalid
  payload was handed to `pre-bash.py` unvalidated, where the guard layer's
  documented fail-open silently allowed the gated call. Every unroutable payload
  now takes one bounded path: the documented `decision: block` response at
  exit 0, with no guard dispatched — and that path is gated on the repo having
  opted in. codeArbiter stays dormant wherever `.codearbiter/CONTEXT.md` does
  not carry `arbiter: enabled`: the adapter short-circuits before any guard
  runs, so it now applies the same activation check the guards do and takes no
  action at all in a repo that never opted in. This also closes the same gap on
  the pre-existing incomplete-stream leg, which declined unconditionally.
- Tribunal runs recover cumulative usage from each exact Codex agent thread
  when its local session artifact is readable, and otherwise record an explicit
  capability or instrumentation reason instead of leaving `tokens_actual`
  unexplained.
- Prune metrics now separate model-visible context savings from file-only
  sidecar cleanup, preventing sidecar bytes from inflating the context-benefit
  decision or cold-cache nudge.
- Prune hooks ignore and repair malformed per-session state rather than letting
  invalid legacy values escape fail-open handling.
- Shared statusline ledger records use ownership-safe atomic shards, so
  concurrent host activity cannot discard session token/cost state.
- Linked-worktree branch metadata is parsed from Git pointer files instead of
  being reported as missing.
- Windows gate-event appends now retain every host-attributed line during
  concurrent Claude/Codex process bursts while permanent lock errors remain
  fail-open.

### Changed
- The generated shared payload includes the new palette and subagent-model
  statusline support for byte-parity with `ca`; Codex still exposes no
  statusline surface, as documented in `docs/parity.md`.

## [0.2.4] — 2026-07-12 — Codex hook-launch repair

### Fixed
- Registered one OS-specific command handler per event, removing concurrent
  interpreter fallbacks that produced spurious failures or conflicting allows.
- Widened the PreToolUse exec matcher to `Bash|shell_command|exec_command|unified_exec`
  so the exec gate fires for every tool name the host map classifies as EXEC; a new
  adapter-suite drift guard fails if the matcher and the tool map ever diverge.
- Raised the documented Codex support floor to rust-v0.143.0, the earliest release
  with source-verified structured `decision:block` handling. The live-verified
  baseline remains 0.144.1.
- Added a Codex-only PreToolUse adapter. It runs the byte-identical shared
  guards, converts their exit-2 verdict to Codex's structured `decision:block`
  response, and preserves the exact gate feedback across the Windows shell.
- Corrected `$ca-doctor` path resolution and remediation for ordinary Codex
  tool calls, which do not inherit the hook runner's plugin-root environment.

### Verified
- Codex 0.144.1 loaded the trusted plugin, injected the SessionStart persona,
  and blocked the live `$ca-doctor` probe with `[H-03]`. This satisfies the
  ADR-0011 promotion gate and removes the beta label.

## [0.2.1] — 2026-07-11 — Codex package validation repair

### Fixed
- Updated the Codex manifest and repository marketplace to the schema validated
  for Codex CLI 0.144.1, including complete interface metadata and explicit
  installation policy.
- Made generated Codex skill frontmatter valid YAML when descriptions or
  argument hints contain mapping punctuation.
- Added a pinned, executable package validator and CI coverage so packaging
  drift fails before release.
- Made gate-event appends a single append write, with a Windows byte-range lock,
  so simultaneous Claude and Codex blocks retain one host-attributed audit line
  per event without extending concurrency guarantees to RMW project state.

The plugin remains BETA until the ADR-0011 live-Codex verification gate passes.

## [0.2.0] — 2026-07-10 — Full command/skill surface (M3): standalone Codex support

Codex-only users are first-class (DECISION-0013, closes #287): the whole
governance surface now ships on this host, generated from `core/surface/`
templates by `tools/build-surface.py` (CI-gated against drift in both
directions).

### Added
- **37 user-invocable entry skills** (`skills/ca-*/SKILL.md`) — every `ca`
  command except the two ledgered exceptions (statusline, prune;
  `docs/parity.md`), including **`ca-init`: standalone opt-in** with no
  Claude-side install required.
- **22 orchestrator routine bodies** (`routines/`), the shared `includes/`
  references, `COMMANDS.md` catalog, `SPRINT.md`, and a generated
  `skills/INDEX.md` surface scan.
- **Codex-native persona.** `ORCHESTRATOR.md` is now rendered per host: this
  plugin's copy speaks `$ca-` skill vocabulary and points to
  `includes/codex-host-notes.md` (tool mapping, degraded paths, sandbox/git
  caveats) instead of duplicating the Claude wording byte-for-byte.

### Changed
- Manifest description: first-run is the `ca-init` skill; the previous pointer
  to the Claude-side `/ca:init` is gone (#259).

BETA until live-Codex verification (plan: `.codearbiter/plans/codex-support.md`).

## [0.1.0] — 2026-07-09 — Initial beta release

The second host: OpenAI Codex CLI enforcement core (ADR-0011 M0–M2).

### Added
- **Codex host adapter (`hostapi.py` / `_host.py`).** Normalizes Codex's native tool payloads (`Bash`, `apply_patch`/`Write`/`Edit`, `mcp__*`) to the same canonical per-file-op shape the shared `core/pysrc/` entries consume, including full `apply_patch` envelope parsing (Add/Update/Delete/Move, added-line extraction, CRLF-lenient, fail-closed opaque fallback).
- **Shared-core enforcement.** SessionStart persona injection, the PreToolUse exec gate (`pre-bash.py`, H-20 no-verify-commit block), the PreToolUse write gate (`pre-write.py`, H-05/H-11/H-18/H-19/H-21), and the PostToolUse scope-touch review (`post-write-edit.py`) run byte-identically to the vendored `core/pysrc/` copies via `tools/sync-core.py`.
- **Host-neutral audit staleness-warn.** The `UserPromptSubmit` audit-staleness check (CONFIRM-09) is registered on Codex; the Claude-format-only prune ENGINE is gated off via `has_prunable_transcript` (parity ledger: `docs/parity.md`).
- **Dual interpreter registration.** `hooks.json` registers every hook twice (primary `python3`/`python` per `command`/`commandWindows`, plus a probe-and-fallback entry), mirroring `ca`'s STUB-fallback design so a Store-alias stub or a missing `python3`/`python` on either platform cannot silently disable every Codex gate.

BETA until live-Codex verification (plan: `.codearbiter/plans/codex-support.md`).
