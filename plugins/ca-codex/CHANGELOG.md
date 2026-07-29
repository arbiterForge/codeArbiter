# Changelog — ca-codex

All notable changes to the **ca-codex** plugin are recorded here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/). ca-codex is the OpenAI Codex CLI sibling to `ca`; the two version and release independently (ADR-0011), sharing one `.codearbiter/` store via the host-abstraction seam in `core/pysrc/`.

---

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
