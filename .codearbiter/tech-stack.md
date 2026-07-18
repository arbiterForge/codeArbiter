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

## Pi adapter

`plugins/ca-pi/tools/` is strict TypeScript on Node 22.19 or newer, tested with
Vitest and built with esbuild. The dependency-free Git package ships a parent
extension, an enforcement-only child extension, and a Windows supervisor.
Python 3 remains required for the shared core.

The external Pi runtime is a test and install input, never a checked-in or
runtime dependency. Supported promotion versions are Pi 0.80.5 and Pi 0.80.10.

## Test

Run all of these; ALL must pass before any commit:

```sh
# Hook guard decisions — every blocked spelling blocks, every legit one allows
python .github/scripts/test_hook_guards.py

# Interpreter plumbing — REAL / STUB / PY2 / NONE matrix, host-specific registration
python .github/scripts/test_hooks_cold_install.py

# /ca:preview helpers — diff-collection + redacting secret-scan (_previewlib)
python .github/scripts/test_preview_lib.py

# UX-conversion-trio copy — Receipt close, stakes lines, register split (structural)
python .github/scripts/test_ux_conversion.py

# Cold-miss nudge — nudge_decision, advisory, idle extraction, hook_run integration (O1–O11)
python .github/scripts/test_prune_nudge.py

# H-14 migration commit-time backstop — detection, producer marker, pre-bash gate (#77)
python .github/scripts/test_migration_backstop.py

# /ca:metrics trends helper — window tiling, 3 metrics, empty-source safety, read-only
python .github/scripts/test_metrics_lib.py

# task-board lifecycle helper — in-flight count (excludes done), dotted-ID grammar,
# field parsing, stale-in-progress nudge, oversize degradation (_taskboardlib)
python .github/scripts/test_taskboardlib.py

# task-board writer + follow-up harvest — next_seq, add_entry, set_state, dedup,
# the 3 extractors, and promote routing/modes (_taskboardlib)
python .github/scripts/test_taskwriter.py

# release-skill hardening helpers — last-tag selection (ca-only, pre-release
# excluded), notes-heading/tag match, release-date consistency, half-finished-
# publish classifier, the CLI, and the SKILL.md structural wiring (_releaselib)
python .github/scripts/test_release_lib.py

# commit-gate board-sync chokepoint — Phase 6 board-edit exemption + prose
# wiring (AC-04..07, ADR-0008); structural SKILL.md/command-doc assertions
python .github/scripts/test_board_sync.py

# provenance store — write_provenance/read_provenance round-trip, on-disk JSON
# shape with schema/doc/created/interview_derived/entries[] (_provenancelib)
python .github/scripts/test_provenancelib.py

# commit-gate provenance auto-heal wiring — Phase 5.5 heal_worklist, re-scout
# scoped to staged paths only, re-baseline rides work commit, claim-changed to
# Phase 6 diff-review; Phase 6/7 provenance exemption + staging wiring (AC-14)
python .github/scripts/test_provenance_wiring.py

# file-scoped-context-injection lib — four-tier map/budget/dedup/index
# (_readinjectlib): allow_output shape, context assembly, cache round-trip
python .github/scripts/test_readinjectlib.py

# pre-read hook entry point — governed-file injection, dedup, fail-open, dormancy
# (pre-read.py): AC-03/09/10/12, miss, and dormant-repo paths
python .github/scripts/test_pre_read.py

# plugins/ca/hooks/tests/ — the hook enforcement + helper logic unittest suite
# (statusline, _ledgerlib, guards, etc.); run in CI via unittest discover
python -m unittest discover -s plugins/ca/hooks/tests -p "test_*.py"
```

Only when `plugins/ca/tools/**` changed:

```sh
cd plugins/ca/tools
npm ci
npm run typecheck
npm test
npm run build          # then: git diff --quiet -- farm.js  (stale build blocks)
```

Only when `plugins/ca-sandbox/tools/**` changed (the ca-sandbox sibling plugin, ADR-0007):

