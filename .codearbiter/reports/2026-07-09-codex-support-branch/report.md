# Tribunal report — 2026-07-09-codex-support-branch

- Scope: `feat/codex-support-m0` branch diff vs `main` (merge-base `ddcfc42`), 7 commits, 128 files.
- Focus: dual-host support — Claude Code and OpenAI Codex CLI sharing one `.codearbiter/` projectContext, via shared core (`core/pysrc/`) + per-host `_host.py` adapters (ADR-0011).
- Date: 2026-07-09. Orchestrator + wave-1 lenses: Fable 5 (high). Waves 2-3: Sonnet 5.
- Token estimate (Phase 0): 1.2M-4.9M band. Observed lens spend (summed `lens-completed`): ~0.85M tokens across 10 lenses (orchestrator overhead not included).

## Lenses
- Launched (10): appsec, architecture, reliability, secrets-supply, test-fidelity, coverage, infra, observability, performance, typesafety.
- Skipped (1): migration — no DB/schema migrations in scope (`migration-pass.py` is a doc-migration hook, not schema).
- Findings: 36 total across the roster. secrets-supply and test-fidelity returned 0.

## Blocking-severity note
Critical/high below are blocking-severity: work that should block shipping the affected code. This lane is not a gate and blocks nothing; the BETA status of ca-codex is the intended hold.

## Findings (kept/combined, by calibrated severity)

