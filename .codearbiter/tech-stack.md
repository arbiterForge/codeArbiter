# Tech stack — codeArbiter (the framework repo itself)

The canonical commands the commit gate and reviewers run in THIS repo. Mirrors
`.github/workflows/ci.yml` — if the two ever disagree, CI is authoritative and
this file is the stale one; fix it here.

## Stack

- **Hooks** (`plugins/ca/hooks/*.py`) — Python 3, stdlib only. No dependencies,
  ever: hooks must run on a stock Windows/macOS/Linux Python with nothing
  installed. The cold-install matrix exists to prove exactly that.
- **Farm dispatcher** (`plugins/ca/tools/`) — TypeScript on Node 20, tested with
  vitest. The plugin ships the built `farm.js`, not `farm.ts` — a stale build is
  a release blocker.
- **Everything else** — prose (skills, commands, agents, ORCHESTRATOR.md),
  governed by the plugin's own authoring gates, not by CI.

## Test

Run all of these; ALL must pass before any commit:

```sh
# Hook guard decisions — every blocked spelling blocks, every legit one allows
python .github/scripts/test_hook_guards.py

# Interpreter plumbing — REAL / STUB / NONE python3 matrix, dual registration
python .github/scripts/test_hooks_cold_install.py
```

Only when `plugins/ca/tools/**` changed:

```sh
cd plugins/ca/tools
npm ci
npm run typecheck
npm test
npm run build          # then: git diff --quiet -- farm.js  (stale build blocks)
```

## Lint / typecheck

- Python hooks: no linter is configured. The floor is a syntax check —
  `python -m py_compile plugins/ca/hooks/<file>.py` for any touched hook.
- TypeScript: `npm run typecheck` in `plugins/ca/tools` (only when tools changed).

## Static checks (CI parity)

```sh
# Cross-reference graph: every skill/command/agent reference resolves
python .github/scripts/check-plugin-refs.py

# Every tracked JSON manifest parses (plugin.json, marketplace.json, hooks.json)
node -e "JSON.parse(require('fs').readFileSync(process.argv[1],'utf8'))" <file>.json
```

## Secrets scan

No dedicated scanner is configured. The gate is two-layered:

1. Manual sweep of the staged diff for credential patterns
   (`api[_-]?key|token|secret|password|BEGIN.*PRIVATE|sk-ant`), case-insensitive.
2. The plugin's own enforcement hooks: H-09b/H-10b block any commit whose diff
   touches crypto/secret lines until a diff-bound security-gate pass marker
   covers those exact lines (`hooks/security-pass.py`).

## Release invariants

- Any change under `plugins/ca/**` on an already-tagged version must bump
  `plugins/ca/.claude-plugin/plugin.json` `version` — `claude plugin update`
  no-ops on an unchanged version string (CI job `version-bump` enforces).
- Version rides in three places; keep them in sync: `plugin.json`, the README
  version badge, and a dated `CHANGELOG.md` section.
