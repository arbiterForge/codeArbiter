# Pi sidebar — full pi-sidebar-tui parity

**Governs:** plugins/ca-pi/tools/src/sidebar*.ts

**Status:** APPROVED 2026-08-10 (user: "approve", after pi-window-promotion-0-84-1 merged as #661)

**Origin:** the user's original 2026-08-08 ask ("subagents I think makes more sense in the sidebar")
plus rulings 2026-08-09: build the compositor-style right column referring to
github.com/bi0h4z4rd88/pi-sidebar-tui, at FULL panel parity (session, todos, subagents,
workspace/git, MCP), against the promoted {0.80.5, 0.84.1} window.

## Problem

Rich live telemetry — subagent/job detail beyond four rows, todo/plan progress, workspace state,
MCP status — does not fit the footer's bounded box, and Pi has no native sidebar API (source-
verified: 0.80.5/0.80.10/0.84.1 expose only footer/header/widget docks). Done = an optional,
fail-soft right-hand sidebar column in the interactive Pi parent, at pi-sidebar-tui panel parity,
that can always restore native rendering.

## Approach

Re-implement pi-sidebar-tui's proven mechanism inside the adapter, dependency-free: obtain the
`tui` handle from the footer factory the lifecycle already holds; narrow the terminal's perceived
width by redefining the `terminal.columns` getter; wrap `tui.doRender` to paint the sidebar column
with synchronized output (DEC 2026, cursor save/restore, wrap off) after every Pi render; import
`visibleWidth`/`truncateToWidth` from the HOST's own `@earendil-works/pi-tui` at runtime (the
footer-metrics loader pattern — no vendored dependency). Trade-off accepted knowingly (user-
chosen over a native widget panel): the two hook points are undocumented surface, so every install
is probe-gated at runtime and every failure disposes back to native rendering — the sidebar may
degrade to unavailable on a future Pi, but it can never wedge the terminal.

## Scope

- A pure sidebar renderer (panel layout, five panels, width-bounded lines) plus a compositor
  owning install/paint/dispose, driven from the existing parent footer lifecycle.
- Five panels at pi-sidebar-tui parity with ca-pi-owned data sources: session (model, thinking,
  context bar, tokens/cost, burn), subagents/jobs (activity registry + dispatch states, the
  full-detail view the footer cannot fit), workspace (cwd + git-facts), todos (the plan-mode
  ledger when a plan session is active), MCP servers (Pi-owned configuration, rendered only when
  Pi exposes any).
- A `/ca-sidebar` native parent command (on | off | toggle | width N).
- Runtime probe gating, fail-soft disposal, doctor health row, docs/parity updates.

**Out of scope:** per-child token counts (blocked on the child-protocol board task); any child,
RPC, JSON, or print-mode rendering; persisting sidebar preferences beyond the session; upstreaming
to pi-sidebar-tui or depending on it at runtime; Claude Code / Codex hosts; fullscreen-mode
specific behavior beyond the probe refusing to install when hooks are absent.

## Decided parameters

- Width: 40 columns default, `/ca-sidebar width N` clamped 24..60; the compositor refuses to
  install (with a one-line notice) when the raw terminal is narrower than width + 60.
- Default state: ON in an interactive parent when the terminal is ≥ 120 columns, OFF below;
  `/ca-sidebar` overrides for the session; no persistence.
- Probe gate: install only when `tui.doRender` is a function, the `terminal.columns` descriptor
  is configurable, and the host `pi-tui` text helpers load — otherwise the sidebar reports
  unavailable via `/ca-doctor` and native rendering is untouched.
- Paint discipline: synchronized output envelope exactly as pi-sidebar-tui (DECSC/DECRC, wrap
  off/on, per-row cursor addressing), separator column `│`, background reset per row.
- Dispose discipline: restore the original `columns` descriptor and `doRender`, request one full
  native re-render; dispose runs on toggle-off, session switch/shutdown, extension unload, and
  automatically on ANY compositor/renderer throw (single warning notify, never repeated).
- Trust gating: workspace/git panel and todos panel require affirmative trust (git-facts and
  plan-ledger reads are trusted-only today); session, subagents, and MCP panels render in any
  interactive parent, dormant repos included.
- Data reuse: session panel consumes the existing footer adapter facts; subagents panel consumes
  the activity registry (caps raised 8→16 active entries, TTLs unchanged) plus dispatch child
  states; no new bridge calls are added for the sidebar.
- Footer coexistence: the footer stays unchanged and authoritative when the sidebar is off or
  unavailable; the sidebar never removes footer segments.

## Acceptance criteria

1. A pure `renderSidebar(input, width, metrics)` returns width-exact lines for the five panels,
   each panel independently fail-soft (a throwing panel renders as its header plus an omitted
   body, never breaking siblings), control/ANSI-sanitized, NO_COLOR-aware, proven at fixed widths.
2. The compositor installs only when every probe passes (doRender function, configurable columns
   descriptor, host pi-tui helpers loaded) in an interactive parent session; a failed probe leaves
   native rendering untouched and surfaces one `/ca-doctor` unavailable row.
3. While installed, Pi's perceived columns shrink by width + 1, the sidebar paints inside a
   synchronized-output envelope after each host render, and content lines truncate to the sidebar
   width (fixture-driven paint tests over a scripted fake tui/terminal). Every paint cycle
   re-validates terminal geometry first (finite rows/columns, raw width still ≥ width + 60);
   a failed re-validation — including Pi 0.84's runtime fullscreen switch changing the render
   surface — skips the paint and, when it persists across consecutive cycles, disposes the
   compositor rather than painting into a surface it no longer understands.
4. Dispose restores the original columns descriptor and doRender and triggers a native re-render;
   it runs on `/ca-sidebar off`, session switch, shutdown, unload, and automatically on any
   compositor throw with a single bounded warning — verified by tests that throw from paint.
5. `/ca-sidebar on|off|toggle|width N` works as a native parent command with bounds enforcement;
   default state follows the ≥ 120-column rule; child/RPC/JSON/print modes expose neither the
   command effects nor any painting.
6. Panels bind their decided data sources: subagents shows kind/label/state/age for up to 16
   active + recent items with overflow count; workspace and todos render only under affirmative
   trust; MCP renders only when Pi exposes servers; session mirrors the footer facts without new
   bridge traffic.
7. The compositor hook probes are exercised against BOTH window versions — fixture contracts for
   each plus the live platform runs at 0.80.5 and 0.84.1 — and the pi-api declaration boundary
   documents the probed surface as runtime-guarded, not source-verified API.
8. Docs and the parity ledger describe the sidebar honestly (probe-gated, undocumented hook
   surface, fail-soft); public doc tests pass; full repo gate green; ca-pi bumps one minor with a
   CHANGELOG section.

## Open questions

None blocking. The undocumented-hook risk is accepted by explicit user choice and mitigated by
probe gating + auto-dispose; if a future Pi removes either hook, the sidebar degrades to
unavailable and the board gains a revisit task (the fail-soft path is AC-2/AC-4's tested branch).
