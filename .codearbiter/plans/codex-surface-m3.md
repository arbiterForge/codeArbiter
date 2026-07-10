# codex-support M3 — generated command/skill surface + standalone Codex init

Parent plan: `codex-support.md` (ADR-0011). Branch: `feat/codex-surface-m3` → PR into `feat/codex-support-m0`.
Resume decisions (2026-07-09, user): full M3 slice; bar = full-capability standalone parity ("every capability just like a Claude user"); #287 resolved as Codex-side init shipped in the generated surface; recorded as DECISION-0013.

Corrected facts vs the parent plan (verified on `38cc5cf`): **39** commands (not 44), **22** skills, **28** agents; `{{PLUGIN_ROOT}}` renders `${CLAUDE_PLUGIN_ROOT}` on BOTH hosts (Codex compat alias, spike item 6); six command/skill name collisions after `ca-` prefixing (`context-check`, `debug`, `decompose`, `refactor`, `release`, `tribunal`).

## Design decisions

- **D1** Agents stay M4 (Codex plugins cannot ship subagents — spike item 7). `check-plugin-refs.py` gets `pending_prefixes=["agents/"]` for ca-codex, removed in M4.
- **D2** No provenance headers in rendered output (breaks Claude byte-identity). Provenance: `core/surface/README.md`, CONTRIBUTING, the `--check` failure message.
- **D3** Codex tree: `plugins/ca-codex/skills/ca-<cmd>/SKILL.md` (37 entry skills = 39 − statusline − prune) + `routines/<name>/SKILL.md` (22 orchestrator-routine bodies, kept out of the skill-discovery root: avoids unprefixed registration + the 6 collisions) + `includes/**`, `COMMANDS.md`, `SPRINT.md`, `ORCHESTRATOR.md` — all generated. Codex path rewrites: `{{PLUGIN_ROOT}}/skills/` → `.../routines/` (55 refs); `commands/<n>.md` → `skills/ca-<n>/SKILL.md` (2 refs).
- **D4** Grammar: `{{PLUGIN_ROOT}}` / `{{PROJECT_DIR}}` / `{{CMD:x}}` (Claude `/ca:x`, Codex `$ca-x`) + `{{IF:claude}}…{{ELSE}}…{{END}}`. Claude render inverts extraction exactly → byte-identity by construction. Renderer hard-fails on `{{CMD:x}}` where x is host-excluded.
- **D5** New ledgered exceptions: `statusline`, `prune` commands don't render for Codex.
- **D6** Runtime vocabulary seam: `cmd_ref(name)` in `hostapi.py`/both `_host.py`; runtime-emitted `/ca:` strings in `session-start`, `pre-write`, `post-write-edit`, `doctor` (146/163 pointers; 200 gated on `has_statusline`), `init-codearbiter` scaffold text, `_provenancelib` route through it. Claude strings identical; `plugins/ca/hooks/*.py` bytes change → ca **2.8.12 → 2.8.13**, isolated commit.
- **D7** Byte-identity proof: one-time = empty `git diff --stat origin/feat/codex-support-m0...HEAD -- plugins/ca/{commands,skills,includes,ORCHESTRATOR.md,COMMANDS.md,SPRINT.md}` in the PR body; standing = always-on CI `surface` job (`build-surface.py --check`, binary, both hosts, both drift directions).
- **D8** orchestrator-parity CI job + `check_orchestrator_parity.py` + `test_orchestrator_parity.py` removed (M3 deliberately breaks ORCHESTRATOR byte-identity); `surface` job is the strict successor; `ci-passed.needs` updated.
- **D9** `.gitattributes`: LF pin scoped to the generated/canonical trees (`core/surface/**`, `plugins/**/*.md`, `docs/**/*.md`, root `*.md`) — a blanket `*.md` would renormalize CRLF operator-state artifacts under `.codearbiter/` (tribunal report bodies, `sprint-log.md`), which must keep their committed bytes. Covered trees were already all-LF in the index; checkout-normalization only.
- **D10** `prose-codex`: `PLUGINS["ca-codex"]` in `check-plugin-refs.py` (`$ca-` catalog regex ↔ `skills/ca-*` dirs; generated `skills/INDEX.md`) + path-gated CI job.
- **D11** House rule (documented in `core/surface/README.md`): shared surface prose names *actions*, never harness-specific tool names; plus a short "adding a harness" contract (capability matrix essential-vs-ledgered, injection shape, acceptance probes) — a future harness is a host-table entry + `_host.py`, not a rewrite.
- **D12** `core/surface/includes/codex-host-notes.md` renders **Codex-only** (renderer CODEX_ONLY set): sandbox/detached-HEAD git caveats, degraded paths, agents-pending-M4.

