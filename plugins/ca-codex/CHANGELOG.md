# Changelog — ca-codex

All notable changes to the **ca-codex** plugin are recorded here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/). ca-codex is the OpenAI Codex CLI sibling to `ca`; the two version and release independently (ADR-0011), sharing one `.codearbiter/` store via the host-abstraction seam in `core/pysrc/`.

---

## [0.2.4] — 2026-07-11 — Codex hook-launch repair

### Fixed
- Registered one OS-specific command handler per event, removing concurrent
  interpreter fallbacks that produced spurious failures or conflicting allows.
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
