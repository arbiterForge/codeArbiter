# Code map — codeArbiter

Coarse concern → path → role orientation, synthesized from Scout C (architecture)
evidence per `context-creation` Phase 5, against the tree as of the
`fix/mode-write-clobber` merge with `origin/main` (2026-09-15). Module/concern
granularity only — not a file listing. Kept in sync via `.provenance/code-map.json`.

## Shared hook library (core/pysrc)

- `core/pysrc/session-start.py` — SessionStart hook; detects an arbiter-enabled repo, injects the ORCHESTRATOR persona and live project state
- `core/pysrc/prompt-submit.py`, `pre-write.py`, `pre-edit.py`, `pre-read.py`, `pre-bash.py`, `babysit.py` — the remaining hook entry points, each a thin dispatcher into the shared libraries below
- `core/pysrc/_hooklib.py` — hook dispatch kernel; host DI seam, gate evaluation, marker/project-root resolution
- `core/pysrc/_bashguardlib.py`, `_protectedstatelib.py`, `_provenancelib.py`, `_sensitivelib.py`, `_releaselib.py`, `_taskboardlib.py`, `_modelib.py`, `_adrlifecycle.py`, `_appendonlyconflictlib.py`, etc. — one domain library per module (shell guarding, protected-state registry, provenance/drift, crypto/secret detection, release orchestration, task board, mode state, ADR lifecycle, sanctioned append-only-conflict resolution)

## Host registry and generated-kernel build (ADR-0031)

- `core/hosts.json` — single source of truth for the three hosts (claude, codex, pi): plugin dirs, command forms, surface rules, tool classes, permission policies
- `tools/host_descriptors.py` — strict loader/validator for `core/hosts.json`, exposing immutable per-host descriptor objects
- `tools/build-surface.py` — descriptor-driven generator; renders `core/surface/` templates through `core/hosts.json` rules into each plugin's byte-identical command/skill/include tree (e.g. a command becomes a Codex/Pi `SKILL.md` via the applicable surface rule)
- `tools/build-host-packages.py` — generates the ca-pi npm `package.json` (scoped name, provenance, files whitelist)
- `tools/sync-core.py` — byte-identical vendoring of `core/pysrc` into each `plugins/ca*/hooks/`; the CI parity gate (`--check`) enforces zero drift
- `plugins/ca/generated/`, `plugins/ca-codex/generated/`, `plugins/ca-pi/generated/` — build-generated `command-catalog.json` (all three) and `roles.json` (ca-pi only); consumed by each host's runtime skill dispatch

## Shared surface definitions (core/surface)

- `core/surface/skills/INDEX.md` — skills directory index; catalogs the full workflow set (context-creation, brainstorming, release, commit-gate, tdd, decision-lifecycle, tribunal, etc.)
- `core/surface/skills/*/SKILL.md` — one multi-phase workflow definition per skill; single source of truth, generated into each plugin
- `core/surface/commands/*.md` — one slash-command definition per file (38 commands: feature, fix, release, sprint, adr, pr, review, override, …); routes to a skill
- `core/surface/agents/INDEX.md`, `core/surface/agents/scout.md` — dispatched-subagent persona directory and the read-only evidence-gatherer role

## Plugin implementations (four sibling plugins)

- `plugins/ca/` (v2.21.3) — the Claude Code plugin; `.claude-plugin/plugin.json` manifest, `hooks/*.py` (vendored from `core/pysrc`), `skills/`/`commands/`/`agents/`/`generated/` (generated from `core/surface`+`core/hosts.json`)
- `plugins/ca-codex/` (v0.13.3) — the Codex CLI plugin; `.codex-plugin/plugin.json` manifest; commands render as `skills/ca-codex/SKILL.md`-style dispatch entries (no native slash commands)
- `plugins/ca-pi/` (v0.14.3, npm-published as `@arbiterforge/ca-pi`) — the Pi governance plugin; `package.json` manifest declares JS `extensions/codearbiter.js` (bundled) plus `skills/`; skills carry a `ca-` name prefix
- `plugins/ca-sandbox/` (v0.1.6) — infrastructure/testing plugin; Docker-based untrusted-code isolation, ephemeral containers, no persistent `.codearbiter/` inside the container

## Release provenance and tag immutability (ADR-0029, ADR-0032, ADR-0034)

- `.github/RELEASE-PROVENANCE.md` — prose contract: immutability rules, receipt capture, legacy-epoch governance
- `.github/published-tags.json` — append-only ledger of original-publication receipts (tag, commit sha, evidence grade) for the four installable tag series
- `.github/legacy-published-tags.json` — ADR-0034's closed, immutable 44-tag legacy epoch; forward-detection only, never original-publication proof
- `.github/scripts/check_tag_immutability.py` — the merge-gate check comparing every live tag ref against the two ledgers above

## Academy integration (submodule, currently unpopulated)