## Tasks

| ID | Files | Action | Verification | Status |
|---|---|---|---|---|
| A1 | `.gitattributes` | LF-pin the generated trees (scoped, per D9) | `git add --renormalize -n .` empty; `git ls-files --eol -- '*.md'` all `i/lf` | ACCEPTED |
| A2 | `tools/build-surface.py` (new) | render engine: per-host token map, IF/ELSE/END parser, LF-binary IO, hard errors on unknown token/unclosed conditional | A5 suite | ACCEPTED |
| A3 | `tools/build-surface.py` | Codex mapping: commands→`skills/ca-<n>/SKILL.md` (+frontmatter synth), skills→`routines/`, path rewrites, `skills/INDEX.md` emission, CODEX_EXCLUDED_CMDS + CODEX_ONLY sets, `{{CMD:excluded}}` hard-fail | A5 suite | ACCEPTED |
| A4 | `tools/build-surface.py` | CLI: default write both trees; `--check`; `--host claude\|codex` | usage errors mirror sync-core | ACCEPTED |
| A5 | `.github/scripts/test_build_surface.py` (new) | determinism, idempotence, token-inversion, excluded-CMD fail, LF-only, collision fail, conditional strip, path rewrites | suite green | ACCEPTED |
| B1 | `core/surface/commands/*.md` (39) | extract via reverse-substitution; add host conditionals where validation fails | Claude render → `git status --porcelain -- plugins/ca` empty | ACCEPTED |
| B2 | `core/surface/skills/**` (46 md) | extract | same invariant | ACCEPTED |
| B3 | `core/surface/includes/**` (25 md) | extract | same invariant | ACCEPTED |
| B4 | `core/surface/SPRINT.md`, `COMMANDS.md` | extract; statusline/prune rows `{{IF:claude}}` | same invariant | ACCEPTED |
| B5 | `core/surface/ORCHESTRATOR.md` | extract + author Codex conditional prose (Commands/Paths/§0/§6/§7) — flag for maintainer review | Claude render clean; Codex render has zero `/ca:` | ACCEPTED |
| B6 | `core/surface/README.md` | grammar, never-edit-rendered rule, D11 house rule + porting contract | n/a (prose) | ACCEPTED |
| B7 | `core/surface/includes/codex-host-notes.md` | D12 Codex-only host notes | renders only into ca-codex | ACCEPTED |
| C1 | `plugins/ca-codex/{skills,routines,includes}/**`, `COMMANDS.md`, `SPRINT.md`, `ORCHESTRATOR.md` | run generator, commit outputs | `--check` green; zero `/ca:` in ca-codex md; `skills/ca-init/SKILL.md` exists; no ca-statusline/ca-prune | ACCEPTED |
| C2 | (verify) | AC1 walkthrough in temp repo: init entry scaffolds store; ca-init routes to `$ca-create-context`/`$ca-decompose` | manual run | ACCEPTED |
| C3 | `plugins/ca-codex/.codex-plugin/plugin.json` | description → first-run via ca-init skill; version 0.2.0; store `interface` metadata | JSON parses; zero `/ca:init` | ACCEPTED |
| C4 | `plugins/ca-codex/CHANGELOG.md` | 0.2.0 entry | Keep-a-Changelog shape | ACCEPTED |
| D1 | `core/pysrc/hostapi.py`, both `_host.py` | `cmd_ref(name)` + unit test | new test green | ACCEPTED |
| D2 | `core/pysrc/{session-start,pre-write,post-write-edit,doctor,init-codearbiter}.py`, `_provenancelib.py` | route runtime `/ca:` strings through `cmd_ref`; doctor pointer/statusline fixes | hooks suite + codex adapter suite green; remaining `/ca:` in core py = comments only | ACCEPTED |
| D3 | vendored hooks | `sync-core.py` re-vendor | `--check` green | ACCEPTED |
| D4 | ca `plugin.json`, README badge, root CHANGELOG | ca 2.8.13 | badge-consistency green | ACCEPTED |
| E1 | `.github/workflows/ci.yml` | drop `orchestrator-parity`; add `surface` (always-on) + wire `test_build_surface.py`; update `ci-passed.needs` | grep zero orchestrator refs; PR CI | ACCEPTED |
| E2 | delete `check_orchestrator_parity.py`, `test_orchestrator_parity.py` | superseded by generator | `git grep orchestrator_parity` → 0 | ACCEPTED |
| E3 | `.github/scripts/check-plugin-refs.py` | ca-codex entry + agents allowlist (M4-removal comment) | all plugins exit 0 | ACCEPTED |
| E4 | `ci.yml` | `prose-codex` job (mirrors prose-sandbox) | PR CI | ACCEPTED |
| F1 | `docs/parity.md` | commands/skills → SHIPPED (M3), corrected counts, new ledgered exceptions, env-var-in-prose LIVE-PENDING note | grep stale figures → 0 | ACCEPTED |
| F2 | `.codearbiter/decisions/decision-log.md` | append DECISION-0013 (user-attributed #287 closure) | format matches log | ACCEPTED |
| F3 | `CONTRIBUTING.md` | generated-surface contract + Windows checkout note | grep build-surface present | ACCEPTED |
| F4 | `CHANGELOG.md` (root, v2.0.0 entry) | remove external-repo attribution reference (user directive; clean-room adaptation, no license obligation) | grep → 0 in tree | ACCEPTED |
| G1 | — | full local gate (sync-core --check · build-surface --check · unittest · adapter suite · build-surface tests · plugin-refs ×3 · badge · license) | all exit 0 | ACCEPTED |
| G2 | — | AC3 one-time proof: empty Claude-md diff vs origin/feat/codex-support-m0 | pasted in PR body | IN-PROGRESS |
| G3 | — | PR → feat/codex-support-m0 (`--body-file`); close-out comments #287/#259 | CI green | IN-PROGRESS |

## Acceptance criteria

- AC1 Codex-only bootstrap via shipped ca-init (C1/C2/D2; closes #287)
- AC2 every command → generated `ca-` skill (37/39, 2 ledgered) (B1/C1)
- AC3 Claude md tree provably byte-unchanged (G2 + standing `surface` job)
- AC4 CI fails on drift both directions (A4/A5/E1)
- AC5 Codex persona + runtime briefing speak Codex-native vocabulary (B5 + D1/D2)
- AC6 parity ledger corrected + DECISION-0013 logged (F1/F2)

## Risks

1. Template-extraction edge cases — mitigated by bijective substitution + per-file empty-diff invariant + `{{CMD:excluded}}` hard-fail enumeration.
2. Codex skill-layout details source-inferred, LIVE-PENDING — layout isolated in one constant; beta label stays until the live pass.
3. `routines/` accidental discovery if Codex scans recursively — fallback: rename routine files via one renderer rule.
4. Exact-briefing-string tests may need updates only under Codex host fixtures (legitimate — the string change is the feature).
