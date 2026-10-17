# Tech stack — codeArbiter

This is the command and toolchain guide. Versions below describe source inputs;
installed hosts, passing CI, coverage results, and published packages require
their own evidence. Owning manifests, workflows, ADRs, and the release registry
remain authoritative when a pin changes.

## Components and runtime

| Component | Source and runtime |
|---|---|
| Shared hooks and bridges | `core/pysrc/`, Python 3 standard library only; generated into the three governance plugins by `tools/sync-core.py`. |
| Shared instructions | `core/surface/`, Markdown projected using `core/hosts.json` by `tools/build-surface.py`. |
| Native artifact engine | `core/artifacts/`, dependency-free Go module pinned to Go 1.27.1; installation-pinned native payload, bounded JSON bridge, file-backed HTML/Markdown artifacts. |
| Claude farm | `plugins/ca/tools/`, strict TypeScript, Node >=20.6, esbuild, Vitest; committed built `farm.js`. |
| Pi adapter | `plugins/ca-pi/tools/`, strict TypeScript, Node >=22.19, esbuild, Vitest; trusted runtime plus isolated child and parent inference broker. |
| Docker sandbox | `plugins/ca-sandbox/tools/`, strict TypeScript and Node >=20.6; Docker container path, installed nixpacks where available, generated-Dockerfile fallback. |
| Documentation | `site/`, Astro 7/Starlight with TypeScript, Vitest and Playwright; static output consumes curated prose, generated resources, and the separately owned Academy source. |

The canonical shared source forms an internal kernel boundary, not a separately published
Python/npm runtime. The root npm manifest is generated from the Pi package;
edit `plugins/ca-pi/package.json` and regenerate it. The Pi package is public;
the build/test tool packages and site are private.

Native schema writes use 0.3.2 and reads support the declared 0.3.0/0.3.1/0.3.2
formats. Format identity and API protocol identity are separate from schema
version. ADR-0043 makes scheduling/progress assistive: ordinary authorized work
does not need approval codes, completion receipts, or delivery tickets. Reported
checks are distinct from assessed evidence. Stable IDs, bounded reads, real
stops, relevant freshness, revision checks, safe writes and recovery remain.
Current contracts live in `core/artifacts/internal/model/`, `schemas/`,
`internal/operations/`, and `docs/artifacts/`; no database or ORM is introduced.

## Host and platform boundaries

Claude, Codex and Pi projections differ according to `core/hosts.json`, with
adapter payloads at `plugins/ca/`, `plugins/ca-codex/` and `plugins/ca-pi/`.
Codex resource charters support host dispatch; they are not native plugin-agent
registrations. The external Pi runtime is a test/install input, never a
checked-in or runtime dependency of this package. The supported promotion version is exact Pi 1.1.0.
The accepted Pi support record and promotion targets own that version;
`core/hosts.json` binds its skill-expansion fingerprint. Upgrading it requires
the owning promotion checks. The `latest` compatibility probe is nonblocking;
it does not expand the supported version set.

Published releases from 0.7.5 record complete Codex resource-charter packaging
in the adapter changelog. Current static package checks verify resource closure
and dispatch routes; historical packaging does not prove a current live session.

Windows uses native Windows Git/Python; Linux/macOS use native tools. Git owns
config parsing and hook execution. The default worktree geometry is supported;
separate-Git-dir, UNC, and WSL combinations are not universally qualified by a
single successful probe. ADR-0038's bounded WSL path translation does not expand
the general platform matrix. ADR lifecycle proof reads require Git 2.45.0+ with
`--no-lazy-fetch`. Preserve normal trust and safe.directory behavior.

CI owns six native platform cells: Linux, Windows and macOS on amd64/arm64.
Source pins include Python 3.14, Node 22.19 and Go 1.27.1 for native packaging;
other jobs select their own versions in `.github/workflows/ci.yml`. A local
Windows result is not a substitute for those cells or an actual installed-host
exercise. Docker integration and browser suites have their own prerequisites;
report missing prerequisites and skips accurately.

