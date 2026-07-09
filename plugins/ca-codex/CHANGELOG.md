# Changelog — ca-codex

All notable changes to the **ca-codex** plugin are recorded here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/). ca-codex is the OpenAI Codex CLI sibling to `ca`; the two version and release independently (ADR-0011), sharing one `.codearbiter/` store via the host-abstraction seam in `core/pysrc/`.

---

## [0.1.0] — 2026-07-09 — Initial beta release

The second host: OpenAI Codex CLI enforcement core (ADR-0011 M0–M2).

### Added
- **Codex host adapter (`hostapi.py` / `_host.py`).** Normalizes Codex's native tool payloads (`Bash`, `apply_patch`/`Write`/`Edit`, `mcp__*`) to the same canonical per-file-op shape the shared `core/pysrc/` entries consume, including full `apply_patch` envelope parsing (Add/Update/Delete/Move, added-line extraction, CRLF-lenient, fail-closed opaque fallback).
- **Shared-core enforcement.** SessionStart persona injection, the PreToolUse exec gate (`pre-bash.py`, H-20 no-verify-commit block), the PreToolUse write gate (`pre-write.py`, H-05/H-11/H-18/H-19/H-21), and the PostToolUse scope-touch review (`post-write-edit.py`) run byte-identically to the vendored `core/pysrc/` copies via `tools/sync-core.py`.
- **Host-neutral audit staleness-warn.** The `UserPromptSubmit` audit-staleness check (CONFIRM-09) is registered on Codex; the Claude-format-only prune ENGINE is gated off via `has_prunable_transcript` (parity ledger: `docs/parity.md`).
- **Dual interpreter registration.** `hooks.json` registers every hook twice (primary `python3`/`python` per `command`/`commandWindows`, plus a probe-and-fallback entry), mirroring `ca`'s STUB-fallback design so a Store-alias stub or a missing `python3`/`python` on either platform cannot silently disable every Codex gate.

BETA until live-Codex verification (plan: `.codearbiter/plans/codex-support.md`).
