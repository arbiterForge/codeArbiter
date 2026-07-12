# Codex Plugin Parity Repair Implementation Plan

**Goal:** Make `ca-codex` validate, install, and enforce correctly on the pinned Codex CLI 0.144.1 baseline while preserving generated Claude/Codex parity and one shared `.codearbiter/` store.

**Architecture:** Repair Codex packaging at the host-adapter boundary, repair generated skill YAML at the canonical `core/surface/` source, and add CI checks that exercise both generators and the pinned plugin schema. Existing shared Python behavior remains canonical under `core/pysrc/`; host distributions remain checked-in deterministic outputs.

**Tech stack:** Python 3 stdlib, JSON, YAML frontmatter parsed by the Codex validator, GitHub Actions YAML, Codex CLI 0.144.1.

## Global constraints

- All committed filenames, paths, prose, and commit messages must remain free of the repository-prohibited framework name.
- Codex validation and live-fire claims are pinned to Codex CLI 0.144.1; the declared minimum remains `rust-v0.134.0` only where existing compatibility tests cover it.
- Generated files are changed only by `tools/sync-core.py` or `tools/build-surface.py` after editing canonical sources.
- Concurrency tests cover sequential shared-store behavior and concurrent append-only logs only; RMW state and the dev marker remain outside this campaign per ADR-0012 after ratification.
- Any `plugins/ca-codex/` payload change requires an independent SemVer bump and changelog entry.

---

### Task 1: Pin executable package validation in CI

**Files:**
- Create: `.github/scripts/validate_codex_plugin.py`
- Create: `.github/scripts/test_validate_codex_plugin.py`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Produces: `validate_plugin(plugin_root: Path, marketplace_path: Path) -> list[str]`, returning every schema or frontmatter error without mutating the tree.
- Produces: CLI output beginning with `Codex validation baseline: 0.144.1` and exiting nonzero when errors exist.

- [ ] Write failing unit tests using temporary manifests for unsupported top-level fields, missing required interface fields, scalar `defaultPrompt`, malformed skill YAML, stale marketplace source shape, missing policies/category, and a fully valid fixture.
- [ ] Run `python .github/scripts/test_validate_codex_plugin.py`; expect failures because the validator module does not exist.
- [ ] Implement the stdlib validator with deterministic error ordering and explicit schema constants for the 0.144.1 baseline. Parse the limited shipped frontmatter grammar without adding a PyYAML dependency; reject unquoted mapping colons in scalar values and invalid `argument-hint` scalar syntax.
- [ ] Add a CI step that prints `codex --version` when available, prints the validator baseline, runs the validator, and keeps the existing tracked-JSON parse check.
- [ ] Run the validator tests; expect all tests to pass.
- [ ] Commit `.github/scripts/validate_codex_plugin.py`, its tests, and `.github/workflows/ci.yml` with message `test(codex): pin plugin package validation`.

### Task 2: Repair canonical skill frontmatter generation

**Files:**
- Modify: `tools/build-surface.py`
- Modify: `.github/scripts/test_build_surface.py` if present; otherwise create it
- Regenerate: `plugins/ca-codex/skills/ca-feature/SKILL.md`
- Regenerate: `plugins/ca-codex/skills/ca-fix/SKILL.md`
- Regenerate: `plugins/ca-codex/skills/ca-new-skill/SKILL.md`
- Regenerate: `plugins/ca-codex/skills/ca-release/SKILL.md`
- Regenerate: `plugins/ca-codex/skills/ca-review/SKILL.md`
- Regenerate any additional Codex surface whose byte output changes from the quoting rule

**Interfaces:**
- Produces: `yaml_double_quote(value: str) -> str`, used by Codex skill synthesis for `description` and `argument-hint` values.
- Preserves: Claude output byte identity.

- [ ] Add generator tests proving colon-bearing descriptions and structured-looking argument hints render as valid quoted YAML for Codex while Claude rendering stays byte-identical.
- [ ] Run the focused generator tests; expect the colon-bearing cases to fail.
- [ ] Add minimal deterministic YAML double-quoting to Codex frontmatter synthesis, escaping backslashes, double quotes, and control characters.
- [ ] Run `python tools/build-surface.py` to regenerate both distributions.
- [ ] Run the focused tests and `python tools/build-surface.py --check`; expect both to pass.
- [ ] Run `python tools/sync-core.py --check`; expect byte identity to remain green.
- [ ] Commit canonical generator changes and generated output with message `fix(codex): emit valid skill frontmatter`.