## Test and build commands

Run checks appropriate to changed behavior and dependencies. CI remains the
exhaustive exact-head validation owner; this list does not require every suite
for every local prose edit. Accepted verification boundaries in
`core/surface/includes/verification-boundary.md` remain in force.

From the repository root:

```text
python tools/sync-core.py --check
python tools/build-surface.py --check
python tools/build-host-packages.py --check
python tools/generate-artifact-types.py --check
python .github/scripts/check-plugin-refs.py
python .github/scripts/check_routing_index_parity.py
python .github/scripts/test_build_surface.py
python .github/scripts/test_host_descriptors.py
python .github/scripts/test_command_catalog.py
python .github/scripts/test_command_route_compatibility.py
python .github/scripts/test_artifact_surface.py
python .github/scripts/test_persona_composition.py
python .github/scripts/test_mode_surface.py
python .github/scripts/test_ci_impact.py
python .github/scripts/test_tag_immutability.py
python .github/scripts/test_tag_publication_receipt.py
python .github/scripts/test_reconcile_tag_receipt.py
python -m unittest discover -s plugins/ca/hooks/tests -p "test_*.py"
```

The three tag suites above cover original-publication receipts, the closed
legacy epoch and append-only reconciliation. They are offline tests, not a live
tag-inventory check or authority to publish. For the affected subsystem, retain
the additional named local checks below; this is an impact-selected catalog,
not a requirement to run all of them for unrelated changes:

```text
# Command declarations, packaged resources and discovery
python .github/scripts/test_codex_skill_resources.py
python .github/scripts/check_command_route_release_state.py declarations
python .github/scripts/test_command_route_release_state.py
python .github/scripts/test_badge_consistency.py

# Artifact representation, workflow, compatibility adapters and package closure
python .github/scripts/test_artifact_consumers.py
python .github/scripts/test_artifact_approval_adapter.py
python .github/scripts/test_artifact_authoring.py
python .github/scripts/test_artifact_workflow.py
python .github/scripts/test_artifact_farm.py
python .github/scripts/test_artifact_native.py
python .github/scripts/test_artifact_package.py
python .github/scripts/test_artifact_conformance.py

# ADR lifecycle, destructive-command registry and security boundaries
python .github/scripts/test_adr_lifecycle.py
python .github/scripts/check_adr_lifecycle.py
python .github/scripts/check_destructive_registry.py
python .github/scripts/test_hook_guards.py
python .github/scripts/test_hooks_cold_install.py
python .github/scripts/test_preview_lib.py
python .github/scripts/test_migration_backstop.py

# Tasks, release, provenance, context injection and mode behavior
python .github/scripts/test_metrics_lib.py
python .github/scripts/test_taskboardlib.py
python .github/scripts/test_taskwriter.py
python .github/scripts/test_release_lib.py
python .github/scripts/test_release_trace.py
python .github/scripts/test_board_sync.py
python .github/scripts/test_provenancelib.py
python .github/scripts/test_provenance_wiring.py
python .github/scripts/test_readinjectlib.py
python .github/scripts/test_pre_read.py
python .github/scripts/test_modelib.py
python .github/scripts/test_prompt_submit.py
python .github/scripts/test_startup_emitters.py
python .github/scripts/test_mode_readers.py
python .github/scripts/test_mode_compaction.py
python .github/scripts/test_prune_nudge.py
python .github/scripts/test_ux_conversion.py
python .github/scripts/test_coverage_union.py
```

Artifact conformance runs with Python 3.14 in a fresh environment installed
from its adjacent hashed lock, using the workflow's wheel-only/no-deps controls.
The release trace requires full Git history and all tags; an absent prerequisite
is an explicit failure, not permission to claim the trace passed. Cross-host
coverage-union tests require the Pi tools dependencies below.

