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

The Pi tools install is an aggregate prerequisite: `npm --prefix plugins/ca-pi/tools ci --ignore-scripts`.

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

## Coverage

One command per TypeScript tree, only when that tree changed:

```sh
npm --prefix plugins/ca/tools run coverage
npm --prefix plugins/ca-pi/tools run coverage
npm --prefix plugins/ca-sandbox/tools run coverage
```

Each prints a text summary and writes an html report to that tree's `coverage/`
(gitignored — run output, never project state). Scope, provider and reporters
live in each tree's `vitest.config.ts`; the script takes no arguments so it is
identical on every platform.

**The threshold is not encoded in the tooling.** `tdd` Phase 5 and `refactor`
Phase 2/6 apply it, reading `stage:` from `.codearbiter/CONTEXT.md` against
`plugins/ca/includes/maturity-coverage.md`. **Lines and branches must both
clear it**; a report satisfying one and not the other does not pass. Putting the
number in three `vitest.config.ts` files would fork that single source of truth
and the copies would drift the first time the stage moves.

Measured baseline at stage 2 (≥ 70%), 2026-07-26:

| tree | lines | branches | verdict |
| --- | --- | --- | --- |
| `plugins/ca/tools` | 67.31% | 59.46% | **below floor** — backfill tracked in #511 |
| `plugins/ca-pi/tools` | 85.37% | 78.73% | clears |
| `plugins/ca-sandbox/tools` | 86.13% | 79.96% | clears |

Two caveats when reading a local report:

- **ca-sandbox self-skips its docker-gated suites** on a host without Docker, so
  a local number reads lower than required CI's. Compare against a run with
  `CA_SANDBOX_REQUIRE_DOCKER=1` before concluding that tree regressed.
- **No CI job enforces coverage.** It is an orchestrator gate the skills run, not
  a required check — deliberately, since wiring a red `ca/tools` into required CI
  would block every merge on an unrelated backfill.

**`site/` is a fourth tested TypeScript tree and has no coverage command** — it
runs vitest 3 with its own suites under `site/test/`, and `tdd` Phase 5 on a
`site/` change therefore still has nothing to run, and takes the **no-tooling
exemption** on the same terms as the Python hooks below — conditions in
`plugins/ca/includes/maturity-coverage.md`, citation required, not restated
here. That gap is tracked in #514 and held open explicitly: `COVERAGE_EXEMPT` in
`.github/scripts/test_ci_impact.py` names it, and a companion test fails if the
exemption ever stops matching a real tree. Visible and reviewed, not closed.
(`COVERAGE_EXEMPT` is a CI allowlist for the doc-contract test — it is not the
agent-facing exemption and cannot be taken in place of one.)

There is **no coverage tooling for the Python hooks** (`plugins/*/hooks/*.py`,
`.github/scripts/*.py`). No numeric floor exists for those surfaces, so `tdd`
Phase 5 and `refactor` Phase 2 and Phase 6 all take the **no-tooling exemption**
— whose conditions live in `plugins/ca/includes/maturity-coverage.md` and are
NOT restated here. In short: it requires a citation, not an assertion, and the
sentence above is the passage to quote.

This paragraph previously read "use the per-symbol direct-test proof alone and
say so in the phase record" — a local copy of the old, laxer rule, naming only
`refactor` Phase 2. That is exactly the drift the exemption's single-source rule
exists to stop: project state was instructing an agent to assert on the one
surface class in this repo where the exemption actually fires, while the include
required it to cite. Deferring, rather than restating, is the fix.

## Static checks (CI parity)

```sh
# Cross-reference graph: every skill/command/agent reference resolves
python .github/scripts/check-plugin-refs.py

# Every tracked JSON manifest parses (plugin.json, .claude-plugin/marketplace.json, hooks.json)
node -e "JSON.parse(require('fs').readFileSync(process.argv[1],'utf8'))" <file>.json
```

## CVE gate (supply chain)

**One threshold, `high`, everywhere.** A HIGH-or-worse advisory fails the build
in every audit gate this repo runs. Two scopes share it, and which one applies
depends on whether the graph's *output* is the product:

| graph | workflow / job | production deps today | scope audited |
| --- | --- | --- | --- |
| `plugins/ca/tools` | `ci.yml` — `tools` | none | production **and dev** |
| `plugins/ca-sandbox/tools` | `ci.yml` — `ca-sandbox-tools` | none | production **and dev** |
| `plugins/ca-pi/tools` | `ci.yml` — `ca-pi-checks` | none | production **and dev** |
| `site` (docs site) | `docs.yml` — `site-check`, which `deploy` needs | astro, starlight, markdown-remark | production |