### HIGH
- **architecture-002** · `.github/workflows/ci.yml:22-68; .github/workflows/ci.yml:425-440; tools/sync-core.py:14-17` · Wire the vendoring contract into CI — sync-core --check, core/** path filters, and ca-codex jobs are all absent · decision: keep · group `group-ci-vendoring` · conf 0.9 · [phase-1](plans/phase-1.md)
- **architecture-004** · `core/pysrc/hostapi.py:176-191; core/pysrc/hostapi.py:168-173; plugins/ca-codex/hooks/_host.py:21-25` · load_host()'s silent fallback to Claude defaults fail-opens the entire write-gate surface on Codex · decision: keep · conf 0.8 · [phase-1](plans/phase-1.md)
- **coverage-003** · `core/pysrc/hostapi.py:176-191; .github/scripts/test_codex_adapter.py:1-666` · hostapi.load_host()'s except-and-fall-back-to-Claude-defaults path has zero test coverage anywhere in the suite · decision: keep · conf 0.85 · [phase-3](plans/phase-3.md)
- **infra-001** · `.github/workflows/release.yml:1-109` · release.yml has no publish path for ca-codex; the plugin can never be tagged/released via the sanctioned mechanism · decision: keep · conf 0.9 · [phase-3](plans/phase-3.md)
- **infra-002** · `.github/scripts/test_hooks_cold_install.py:68-69; plugins/ca-codex/hooks/hooks.json:1-71; plugins/ca/hooks/hooks.json:1-68` · Cold-install interpreter matrix never exercises ca-codex's differently-shaped hooks.json, and ca-codex's own mechanism drops STUB-python3 coverage · decision: keep · conf 0.85 · [phase-3](plans/phase-3.md)
- **observability-001** · `core/pysrc/_hooklib.py:660-712` · gate-events.log/overrides.log cannot attribute an entry to Claude or Codex despite both hosts sharing one audit trail · decision: combine · group `group-shared-store` · conf 0.9 · [phase-3](plans/phase-3.md)
### MEDIUM
- **appsec-001** · `plugins/ca-codex/hooks/_host.py:116-145; plugins/ca-codex/hooks/_host.py:229-242` · parse_apply_patch fail-closed 'opaque' net is whole-envelope, not per-file — a dropped directive line un-guards a protected write · decision: keep · conf 0.7 · [phase-1](plans/phase-1.md)
- **architecture-001** · `core/pysrc/pre-write.py:153-164; core/pysrc/pre-edit.py:205-216; core/pysrc/_hooklib.py:76-84` · Remove or wire the dead `host` parameter on all 20 run(host) entry points — the seam handle is cosmetic · decision: keep · conf 0.85 · [phase-1](plans/phase-1.md)
- **architecture-003** · `.github/scripts/test_codex_adapter.py:1-665; .github/workflows/ci.yml:146-252` · test_codex_adapter.py (665 LOC) has zero callers — the adapter contract suite is orphaned · decision: keep · group `group-ci-vendoring` · conf 0.85 · [phase-1](plans/phase-1.md)
- **architecture-005** · `plugins/ca-codex/hooks/hooks.json:1-70; plugins/ca-codex/.codex-plugin/plugin.json:5; tools/sync-core.py:41-50` · ca-codex vendors ~15 entry scripts with zero invokers on that host, and its manifest points users at a /ca-init that does not ship · decision: keep · conf 0.8 · [phase-1](plans/phase-1.md)
- **architecture-006** · `core/pysrc/_hooklib.py:341-353; core/pysrc/hostapi.py:66-96; plugins/ca-codex/hooks/_host.py:173-187` · Host.project_root's payload-cwd leg is dead in production — no caller ever passes the payload · decision: combine · group `group-project-root-seam` · conf 0.8 · [phase-1](plans/phase-1.md)
- **architecture-010** · `plugins/ca-codex/ORCHESTRATOR.md:1-147; tools/sync-core.py:30-38` · ORCHESTRATOR.md is a hand-duplicated two-copy surface with no sync mechanism — the declined copy-and-adapt mode, unguarded · decision: keep · conf 0.85 · [phase-1](plans/phase-1.md)
- **coverage-001** · `plugins/ca-codex/hooks/_host.py:116-145; .github/scripts/test_codex_adapter.py:237-260` · No test covers a partially-recognized apply_patch envelope that silently drops an unrecognized directive instead of failing closed · decision: combine · group `group-parser-partial-op` · conf 0.85 · [phase-3](plans/phase-3.md)
- **coverage-004** · `core/pysrc/session-start.py:539-557; plugins/ca/hooks/tests/test_session_start.py:187-260; .github/scripts/test_codex_adapter.py:118-125` · session-start.py's host.has_statusline gate is asserted as a flag value but never exercised through main()'s actual skip behavior · decision: keep · conf 0.8 · [phase-3](plans/phase-3.md)
- **infra-003** · `.github/scripts/check_license_consistency.py:37-41; .github/workflows/ci.yml:408-423; plugins/ca-codex/.codex-plugin/plugin.json:7` · license-consistency CI check never examines ca-codex's plugin.json, so a license drift on the new plugin ships undetected · decision: keep · conf 0.85 · [phase-3](plans/phase-3.md)
- **observability-004** · `core/pysrc/session-start.py:539-649; core/pysrc/doctor.py:176-195` · session-start.py and doctor.py never surface which host they resolved — a dormant Codex install is indistinguishable from a working one at the one place a maintainer would look · decision: keep · conf 0.8 · [phase-3](plans/phase-3.md)
- **performance-001** · `core/pysrc/hostapi.py:173-198; plugins/ca-codex/hooks/_host.py:173-198; core/pysrc/_hooklib.py:341-353` · Every Codex-host hook invocation spawns a git subprocess because project_root() never threads the payload cwd through · decision: combine · group `group-project-root-seam` · conf 0.85 · [phase-3](plans/phase-3.md)
- **performance-003** · `core/pysrc/_hooklib.py:341-353; core/pysrc/_hooklib.py:660-685; core/pysrc/_hooklib.py:696-712` · Host.project_root() is never memoized at the process level — every BLOCK/REMIND/WARN re-resolves it, multiplying Codex's per-call subprocess spawn within a single invocation · decision: combine · group `group-project-root-seam` · conf 0.8 · [phase-3](plans/phase-3.md)
- **reliability-001** · `core/pysrc/doctor.py:85-93; plugins/ca-codex/.codex-plugin/plugin.json:1` · doctor.py hard-codes .claude-plugin/plugin.json, so every healthy ca-codex install is reported UNHEALTHY (FAIL + exit 1) · decision: combine · group `group-manifest-path` · conf 0.9 · [phase-1](plans/phase-1.md)
- **reliability-005** · `plugins/ca-codex/hooks/_host.py:173-198; core/pysrc/_hooklib.py:341-353; core/pysrc/pre-write.py:130-134` · CodexHost.project_root's designed primary signal (payload cwd) is unreachable — no shared-core call site passes a payload — and when wired it returns the session cwd verbatim, not the repo root · decision: combine · group `group-project-root-seam` · conf 0.75 · [phase-1](plans/phase-1.md)
- **reliability-008** · `plugins/ca-codex/hooks/hooks.json:1-70; plugins/ca/hooks/hooks.json:11-40; core/pysrc/_hooklib.py:17-24` · ca-codex hooks.json drops the dual interpreter registration — a python interpreter miss makes every Codex gate silently fail open · decision: keep · conf 0.7 · [phase-1](plans/phase-1.md)
### LOW
- **architecture-008** · `core/pysrc/pre-edit.py:53-56; core/pysrc/pre-edit.py:86-92; core/pysrc/pre-edit.py:119-122` · Shared-core pre-edit.py branches on Claude-native tool names, bypassing the normalize_tool seam it sits behind · decision: keep · conf 0.75 · [phase-1](plans/phase-1.md)
- **coverage-002** · `plugins/ca-codex/hooks/_host.py:243-247; .github/scripts/test_codex_adapter.py:252-260` · CodexHost.iter_file_ops' non-write-tool defensive fallback branch (mcp__*/OTHER carrying file_path) is untested · decision: keep · conf 0.75 · [phase-3](plans/phase-3.md)
- **reliability-002** · `core/pysrc/_updatelib.py:83-94; core/pysrc/session-start.py:494-505` · Update-available notifier silently never fires on Codex: _updatelib.installed_version reads .claude-plugin/plugin.json, absent in ca-codex · decision: combine · group `group-manifest-path` · conf 0.9 · [phase-1](plans/phase-1.md)
- **reliability-006** · `core/pysrc/prune-transcript.py:41-59` · prune-transcript staleness_check resolves root from raw payload cwd, diverging from the seam — CONFIRM-09 warnings silently never fire in cwd≠root sessions · decision: keep · conf 0.8 · [phase-1](plans/phase-1.md)
- **reliability-009** · `core/pysrc/_githooks.py:122-137; core/pysrc/_githooks.py:297-372; core/pysrc/session-start.py:570-576` · Dual-host git-hook shims ping-pong between plugin roots; uninstalling one plugin silently fail-opens git-level enforcement installed by it for the other host · decision: keep · conf 0.75 · [phase-1](plans/phase-1.md)