The ADR acceptance protocol is independent of ordinary task progress. Its first
commit uses `.github/scripts/prepare_adr_acceptance.py` to create a worktree-local
transition packet bound to the exact HEAD/index, accepted ADR bytes, decision-log
append, sealed obligations, expiry and independent reviewer identity. Only that
exact pending transition is admitted locally; explicit-revision, export,
clean-tree and GitHub-event validation remain strict. After the source commit,
stage its acceptance binding, run both lifecycle commands above and commit that
sole ledger append through the commit owner. Clear the packet with
`python .github/scripts/prepare_adr_acceptance.py --clear` only after that commit
succeeds. Legacy `baseline` bindings remain closed to the original migration
snapshot `10d9b012d91681498bdf911dd82ffa28e112407f`; later commits cannot acquire
legacy status instead of the acceptance protocol.

Run Python syntax compilation for changed canonical modules. Shared hook tests
are maintained in `plugins/ca/hooks/tests/`; `.github/scripts/` owns additional
contract/integration suites. Artifact/context adapters, provenance, task-board,
release, host-platform and security changes require their corresponding named
suites. Read current workflows and tests instead of copying dated suite counts.

From `core/artifacts/`:

```text
go test -buildvcs=false ./...
go vet -buildvcs=false ./...
```

From the root, build into a fresh output directory:

```text
python tools/build-artifacts.py --output <output-directory>
python .github/scripts/test_artifact_cli.py --coverage-output <coverage-profile>
python tools/test-artifact-mixed-schema.py --old <old-binary> --candidate <candidate-binary>
```

Artifact integration suites may use `ARTIFACT_TEST_INSTALLATION` to select an
already-built candidate. This avoids redundant builds; it does not manufacture
installed-host or release evidence. The mixed-schema drill uses disposable
fixtures and preserves complete-store rollback/export, including later work
and retained stops.

| Working directory | Install and checks |
|---|---|
| `plugins/ca/tools/` | `npm ci`, `npm run typecheck`, `npm test`, `npm run build`; `npm run coverage` for coverage. |
| `plugins/ca-sandbox/tools/` | Same commands; Docker-dependent tests require Docker and must report any skips. |
| `plugins/ca-pi/tools/` | `npm ci --ignore-scripts`, `npm run typecheck`, `npm test`, `npm run build`; `npm run coverage` for coverage. |
| `site/` | `npm ci`, `npm run typecheck`, `npm test`, `npm run build`, `npm run link-audit`; `npm run coverage` for coverage. |

When Pi source, shared core or Pi package generators change, install the tools
dependencies before invoking the platform aggregate or its fixture subprocesses.
The Pi tools install is an aggregate prerequisite: `npm --prefix plugins/ca-pi/tools ci --ignore-scripts`.
Missing Vitest is a missing prerequisite, not a passing or silently skipped
platform result. From the repository root:

```text
npm --prefix plugins/ca-pi/tools ci --ignore-scripts
npm --prefix plugins/ca-pi/tools run typecheck
npm --prefix plugins/ca-pi/tools test
npm --prefix plugins/ca-pi/tools run build
python .github/scripts/test_pi_package.py
python .github/scripts/test_pi_parity.py
python .github/scripts/test_public_pi_docs.py
python .github/scripts/test_pi_platform_contract.py --fixtures-only
```

A supported-version aggregate adds `--pi-version 1.1.0` after installing that
exact external Pi version from its reviewed host lock with scripts disabled.
CI owns the supported Windows/macOS/Linux matrix. Fixture-only success does not
establish a live runtime or another platform; report unavailable cells as such.

Site scripts own generation through pre-hooks. `npm test` also runs Academy
non-root-base and rendered-release checks. Rebuilt tracked bundles and generated
resources must match their owners; do not hand-edit output to pass parity.

Site browser publication validation belongs to `.github/workflows/docs.yml`,
not the routine contributor or commit-gate loop. Local unit/build/link checks
do not require browser installation or a browser run. The hosted gate uses
Chrome already supplied by the GitHub runner image, records the observed version,
and acquires no browser, ffmpeg or OS dependencies. The npm lockfile does not
authenticate those browser bytes, and no fixed hosted Chrome version is claimed.
A failed browser gate blocks Pages artifact publication; PR validation stays
read-only and the separately authorized deploy job owns publication permissions.

