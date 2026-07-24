# Tribunal report — 2026-07-17-pi-support-branch

- Run: `2026-07-17-pi-support-branch` · scope: repo root, branch `feat/pi-support` (+79,523/−1,003, 469 files)
- Models: Fable 5 (orchestrator + appsec/architecture/reliability), Sonnet 5 (remaining lenses + sidecar), Haiku 4.5 (mappers)
- Tokens: estimated band 7M–29M; observed subagent spend ~1.3M (best-effort sum of `lens-completed`/sidecar events; orchestrator spend not included; well under band because the appsec/secrets scopes came back clean quickly)
- Lenses launched (10): appsec, architecture, reliability, secrets-supply, test-fidelity, coverage, infra, observability, performance, typesafety. Skipped (1): migration (no database/schema migrations in scope).
- Findings: 0 critical · 4 high · 8 medium · 5 low (calibrated). Kept/combined: 15. Investigate: 3. Decision-required: 1.

Critical/high are blocking-severity findings: work that should block shipping the affected code. This lane is not a gate and blocks nothing.

## High

- `infra-001` · `.github/workflows/ci.yml:829-867` · `ca-pi-codeql` job absent from the `ci-passed` merge gate (branch protection requires only Merge readiness; job uses `upload: never`, so its findings reach nothing) · add to needs/required_results · keep · plans/phase-3.md
- `observability-001` · `plugins/ca-pi/tools/src/runner.ts` / `dispatch.ts` · Pi child dispatch writes no gate-events.log audit line and discards child stderr, unlike sibling paths bridge.ts:213-243 and compaction.ts:436-451 · add audit parity + bounded stderr retention · combine (pi-child-audit) · plans/phase-3.md
- `coverage-001` · `plugins/ca-pi/tools/src/windows-supervisor.ts:33-175` · supervisor protocol logic never executed by any test (only a source-text string check) · unit-test parseLaunch/boundedRead/fail-closed wiring · keep · plans/phase-3.md
- `coverage-002` · `plugins/ca-pi/tools/src/runtime-resolver.ts:105-159` · trust-boundary fail-closed branches mocked out in the only test touching them · dedicated un-mocked suite · keep · plans/phase-3.md
- `typesafety-001` · `plugins/ca-pi/tools/src/pi-api.d.ts:1-7` · `ExtensionAPI` is an empty stub; host-boundary calls go through `as unknown as` / `as never` casts (extension.ts:428-537) · structural port interfaces · keep · plans/phase-3.md

## Medium

- `reliability-001` · `bridge.ts:302-335` · win32 killTree: spawnSync taskkill with no timeout, no kill fallback, no settle deadline; a failed kill wedges the gated call · combine (bridge-hardening) · plans/phase-1.md
- `reliability-003` · `bridge.ts:172-199` · `this.ready = validatePaths()` unhandled until first call(); pre-first-call rejection crashes the process · combine (bridge-hardening) · plans/phase-1.md
- `architecture-001` · `core/pysrc/pre-bash.py:765-1075` · 1,119-LOC fat entry point violating the repo's thin-entrypoint convention; synced to 3 hosts · extract `_bashguardlib.py` · keep · plans/phase-1.md
- `architecture-002` · `core/pysrc/_hooklib.py` · god module: 46 functions, imported by 28/44 core modules · partition along concern seams · keep (after architecture-001) · plans/phase-1.md
- `coverage-003` · `core/pysrc/_gitexec.py:16-37` · trusted-executable path validation has no direct unit test · keep · plans/phase-3.md
- `coverage-004` · `tools/ci-impact.py:422-448` · the fail-safe except branch (the actual guarantee) untested · keep · plans/phase-3.md
- `observability-002` · `windows-supervisor.ts` / `process-tree.ts` · all failure modes collapse to bare REFUSED/false with no reason · combine (pi-child-audit) · plans/phase-3.md
- `performance-002` · `.github/scripts/pi_benchmark.py` + `benchmark-boundary.ts:40-45` · benchmark stubs BridgePort.call, so the real per-call Python spawn cost is unmeasured · keep · plans/phase-3.md

## Low

- `reliability-004` · `core/pysrc/session-start.py:864-872` · unguarded write_standup_marker can fail the never-brick SessionStart hook · keep · plans/phase-1.md
- `reliability-005` · `tools/sync-core.py:105-111` · non-atomic vendored-copy writes; interruption leaves truncated hook files · keep · plans/phase-1.md
- `architecture-003` · `bridge.ts:406` / `compaction.ts:453` / `attestation.ts:4` · three dead exports, zero callers · keep · plans/phase-1.md
- `typesafety-002` · `core/pysrc/_gitexec.py`, `_prunepolicy.py` · missing the mandated `# Public API` header convention · keep · plans/phase-3.md

## Decisions needed

- `performance-001` · `bridge.ts:269-338` · Every gated Pi tool call spawns a fresh Python bridge process (CPython cold start + hook-module import). Question: accept per-call spawn as the cross-host standard cost model, or move to a persistent bridge worker (daemon lifecycle + new security surface)? ADR-candidate — resolve via `/ca:adr`. Downgraded from high at calibration: Claude Code's harness also spawns per-call hook processes, so this is parity, not regression.

## Investigate appendix

- `reliability-002` · `runner.ts:603-637` · spawn-error listener attachment window; nextTick ordering claim needs a repro (0.6)
- `architecture-004` · `core/pysrc/_prunelib.py` · 1,365-LOC accretion; continue the _prunepolicy extraction opportunistically (0.6)
- `test-fidelity-001` · `test_pi_platform_contract.py:133-144` · duplicated 120_000 timeout literal (0.4)

## Sidecar — docs-site content audit (user-mandated adjunct, not lens findings)

Findings on disk under `findings/docs-claude-code/` (15: 3H/7M/5L), `findings/docs-codex/` (3: 1H/1M/1L), `findings/docs-pi/` (6: 3H/3M), `findings/docs-visuals/` (9 opportunities).

Headline: the published docs site documents a two-host world. Pi has zero presence (no page, no sidebar entry, no install/trust/troubleshooting content — it all lives only in repo-root README/docs), ca-sandbox has no page, and overview/index/install still say two hosts while the repo ships four plugins. Codex docs are in good shape (no stale beta labels, parity page exists); worst Codex gap is that the reference section never states Codex runs roles inline rather than Task-dispatch.

Visuals: 11 hand-drawn technical SVGs already exist and carry the load. Top three additions: a commit-gate 9-phase diagram, a core→three-host generation fan-out diagram, and a social-preview/og:image card. Recommendation across the board: house-style hand-drawn SVG or mermaid, not GPT-rendered images — the one place generated art could apply (SMARTS lens icons, landing decoration) is flagged as a slop risk to avoid.

One process note: the Claude Code docs walker reported a suspicious system-reminder-styled block referencing ADR-0008 inside a tool result during its walk. It did not act on it. Worth a separate look as a possible prompt-injection vector in a hook or tool-response path.