## Decisions needed (decision-required — resolve via `/ca:adr` or a discussion, not a fix ticket)

- **architecture-007** (high, conf 0.8) · group `group-shared-store` · `core/pysrc/_hooklib.py:660-693; core/pysrc/_hooklib.py:626-649; core/pysrc/taskwrite.py:1-133`
  - Two hosts share one .codearbiter/ store with no concurrency contract and no host attribution in the audit trail
  - Question / rationale: ADR-grade: define the coordination contract for two hosts sharing one .codearbiter/ store: locking/CAS on read-modify-write state, and host= attribution in gate-events.log/overrides.log. Resolve via /ca:adr. Grouped with reliability-004 and reliability-007.
- **reliability-004** (high, conf 0.75) · group `group-shared-store` · `core/pysrc/taskwrite.py:73-120`
  - taskwrite.py board mutation is a lock-free read-modify-write — concurrent Claude+Codex sessions in one repo lose updates to open-tasks.md
  - Question / rationale: Concrete instance of the group-shared-store contract: lock/CAS the board read-modify-write. Grouped with architecture-007.
- **appsec-002** (medium, conf 0.6) · `plugins/ca-codex/hooks/hooks.json:16-55; plugins/ca-codex/hooks/_host.py:163-169`
  - Codex MCP file-write tools (mcp__*) normalize to OTHER and bypass every write-path guard
  - Question / rationale: security-controls.md must state MCP-tool writes explicitly in- or out-of-scope for the write gate on Codex; not a clear code fix, a boundary-scope decision.
- **reliability-007** (medium, conf 0.7) · group `group-shared-store` · `core/pysrc/session-start.py:446-467; core/pysrc/session-start.py:546-549`
  - SessionStart of either host clears the shared dev-active marker and logs a synthetic 'DEV: exit' while the other host's session may still be live in /dev
  - Question / rationale: SessionStart unconditionally clears the repo-global dev-active marker and logs a synthetic DEV: exit, clobbering a concurrent host live /dev session and writing a false audit close. Part of the group-shared-store repo-global-vs-session-local contract.

## Duplicate / corroborating (folded into an anchor, not filed separately)

- observability-002 → duplicate of **architecture-004** · Same defect as architecture-004 from the observability angle — load_host swallows a broken _host.py with zero breadcrumb; the fix must emit a signal, not just fail closed.
- observability-003 → duplicate of **reliability-002** · Same defect as reliability-002 — update notifier dark on Codex via the wrong manifest path; folds into group-manifest-path.
- performance-002 → duplicate of **architecture-001** · Same root as architecture-001 (dead run(host) param) — the perf consequence is _host.py exec-loaded twice per invocation. Fixing the dead param fixes this.
- reliability-003 → duplicate of **architecture-004** · Same root cause as architecture-004 (load_host silent Claude-default fallback fail-opens the Codex write gate).
- typesafety-001 → duplicate of **architecture-004** · Duplicate of architecture-004; the reproduction raises confidence in that anchor and the fix MUST fail closed.

## Investigate appendix (below confidence gate; preserved, not filed)

- architecture-009 (low, conf 0.6) · `core/pysrc/_hooklib.py:1-773` · _hooklib.py accretion: 773 LOC spanning six unrelated concern clusters in the most-consumed module