The native artifact browser job in ci.yml is a separate qualification boundary:
it renders the native candidate's examples and runs their offline review checks
under the named hosted environment. This does not turn browser setup into a
universal local requirement. A specifically required, authorized local host or
device canary follows verification-boundary.md and retains its own environment
and scope; it cannot substitute for the owning hosted publication gate.

## Coverage

These source-tree bindings retain the maintainer-approved language-specific
profiles of 2026-09-26. The shared policy is
`core/surface/includes/maturity-coverage.md`; every required metric must clear
the stage threshold, currently 70% at stage 2. Changing a profile, narrowing
production scope or excluding source to obtain a pass requires an explicit
user decision; ordinary maintenance does not re-request the existing approval.

| source tree | profile | Production scope and exclusions | Supported measurement hosts |
|---|---|---|---|
| `plugins/ca/tools` | `lines-branches` | Top-level `*.ts`; excludes `*.test.ts` and `*.config.ts`. | Ubuntu + Windows union. |
| `plugins/ca-pi/tools` | `lines-branches` | `src/**/*.ts`; tests outside src are not production scope. | Ubuntu + Windows union. |
| `plugins/ca-sandbox/tools` | `lines-branches` | Top-level `*.ts`; excludes `*.test.ts`, `*.config.ts`, `__fixtures__/**`. | Ubuntu with Docker. |
| `site/` | `lines-branches` | `scripts/**/*.ts`; excludes `scripts/**/*.test.ts`. Astro src components are covered by build/link/browser checks, not this numeric report. | Ubuntu. |
| `core/artifacts/` | `go-native` | All production packages with `-coverpkg=./...`, including packages reached through other packages' tests; unit plus instrumented executable integration profiles. | Linux, Windows and macOS, each amd64 + arm64. |

TypeScript's tool is Vitest V8, with text-summary and HTML reporters; each tree's
vitest.config.ts owns the exact include/exclude declaration. Both lines and
branches must pass. Run the affected tree's command:

```text
npm --prefix plugins/ca/tools run coverage
npm --prefix plugins/ca-pi/tools run coverage
npm --prefix plugins/ca-sandbox/tools run coverage
npm --prefix site run coverage
```

Reports live in ignored coverage output directories, not project state. A local
sandbox run without Docker can self-skip integration suites; required CI uses
`CA_SANDBOX_REQUIRE_DOCKER=1` so missing Docker cannot erase the required evidence.
TypeScript's numeric floor is applied by the owning workflow instructions, not
duplicated in Vitest configuration or claimed as an enforced CI numeric gate.

For the two platform-forked trees, coverage_union.py binds source, configuration,
lockfile and checkout before testing, checks them afterward, then verifies host
reports and normalizes copies into a fresh merge directory. Vitest merges the
verified reports. Preserve one identity per source and distinct tree namespaces;
never average percentages, merge incompatible reports, discard host-specific
source or invent missing host coverage. Original evidence remains unchanged.

Native Go measures statements, not lines or branches. The CLI test builds an
instrumented executable; collection binds production/test/embedded inputs,
toolchain, platform and profile bytes. Use fresh output paths outside the module:

```text
python .github/scripts/test_artifact_cli.py --coverage-output <new-cli-profile>
python tools/artifact-coverage.py collect --module-root core/artifacts --output <new-native-directory> --expect-platform windows/amd64 --extra-profile <new-cli-profile>
python tools/artifact-coverage.py summarize --module-root core/artifacts --input <new-native-directory> --expect-platform windows/amd64 --require-integration
```

