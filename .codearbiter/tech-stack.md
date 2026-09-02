# Tech stack — codeArbiter (the framework repo itself)

The canonical commands the commit gate and reviewers run in THIS repo. Mirrors
`.github/workflows/ci.yml` — if the two ever disagree, CI is authoritative and
this file is the stale one; fix it here.

## Stack

- **Canonical shared source** (`core/pysrc/`, `core/surface/`) — these directories
  are the canonical shared source for stdlib-only Python enforcement logic and
  markdown templates. Generators materialize this internal kernel into host packages;
  `core/` is not published as a separate runtime package.
- **Claude Code adapter** (`plugins/ca/`) — native hooks, commands, skills, agents,
  and the Node 20 farm dispatcher under `plugins/ca/tools/`. Hooks are Python 3,
  stdlib only; the dispatcher is TypeScript tested with Vitest and ships built
  `farm.js`.
- **Codex adapter** (`plugins/ca-codex/`) — Codex manifest and hook shims plus
  generated skills and packaged resource charters. Published releases from 0.7.5
  contain the complete charter set for host-provided thread dispatch. The hosted
  static package gate verifies release bytes, resource closure, and dispatch routes.
  These charters are not native Codex plugin-agent registrations.
- **Pi adapter** (`plugins/ca-pi/`) — generated Python/policy payload plus its thin
  TypeScript host extension and supervised child-process boundary.
- **Infrastructure sibling** (`plugins/ca-sandbox/`) — isolated exploration tools;
  it is not part of the governance kernel.
- **Codex release evidence** (`.github/scripts/check_codex_skill_resources.py`) - Python 3 standard-library validation on GitHub-hosted runners. It treats candidate bytes as inert, enforces bounded ZIP parsing, and validates manifest, front matter, resource closure, hooks, generated parity, and deterministic package identity without credentials or desktop infrastructure.

## Runtime and Git support boundary

- Hook and linked-worktree support is same-runtime: Windows with Git for Windows
  and its bundled hook shell, native Linux, or native macOS. The checkout and its
  linked worktrees must be created and used by that runtime's Git.
- CI exercises the current runner Python 3 and Git on Windows, Ubuntu, and macOS.
  Direct Windows hook evidence also covers CPython 3.10, 3.12, and 3.14, plus
  primary and linked worktrees with Git for Windows 2.55.0. No broader numeric
  Python-minor or Git-version floor is declared from that evidence.
- The selected Git binary owns `core.hooksPath` parsing through
  `rev-parse --git-path hooks`; codeArbiter does not reinterpret Git path grammar.
  It must also provide `git hook run` for doctor's harmless managed `pre-push`
  live-fire probe.
- Same-runtime linked worktrees include Git's native absolute and relative
  worktree-admin pointers under the default `<main>/.git/worktrees` layout.
  The selected Git binary must confirm both the absolute admin directory and
  common directory, and both linked and reported-main checkouts must own real
  `CONTEXT.md` files that independently satisfy the canonical activation parser,
  before codeArbiter resolves the shared primary marker root.
  `git init --separate-git-dir` worktrees are
  outside this marker-root contract; storage without that governed identity
  falls back locally.
- A live Git for Windows 2.55.0 probe resolved a default-layout primary and
  linked worktree through a localhost UNC share after one-shot `safe.directory`
  trust, while the untrusted form failed closed. This does not promote every
  remote SMB server or ownership policy to a supported cell.
- WSL is not a separately verified named cell. Alternating Windows Git and WSL
  Git over one physical repository or shared `.git`, including consuming a
  linked worktree created by the other runtime, is unsupported. Git Bash is the
  Windows hook shell and is not equivalent to WSL.

## Pi adapter

`plugins/ca-pi/tools/` is strict TypeScript on Node 22.19 or newer, tested with
Vitest and built with esbuild. The dependency-free Git package ships a parent
extension, an enforcement-only child extension, and a Windows supervisor.
Python 3 remains required for the shared core.

The external Pi runtime is a test and install input, never a checked-in or
runtime dependency. Supported promotion versions are Pi 0.80.5 and Pi 0.84.1.

## Test

Run all of these; ALL must pass before any commit:

