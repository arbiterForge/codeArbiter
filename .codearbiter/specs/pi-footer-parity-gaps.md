# Pi footer parity gaps

**Governs:** plugins/ca-pi/tools/src/footer.ts, plugins/ca-pi/tools/src/footer-state.ts, plugins/ca-pi/tools/src/status.ts

**Status:** APPROVED 2026-08-08 by the repository owner (mid-session explicit approval)

**Origin:** /ca:brainstorming 2026-08-08. Split agreed with the user: this spec covers only the
footer parity gap-closure; the sidebar panel surface is a separately queued feature with its own
API-verification prerequisite (Pi 0.80.x widget/overlay capability is unverified).

## Problem

The ca-pi footer shipped under the approved `pi-live-experience-parity` spec (2026-07-18) but still
omits three information classes the Claude Code statusline renders: the per-message token-burn
sparkline, the git repository name and dirty indicator, and per-subagent/job detail rows. A user
running the same project under Pi sees less live telemetry than under Claude Code. Done = the footer
renders those three classes from Pi-observable data with the same fail-soft guarantees the footer
already carries.

## Approach

Extend the existing footer pipeline — `FooterInput` → `renderFooter`, `adaptPiFooterState`, and
refresh-time enrichment in `PiFooterLifecycle` — rather than adding any new surface or bridge
traffic. This is the only sane approach: a second renderer would duplicate a shipped, tested,
fail-soft surface, and serving the sparkline through the Python bridge adds per-call spawn cost
(ADR-0021) for data Pi already holds in-process. Trade-off accepted: refresh-time git enrichment is
only as fresh as the last footer refresh (turn boundary), in exchange for a render path that never
spawns processes.

## Scope

- Close the remaining Claude Code statusline parity gaps in the shipped ca-pi footer: the
  per-message token-burn sparkline, the git repository name and dirty indicator, and multi-row
  subagent/job activity detail.
- Update the public Pi docs and parity ledger to describe the new segments.

**Out of scope:** provider rate-limit windows (Pi exposes none; approved parity spec AC-07 records
omission — never fabricated); any new sidebar/widget UI surface (queued sibling feature); per-child
token counts (`DispatchChild` carries no usage — a child-protocol change, queued for triage);
dispatch-outcome glyphs on activity rows; porting these segments to Claude Code or Codex hosts; any
new runtime dependency; child/RPC/print-mode UI (footer remains parent-interactive only).

## Decided parameters

- Sparkline metric: input+output tokens per assistant message (matches the CC statusline's
  per-call burn), last ≤ 20 messages, 8-level block glyphs (`▁▂▃▄▅▆▇█`).
- Sparkline sourcing: pure derivation from `sessionManager.getEntries()` at render, scan bounded to
  the final 400 entries; independent of whether the bridge usage snapshot is active.
- Sparkline placement: wide layout only; compact layout omits it.
- Git enrichment mechanism: bounded `git` spawn at refresh time (explicit argv, `shell: false`,
  2-second timeout, output cap), never in the render path; cached until the next refresh.
- Git repository display: origin remote parsed to `owner/name` when possible, else the toplevel
  directory basename; sanitized and length-capped like every footer string.
- Git enrichment gating: affirmatively trusted projects only, per the approved parity spec's
  "trusted dirty-state enrichment" language; untrusted or dormant repos keep branch-only display.
- Activity rows: up to 4 rows in wide layout (state glyph, kind, label, age), newest-first, one
  `+N more` overflow line beyond 4; compact layout keeps the existing one-line segment; the
  activity registry's existing caps (8 active / 8 recent, TTLs) are unchanged.
- Failure behavior: every new segment omits itself on any failure — timeout, spawn error, malformed
  entries — and never invents a value (AC-07 precedent).
- Staleness bound: dirty/repository facts may lag the working tree by one footer refresh; accepted.

## Acceptance criteria

1. The wide footer layout renders a per-message burn sparkline derived from the last up-to-20
   assistant-message usage entries of the current Pi session, each bar scaled from that message's
   input+output tokens using 8-level block glyphs; it renders identically whether or not the bridge
   usage snapshot is active; with no usage series the segment is omitted; the compact layout never
   renders it.
2. Sparkline derivation is pure and bounded: it scans at most the final 400 session entries, skips
   malformed entries, allocates no persistence, and never throws (proven at fixed render widths).
3. The footer adapter wires git repository and dirty state from refresh-time enrichment: repository
   is the origin remote's owner/name when parseable else the toplevel directory basename; dirty is
   true iff `git status --porcelain` output is non-empty; both fields are omitted — never guessed —
   when the git spawn fails, exceeds its 2-second timeout, or the project is not affirmatively
   trusted.
4. Git enrichment executes only during footer refresh (never inside the render path), spawns git
   with explicit argv and `shell: false`, caps captured output, and passes fixture tests on both
   Windows and POSIX.
5. The wide layout renders up to 4 activity rows (state glyph, kind, label, age), newest-first,
   appending a `+N more` overflow line when more items exist; the compact layout keeps the existing
   one-line activity segment.
6. Every new segment obeys NO_COLOR, width clamping, and control/ANSI sanitization, and degrades
   independently — a failing segment never breaks the box or the minimal-safe-line fallback.
7. Rate-window telemetry and per-child token counts remain absent from the rendered footer and are
   never fabricated (structural renderer assertions).
8. The public Pi docs and the Pi parity ledger describe the sparkline, git enrichment, and activity
   rows accurately; `test_public_pi_docs.py` and the parity checks pass.
9. The full ca-pi verification gate passes: typecheck, vitest suites, regenerated checked-in
   extension bundles, `sync-core`/`build-surface`/`build-host-packages --check`, and the
   package/parity aggregates.

## Open questions

None. No `[CONFIRM-NN]` raised: the two genuinely open threads (Pi 0.80.x widget/overlay API
capability; per-child token observability) belong to the queued sidebar feature and the queued
child-protocol follow-up respectively, not to this spec.
