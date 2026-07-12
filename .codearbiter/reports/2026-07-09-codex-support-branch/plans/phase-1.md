# Phase-1 plan — wave 1 (appsec, architecture, reliability) kept work

Roadmap for the `keep`/`combine` findings from wave 1. Decision-required items get a pointer, not a fix.
21 findings triaged → 12 kept/combined fixes across 6 work groups, 4 decision-required, 2 investigate, 1 duplicate.

## Group A — Codex host fail-open hardening (the enforcement-integrity core)
Findings: architecture-004 (high) + reliability-003 (duplicate). Also depends-related to appsec-001.
- `hostapi.load_host()` must distinguish "`_host.py` present but failed to load" from "no `_host.py`". Present-but-broken → fail CLOSED (or emit a loud stderr breadcrumb and refuse to guard foreign payloads), never silently return the Claude-default `Host()`.
- Acceptance: a syntactically-broken ca-codex `_host.py` causes the write gate to block/refuse, not allow; a signal is emitted.

## Group B — apply_patch parser completeness (appsec-001, medium)
- Make the fail-closed "opaque" op trip per-file / on ANY unrecognized `*** ` directive line inside a recognized envelope, not only when the whole parse yields zero ops.
- Acceptance: an envelope mixing a recognized `Add File` op with an unrecognized `*** Copy File:` (or mis-spaced `*** Move to:`) yields an opaque/blocking op, not a partial allow.
- `depends_on`: Group A (both are the Codex write-guard trust boundary).

## Group C — group-manifest-path (reliability-001 medium + reliability-002 low, combine)
- Introduce a host-aware plugin-manifest path (`.claude-plugin/` vs `.codex-plugin/`) — resolve via the Host object, not a hardcoded literal.
- Fixes: doctor.py false-UNHEALTHY on every ca-codex install; `_updatelib.installed_version` returning None so the update-notifier never fires on Codex.
- Acceptance: `doctor.py` reports HEALTHY on a correct ca-codex install; the update notice can fire on Codex. (Secondary, note for Group-shared-store/decision: the cached `latest` is the ca release stream — per-host version source is a follow-up.)

## Group D — group-project-root-seam (architecture-006 + reliability-005, combine, medium)
- Resolve the seam's root-signal design: the payload-cwd leg of `Host.project_root` is dead in production (no caller passes a payload), and `CodexHost` leg-1 returns session cwd verbatim (subdir → wrong root).
- Either wire the payload through the entry `main()`s AND make the leg climb to the git toplevel, or delete the dead leg and document the real resolution order. Do not ship a docstring asserting a path production never takes.
- Acceptance: a Codex session started in a repo subdir resolves the repo root, and the tests exercise the SAME path production uses.

## Group E — pattern-drift / seam-consistency (keep)
- architecture-001 (medium): remove or truly wire the dead `run(host)` parameter on all 20 entries.
- architecture-008 (low): route pre-edit.py's `MultiEdit`/`NotebookEdit` native-name branches through `normalize_tool` categories.
- reliability-006 (low): route prune-transcript `staleness_check` root resolution through the host seam's `project_root` instead of raw payload cwd.
- Acceptance: no shared-core file branches on a raw native tool name or resolves root off-seam; `run(host)` is either injectable or gone.

## Group F — ca-codex packaging hygiene (keep)
- architecture-005 (medium): capability-gate / trim the ~15 unreachable vendored entries so ca-codex does not ship non-registered enforcement scripts as trust-surface; fix the manifest's `/ca-init` first-run pointer.
- reliability-008 (medium): mirror ca's dual `python3`/`python` interpreter registration in ca-codex `hooks.json` (cold-install fail-open).
- reliability-009 (low): make the dual-host git-hook shim resolve either plugin's enforcer or fail closed, not fail-open on a dangling absolute path.
- Note: architecture-002/003 (CI wiring) live in the group-ci-vendoring plan (phase carried into report; infra lens wave 3 may deepen).

## Decision-required (ADR-grade — resolve via /ca:adr, not fixed here)
- **group-shared-store** (architecture-007 high, reliability-004 high, reliability-007 medium): the coordination contract for two hosts sharing one `.codearbiter/` store — locking/CAS on read-modify-write state, `host=` attribution in the audit logs, and repo-global-vs-session-local marker scoping (dev-active). ADR-candidate.
- **appsec-002** (medium): MCP-tool write scope on Codex — state in `security-controls.md` whether MCP writes are in/out of scope for the write gate. ADR/security-controls-candidate.

## Investigate (not filed)
- architecture-009 (low): `_hooklib.py` god-module accretion (773 LOC / 6 clusters). Debt, no correctness impact.