```sh
# Codex packaged-resource and static candidate schemas
python .github/scripts/test_codex_skill_resources.py

# Workflow trust separation and exact CI impact routing
python .github/scripts/test_ci_impact.py

# ADR-0033 accepted/planned lifecycle, immutable bindings, and verified-only export
python .github/scripts/test_adr_lifecycle.py
python .github/scripts/check_adr_lifecycle.py

# ADR-0026/0030 authoritative four-item destructive registry and resident-copy parity
python .github/scripts/check_destructive_registry.py

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

# A-1.11 release resolution trace — proves the portable-mechanism split
# (core/pysrc/_releaselib.py + declared release-targets.md) reproduces the
# pinned pre-change lane's resolved variables for ca and ca-pi, and states
# the one intended divergence (AC-1.12, pre-release-marker scope). Needs
# FULL git history and all tags (fetch-depth: 0, fetch-tags: true) — its own
# preflight fails loudly, not silently, if either is missing.
python .github/scripts/test_release_trace.py

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

# mode plane core (_modelib) — token matching, marker_root resolution, the
# asymmetric fail direction, ledger backing, and CONTEXT.md's mode vocabulary
python .github/scripts/test_modelib.py

# composed persona — safety-core anchors, their ordering, precedence over every
# mode body, and §N citation resolution in all three modes
python .github/scripts/test_persona_composition.py

# prompt-seam interceptor (prompt-submit.py) — deterministic flip with no model
# turn, per-host envelopes, dedup, and the compaction-generation bump
python .github/scripts/test_prompt_submit.py

# startup emitters (session-start.py) — persona removed, eight composable
# emitters, per-mode selection, golden fixture with explicit-flag regeneration
python .github/scripts/test_startup_emitters.py

# mode readers — statusline badges/red-shift, arbiter state, _STALE_FLOWS both
# arms, and the override counter's exclusion of mode rows
python .github/scripts/test_mode_readers.py

# mode compaction seam — the mode survives a compaction; an unvouched or corrupt
# anchor clears to arbiter rather than retaining a gates-off posture
python .github/scripts/test_mode_compaction.py

# mode surface + docs coverage — no surface or published doc still references a
# deleted command; the curated site prose has no other gate comparing it
python .github/scripts/test_mode_surface.py

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
`--pi-version 0.84.1` after installing that exact external Pi version with
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
npm --prefix site run coverage
```

Each prints a text summary and writes an html report to that tree's `coverage/`
(gitignored — run output, never project state). Scope, provider and reporters
live in each tree's `vitest.config.ts`.

