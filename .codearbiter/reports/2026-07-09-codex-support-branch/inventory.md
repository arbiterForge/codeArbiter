# Inventory — 2026-07-09-codex-support-branch

Scope: `feat/codex-support-m0` branch diff vs main (merge-base `ddcfc42`), 7 commits, 128 files, ~28.9k insertions.
Focus (user-directed): dual-host support — Claude Code and Codex CLI sharing one `.codearbiter/` projectContext in the same repo.

## Structure

- **`core/pysrc/`** (canonical shared core, ~40 files): all host-neutral hook entry scripts (`pre-write.py`, `pre-bash.py`, `pre-edit.py`, `pre-read.py`, `post-write-edit.py`, `security-pass.py`, `git-enforce.py`, `session-start.py`, `statusline.py`, `taskwrite.py`, `boardsync.py`, `doctor.py`, `preview.py`, `prune-transcript.py`, `update-refresh.py`, `metrics.py`, `babysit.py`, `migration-pass.py`, `init-codearbiter.py`, `wire-statusline.py`) plus shared `_*lib.py` modules and `hostapi.py` (the host seam).
- **`tools/sync-core.py`** (110 LOC): byte-level vendoring core → `plugins/ca/hooks/` and `plugins/ca-codex/hooks/`; `--check` is the CI parity gate. Excludes `_host.py`.
- **`plugins/ca/hooks/`**: vendored copies + `_host.py` (31 LOC — `HOST = hostapi.Host()`, Claude defaults).
- **`plugins/ca-codex/hooks/`**: vendored copies + `_host.py` (250 LOC — `CodexHost` + `parse_apply_patch`), `hooks.json` (70 LOC, Codex hook registration), `.codex-plugin/plugin.json`, `ORCHESTRATOR.md`.
- **Tests**: `.github/scripts/test_codex_adapter.py` (665 LOC); existing hook suites under `plugins/ca/hooks/tests/` and `.github/scripts/`.
- **Docs/governance**: ADR-0011, spike `codex-extension-surface.md`, plan `codex-support.md`, `docs/parity.md`, README/CHANGELOG.

Languages: Python 3 stdlib-only (~95% of scope), JSON manifests, Markdown.

## Dedup-aware reading rule (cost lever, acknowledged Phase 0)

Vendored copies under `plugins/*/hooks/*.py` are byte-identical to `core/pysrc/` by contract. Lenses read **`core/pysrc/` as canonical** plus the per-plugin non-synced files (`_host.py` ×2, `hooks.json`, plugin manifests); copy fidelity is verified via `python tools/sync-core.py --check`, not by re-reading copies.

## Risk ranking (highest first) & trust boundaries

1. **`plugins/ca-codex/hooks/_host.py` + `core/pysrc/hostapi.py`** — TRUST BOUNDARY: untrusted tool payloads from either host cross here into shared guard logic. `parse_apply_patch` is a security-critical parser: any divergence from Codex's lenient Rust parser where Codex APPLIES what the adapter fails to decompose = guard bypass. Fail-closed "opaque" op is the load-bearing mitigation.
2. **Enforcement entries** (`pre-write.py`, `pre-bash.py`, `pre-edit.py`, `post-write-edit.py`, `security-pass.py`, `git-enforce.py`) — gate integrity; must behave identically through the seam on both hosts.
3. **Shared `.codearbiter/` projectContext contract** — TRUST BOUNDARY between concurrent hosts: `_arbiterstatelib.py`, `_ledgerlib.py`, `_taskboardlib.py`, `_provenancelib.py`, `session-start.py`, append-only logs. Two hosts (Claude + Codex sessions) may read/write the same state dir concurrently; corruption or lost-update here breaks the audit trail (conflict-hierarchy level 1).
4. **`plugins/ca-codex/hooks/hooks.json`** — silent-un-enforcement risk: a hook missing from registration simply never runs (commit `e19778c` fixed exactly this class). Registration completeness vs the ca side is auditable.
5. **`tools/sync-core.py` + CI wiring** — drift = the two hosts silently enforcing different rules.
6. **Host-conditional behavior** (`has_statusline`/`has_read_tool`/`has_prunable_transcript` gates; `project_root` divergence — Codex deliberately ignores `CLAUDE_PROJECT_DIR`) — wrong-project resolution risk in nested/adjacent sessions.
7. Docs/governance artifacts — lowest.

## AI-authorship markers & iteration depth

Entire branch is AI-authored under supervision (uniform conventional-commit shapes; large surface over only 7 commits → high generation ratio). `e19778c` (a registration bug fixed post-hoc) evidences the silent-un-enforcement failure mode already occurring once. Scrutiny boost + small severity prior on: `plugins/ca-codex/hooks/_host.py`, `hooks.json`, and the seam call-site refactor across all entry scripts (M1 touched ~30 files in one commit).

## Active lenses

appsec, architecture, reliability, secrets-supply, test-fidelity, coverage, infra, observability, performance, typesafety. **Skipped: migration** (no DB migrations in scope).
Wave partition (recorded in run-started): 1=[appsec, architecture, reliability] · 2=[secrets-supply, test-fidelity] · 3=[coverage, infra, observability, performance, typesafety].