### Task 3: Repair the manifest and repository marketplace

**Files:**
- Modify: `plugins/ca-codex/.codex-plugin/plugin.json`
- Modify: `.agents/plugins/marketplace.json`
- Modify: `.github/scripts/test_codex_adapter.py`
- Modify: `plugins/ca-codex/CHANGELOG.md`

**Interfaces:**
- Manifest interface fields: `displayName`, `shortDescription`, `longDescription`, `developerName`, `category`, `capabilities`, `defaultPrompt`, and `brandColor` with validator-approved types.
- Marketplace entry: `{name, source: {source: "local", path: "./plugins/ca-codex"}, policy: {installation: "AVAILABLE", authentication: "ON_INSTALL"}, category: "Developer Tools"}`.

- [ ] Extend adapter tests to assert the exact accepted manifest and marketplace shapes, asset/component references, and SemVer shape.
- [ ] Run `python .github/scripts/test_codex_adapter.py`; expect new assertions to fail against the current JSON.
- [ ] Update the manifest, removing top-level `displayName`, converting `defaultPrompt` to an array, and adding required interface fields. Bump `0.2.0` to `0.2.1` and add the dated repair changelog section.
- [ ] Update the repository marketplace to the validated local-source, policy, and category shape while preserving its root metadata where accepted.
- [ ] Run the adapter suite and pinned validator; expect both to pass.
- [ ] Commit the manifest, marketplace, tests, and changelog with message `fix(codex): repair plugin package metadata`.

### Task 4: Enforce shared-store and generator parity

**Files:**
- Create: `.github/scripts/test_dual_host_store.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `.codearbiter/decisions/0012-dual-host-store-concurrency-parity.md` only after explicit ratification

**Interfaces:**
- Test helper: `run_hook(plugin: str, script: str, payload: dict, cwd: Path) -> CompletedProcess[str]`.
- Test scenarios: one store, shared enablement/context, idempotent initialization, host-attributed append-only audit writes, concurrent audit-log appends, and one enforcement result per host event.

- [ ] Record explicit ADR-0012 ratification before treating its scope as accepted; do not invent the ratifier identity.
- [ ] Write sequential dual-host tests plus concurrent append-only-log tests. Do not assert race freedom for `open-tasks.md` or `.markers/dev-active`.
- [ ] Run `python .github/scripts/test_dual_host_store.py`; expect any newly exposed parity defect to fail with the exact host/scenario named.
- [ ] Make only host-parity fixes required by those tests in canonical `core/pysrc/`, then run `python tools/sync-core.py` to vendor them. Do not add locks or CAS for de-scoped state.
- [ ] Add the dual-host test, `python tools/sync-core.py --check`, and `python tools/build-surface.py --check` to required CI coverage.
- [ ] Run the new test and both generator checks; expect all to pass.
- [ ] Commit with message `test(codex): enforce dual-host shared-store parity`.

### Task 5: Install and live-fire the pinned Codex package

**Files:**
- Modify: `docs/codex-parity-testing.md`
- Modify: `docs/parity.md`
- Modify: `plugins/ca-codex/CHANGELOG.md` only if live results change release notes
- Modify beta/preview labels only after all three ADR-0011 live checks pass

**Interfaces:**
- Evidence record includes CLI version, validator identity, marketplace add/install output, installed snapshot path, trust-review result, SessionStart stdout result, and exit-2/non-empty-stderr result.

- [ ] Update the live-parity guide with exact Codex 0.144.1 marketplace and plugin commands and a result block for the three promotion checks.
- [ ] Run the pinned validator and capture the pre-fix failure evidence from the parent commit plus the post-fix clean output for the eventual PR description.
- [ ] Add this repository as a local marketplace and install `ca-codex` without changing unrelated marketplace entries.
- [ ] Inspect the installed snapshot and confirm manifest, hooks, and generated skills are present.
- [ ] Start a fresh Codex thread on a throwaway enabled fixture and record SessionStart stdout persona injection.
- [ ] Exercise the untrusted/approved hook states and confirm doctor reports both correctly.
- [ ] Trigger a protected write and record exit 2 with non-empty stderr surfaced to the model.
- [ ] If all three live checks pass, remove beta/preview labeling and update `docs/parity.md`; otherwise retain beta and ledger each failed observation.
- [ ] Run the complete relevant suite, `git diff --check`, the prohibited-name scan over the branch delta, and verify the working tree contains no generated drift.
- [ ] Commit documentation and promotion status with message `docs(codex): record live parity verification`.