**The COMMAND is identical on every platform. The REPORT is not** (issue #521).
The script takes no arguments, so nothing about the invocation varies — but code
behind a platform fork cannot execute off its own platform, and a single-host
report scores the other platform's arm as uncovered no matter how well tested it
is. Measured here: `plugins/ca/tools` reads 66.18% branches on Windows and
65.35% on Linux, and `exec.ts` alone reads 87.50% against 76.38% — an 11-point
gap that is entirely `awaitTaskkill` plus the win32 `treeKill` arm on one side
and the POSIX arm on the other.

**A quoted figure is the union across a tree's supported hosts**, per tree:

| tree | forks on platform | union in CI |
| --- | --- | --- |
| `plugins/ca/tools` | yes — `exec.ts` on `process.platform` | **ubuntu + windows**, merged |
| `plugins/ca-pi/tools` | yes — Windows supervisor / process-tree paths | **ubuntu + windows**, merged |
| `plugins/ca-sandbox/tools` | no | single-host (ubuntu); docker caveat below |
| `site/` | no | single-host (ubuntu) |

CI produces the union for both forked trees — `[CHECK] | [REPO] | Coverage union`
for `plugins/ca/tools` and `[CHECK] | [PI  ] | Coverage union` for
`plugins/ca-pi/tools` — one advisory matrix cell per host writing a vitest
**blob** report, merged with `vitest --merge-reports`. Merging is a
genuine union of executed code, not the last report winning: verified on two
disjoint suites, 7 + 65 branches merging to 72 and 18 + 69 lines to 87. The job
says so when only one host reported, so a partial figure is never mistaken for
the union.

Each tree's blobs are namespaced `coverage-blob-<tree>-os-<host>`, so one
tree's merge cannot collect another's. The naive names collided — a `ca-*` glob
also matches `ca-pi-*` — which would have merged two trees into one figure under
`ca`'s name, silently and with a plausible number.

Locally, one host's report is a legitimate figure — **name the host** and say the
other's contribution is missing. The rule and its conditions live in
`plugins/ca/includes/maturity-coverage.md`; this table is the per-tree half it
refers to.

**The threshold is not encoded in the tooling.** `tdd` Phase 5 and `refactor`
Phase 2/6 apply it, reading `stage:` from `.codearbiter/CONTEXT.md` against
`plugins/ca/includes/maturity-coverage.md`. **Lines and branches must both
clear it**; a report satisfying one and not the other does not pass. Putting the
number in three `vitest.config.ts` files would fork that single source of truth
and the copies would drift the first time the stage moves.

Measured baseline at stage 2 (≥ 70%), refreshed 2026-07-29 from CI. The two
platform-forked trees carry their **union** figure; the others are single-host
because they have nothing to merge. Every row names how it was measured, which
is the rule #521 exists to enforce:

| tree | lines | branches | verdict | host |
| --- | --- | --- | --- | --- |
| `plugins/ca/tools` | 76.82% | 73.15% | clears | **union** (ubuntu + windows) |
| `plugins/ca-pi/tools` | 82.51% | 77.10% | clears | **union** (ubuntu + windows) |
| `plugins/ca-sandbox/tools` | 86.13% | 79.96% | clears | windows |
| `site` | 91.29% | 84.85% | clears | ubuntu-equivalent (no platform fork) |

**The union changed the answer for `plugins/ca/tools`.** #511 drove that tree
against 66.18% branches on Windows and 65.35% on Linux — both below the floor.
Merged, it is 73.15%, and clears by three points. The shortfall was never missing
tests: it was ~7 points of platform-forked `exec.ts` code that cannot execute off
its own host, scored as uncovered on whichever host happened to run. That is the
concrete case for the rule, and the reason a single-host figure is no longer
quotable here.

Two caveats when reading a local report:

- **ca-sandbox self-skips its docker-gated suites** on a host without Docker, so
  a local number reads lower than required CI's. Compare against a run with
  `CA_SANDBOX_REQUIRE_DOCKER=1` before concluding that tree regressed.
- **No CI job enforces coverage.** It is an orchestrator gate the skills run, not
  a required check — deliberately, since wiring a red `ca/tools` into required CI
  would block every merge on an unrelated backfill.

**`site/` is inside the coverage gate** (#514 / DECISION-0032). It was the one
tested tree with no command, so `tdd` Phase 5 reached it and took the no-tooling
exemption on a tree that has 438 real tests — the #507 failure mode, by a
different door. It now runs vitest 4 like the plugin trees, with
`@vitest/coverage-v8` pinned to the same exact version (the two are peer-pinned;
a caret on one and not the other is how they drift apart).

Its coverage `include` is scoped to `scripts/` — the generator, link-audit and
rehype helpers that the suites actually exercise. Deliberately NOT `src/`: those
are Astro components rendered at build time and covered by the build plus the
link audit, so counting them would report a large permanently-dark surface no
test in this tree was ever meant to reach.

`COVERAGE_EXEMPT` in `.github/scripts/test_ci_impact.py` is now **empty**, and a
companion test still fails on a stale entry. (It is a CI allowlist for the
doc-contract test — never the agent-facing exemption, and it cannot be taken in
place of one.)

One thing that does NOT transfer: `site/` is the only tree here with production
dependencies (astro, starlight, markdown-remark) and is deliberately off the
dev-inclusive CVE gate, whose sweep lives in `docs.yml`. Adding a coverage
provider does not change that posture — the provider is a dev dependency, and
the audit scope is unchanged.

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
  synchronized. Distribution is the pinned Git tag (reproducible channel) plus
  the CI-published `npm:@arbiterforge/ca-pi` package on every `ca-pi-v*` tag
  (ADR-0029, `.github/workflows/npm-publish.yml`).