- `npm audit --omit=dev --audit-level=high` — the production gate, run on all
  four graphs. On `site` it is the live gate: that is the only graph declaring
  production dependencies. On the three tools graphs it audits an empty graph
  and is purely a *durability* setting, deciding what happens the day one of
  them takes on a runtime dependency.
- `npm audit --audit-level=high` — the dev-inclusive gate (issue #434), run on
  the three `plugins/*/tools` graphs. Every package in those trees is a dev
  dependency, and they are the ones that build `farm.js`, `sandbox.js`, and the
  ca-pi extension bundles — committed, shipped artifacts. A build-time
  compromise there lands in a reviewed artifact, so "dev dependency"
  understates the blast radius when the dev dependency's output is the product.

`site`'s dev tree is deliberately not on the dev-inclusive gate: its build
output is a static site republished from source on every deploy, not a committed
binary artifact carried into consumers' repositories.

This enforces the supply-chain posture described in `security-controls.md`.

**What the threshold actually buys, honestly.** Three of the four graphs above
declare no production dependencies at all, so `--omit=dev` audits an empty graph
in those jobs and the threshold there is inert at any value — it is a
*durability* setting that decides what happens the day one of them takes on a
runtime dependency. The one live graph is `site`, and until issue #403 nothing
audited it: #400's three HIGH advisories all lived in `site/package-lock.json`,
which is why the site gate is the part of this change with immediate effect. The
threshold was lowered from `critical` to `high` across all four so a single rule
covers the repo — not because the farm or sandbox audits would have caught #400.
They would not have seen it.

**What issue #434 found, and how the dev gate was proven.** Measured in
`plugins/ca/tools`, `npm audit --json` reported `{prod: 1, dev: 104}` — the
single prod entry being the root package itself — and one **HIGH** advisory,
GHSA-r28c-9q8g-f849 (`postcss` ≤ 8.5.17, arbitrary `.map` file disclosure via
source-map auto-loading). The `--omit=dev` gate reported **zero vulnerabilities
against the vulnerable lockfile and against the fixed one alike**, at any
threshold. The advisory surfaced only because dependabot happened to file the
bump on a sibling graph — luck, not a control.

The dev-inclusive gate was proven against that exact known-vulnerable state
rather than only against a clean one: run on the pre-fix `plugins/ca/tools`
lockfile (postcss 8.5.15) it exits 1 and names the advisory, where the
production gate exits 0. All four graphs pass both applicable gates today.

## Secrets scan

The gate is three-layered — one hosted backstop plus two cooperative local
layers:

1. `ci.yml`'s `secret-scan` job (issue #404): gitleaks' full default ruleset,
   run as a required check for the `ci-passed` merge gate. The scanner is pinned
   by image digest and runs in a network-isolated, read-only container over a
   read-only mount. This is the only layer a bot, a fork, a web edit, or a plain
   `git push` cannot skip — the two below run only inside a contributor's local
   session. It scans in **two modes**, because each is blind to what the other
   catches: `gitleaks dir` over the merge-result tree (what would land on main),
   and, on a pull request, `gitleaks git --log-opts <merge-base>..HEAD` over the
   PR's own commits. Without the second, a credential added in one commit and
   deleted in the next passes green and still reaches main's history under a
   merge or rebase merge, both of which this repo allows. Findings print with
   `--redact --verbose`, so a red job names the file, line, rule, and commit
   while the secret itself stays `REDACTED`.

   Its allowlist (`.gitleaks.toml`) waives individual fake fixture literals by
   value, never a file path — a `paths` waiver drops the whole file from the
   scan — and every waiver is anchored `\A<literal>\z`. The anchoring is the
   load-bearing part: gitleaks substring-matches allowlist regexes, so an
   unanchored literal waives every secret that merely contains it, and no choice
   of `regexTarget` fixes that. `.github/scripts/test_ci_impact.py` enforces both
   rules, and the `secret-scan` job re-runs that contract itself, so a path-filter
   edit can never leave the allowlist unguarded.
2. Manual sweep of the staged diff for credential patterns
   (`api[_-]?key|token|secret|password|private[_-]?key|passphrase|credential|BEGIN.*PRIVATE|AKIA|ghp_|sk-ant`),
   case-insensitive. This is the convenience layer; the authoritative classifier
   is `_hooklib.SECRET_RE`, pinned against the farm redactor by the shared
   `hooks/secret-detection-corpus.json`, which also matches a secret keyword as
   the trailing segment of a compound name (e.g. `FARM_API_KEY = "..."`).
3. The plugin's own enforcement hooks: H-09b (crypto/TLS) and H-10b (secrets)
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