- `.gitmodules` — pins `academy-source` to `https://github.com/arbiterForge/arbiter-academy.git`; the checkout is present but empty (not yet initialized/populated) as of this merge

## Documentation site (site/)

- `site/astro.config.mjs`, `site/base.mjs` — Astro build configuration and the single source of truth for the site's base path
- `site/package.json` — npm manifest; vitest content-structure suite + link-audit
- `site/src/curated/` — hand-written doc prose, merged by the generator (not auto-synced to the surface it documents)
- `site/src/generated/` — fragments generated from `core/surface` skills/commands
- `site/scripts/release-applicability.ts` — new release-applicability tooling (hashes content with the approved `createHash("sha256")`)

## Project state store (.codearbiter/)

- `.codearbiter/CONTEXT.md` — project identity/scope/stage; `arbiter: enabled` frontmatter gates session startup and every enforcement hook
- `.codearbiter/decisions/`, `.codearbiter/decisions/adr-lifecycle.jsonl` — Architecture Decision Records and the append-only ADR lifecycle ledger (proposal → accepted → obligations bound/verified)
- `.codearbiter/specs/`, `.codearbiter/plans/` — approved feature specs and execution plans (`/ca:feature`)
- `.codearbiter/open-tasks.md` — task board; append-only via `taskwrite.py`, never a direct edit
- `.codearbiter/open-questions.md` — deferred `[CONFIRM-NN]` items
- `.codearbiter/gate-events.log`, `overrides.log`, `triage.log`, `sprint-log.md` — append-only audit trails
- `.codearbiter/.provenance/` — per-doc source evidence and hashes backing drift detection
- `.codearbiter/security-controls.md` — the project's approved/forbidden crypto primitives, secret-handling policy, and declared boundary exceptions

## Test infrastructure (tests/, plugin hook tests)

- `tests/test_p05_fixture.py` — protocol-level test suite exercising hook entry points, gate evaluation, and state mutations
- `plugins/ca/hooks/tests/` — the primary unit-test suite for the shared hook libraries (not synced by `sync-core.py`; single copy); includes `test_crypto_context.py`, a detector-fixture file whose crypto-pattern strings are deliberately non-operational (mirrors the `.github/scripts/` `createHash("md5")` precedent in `security-controls.md`)

## CI/CD (.github/)

- `.github/workflows/ci.yml`, `release.yml`, `codeql.yml`, `docs.yml`, `npm-publish.yml`, `pi-promotion.yml` — GitHub Actions workflows gating test/lint, release, security scanning, docs, and publishing
- `.github/scripts/` — helper scripts invoked by workflows (release checks, contract/consistency checks, provenance/tag-immutability tooling, ADR lifecycle checks)

## Architectural pattern

**Multi-host governance framework, shared core + generated kernels** (ADR-0007, ADR-0011, ADR-0013, ADR-0031): `core/pysrc` (host-agnostic Python logic) and `core/surface` (host-agnostic markdown templates) are the single source of truth. `core/hosts.json` plus `tools/build-surface.py`/`tools/host_descriptors.py` deterministically render that source into each host's native surface (Claude slash commands, Codex/Pi generated `SKILL.md` dispatch entries) — not hand-maintained copies. `tools/sync-core.py` vendors the Python hook layer byte-identically. Each plugin then layers only a thin, platform-specific adapter (manifest format, generated `command-catalog.json`) on top.

**Hook-gated skill orchestration:** every tool call or slash command routes through a `core/pysrc` hook (`session-start`, `prompt-submit`, `pre-edit`, `pre-write`, `pre-bash`, …), which gates via `_hooklib` against `CONTEXT.md` frontmatter and project state, then dispatches to a `core/surface/skills/*/SKILL.md` workflow that reads/writes `.codearbiter/` state and may dispatch subagents (`core/surface/agents/`).

**Release immutability:** published tags across all four series never move or delete; a bad release is corrected only by a new version. Two independent layers — a repository ruleset (prevention) and `.github/scripts/check_tag_immutability.py` against the two ledgers (detection) — enforce this, per ADR-0032/ADR-0034.

## Public interfaces

- Slash commands — `core/surface/commands/*.md` (38), rendered per-host via `core/hosts.json` surface rules
- Hook entry points — `core/pysrc/*.py`, registered per-host in each plugin's manifest
- Plugin manifests — `plugins/ca/.claude-plugin/plugin.json`, `plugins/ca-codex/.codex-plugin/plugin.json`, `plugins/ca-pi/package.json`, `plugins/ca-sandbox/.claude-plugin/plugin.json`
- Project-state contract — `.codearbiter/CONTEXT.md` frontmatter, `decisions/`, `open-questions.md`, `open-tasks.md`
- Release-provenance contract — `.github/published-tags.json`, `.github/legacy-published-tags.json`, `.github/RELEASE-PROVENANCE.md`