That example is explicitly a Windows/amd64 local figure. Required native CI
collects all six cells, requires executable integration for every cell, and
enforces the current 70% statement floor. Missing, duplicate, stale, partial or
mismatched required reports block the complete verdict. Without selected
`--expect-platform` options, summarize requires the complete six-platform set.
Label lines/branches unmeasured, never inferred, zero or passed. Reconcile the
fixed CI floor with the maturity table if stage changes.

There is **no coverage tooling for the Python hooks or build tools**
(`core/pysrc/*.py`, `plugins/*/hooks/*.py`, `.github/scripts/*.py`, `tools/*.py`).
Those surfaces use direct unittest and behavioral checks, not TypeScript
instrumentation. The shared maturity policy owns the no-tooling exemption and
its citation requirements; this sentence identifies the exact exempt surface.
Go native statements are not the no-tooling exemption.

Every profile also retains **critical-path** outcome tests and focused mutation
checks. For changed critical boundaries, cover approval/rejection, malformed or
stale inputs, filesystem containment and recovery where applicable. Assert the
actual boundary outcome; removing or inverting a safeguard must make its focused
test fail. Missing critical-path evidence blocks even if the numeric floor passes.
Scope this work to affected obligations and callers, without unrelated expansion.

Name measured hosts in every reported figure. A scoped local result can be
PARTIAL under verification-boundary.md; complete exact-head hosted evidence is
required before merge. Keep measurements in dated reports. Accepted historical
packets, frozen fixtures, installed-host proof and release receipts retain their
original identity and scope and cannot be relabelled as current qualification.

## Supply chain, publication and retained decisions

`security-controls.md` owns crypto, credentials, network boundaries, approved
licenses, immutable tags and accepted exceptions. The high-severity audit gate
includes development dependencies in the three tools projects; the site gate
uses production dependencies and its exact, expiring approved-advisory file.
Use `.github/scripts/npm_audit_gate.py` as the hosted owner rather than treating
a raw audit result as the full exception-aware policy.

Run the dev-inclusive check from each of the three tools directories listed
above; no production-only flag is used for these build/test dependency graphs:

```text
npm audit --audit-level=high
```

From site, use the hosted exception-aware production scope:

```text
npm audit --omit=dev --json | python ../.github/scripts/npm_audit_gate.py --exceptions audit-exceptions.json --audit-level=high
```

The pinned, redacted gitleaks CI scan is read-only and network-free for candidate
content, covering the selected tree/PR range. Only exact literal allowlist
entries are accepted. The local staged scan and commit-time crypto/secret
markers are separate controls, not substitutes for each other.

For the local convenience sweep, this command checks the staged diff without
printing possible credentials. Exit 0 means no pattern hit, 1 requires inspection,
and 2 means the Git read failed. It is deliberately broader than the authoritative
shared SECRET_RE classifier and does not mint a security-pass marker:

```text
python -c 'import re,subprocess,sys; r=subprocess.run(["git","diff","--cached","--no-ext-diff","--no-textconv","--unified=0","--"],capture_output=True); code=2 if r.returncode else int(bool(re.search(rb"api[_-]?key|token|secret|password|private[_-]?key|passphrase|credential|BEGIN.*PRIVATE|AKIA|ghp_|sk-ant",r.stdout,re.I))); print({0:"No staged credential-pattern match",1:"Potential staged credential pattern; inspect locally without logging secrets",2:"Staged diff could not be read"}[code]); sys.exit(code)'
```

`.codearbiter/release-targets.md` declares four release series. Only `ca` is
eligible for the repository-wide Latest badge. Governance package publication
belongs to the hosted qualified cohort, not a local fallback build. Pi root
manifest generation, npm provenance, registry ownership and credential handling
follow release workflows. Published tags are immutable; corrections get new
versions. Preserve the closed legacy publication ledger and its evidence grades.

Feature Forge `--farm` remains preview, explicit opt-in and off by default under
the user decision recorded 2026-09-16 in open-questions.md and the owning farm
include. That decision reset qualification and did not enable typed-HTML farm
projection. Preserve that separate integration/qualification boundary until its
actual completion and promotion evidence is recorded.
