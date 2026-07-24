# Inventory — 2026-07-17-pi-support-branch

Scope: repo root, branch feat/pi-support (21 commits, +79,523/−1,003 over origin/main).
Sources: map-structure + map-deps reports (Haiku mappers), orchestrator git scan.

## Structure

- `core/pysrc/` (44 py) + `core/surface/` (146 md) — canonical kernel; byte-synced into
  `plugins/ca/`, `plugins/ca-codex/`, `plugins/ca-pi/` by `tools/sync-core.py` / `build-surface.py`.
- `plugins/ca/` — Claude Code host: 21 hook entries, farm dispatcher (farm.ts→farm.js).
- `plugins/ca-pi/` — NEW this branch (~400 files): 46 hooks, 23 TS tool sources
  (bridge/runner/extension/child-extension/tool-guard/process-tree), built extensions/*.js,
  helpers/windows-supervisor.js, 40+ generated skills, roles.json.
- `plugins/ca-codex/` — Codex host (119 py, generated).
- `plugins/ca-sandbox/` — container isolation plugin (TS).
- `site/` — Astro/Starlight docs site: 675 md docs, 75 astro files, vitest suite.
- `.github/scripts/` — 48 python test scripts (27 new on this branch); ci.yml 14 jobs,
  ca-pi matrix 3 OS × Pi 0.80.5/0.80.6; new codeql.yml scoped to ca-pi TS.
- `tools/` — 9 python builders (sync-core, build-surface, build-host-packages, ci-impact).

## Largest units (audit anchors)

_hooklib.py 1201 LOC · _prunelib.py 1365 · pre-bash.py 1119 · _readinjectlib.py 1036 ·
session-start.py 897 · runner.ts 792 · process-tree.ts 766 · _provenancelib.py 828 ·
_taskboardlib.py 792 · statusline.py 736 · _githooks.py 706.

## Integration surface

- Outbound network: update-notifier HTTPS GET (documented, _updatelib.py); farm dispatcher
  API calls; otherwise none in shipped code.
- Subprocess: git across ~11 py modules; bridge.ts spawns python; process-tree taskkill;
  runner.ts child Pi launches (stdin-only task content per security-controls).
- Env surface: CLAUDE_PROJECT_DIR/PLUGIN_ROOT, 12 CODEARBITER_* vars, CODEARBITER_SUBAGENT
  (Pi child marker), PATH/SystemRoot/WINDIR/TEMP in process-tree.
- External runtimes (test/install-only): Pi 0.80.5/0.80.6 (--ignore-scripts), Docker.

## Risk ranking & trust boundaries (highest first)

1. **plugins/ca-pi/tools/src/** — NEW, child-process spawning, tool-guard enforcement,
   env-allowlist construction, Windows supervisor. Trust boundaries: Pi trusted-extension
   runtime ↔ adapter (ADR-0014 opaque auth boundary); parent ↔ child env minimization;
   unknown-tool fail-closed guard. Untrusted-adjacent: repo content read pre-trust.
2. **core/pysrc/ enforcement path** (_hooklib, pre-bash, _githooks, _gitexec, git-enforce) —
   guards + append-only audit integrity; synced 3-ways (drift = enforcement gap on a host).
3. **Generators** (sync-core, build-surface, build-host-packages) — supply the byte-identity
   invariant CI enforces; a generator bug ships silently to 3 hosts.
4. **.github/workflows/** — new ci-impact selection + codeql; CI is the enforcement backstop.
5. **plugins/ca-sandbox/** — untouched this branch, previously audited (07-09 run).
6. **site/** — no trust boundary (static build), but user-facing content quality scope.

## AI-authorship / iteration-depth overlay

Branch: 21 commits, single author, ~3,800 added lines/commit → very high AI-generation
ratio. Scrutiny boost + small severity prior at triage for: plugins/ca-pi/** (entire),
core/pysrc new modules (_gitexec.py, _prunepolicy.py), .github/scripts/test_pi_*.py,
ci-impact machinery. High churn since 06-20: _hooklib.py (14), pre-bash.py (13),
ci.yml (21), session-start.py (11) — churn boost applies.

## Active lenses

Launched (10): appsec, architecture, reliability, secrets-supply, test-fidelity,
coverage, infra, observability, performance, typesafety.
Skipped (1): migration — no database/schema migrations exist in scope (the "migration"
hooks are plugin-version migration backstops, judged under reliability/infra).

Sidecar (user-mandated adjunct, findings kept under findings/docs-*): docs-content walk
per governance host (claude-code, codex, pi) + docs-visuals pass (image/diagram
opportunities). Not lens findings; reported in a dedicated report section.