```sh
cd plugins/ca-sandbox/tools
npm ci
npm run typecheck
npm test                # docker-gated suites run serially (fileParallelism off); needs a Docker engine
npm run build           # then: git diff --quiet -- sandbox.js  (stale build blocks)
```

ca-sandbox's docker-gated tests build real ephemeral containers (and on Windows drive nixpacks via the
WSL bridge), so they need Docker available and are slower; they self-skip when `docker info` fails.

When `plugins/ca-pi/**`, `core/**`, or the Pi package generators changed:

```sh
npm --prefix plugins/ca-pi/tools ci --ignore-scripts
npm --prefix plugins/ca-pi/tools run typecheck
npm --prefix plugins/ca-pi/tools test
npm --prefix plugins/ca-pi/tools run build
python tools/sync-core.py --check
python tools/build-surface.py --check
python tools/build-host-packages.py --check
python .github/scripts/test_pi_package.py
python .github/scripts/test_pi_parity.py
python .github/scripts/test_public_pi_docs.py
```

The platform aggregate is `python .github/scripts/test_pi_platform_contract.py
--fixtures-only`. A supported-version run adds `--pi-version 0.80.5` or
`--pi-version 0.80.10` after installing that exact external Pi version with
scripts disabled. CI owns the Windows/macOS/Linux matrix.

## Lint / typecheck

- Python hooks: no linter is configured. The floor is a syntax check —
  `python -m py_compile plugins/ca/hooks/<file>.py` for any touched hook.
- TypeScript: `npm run typecheck` in `plugins/ca/tools` (only when tools changed).

## Static checks (CI parity)

```sh
# Cross-reference graph: every skill/command/agent reference resolves
python .github/scripts/check-plugin-refs.py

# Every tracked JSON manifest parses (plugin.json, .claude-plugin/marketplace.json, hooks.json)
node -e "JSON.parse(require('fs').readFileSync(process.argv[1],'utf8'))" <file>.json
```

## CVE gate (supply chain)

The configured CVE gate is `npm audit --omit=dev --audit-level=critical`, run in
CI (the `tools` job, after `npm ci`) against the shipped dependency set. A
CRITICAL advisory fails the build; lower severities are intentionally not
gating, so routine dev-tool advisories don't block unrelated PRs. This enforces
the supply-chain posture described in `security-controls.md`.

## Secrets scan

No dedicated secrets scanner is configured. The gate is two-layered:

1. Manual sweep of the staged diff for credential patterns
   (`api[_-]?key|token|secret|password|private[_-]?key|passphrase|credential|BEGIN.*PRIVATE|AKIA|ghp_|sk-ant`),
   case-insensitive. This is the convenience layer; the authoritative classifier
   is `_hooklib.SECRET_RE`, pinned against the farm redactor by the shared
   `hooks/secret-detection-corpus.json`, which also matches a secret keyword as
   the trailing segment of a compound name (e.g. `FARM_API_KEY = "..."`).
2. The plugin's own enforcement hooks: H-09b (crypto/TLS) and H-10b (secrets)
   block any commit whose diff touches a crypto or secret line until a diff-bound
   security-gate pass marker covers those exact lines (`hooks/security-pass.py`).

## Release invariants

- Any change under `plugins/ca/**` on an already-tagged version must bump
  `plugins/ca/.claude-plugin/plugin.json` `version` — `claude plugin update`
  no-ops on an unchanged version string (CI job `version-bump` enforces).
- Version rides in three places; keep them in sync: `plugin.json`, the README
  version badge, and a dated `CHANGELOG.md` section.
- `ca-pi` releases independently as `ca-pi-v<version>`. The nested
  `plugins/ca-pi/package.json` is the version source; regenerate the root
  `package.json`, update `plugins/ca-pi/CHANGELOG.md`, and keep both manifests
  synchronized. Distribution is pinned Git only; there is no npm release.
