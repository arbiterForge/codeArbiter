# Pi Harness Support Implementation Plan

> **Execution route:** Continue through `$ca-feature` on `feat/pi-support`. Every task follows the
> repository TDD phases and its `status` cell is updated in place. Do not create a milestone branch,
> merge a partial milestone, publish a package, tag a release, or commit outside `$ca-commit`.

**Status:** APPROVED — 2026-07-13 by SUaDtL@users.noreply.github.com
**Spec:** `.codearbiter/specs/pi-support.md` — APPROVED 2026-07-13
**Decisions:** ADR-0013, ADR-0014
**Goal:** Ship `ca-pi` as a full-parity Pi governance package generated from the same arbiter core as
`ca` and `ca-codex`, with a thin Pi adapter, independently versioned Git distribution, and no partial
promotion.

**Architecture:** `core/hosts.json` becomes the data source for every host target; the Python and
markdown generators consume it instead of branching over Claude/Codex. `ca-pi` ships generated
skills, charters, shared stdlib Python, and two built JavaScript extensions: a parent adapter and an
enforcement-only child adapter. The adapter translates Pi events to a bounded canonical JSON bridge;
mutating built-ins are wrapped at their actual `execute()` boundary so the shared core judges the
final arguments after every `tool_call` mutation.

**Tech stack:** Python 3 stdlib core and generators; TypeScript 5.9.3 on Node >=22.19.0; esbuild
0.28.1; Vitest 4.1.9; Pi 0.80.5 minimum and 0.80.6 live-verified; GitHub Actions on Windows, macOS,
and Linux.

## Global constraints

- `core/pysrc/` and `core/surface/` remain authoritative. Pi may add codecs/adapters, never H-rules,
  workflow phases, reviewer policy, SMARTS policy, or handwritten command bodies.
- All work stays on `feat/pi-support`; M1-M6 are internal checkpoints, not release units.
- `@earendil-works/pi-coding-agent` remains an externally installed, exact-pinned host. It is never
  added to `dependencies`, bundled, copied, or locked beneath `plugins/**`. Host-provided imports are
  externalized and module identity is tested.
- Pi package distribution is Git-backed for this feature. npm publication is not part of this plan.
- Root `package.json` is private generated Pi metadata only: no workspaces, scripts, dependencies, or
  devDependencies.
- `plugins/ca-pi/tools/` is an isolated Node >=22.19.0 build/test workspace. Existing Node-20 tool
  workspaces retain their current engines and lockfiles.
- Python remains stdlib-only. Every bridge process uses an absolute interpreter and installed script,
  argv arrays, `shell: false`, bounded stdin/stdout/stderr, explicit cwd, and tree termination.
- Pi authentication is opaque host state under ADR-0014. No code reads or copies `auth.json`, resolves
  credentials, clones the parent environment, or places credentials/task/prompt text in argv,
  environment, temp files, logs, snapshots, audits, fixtures, or failure text.
- Child environments exclude `FARM_API_KEY` and `CLAUDE_CODE_OAUTH_TOKEN`, select one exact
  provider/model without fallback, disable ambient discovery, and load only the child enforcement
  adapter plus explicit generated skills/charters.
- `CODEARBITER_SUBAGENT=1` suppresses recursive dispatch only. Ambient misuse blocks and points to
  `/ca-doctor`; all child enforcement remains active.
- Unknown Pi tools are potentially mutating and block unless the generated descriptor classifies
  them read-only. A declared external mutating tool remains blocked until it has a final-execution
  wrapper; event-order approval alone is insufficient.
- `ca-pi` never grants project trust. Same-process trusted extensions remain ADR-0010 residual risk;
  inability to prove final-argument governance is a promotion STOP that reopens ADR-0013.
- Every generated text file is UTF-8/LF. Regeneration may update all expected host outputs; a second
  run must produce no diff.
- Existing user changes to `.codearbiter/gate-events.log`, `.codearbiter/open-tasks.md`, and unrelated
  scratch files are out of scope and must be preserved.

## File responsibility map

| File or tree | Responsibility |
|---|---|
| `core/hosts.json` | Canonical host descriptor: paths, command spelling, surface transforms, capabilities, Pi tool classes, package outputs. |
| `tools/host_descriptors.py` | Strict stdlib parser/validator used by every generator and CI test. |
| `tools/build-surface.py` | Descriptor-driven rendering of commands, routines, includes, charters, catalogs, and Pi command metadata. |
| `tools/sync-core.py` | Descriptor-driven byte vendoring of `core/pysrc/*.py` into all governance hosts. |
| `tools/build-host-packages.py` | Generate/check root Pi metadata from `plugins/ca-pi/package.json` and the host descriptor. |
| `core/surface/agents/` | Canonical role charters extracted byte-for-byte from `plugins/ca/agents/`. |
| `plugins/ca-pi/package.json` | Independent `ca-pi` version source; private and dependency-free. |
| `package.json` | Generated Git-install entry pointing Pi to built extensions and generated skills. |
| `plugins/ca-pi/hooks/` | Vendored shared Python plus thin `_host.py` and `pi-bridge.py`. |
| `plugins/ca-pi/tools/src/contracts.ts` | Canonical TypeScript request/response, event, result, and terminal-state types. |
| `plugins/ca-pi/tools/src/bridge.ts` | Bounded Python subprocess client and failure-direction classifier. |
| `plugins/ca-pi/tools/src/tool-guard.ts` | Built-in execution wrappers and fail-closed unknown-tool handler. |
| `plugins/ca-pi/tools/src/extension.ts` | Parent lifecycle wiring, activation, aliases, status, collision checks, dispatch tool. |
| `plugins/ca-pi/tools/src/child-extension.ts` | Enforcement-only child lifecycle; no aliases, UI orchestration, or recursive dispatch. |
| `plugins/ca-pi/tools/src/child-env.ts` | Minimal OS/runtime/provider environment construction and secret removal. |
| `plugins/ca-pi/tools/src/runner.ts` | Fresh Pi RPC/JSONL process launch, bounded protocol, cancellation, timeout, and tree cleanup. |
| `plugins/ca-pi/tools/src/roles.ts` | Generated role lookup, exact tool set, charter/skill paths, depth/concurrency policy. |
| `plugins/ca-pi/tools/src/compaction.ts` | Pi semantic codec and native custom-compaction result built through the hardened runner. |
| `plugins/ca-pi/tools/src/doctor.ts` | Version, origin, trust, collision, Python, bridge, child, wrapper-self-test, and active-dispatch diagnoses. |
| `plugins/ca-pi/extensions/codearbiter.js` | Built parent extension shipped to Pi. |
| `plugins/ca-pi/extensions/codearbiter-child.js` | Built enforcement-only child extension shipped to Pi. |
| `.github/scripts/test_pi_*.py` | Cross-language packaging, parity, live-host, benchmark, and release checks. |
| `.github/workflows/ci.yml` | Three-platform Pi contract jobs, static analysis, path filters, and independent version guard. |
| `docs/pi-parity-testing.md` | Reproducible trusted/live Pi promotion runbook. |
| `docs/parity.md` | Three-host evidence ledger and explicit host-impossible/degraded rows. |

## TDD Phase 1 obligation ledger

Every approved acceptance criterion is one obligation and has exactly one owning task. No additional
contract/security obligation is needed: ADR-0014's constraints were incorporated into AC-11, AC-13,
AC-17, AC-29, and AC-36 before approval.

| Obligation | Spec source | Owning task | Initial status |
|---|---|---:|---|
| PI-AC-01 N-host generation | AC 1 | 1 | COVERED |
| PI-AC-02 clean regeneration | AC 2 | 1 | COVERED |
| PI-AC-03 shared Python byte identity | AC 3 | 1 | COVERED |
| PI-AC-04 no governance duplication | AC 4 | 1 | COVERED |
| PI-AC-05 root Git package | AC 5 | 2 | COVERED |
| PI-AC-06 no runtime Pi copy | AC 6 | 2 | COVERED |
| PI-AC-07 version contract | AC 7 | 2 | COVERED |
| PI-AC-08 dormancy | AC 8 | 3 | COVERED |
| PI-AC-09 activation/persona/host | AC 9 | 3 | COVERED |
| PI-AC-10 command parity | AC 10 | 3 | COVERED |
| PI-AC-11 canonical/unknown mapping | AC 11 | 4 | COVERED |
| PI-AC-12 verdict parity | AC 12 | 4 | COVERED |
| PI-AC-13 mutation fail-closed | AC 13 | 4 | COVERED |
| PI-AC-14 advisory fail-open | AC 14 | 4 | COVERED |
| PI-AC-15 read/write notices | AC 15 | 5 | COVERED |
| PI-AC-16 Git backstop | AC 16 | 5 | COVERED |
| PI-AC-17 subagent isolation | AC 17 | 6 | COVERED |
| PI-AC-18 subagent orchestration | AC 18 | 7 | COVERED |
| PI-AC-19 process-tree cleanup | AC 19 | 7 | COVERED |
| PI-AC-20 no-inline promotion | AC 20 | 6 | COVERED |
| PI-AC-21 composable status | AC 21 | 3 | COVERED |
| PI-AC-22 settled lifecycle | AC 22 | 3 | COVERED |
| PI-AC-23 host-neutral prune policy | AC 23 | 8 | COVERED |
| PI-AC-24 Pi compaction safety | AC 24 | 8 | COVERED |
| PI-AC-25 prune command parity | AC 25 | 8 | COVERED |
| PI-AC-26 farm preview parity | AC 26 | 9 | COVERED |
| PI-AC-27 shared-store attribution | AC 27 | 9 | COVERED |
| PI-AC-28 doctor coverage | AC 28 | 5 | COVERED |
| PI-AC-29 secret safety | AC 29 | 6 | COVERED |
| PI-AC-30 static analysis | AC 30 | 10 | COVERED |
| PI-AC-31 relative performance | AC 31 | 11 | COVERED |
| PI-AC-32 cross-platform contract | AC 32 | 11 | COVERED |
| PI-AC-33 independent release guard | AC 33 | 2 | COVERED |
| PI-AC-34 documentation parity | AC 34 | 12 | COVERED |
| PI-AC-35 live promotion evidence | AC 35 | 13 | OPEN |
| PI-AC-36 threat-model gate | AC 36 | 10 | COVERED |
| PI-AC-37 repository regression gate | AC 37 | 14 | OPEN |
| PI-AC-38 single-branch/full-parity gate | AC 38 | 14 | OPEN |

## Status protocol and checkpoints

Each task status moves `PENDING -> IN_PROGRESS -> ACCEPTED`. `ACCEPTED` requires the task's red tests
to have failed for the named reason, then passed unchanged, plus its focused type/syntax checks and
review. Checkpoints occur after Tasks 1-2 (generation/package), 3-5 (enforcement), 6-9
(agents/prune/farm), and 10-14 (promotion). No checkpoint creates a branch or publishes an artifact.

### Batch 2 combined checkpoint (Tasks 3-5): ACCEPTED - 2026-07-15

Tasks 3-5 passed their focused tests and were individually accepted, but the combined integration
and security review found cross-task failures that those focused tests did not detect. The combined
checkpoint therefore supersedes the individual task acceptances for promotion purposes. Tasks 6-9
must not start until this checkpoint receives a fresh independent clean review.

Confirmed blockers, in required fix order:

1. **CRITICAL - pre-trust/dormancy Python resolution:** extension load resolves and may spawn a bare
   interpreter candidate before activation or trust. A poisoned working-directory `py.exe` was
   executed in the review probe. Defer resolution until activation/trust and eliminate project-cwd
   executable search; add a poisoned-cwd live regression test.
2. **HIGH - activation parser drift:** the TypeScript parser rejects canonical inputs accepted by
   `core/pysrc/_hooklib.py`, including case, indentation, and BOM variants. Generate or share one
   parser contract and add cross-host fixtures.
3. **HIGH - enforcement installation is not fail-closed in real Pi:** Pi catches ordinary lifecycle
   handler errors and continues after an installation failure. Add an always-installed bootstrap
   guard or explicit host shutdown, then prove it through real-Pi RPC fault injection.
4. **HIGH - supported-version split:** the adapter accepts every version at or above 0.80.5 while
   the approved contract supports exactly 0.80.5 and 0.80.6. Enforce the exact set before tool
   registration and test 0.80.7, prereleases, and 1.x, including the latest-version canary.
5. **HIGH - read-context parity false-green:** native Pi `{path: ...}` read input is not normalized
   to `{file_path: ...}` before `pre-read.py`, and model-visible context is dropped. Integrate the
   canonical payload normalization, preserve context on the real result route, and assert exact
   model-visible output.
6. **MEDIUM - doctor live-fire overstates host coverage:** the current probe calls the stored wrapper
   directly instead of the active Pi dispatcher. Exercise active dispatch or relabel the check as a
   wrapper self-test while keeping PI-AC-28 open.

Before accepting the checkpoint, re-audit two unresolved security candidates: structured doctor
values may bypass shared-corpus redaction, and enforcement wrappers may survive shutdown or
deactivation in a reused Pi process. These are audit questions, not yet confirmed findings.

The subsequent security rereview confirmed one additional HIGH: a globally discovered extension
could begin repository-aware Git startup before affirmative project trust. The 2026-07-15 residual
fix makes host loading discovery rather than authorization. Every `session_start` first invalidates
the prior lifecycle and enters an activation-check fail-closed generation, reads only the canonical
marker, and then requires `context.isProjectTrusted?.() === true` before Python/Git resolution,
bridge/shared startup, enforcement, hooks, Git reads, or fetch. Missing/false trust retains guarded
mutation, fresh native untrusted reads, one fixed trust direction, and side-effect-free doctor;
false-to-true same-process retry clears cached identities and performs a normal activation. The
The final same-reviewer rereviews accepted the correction on 2026-07-15: integration returned
Spec YES / APPROVED with zero findings, and security returned PASS with zero CRITICAL/HIGH/MEDIUM/LOW
findings. Fresh controller verification reproduced Pi 138/138, package/RPC 20/20, parity 19/19,
doctor 7/7, clean generation, and the deterministic parent hash recorded below. The combined
checkpoint is accepted and no longer gates Tasks 6-9.

The durable evidence, hashes, preserved user dirt, and restart sequence are recorded in
`.codearbiter/reports/2026-07-14-pi-support-handoff/report.md`.
The remediation and rereview chain is recorded in the sibling `batch-2-*` reports in that directory.

---

### Task 1: Descriptor-driven three-host generation and canonical charters

**Status:** ACCEPTED
**Owns:** PI-AC-01, PI-AC-02, PI-AC-03, PI-AC-04
**Review:** Spec compliant and quality approved after one fix loop; fresh controller verification passed.
The reviewer recorded one non-blocking coverage note: the legacy LF unit-test loop names Claude and
Codex only. A strict controller scan proved all 184 generated Pi text files are UTF-8/LF; Task 14's
full-regression gate must close or explicitly retain this note.

**Files:**
- Create: `core/hosts.json`
- Create: `tools/host_descriptors.py`
- Create: `.github/scripts/test_host_descriptors.py`
- Create: `core/surface/agents/*.md` from every existing `plugins/ca/agents/*.md`
- Modify: `tools/build-surface.py`
- Modify: `tools/sync-core.py`
- Modify: `.github/scripts/test_build_surface.py`
- Modify: `.github/scripts/test_sync_core.py`
- Generated: `plugins/ca-pi/{hooks,skills,routines,includes,agents}/**`
- Generated/verified unchanged where templates do not require a three-host edit:
  `plugins/ca/**`, `plugins/ca-codex/**`

**Interfaces:**
- Produces: `HostDescriptor`, `load_host_descriptors(repo: str) -> tuple[HostDescriptor, ...]`,
  `host_descriptor(name: str, repo: str) -> HostDescriptor`.
- Produces descriptor fields `name`, `plugin_dir`, `hooks_dir`, `command_form`, `tokens`,
  `capabilities`, `surface.rules`, `surface.managed_subtrees`, `surface.catalog`, `tool_classes`, and
  optional `package`.
- Consumers: Tasks 2-14; no later task may add a parallel host list.

- [ ] **Step 1: Write descriptor and generator tests first**

```python
def test_three_governance_hosts_are_data_not_binary_switches():
    hosts = load_host_descriptors(REPO)
    assert [host.name for host in hosts] == ["claude", "codex", "pi"]
    assert [host.plugin_dir for host in hosts] == [
        "plugins/ca", "plugins/ca-codex", "plugins/ca-pi",
    ]
    for path in ("tools/build-surface.py", "tools/sync-core.py"):
        text = open(path, encoding="utf-8").read()
        assert 'host == "claude"' not in text
        assert 'host == "codex"' not in text
        assert 'host == "pi"' not in text

def test_generation_is_clean_on_second_run():
    run_generator("tools/build-surface.py")
    run_generator("tools/sync-core.py")
    first = snapshot_generated_trees()
    run_generator("tools/build-surface.py")
    run_generator("tools/sync-core.py")
    assert snapshot_generated_trees() == first
```

- [ ] **Step 2: Run the new tests red while all existing generator tests stay green**

Run:

```powershell
python .github/scripts/test_host_descriptors.py
python .github/scripts/test_build_surface.py
python .github/scripts/test_sync_core.py
```

Expected: the new suite fails because `core/hosts.json`/`host_descriptors.py` and the Pi target do not
exist; existing Claude/Codex cases pass.

- [ ] **Step 3: Add the strict descriptor schema and generic transform rules**

`tools/host_descriptors.py` must expose these exact immutable types and reject unknown keys, duplicate
names/paths, escaping paths, malformed command templates, unknown condition tags, and noncanonical
tool classes:

```python
@dataclass(frozen=True)
class SurfaceRule:
    source_prefix: str
    output_pattern: str
    exclude: frozenset[str]
    add_skill_frontmatter: bool = False

@dataclass(frozen=True)
class HostDescriptor:
    name: str
    plugin_dir: str
    hooks_dir: str
    command_form: str
    tokens: Mapping[str, str]
    capabilities: Mapping[str, bool]
    surface_rules: tuple[SurfaceRule, ...]
    managed_subtrees: tuple[str, ...]
    catalog: str | None
    tool_classes: Mapping[str, str]
    package: Mapping[str, object] | None
```

`core/hosts.json` declares all three hosts. Generic rules map source prefixes to output patterns;
`build-surface.py` applies the first matching rule and expands `{relative}`, `{stem}`, and `{name}`.
Conditionals accept any descriptor name. `sync-core.py` derives every hooks target from the same
descriptors.

- [ ] **Step 4: Extract and generate role charters without changing Claude bytes**

Copy each current `plugins/ca/agents/*.md` into `core/surface/agents/` as canonical input, teach the
generic rules to render Claude agents and Pi charters, and add a byte comparison before deleting no
source. Pi charters use descriptor token substitution and remain non-discoverable except when passed
explicitly to a child.

- [ ] **Step 5: Prove no governance policy was handwritten into Pi**

Add a structural test that normalizes generated Pi command/skill/charter bodies back to template
tokens and compares them with `core/surface/`. Permit only `_host.py`, `pi-bridge.py`, built extension
artifacts, package metadata, catalogs, and host notes outside generated trees.

- [ ] **Step 6: Regenerate twice and run the complete generator gate**

```powershell
python tools/build-surface.py
python tools/sync-core.py
python tools/build-surface.py --check
python tools/sync-core.py --check
python .github/scripts/test_host_descriptors.py
python .github/scripts/test_build_surface.py
python .github/scripts/test_sync_core.py
git diff --check
```

Expected: three hosts render, every shared Python file is byte-identical, no orphan exists, and the
second write reports zero changed files.

---

### Task 2: Git package metadata, Pi toolchain, module identity, and version guard

**Status:** ACCEPTED
**Owns:** PI-AC-05, PI-AC-06, PI-AC-07, PI-AC-33
**Review:** Spec compliant and independently approved after four task-review rounds plus one combined
scope-security fix loop. Fresh controller verification passed the complete Task 1/2 gate with the
reviewed lock unchanged, deterministic bundles, zero live fixture daemons, and no `node_modules`
status leak. Hosted Windows/macOS/Linux execution for Pi 0.80.5/0.80.6 remains promotion evidence
owned by Tasks 13-14, not a substitute for this accepted local package contract.

**Files:**
- Create: `plugins/ca-pi/package.json`
- Create: `plugins/ca-pi/CHANGELOG.md`
- Create: `plugins/ca-pi/tools/package.json`
- Create: `plugins/ca-pi/tools/package-lock.json`
- Create: `plugins/ca-pi/tools/tsconfig.json`
- Create: `plugins/ca-pi/tools/vitest.config.ts`
- Create: `plugins/ca-pi/tools/src/pi-api.d.ts`
- Create: `plugins/ca-pi/tools/src/extension.ts` as a dormant no-op host entrypoint
- Create: `plugins/ca-pi/tools/src/child-extension.ts` as an explicit-only dormant no-op entrypoint
- Create: `plugins/ca-pi/tools/build.mjs`
- Create: `plugins/ca-pi/tools/test/package.test.ts`
- Create: `tools/build-host-packages.py`
- Create: `.github/scripts/test_pi_package.py`
- Modify: `.github/workflows/ci.yml`
- Generated: `package.json`

**Interfaces:**
- Produces: `render_package(host: HostDescriptor, version: str) -> bytes` and CLI modes
  `python tools/build-host-packages.py [--check]`.
- Produces npm scripts `build`, `typecheck`, and `test`; built entrypoints are
  `../extensions/codearbiter.js` and `../extensions/codearbiter-child.js`.
- Consumes Task 1 descriptors.

- [ ] **Step 1: Write red packaging and identity tests**

```python
def test_root_manifest_is_private_dependency_free_pi_metadata():
    data = json.loads((REPO / "package.json").read_text("utf-8"))
    assert data["private"] is True
    assert data["engines"] == {"node": ">=22.19.0"}
    assert data["pi"]["extensions"] == [
        "./plugins/ca-pi/extensions/codearbiter.js",
    ]
    assert data["pi"]["skills"] == ["./plugins/ca-pi/skills"]
    for forbidden in ("dependencies", "devDependencies", "workspaces", "scripts"):
        assert forbidden not in data

def test_pi_runtime_is_not_present_beneath_plugin():
    assert not list((REPO / "plugins/ca-pi").rglob("pi-coding-agent"))
    assert not list((REPO / "plugins/ca-pi").rglob("pi-agent-core"))
```

`package.test.ts` asserts both bundles contain external host imports, contain no copied Pi source,
and load against the live host's single module registry in the isolated integration fixture.

- [ ] **Step 2: Run packaging tests red**

```powershell
python .github/scripts/test_pi_package.py
```

Expected: FAIL because no Pi manifests, build workspace, bundles, or generated root package exist.

- [ ] **Step 3: Create the dependency-free package pair and isolated build workspace**

Use independent initial version `0.1.0`. The build workspace pins only already-vetted development
tools and runs installs with lifecycle scripts disabled:

```json
{
  "name": "ca-pi-tools",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "engines": { "node": ">=22.19.0" },
  "scripts": {
    "build": "node ./build.mjs",
    "typecheck": "tsc --noEmit",
    "test": "vitest run"
  },
  "devDependencies": {
    "@types/node": "25.9.4",
    "esbuild": "0.28.1",
    "typescript": "5.9.3",
    "vitest": "4.1.9"
  }
}
```

If the lock would resolve any version or license not already present in the reviewed repo toolchains,
route that exact package/version through `$ca-add-dep` before `npm install`. Run
`npm install --ignore-scripts --package-lock-only` only after that check.

**Dependency-gate resolution (2026-07-14):** SUaDtL@users.noreply.github.com selected conflict
resolution option 1, extending MPL-2.0 and 0BSD to development-only `plugins/*/tools`. The reviewed
lock may proceed unchanged with `--ignore-scripts`; keep `NAPI_RS_FORCE_WASI` unset, expose no
secret-bearing environment to build/test jobs, smoke-test native binding selection on every CI
platform, and prove no dependency source, `.node`, `.wasm`, `node_modules`, Vite, or Rolldown artifact
enters the distributed `ca-pi` payload.

- [ ] **Step 4: Generate root metadata and externalized bundles**

`build-host-packages.py` reads only the nested version and descriptor paths, writes deterministic
two-space JSON with LF, and checks version equality. `build.mjs` bundles local adapter modules but
marks `@earendil-works/pi-coding-agent`, `@earendil-works/pi-ai`,
`@earendil-works/pi-agent-core`, `@earendil-works/pi-tui`, and `typebox` external; it emits no source
map and no lifecycle script. The initial entrypoints import one host runtime symbol to prove external
resolution and otherwise register nothing; Task 3 replaces the parent no-op with lifecycle wiring and
Task 6 replaces the child no-op with enforcement-only wiring.

- [ ] **Step 5: Prove Pi 0.80.5/0.80.6 and Node failure directions without real auth**

Run isolated `PI_CODING_AGENT_DIR` fixtures with a deterministic local provider. Verify 0.80.5 and
0.80.6 discover the root package; an older captured capability fixture, Node below 22.19.0, and
missing Python each return the exact doctor direction and never partially activate. The npm-latest
probe reports separately and is nonblocking.

- [ ] **Step 6: Add the independent release guard and verify clean generation**

Add `ca-pi` to CI path outputs and a `version-bump-pi` job using tag namespace `ca-pi-v<version>`.
First introduction passes; a changed previously tagged payload with unchanged version fails; version,
changelog, and generated root metadata must advance together.

```powershell
python tools/build-host-packages.py
python tools/build-host-packages.py --check
npm --prefix plugins/ca-pi/tools ci --ignore-scripts
npm --prefix plugins/ca-pi/tools run typecheck
npm --prefix plugins/ca-pi/tools test -- test/package.test.ts
npm --prefix plugins/ca-pi/tools run build
python .github/scripts/test_pi_package.py
git diff --check
```

---

### Task 3: Dormant activation, persona, aliases, collisions, and status lifecycle

**Status:** ACCEPTED
**Owns:** PI-AC-08, PI-AC-09, PI-AC-10, PI-AC-21, PI-AC-22

**Review:** Independently approved after three fix loops. Fresh controller verification passed exact
activation/dormancy, chained persona refresh, generated command ownership, DECISION-0018
native-equivalent alias expansion through a real package-installed Pi RPC turn, composable settled
status, supported-matrix wiring, symlink/terminator fail-closed cases, and process-tree cleanup. The
reviewed dependency lock remained unchanged; Task 4 now supplies the concrete bridge that replaces
Task 3's deliberately visible temporary bridge degradation.

**Review ledger from Batch 1:** Run compatibility successfully before publishing any runtime
identity/version state, or remove the mutable exports; every incompatibility test must leave them
unset and register nothing.

**Files:**
- Create: `plugins/ca-pi/tools/src/activation.ts`
- Create: `plugins/ca-pi/tools/src/commands.ts`
- Create: `plugins/ca-pi/tools/src/contracts.ts`
- Create: `plugins/ca-pi/tools/src/status.ts`
- Modify: `plugins/ca-pi/tools/src/extension.ts`
- Create: `plugins/ca-pi/tools/test/activation.test.ts`
- Create: `plugins/ca-pi/tools/test/commands.test.ts`
- Create: `plugins/ca-pi/tools/test/status.test.ts`
- Generated: `plugins/ca-pi/generated/command-catalog.json`
- Modify: `tools/build-surface.py`

**Interfaces:**
- Produces: `isEnabled(cwd: string) -> Promise<boolean>`; `registerAliases(pi, catalog) -> void`;
  `assertCommandOwnership(pi, packageRoot) -> Collision[]`; `setArbiterStatus(ctx, text) -> void`;
  `BridgePort.call(request, signal) -> Promise<BridgeResponse>`; parent extension default factory.
- Consumes: Task 2 entrypoint. Task 3 uses an injected `BridgePort` fake; Task 4 supplies the concrete
  process-backed implementation without changing the lifecycle interface.

- [ ] **Step 1: Write lifecycle tests against a fake ExtensionAPI**

```typescript
it("stays fully dormant without arbiter: enabled", async () => {
  const host = fakePi();
  installParent(host.pi, { bridge: host.bridge });
  await host.emit("session_start", { reason: "startup" }, host.ctx("bare"));
  expect(host.bridge.calls).toEqual([]);
  expect(host.injectedMessages).toEqual([]);
  expect(host.statusCalls).toEqual([]);
});

it("registers one ca alias per generated command", () => {
  const host = fakePi();
  registerAliases(host.pi, catalog);
  expect(host.commandNames()).toEqual(catalog.map((entry) => `ca-${entry.name}`));
  host.invoke("ca-feature", "add caching");
  expect(host.userMessages).toHaveLength(1);
  expect(host.userMessages[0]).toContain('<skill name="ca-feature" location="');
  expect(host.userMessages[0]).toContain("References are relative to ");
  expect(host.userMessages[0]).toMatch(/<\/skill>\n\nadd caching$/u);
  expect(host.userMessages[0]).not.toContain("/skill:ca-feature");
});

it("clears only codearbiter status at agent_settled", async () => {
  const host = fakePi();
  installParent(host.pi, deps);
  await host.emit("agent_start", {}, host.ctx("enabled"));
  await host.emit("agent_end", {}, host.ctx("enabled"));
  expect(host.lastStatus("codearbiter")).toBeDefined();
  await host.emit("agent_settled", {}, host.ctx("enabled"));
  expect(host.lastStatus("codearbiter")).toBeUndefined();
  expect(host.statusKeys()).toEqual(["codearbiter"]);
});
```

- [ ] **Step 2: Run the three test files red**

```powershell
npm --prefix plugins/ca-pi/tools exec vitest run test/activation.test.ts test/commands.test.ts test/status.test.ts
```

Expected: FAIL because the parent extension and generated command catalog do not exist.

- [ ] **Step 3: Implement activation and per-turn persona refresh**

`session_start` invalidates prior lifecycle/bridge identities, enters the activation-check blocked
generation, resolves the current cwd, and checks only `.codearbiter/CONTEXT.md` frontmatter without
Python or Git. It asks the bridge for startup state only when enabled and
`context.isProjectTrusted?.() === true`. Enabled missing/false trust performs no repository-aware
startup, leaves mutators blocked, delegates native reads through fresh untrusted settings, and emits
one fixed trust direction. Cache the generated persona/state in memory only after authorization.
`before_agent_start` appends that cached content to the current chained system prompt and refreshes
live state through the bridge; it never replaces user/system prompt content and never persists raw
prompt text.

- [ ] **Step 4: Generate and register aliases with provenance checks**

The catalog is generated from command templates and contains `{name, description, skillPath}` only.
Pi's public extension `sendUserMessage()` disables slash-command and skill expansion, so each
`/ca-*` handler resolves its generated `skillPath`, strips only frontmatter, constructs the same
native `<skill name="..." location="...">` envelope used by supported Pi versions, appends the
unchanged argument string, and sends the expanded content through the public API. User-entered
`/skill:ca-*` remains the native fallback. Pin this adapter seam against Pi 0.80.5 and 0.80.6; a
missing/unreadable/out-of-package skill fails visibly rather than sending literal slash text. After
resources load, inspect `pi.getCommands()` and require each unsuffixed alias to have extension source
provenance from the installed `ca-pi` package. A suffix, duplicate, project owner, or missing
fallback sets a visible degraded status and makes doctor unhealthy; it never silently selects a
different owner.

- [ ] **Step 5: Implement composable status and settled semantics**

Use only `ctx.ui.setStatus("codearbiter", value)`. Start/update status on governed bridge/agent work,
retain it through `agent_end`, retries, and compaction continuations, and clear only on
`agent_settled` or `session_shutdown`.

- [ ] **Step 6: Run focused tests and a real isolated RPC discovery probe**

```powershell
npm --prefix plugins/ca-pi/tools exec vitest run test/activation.test.ts test/commands.test.ts test/status.test.ts
npm --prefix plugins/ca-pi/tools run typecheck
python .github/scripts/test_pi_package.py --rpc-commands
```

Expected: bare repo is silent; enabled repo reports `host: pi`; every alias/fallback is unique; the
RPC stream includes the keyed status update; retry/compaction fixtures clear only at settled.

---

### Task 4: Canonical Python bridge and final-execution tool enforcement

**Status:** ACCEPTED
**Owns:** PI-AC-11, PI-AC-12, PI-AC-13, PI-AC-14

**Review:** Independently approved after exploit-driven fix loops covering final-argument TOCTOU,
shared-corpus redaction on every bridge channel, retry-safe fail-closed installation, exact Python 3
resolution, strict duplicate-free finite event schemas, native Pi failed-tool semantics, ordinary
immutable judgment/execution snapshots, and exact integer protocol versions. Fresh controller
verification passed 55/55 Pi tests, 18/18 three-host parity fixtures, 14/14 isolated package/RPC
tests, 12/12 descriptor tests, TypeScript typecheck, deterministic bundle generation, and the
unchanged reviewed dependency lock.

**Review ledger from Batch 1:** Add a CI-backed parity test asserting Claude and Codex descriptor
`tool_classes` equal their live `TOOL_MAP` values, prove Pi's guard consumes the descriptor directly,
and retain unknown-tool fail-closed mutation coverage.

**Files:**
- Create: `plugins/ca-pi/hooks/_host.py`
- Create: `plugins/ca-pi/hooks/pi-bridge.py`
- Modify: `plugins/ca-pi/tools/src/contracts.ts`
- Create: `plugins/ca-pi/tools/src/bridge.ts`
- Create: `plugins/ca-pi/tools/src/tool-guard.ts`
- Create: `plugins/ca-pi/tools/src/redaction.ts`
- Create: `plugins/ca-pi/tools/test/bridge.test.ts`
- Create: `plugins/ca-pi/tools/test/tool-guard.test.ts`
- Create: `.github/scripts/test_pi_parity.py`
- Modify: `plugins/ca-pi/tools/src/extension.ts`

**Interfaces:**
- Produces: `BridgeClient implements BridgePort` with
  `call(request, signal) -> Promise<BridgeResponse>`;
  `wrapBuiltins(pi, bridge) -> void`; `guardUnknownTools(pi, descriptor) -> void`.
- Canonical request: `{version: 1, event, cwd, sessionId, tool?, input?, result?}`.
- Canonical response: `{version: 1, outcome, ruleId?, message?, context?, resultPatch?, auditCode?}`
  where outcome is `allow | block | warn | notice`.
- Consumes Task 1 `tool_classes` and Task 2 host-provided built-in tool factories.

- [ ] **Step 1: Write bridge framing, failure-direction, and wrapper tests**

```typescript
it("blocks a mutating call when Python returns malformed protocol", async () => {
  const bridge = fakeBridge({ stdout: "not-json", code: 0 });
  const response = await bridge.call(toolRequest("bash", { command: "git status" }));
  expect(response).toMatchObject({ outcome: "block", ruleId: "PI-BRIDGE" });
  expect(response.message).toContain("/ca-doctor");
});

it("allows read on bridge failure and emits one redacted warning", async () => {
  const bridge = fakeBridge({ stderr: "OPENAI_API_KEY=synthetic-secret", code: 1 });
  const response = await bridge.call(toolRequest("read", { path: "README.md" }));
  expect(response.outcome).toBe("warn");
  expect(JSON.stringify(response)).not.toContain("synthetic-secret");
});

it("judges the final args inside the execution override", async () => {
  const host = fakePiWithBuiltin("bash");
  wrapBuiltins(host.pi, host.bridge);
  host.addLaterToolMutation("bash", { command: "git commit --no-verify" });
  await host.execute("bash", { command: "git status" });
  expect(host.bridge.lastRequest().input).toEqual({ command: "git commit --no-verify" });
  expect(host.builtinExecutions).toEqual([]);
});
```

- [ ] **Step 2: Run the bridge and tool tests red**

```powershell
npm --prefix plugins/ca-pi/tools exec vitest run test/bridge.test.ts test/tool-guard.test.ts
python .github/scripts/test_pi_parity.py --fixtures-only
```

Expected: FAIL because no canonical bridge, Pi host adapter, or execution wrappers exist.

- [ ] **Step 3: Implement the one-process canonical bridge**

`pi-bridge.py` validates one UTF-8 JSON object against exact allowed keys/types/byte limits, converts
it to the existing shared entry payload, and invokes exactly one shared entry inside that Python
process while capturing its stdout/stderr/exit status. Its routing table is mechanical:

```python
ENTRY_BY_EVENT = {
    ("session_start", None): "session-start.py",
    ("tool_call", "EXEC"): "pre-bash.py",
    ("tool_call", "WRITE"): "pre-write.py",
    ("tool_call", "EDIT"): "pre-edit.py",
    ("tool_call", "READ"): "pre-read.py",
    ("tool_result", "WRITE"): "post-write-edit.py",
    ("tool_result", "EDIT"): "post-write-edit.py",
}
```

No H-rule lives in the bridge. Exit 2 becomes `block`; shared stdout becomes bounded `context` or
`notice`; crashes/malformed output become a bridge error for the TypeScript failure classifier.
Audit fields are fixed codes, host, rule ID, correlation ID, and byte counts only.

- [ ] **Step 4: Implement bounded process transport and redaction-before-truncation**

Resolve Python once through an absolute-path probe, validate `pi-bridge.py` beneath the installed
package, use `spawn(executable, [script], {shell: false, cwd, env})`, write one request then close
stdin, cap each stream before accumulation, normalize control/newline characters, run the shared
secret corpus through `redaction.ts`, then truncate. Timeout/crash/protocol overflow blocks mutation
and warns for read/post/status.

- [ ] **Step 5: Wrap built-in execution instead of trusting handler order**

Create Pi's built-in `bash`, `write`, `edit`, and `read` definitions through the host-provided factory
APIs. Spread the original definition and replace `execute()` with a wrapper that sends the final
params to the bridge immediately before delegating. On `block`, return a canonical non-executed tool
result; on `allow`, call the original execute unchanged; on read warning, delegate and append the
warning. A global `tool_call` handler blocks every undeclared tool and verifies that each active
mutating built-in's `sourceInfo` still points to the installed `ca-pi` wrapper; a later tool override
therefore blocks rather than silently replacing governance. Descriptor-declared external tools may be
read-only; a mutating external tool cannot be admitted without its own final executor wrapper.

- [ ] **Step 6: Run the shared parity corpus across all three hosts**

`test_pi_parity.py` invokes real Claude/Codex Python entries and `pi-bridge.py` with equivalent
fixtures for H-01, H-03, H-05, H-09b, H-10b, H-11, H-18, H-19, H-20, dormant input, malformed input,
unknown tool, Python missing, timeout, crash, and protocol overflow. It compares outcome/rule IDs,
with documented stricter-only differences.

```powershell
npm --prefix plugins/ca-pi/tools exec vitest run test/bridge.test.ts test/tool-guard.test.ts
npm --prefix plugins/ca-pi/tools run typecheck
python .github/scripts/test_pi_parity.py
python -m py_compile plugins/ca-pi/hooks/_host.py plugins/ca-pi/hooks/pi-bridge.py
```

Expected: identical verdicts for equivalent operations; every mutating bridge failure and unknown
tool is non-executing; read/advisory failures warn without exposing raw payloads.

---

### Task 5: Notices, Git backstop, and comprehensive doctor

**Status:** ACCEPTED
**Owns:** PI-AC-15, PI-AC-16, PI-AC-28

**Review:** PI-AC-15 notices and PI-AC-16 Git backstop were independently approved after exploit-driven
fix rounds. The public Pi-native doctor collects canonical active origins/owners/wrappers, validates
descriptor-owned DECISION-0018 fingerprints for Pi 0.80.5/0.80.6, and runs a non-mutating H-03
wrapper self-test directly against the stored governed bash wrapper. That self-test does not traverse
Pi's active dispatcher because the supported Pi APIs expose no deterministic submission seam. The
supported-version local promotion reproduced the wrapper, final-argument, child, and doctor result
codes; PI-AC-28 is covered with the active-dispatch limitation retained as an explicit DEGRADED parity
row. Task 6 replaced the former child placeholder with the hardened enforcement-only child.

**Review ledger from Batch 1:** Doctor must report the canonical active CLI/package origin and state
explicitly that module-identity validation proves self-consistency with the operator-launched Pi
runtime, not publisher authenticity. Per DECISION-0018, doctor must also diagnose supported-version
drift in the native-equivalent skill expansion contract.

**Files:**
- Create: `plugins/ca-pi/tools/src/notices.ts`
- Create: `plugins/ca-pi/tools/src/doctor.ts`
- Create: `plugins/ca-pi/tools/test/notices.test.ts`
- Create: `plugins/ca-pi/tools/test/doctor.test.ts`
- Create: `.github/scripts/test_pi_doctor.py`
- Modify: `core/pysrc/doctor.py`
- Modify: `core/pysrc/_githooks.py`
- Modify/Generate: all shared Python vendored copies via `tools/sync-core.py`

**Interfaces:**
- Produces: `applyToolResultNotice(event, response) -> ToolResultPatch | undefined`;
  `diagnosePi(input) -> readonly Diagnosis[]`; `runPiWrapperSelfTest(deps) -> Promise<Diagnosis>`.
- Diagnosis has exact fields `{id, state: "healthy" | "degraded" | "unhealthy", message,
  remediation}`.

- [ ] **Step 1: Write notice de-duplication, backstop, and doctor fixture tests**

```typescript
it("adds each governed notice once", () => {
  const first = applyToolResultNotice(writeResult("src/auth.ts"), h17Notice());
  const second = applyToolResultNotice(first, h17Notice());
  expect(countText(second, "H-17")).toBe(1);
});

it.each([
  "package", "trust", "version", "python", "core", "commands", "bridge",
  "child", "ambient-marker", "module-identity", "final-arguments",
])("returns one exact remediation for broken %s", (fixture) => {
  const result = diagnosePi(brokenFixture(fixture));
  expect(result.filter((row) => row.state === "unhealthy")).toHaveLength(1);
  expect(result[0].remediation).toMatch(/^Run |^Reinstall |^Remove |^Upgrade /);
});
```

The Python integration creates an enabled temporary Git repo, runs Pi session start, and verifies the
installed `.git/hooks/pre-commit` rejects a prohibited staged operation with the expected H-ID.

- [ ] **Step 2: Run focused tests red**

```powershell
npm --prefix plugins/ca-pi/tools exec vitest run test/notices.test.ts test/doctor.test.ts
python .github/scripts/test_pi_doctor.py
```

Expected: FAIL because notice patching and Pi diagnoses are absent.

- [ ] **Step 3: Wire pre-read and post-write/edit notices through shared responses**

Map Pi read/write/edit result shapes without replacing their native details. Add generated context or
reminders in a bounded text content block carrying a stable codeArbiter marker. Before insertion,
scan existing content for that marker so parallel/retry events never duplicate it.

- [ ] **Step 4: Prove shared Git-hook installation is host-idempotent**

Exercise Claude then Pi, Pi then Codex, and Pi twice against one repo. `_githooks.py` must leave one
current shim targeting the shared enforcer, preserve custom hooksPath behavior, and keep every
existing cold-install case green. Invoke the installed hook as a subprocess; do not assert only on
file contents.

- [ ] **Step 5: Implement doctor origin/trust/collision/bridge/child/wrapper checks**

Use Pi's command provenance and extension context without granting trust. Report package origin and
version, supported Pi/Node/Python, enabled context, exact command owners, host-module identity,
bridge health, ambient recursion marker, child discovery contract, and final-executor wrapper. For
enabled missing/false trust, do not prepare/probe the bridge or run the wrapper self-test; report
Python, bridge, and final-wrapper verification as intentionally withheld with the fixed trust
remediation. After affirmative trust, the wrapper self-test submits a dry-run staging command
directly to the stored governed wrapper, requires the exact shared H-03 block, and verifies no
repository mutation. Report active-dispatch coverage as degraded until supported-version real-host
promotion/CI evidence closes PI-AC-28.

- [ ] **Step 6: Run doctor, cold-install, and hook regression suites**

```powershell
npm --prefix plugins/ca-pi/tools exec vitest run test/notices.test.ts test/doctor.test.ts
python .github/scripts/test_pi_doctor.py
python .github/scripts/test_hooks_cold_install.py
python .github/scripts/test_hook_guards.py
python -m unittest discover -s plugins/ca/hooks/tests -p "test_*.py"
```

---

### Task 6: Hardened child launch, opaque auth, and isolation contract

**Status:** ACCEPTED
**Owns:** PI-AC-17, PI-AC-20, PI-AC-29

**Files:**
- Create: `plugins/ca-pi/tools/src/child-env.ts`
- Create: `plugins/ca-pi/tools/src/runner.ts`
- Modify: `plugins/ca-pi/tools/src/child-extension.ts`
- Create: `plugins/ca-pi/tools/src/roles.ts`
- Create: `plugins/ca-pi/tools/test/child-env.test.ts`
- Create: `plugins/ca-pi/tools/test/runner-isolation.test.ts`
- Create: `plugins/ca-pi/tools/test/fixtures/pi-0.80.6-help.txt`
- Create: `.github/scripts/test_pi_child_live.py`
- Generated: `plugins/ca-pi/generated/roles.json`
- Modify: `tools/build-surface.py`

**Interfaces:**
- Produces: `buildChildEnv(input: ChildEnvInput) -> NodeJS.ProcessEnv`;
  `buildChildArgv(input: ChildLaunchInput) -> readonly string[]`;
  `runPiChild(request, signal) -> Promise<ChildResult>`; enforcement-only child factory.
- `ChildLaunchInput` includes exact `nodePath`, `piCliPath`, `provider`, `model`, `tools`, `cwd`,
  `childExtensionPath`, `skillPaths`, and `charterPath`; task text is not a field in argv/env builders.

- [ ] **Step 1: Write environment and argv exclusion tests**

```typescript
it("starts from a minimal provider-specific environment", () => {
  const parent = secretBearingParentEnv();
  const child = buildChildEnv({ platform: "win32", parent, provider: "openai" });
  expect(child.OPENAI_API_KEY).toBe(parent.OPENAI_API_KEY);
  expect(child.ANTHROPIC_API_KEY).toBeUndefined();
  expect(child.FARM_API_KEY).toBeUndefined();
  expect(child.CLAUDE_CODE_OAUTH_TOKEN).toBeUndefined();
  expect(child.CODEARBITER_SUBAGENT).toBe("1");
  expect(child.PI_OFFLINE).toBe("1");
  expect(child.PI_TELEMETRY).toBe("0");
});

it("puts no task, prompt, or secret in argv", () => {
  const argv = buildChildArgv(childLaunchFixture());
  expect(argv).toEqual([
    absolutePiCli, "--mode", "rpc", "--no-approve", "--no-extensions",
    "--no-skills", "--no-prompt-templates", "--no-themes", "--no-context-files",
    "--no-session", "--offline", "--provider", "openai", "--model", "gpt-test",
    "--tools", "read,bash,edit,write", "-e", absoluteChildExtension,
    "--append-system-prompt", absoluteCharter, "--skill", absoluteSkillFile,
  ]);
  expect(argv.join(" ")).not.toContain("task-secret-sentinel");
});
```

- [ ] **Step 2: Run child isolation tests red**

```powershell
npm --prefix plugins/ca-pi/tools exec vitest run test/child-env.test.ts test/runner-isolation.test.ts
python .github/scripts/test_pi_child_live.py --fixture-only
```

Expected: FAIL because no minimal environment, exact argv, runner, or child extension exists.

- [ ] **Step 3: Implement explicit OS and provider allowlists**

OS baselines are explicit per platform. Provider secret/config names are parsed into a reviewed map
from the pinned help fixture and checked for drift against 0.80.5/0.80.6 help output. After every
merge, delete `FARM_API_KEY` and `CLAUDE_CODE_OAUTH_TOKEN` again so a caller cannot reintroduce them.
Keep `HOME`/`USERPROFILE` and Pi config-location variables so Pi itself can resolve its opaque auth;
never open or stat the auth file from `ca-pi`.

- [ ] **Step 4: Implement exact node+CLI launch and stdin-only RPC**

Launch `[process.execPath, absolute dist/cli.js, ...argv]`, never a shell/shim. Validate both paths as
absolute real files, send bounded RPC `prompt` content over stdin, and allow only strict JSONL record
types/keys. Use a random correlation ID unrelated to task content. Never echo malformed input,
provider errors, or raw JSONL in diagnostics.

- [ ] **Step 5: Build the enforcement-only child adapter and role catalog**

Generate role names, charter paths, mapped Pi tools, and author/reviewer classification from canonical
agent frontmatter. The child adapter installs Task 4 wrappers and notices only. It registers no
aliases, dispatch tool, farm tool, or recursive orchestration. An ambient marker in a parent launch
is unhealthy; a validated child launch requires both the marker and a one-use parent-created nonce
correlated through the private stdin handshake, never environment. The nonce is defense-in-depth
against accidental ambient-marker reuse, not a same-user security proof or OS sandbox boundary.

- [ ] **Step 6: Prove fresh PID/context and no-inline promotion**

Run two children against the deterministic provider. Assert distinct PIDs, empty session files,
disabled saved/default trust, no project/global resource discovery, correct exact tools, active H-03
enforcement, and no recursive dispatch registration. If child launch fails, an inline result may be
returned only with terminal state `degraded`; doctor and promotion remain unhealthy.

```powershell
npm --prefix plugins/ca-pi/tools exec vitest run test/child-env.test.ts test/runner-isolation.test.ts
npm --prefix plugins/ca-pi/tools run typecheck
python .github/scripts/test_pi_child_live.py
```

---

### Task 7: Single, chained, and parallel orchestration with process-tree cleanup

**Status:** ACCEPTED
**Owns:** PI-AC-18, PI-AC-19

**Files:**
- Create: `plugins/ca-pi/tools/src/dispatch.ts`
- Create: `plugins/ca-pi/tools/src/process-tree.ts`
- Create: `plugins/ca-pi/tools/test/dispatch.test.ts`
- Create: `plugins/ca-pi/tools/test/process-tree.test.ts`
- Create: `.github/scripts/test_pi_process_tree.py`
- Modify: `plugins/ca-pi/tools/src/extension.ts`

**Interfaces:**
- Produces registered tool `codearbiter_dispatch` and
  `dispatch(request: DispatchRequest, signal: AbortSignal) -> Promise<DispatchResult>`.
- Terminal states are exactly `accepted | changes_requested | blocked | cancelled | timeout |
  depth_exceeded | oversized | protocol_error | crashed | degraded`.
- Modes are exactly `single | chain | parallel`; concurrency/depth/output/time limits come from one
  immutable policy object.

- [ ] **Step 1: Write orchestration state-table tests**

```typescript
it.each([
  ["single", ["security-reviewer"]],
  ["chain", ["backend-author", "coverage-auditor"]],
  ["parallel", ["security-reviewer", "auth-crypto-reviewer"]],
])("dispatches %s with deterministic role ordering", async (mode, roles) => {
  const result = await dispatch({ ...baseRequest, mode, roles }, neverAbort.signal);
  expect(result.children.map((child) => child.role)).toEqual(roles);
});

it.each(["cancelled", "timeout", "depth_exceeded", "oversized", "protocol_error", "crashed"])(
  "returns terminal state %s without an unhandled rejection",
  async (state) => expect(await runFailureFixture(state)).toMatchObject({ state }),
);
```

- [ ] **Step 2: Run dispatch and process tests red**

```powershell
npm --prefix plugins/ca-pi/tools exec vitest run test/dispatch.test.ts test/process-tree.test.ts
python .github/scripts/test_pi_process_tree.py --fixture-only
```

- [ ] **Step 3: Implement bounded mode semantics**

Single runs one role. Chain passes only the prior child's bounded structured result to the next role,
never raw JSONL. Parallel uses a FIFO semaphore, preserves requested result ordering, and aborts all
siblings on parent cancellation. Validate role names before spawning; reject duplicate authors,
depth above policy, zero/negative limits, and aggregate output above the cap.

- [ ] **Step 4: Implement cross-platform process-tree termination**

POSIX launches a detached process group and signals group `SIGTERM`, then `SIGKILL` after the bounded
grace. Windows launches a distinct process group, uses `taskkill /PID <pid> /T` without a shell, waits,
and verifies exit. Cleanup is idempotent and runs for timeout, cancellation, protocol overflow,
startup failure, and parent shutdown.

- [ ] **Step 5: Live-test a child that spawns a grandchild**

The fixture reports parent/child/grandchild PIDs over bounded JSON before waiting. Cancel and timeout
variants must prove all PIDs are gone on Windows, macOS, and Linux; absence is checked by OS-native
process APIs, not elapsed time alone.

```powershell
npm --prefix plugins/ca-pi/tools exec vitest run test/dispatch.test.ts test/process-tree.test.ts
python .github/scripts/test_pi_process_tree.py
```

---

### Task 8: Host-neutral prune policy and Pi-native compaction

**Status:** ACCEPTED
**Owns:** PI-AC-23, PI-AC-24, PI-AC-25

**Files:**
- Create: `core/pysrc/_prunepolicy.py`
- Create: `plugins/ca-pi/tools/src/compaction.ts`
- Create: `plugins/ca-pi/tools/test/compaction.test.ts`
- Create: `.github/scripts/test_prune_policy_parity.py`
- Modify: `core/pysrc/_prunelib.py`
- Modify: `core/pysrc/prune-transcript.py`
- Modify: `plugins/ca-pi/hooks/pi-bridge.py`
- Modify: `plugins/ca-pi/tools/src/contracts.ts`
- Modify: `plugins/ca-pi/tools/src/bridge.ts`
- Modify: `plugins/ca-pi/tools/src/extension.ts`
- Modify/Generate: `core/surface/commands/prune.md` and all host renders

**Interfaces:**
- Produces Python `SemanticEntry`, `PrunePolicy`, `PrunePlan`, and
  `plan_prune(entries, policy) -> PrunePlan`.
- Produces TypeScript `handleBeforeCompact(event, ctx, runner) -> Promise<CompactionResult | void>`.
- Consumes Task 7 hardened runner for a no-tool, exact-provider/model summarization child.

- [ ] **Step 1: Write equivalent Claude/Pi semantic fixture tests**

```python
def test_codecs_choose_identical_policy_outcomes():
    claude_entries = claude_codec(load_fixture("prune-equivalent-claude.jsonl"))
    pi_entries = pi_codec(load_fixture("prune-equivalent-pi.json"))
    left = plan_prune(claude_entries, STANDARD_POLICY)
    right = plan_prune(pi_entries, STANDARD_POLICY)
    assert left.protected_ids == right.protected_ids
    assert left.actions == right.actions
    assert left.metrics == right.metrics
    assert left.audit_codes == right.audit_codes
```

`compaction.test.ts` asserts no active session file write API is called, the returned
`firstKeptEntryId` is policy-selected, summaries are bounded/redacted, and a second identical plan is
idempotent.

- [ ] **Step 2: Run prune/compaction tests red and existing prune tests green**

```powershell
python .github/scripts/test_prune_policy_parity.py
python .github/scripts/test_prune_nudge.py
python -m unittest plugins.ca.hooks.tests.test_prune_cli plugins.ca.hooks.tests.test_prune_single_parse
npm --prefix plugins/ca-pi/tools exec vitest run test/compaction.test.ts
```

- [ ] **Step 3: Extract selection policy without changing Claude serialization**

Move protected-tail, tier ordering, marker/idempotency decisions, dry metrics, and audit outcome
selection into `_prunepolicy.py`. Keep Claude JSONL parse/mutation/write/backup logic in `_prunelib.py`.
Run existing byte, shrink-only, live-file, and self-heal tests unchanged as the refactor proof.

- [ ] **Step 4: Implement Pi semantic codec and custom compaction result**

Convert Pi session entries into `SemanticEntry` without writing the session. Use the policy-selected
kept boundary. Generate the native summary through a no-tools, no-session RPC child using the current
exact provider/model, the generated compaction charter, and stdin-only bounded conversation content;
Pi remains the credential resolver. Return `{summary, firstKeptEntryId, tokensBefore}` and record only
redacted metrics/audit codes after `session_compact` confirms success.

- [ ] **Step 5: Render full prune command parity for Pi**

Pi's `/ca-prune` alias and `/skill:ca-prune` expose `status`, `dry`, `run <inactive-copy>`, `audit`,
`on`, and `off`. Active sessions may use event-driven native compaction only; manual `run` rejects an
active target and retains existing opt-in/inactive-copy rules.

- [ ] **Step 6: Run all prune gates**

```powershell
python .github/scripts/test_prune_policy_parity.py
python .github/scripts/test_prune_nudge.py
python -m unittest discover -s plugins/ca/hooks/tests -p "test_prune*.py"
npm --prefix plugins/ca-pi/tools exec vitest run test/compaction.test.ts
python tools/sync-core.py --check
python tools/build-surface.py --check
```

---

### Task 9: Farm preview routing and shared-store attribution

**Status:** ACCEPTED
**Owns:** PI-AC-26, PI-AC-27

**Files:**
- Create: `plugins/ca-pi/tools/src/farm.ts`
- Create: `plugins/ca-pi/tools/test/farm.test.ts`
- Create: `.github/scripts/test_pi_shared_store.py`
- Modify: `core/surface/includes/farm.md`
- Modify: `core/surface/skills/subagent-driven-development/SKILL.md`
- Modify: `docs/parity.md`

**Interfaces:**
- Produces: `runFarmPreview(input, signal) -> Promise<FarmResult>` that invokes the existing built
  `plugins/ca/tools/farm.js` contract by absolute path for Git distribution.
- Consumes Task 7 dispatch as the Pi-native fallback/preview integration seam; no second farm engine.

- [ ] **Step 1: Write farm routing and three-pair store tests**

```typescript
it("routes preview farm to the one shared built backend", async () => {
  const spawnCapture = fakeSpawn();
  const result = await runFarmPreview(fixture, neverAbort.signal, { spawn: spawnCapture });
  expect(result.backend).toBe(absoluteRepoPath("plugins/ca/tools/farm.js"));
  expect(result.label).toBe("preview");
  expect(spawnCapture.env.FARM_API_KEY).toBe("dummy-farm-key");
  expect(spawnCapture.env.OPENAI_API_KEY).toBeUndefined();
});
```

`test_pi_shared_store.py` concurrently runs Claude/Pi, Codex/Pi, and Pi/Pi audit writers against the
same fixture and requires parseable append-only lines containing `HOST: pi`, with no guarantee
stronger than ADR-0012's existing same-host baseline.

- [ ] **Step 2: Run farm/store tests red**

```powershell
npm --prefix plugins/ca-pi/tools exec vitest run test/farm.test.ts
python .github/scripts/test_pi_shared_store.py
```

- [ ] **Step 3: Reuse the built farm contract without copying it**

Resolve `plugins/ca/tools/farm.js` inside the Git-installed checkout, validate containment and build
freshness, and invoke it with argv arrays and its existing plan schema. Do not pass ordinary child
provider credentials to farm and do not pass `FARM_API_KEY` to ordinary Pi children. Missing backend
is a visible preview degradation, never a silent alternate implementation.

- [ ] **Step 4: Preserve preview labeling and log the future embedded spike**

Render Pi-native instructions that select the same plan contract and retain `[CONFIRM-05]` as the
stable-promotion bar. Add a non-shipping parity-ledger note for a future spike: evaluate whether the
hardened Pi child runner can become an embedded farm worker while preserving the shared plan/result
contract and avoiding a second dispatcher.

- [ ] **Step 5: Run farm and store regression gates**

```powershell
npm --prefix plugins/ca-pi/tools exec vitest run test/farm.test.ts
python .github/scripts/test_pi_shared_store.py
npm --prefix plugins/ca/tools test
npm --prefix plugins/ca/tools run build
python .github/scripts/test_dual_host_store.py
```

---

### Task 10: Security promotion gates and static analysis

**Status:** ACCEPTED
**Owns:** PI-AC-30, PI-AC-36

**Files:**
- Create: `plugins/ca-pi/tools/test/security.test.ts`
- Create: `plugins/ca-pi/tools/test/final-arguments.test.ts`
- Create: `.github/scripts/test_pi_security.py`
- Create: `.github/workflows/codeql.yml`
- Modify: `.github/workflows/ci.yml`
- Modify: `.codearbiter/security-controls.md` only if implementation evidence requires a narrower
  clarification; any material boundary change routes through `$ca-conflict`/`$ca-adr` first.

**Interfaces:**
- Consumes Tasks 3-9 as a black-box installed package.
- Produces machine-readable security result codes consumed by Task 13 promotion evidence; no raw
  prompt, environment value, provider body, tool result, or stderr is retained.

- [ ] **Step 1: Write adversarial tests for every ADR-0014 constraint**

```typescript
it("blocks a later extension's mutation at final execution", async () => {
  const session = await liveFixture([caPiExtension, laterMutationExtension]);
  const result = await session.call("bash", { command: "git status" });
  expect(result.ruleId).toBe("H-20");
  expect(session.executedCommands).toEqual([]);
});

it("never grants project trust", async () => {
  const decision = await emitProjectTrust(caPiExtension, untrustedProjectFixture());
  expect(decision).toEqual({ trusted: "undecided" });
});

it("blocks an undeclared mutating extension tool", async () => {
  const result = await callExtensionTool("project_write_anywhere", { path: "README.md" });
  expect(result).toMatchObject({ blocked: true, ruleId: "PI-UNKNOWN-TOOL" });
});

it("blocks when a later extension replaces a governed built-in", async () => {
  const session = await liveFixture([caPiExtension, laterBashOverride]);
  const result = await session.call("bash", { command: "git status" });
  expect(result).toMatchObject({ blocked: true, ruleId: "PI-TOOL-OWNER" });
  expect(session.executedCommands).toEqual([]);
});
```

Add fixtures for prototype keys, escaping paths, oversized JSON/JSONL, control/newline injection,
command/skill collision, ambient marker, saved parent trust, `defaultProjectTrust=always`, provider
fallback, environment reintroduction, real-home path access, compaction content, and farm-key bleed.

- [ ] **Step 2: Run security tests red**

```powershell
npm --prefix plugins/ca-pi/tools exec vitest run test/security.test.ts test/final-arguments.test.ts
python .github/scripts/test_pi_security.py
```

Expected: at least final-executor ordering, trust, and static-analysis coverage fail before the gates
are wired.

- [ ] **Step 3: Close only implementation gaps; do not relax ADR-0014**

Fix the adapter/runner/descriptors until every adversarial fixture is non-executing or safely
redacted. If a later handler can still alter final executed arguments, if Pi auth must be interpreted
by `ca-pi`, or if a mutating external tool must be allowed without a wrapper, stop the feature and
reopen ADR-0013. No override can promote that result as parity.

- [ ] **Step 4: Add TypeScript CodeQL coverage and preserve existing workflow pin policy**

Configure JavaScript/TypeScript analysis for `plugins/ca-pi/tools/src/**` and the checked-in built
extensions, with generated/vendor exclusions limited to shared Python copies and `node_modules`.
Pin every action to a reviewed commit SHA. CI fails on unresolved high-severity results; lower findings
remain visible and route through the normal review/triage policy.

- [ ] **Step 5: Run the full security evidence set**

```powershell
npm --prefix plugins/ca-pi/tools exec vitest run test/security.test.ts test/final-arguments.test.ts
python .github/scripts/test_pi_security.py
python .github/scripts/test_hooklib.py
python .github/scripts/test_hook_guards.py
git diff -- .codearbiter/security-controls.md .github/workflows plugins/ca-pi
```

Expected: threat gate `PROCEED-WITH-CONSTRAINTS`, no HIGH/CRITICAL static result, no real auth/home
touch, and the live two-extension final-argument proof passes.

---

### Task 11: Relative performance and cross-platform contract

**Status:** ACCEPTED
**Owns:** PI-AC-31, PI-AC-32

**Files:**
- Create: `.github/scripts/pi_benchmark.py`
- Create: `.github/scripts/test_pi_benchmark.py`
- Create: `.github/scripts/test_pi_platform_contract.py`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Produces benchmark JSON `{platform, host, sampleCount, startupMs, coreP50Ms, adapterP50Ms,
  adapterP95Ms}` with no payload content.
- Pass formula: `pi_p95 <= slower_existing_p95 + max(slower_existing_p95 * 0.25, 10.0)`.
- Cross-platform runner accepts `--pi-version 0.80.5|0.80.6|latest` and marks only `latest` nonblocking.

- [ ] **Step 1: Write benchmark math and deterministic platform tests**

```python
def test_relative_limit_uses_slower_host_plus_larger_margin():
    assert promotion_limit(20.0, 30.0) == 40.0
    assert promotion_limit(80.0, 60.0) == 100.0

def test_pi_p95_must_fit_relative_limit():
    assert benchmark_passes(pi_p95=39.9, claude_p95=20.0, codex_p95=30.0)
    assert not benchmark_passes(pi_p95=40.1, claude_p95=20.0, codex_p95=30.0)
```

Platform fixtures exercise spaces/non-ASCII paths, LF/CRLF input, Windows/POSIX executable
resolution, UTF-8 JSONL, cancellation, process trees, generated paths, and second-run idempotency.

- [ ] **Step 2: Run the new benchmark/platform tests red**

```powershell
python .github/scripts/test_pi_benchmark.py
python .github/scripts/test_pi_platform_contract.py --fixtures-only
```

- [ ] **Step 3: Implement 100-event warm measurements with separated timing**

Measure the same canonical read/exec/write fixture corpus for Claude, Codex, and Pi. Record cold
startup once, shared Python core time separately, and adapter-only p50/p95 from 100 warm events after
five warmups. Use `time.perf_counter_ns()`, deterministic local IO, no provider request, and a
temporary enabled repo per sample group.

- [ ] **Step 4: Add Windows/macOS/Linux CI matrices**

Use Python 3 and Node 22.19; install exact external Pi versions with `npm install -g --ignore-scripts`
only in live-host jobs. Deterministic adapter tests do not require network or real auth. Run package
discovery, paths, encoding, bridge, tool enforcement, subagent cancellation, process cleanup, prune,
and benchmark on every OS. A macOS live credentialed run is required only if the matrix differs from
Windows/Linux behavior.

- [ ] **Step 5: Run local benchmark and platform checks**

```powershell
python .github/scripts/test_pi_benchmark.py
python .github/scripts/pi_benchmark.py --samples 100
python .github/scripts/test_pi_platform_contract.py --pi-version 0.80.6
```

Expected: Pi satisfies the relative p95 threshold; measurements name adapter/core/startup separately;
the local OS contract is green and CI owns the other OS evidence.

---

### Task 12: Project vocabulary, install docs, parity ledger, and release documentation

**Status:** ACCEPTED
**Owns:** PI-AC-34

**Review ledger from Batch 1:** Document that module-identity validation proves self-consistency with
the operator-launched Pi runtime, not publisher authenticity, alongside the canonical active
CLI/package-origin diagnostic.

**Files:**
- Create: `docs/pi-parity-testing.md`
- Create: `core/surface/includes/pi-host-notes.md`
- Create: `.github/scripts/test_public_pi_docs.py`
- Modify: `.codearbiter/CONTEXT.md`
- Modify: `.codearbiter/tech-stack.md`
- Modify: `.codearbiter/coding-standards.md`
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/hooks.md`
- Modify: `docs/parity.md`
- Modify: `CHANGELOG.md`
- Modify: `plugins/ca-pi/CHANGELOG.md`
- Modify: `.github/scripts/check-plugin-refs.py`
- Modify: `.github/scripts/check_license_consistency.py`

**Interfaces:**
- Produces user commands `pi install git:<owner>/<repo>@ca-pi-v<version>`, `pi list`, `pi config`,
  `/ca-init`, `/ca-doctor`, and `/skill:ca-init` with evidence-backed version/platform limits.
- Documents Git distribution only; npm is explicitly future work, not an available install path.

- [ ] **Step 1: Write public-doc structural tests**

```python
def test_public_surfaces_name_all_three_governance_hosts():
    readme = read("README.md")
    for name in ("Claude Code", "Codex CLI", "Pi"):
        assert name in readme

def test_pi_install_claims_are_pinned_and_not_npm():
    text = read("docs/pi-parity-testing.md")
    assert "@ca-pi-v" in text
    assert "Pi 0.80.5" in text
    assert "Pi 0.80.6" in text
    assert "npm publish" not in text
```

Also assert command counts/catalog links match generated output, every Pi exception has a status and
evidence pointer, `--farm` remains preview, and the future embedded-farm item is labeled a spike.

- [ ] **Step 2: Run doc/reference tests red**

```powershell
python .github/scripts/test_public_pi_docs.py
python .github/scripts/check-plugin-refs.py ca-pi
```

- [ ] **Step 3: Update project vocabulary and technical conventions**

Describe four sibling plugins (`ca`, `ca-codex`, `ca-pi`, `ca-sandbox`) while keeping three
governance hosts generated from one core. Add Pi TypeScript commands, Node floor, exact build/test
commands, external-host dependency rule, Git package layout, trust boundary, status/compaction/tool
mapping, and independent tag/version rules to the canonical docs.

- [ ] **Step 4: Write the install/live-test runbook and three-host parity ledger**

The runbook starts with isolated homes/dummy local providers, then a local opt-in credentialed pass
whose artifact contains only result codes/timings. Cover package origin, project trust, activation,
aliases, final mutation block, subagents, cancellation, status, compaction, farm preview, uninstall,
and shared-state continuity. Convert `docs/parity.md` from a two-host comparison into a matrix with
Claude/Codex/Pi evidence and explicit exceptions.

- [ ] **Step 5: Record the Git-only release shape and future spikes**

Document `ca-pi-v*` tags, synchronized nested/root versions, and no npm release today. Record two
future spikes without making them current dependencies: npm packaging, and a Pi-native embedded farm
worker built on the hardened child runner while retaining the shared farm contract.

- [ ] **Step 6: Run prose and generation checks**

```powershell
python tools/build-surface.py
python tools/build-host-packages.py
python .github/scripts/test_public_pi_docs.py
python .github/scripts/check-plugin-refs.py ca
python .github/scripts/check-plugin-refs.py ca-codex
python .github/scripts/check-plugin-refs.py ca-pi
python .github/scripts/check_license_consistency.py .
python tools/build-surface.py --check
python tools/build-host-packages.py --check
```

---

### Task 13: Live supported-version promotion evidence

**Status:** IN_PROGRESS
**Owns:** PI-AC-35

**Review ledger from Batch 1:** Promotion evidence must include every committed Windows/macOS/Linux
x Pi 0.80.5/0.80.6 matrix cell plus the separately reported latest canary; the supported six-cell
matrix is required and the canary remains nonblocking. Invoke representative `/ca-*` aliases in the
real loop and prove their expanded skill bodies execute rather than reaching the model as slash text.

**Files:**
- Create: `docs/reports/pi-support/promotion.json`
- Create: `docs/reports/pi-support/promotion.md`
- Modify: `docs/parity.md` with links to the completed evidence only after runs pass.

**Interfaces:**
- Consumes Task 12 runbook and Tasks 1-11 test/live harnesses.
- Evidence JSON permits only version, platform, architecture, result code, boolean pass, timing
  summary, and redacted diagnostic code. It forbids task text, prompts, repo content, paths beneath a
  user home, environment values, provider response bodies, and raw JSONL/stderr.

- [ ] **Step 1: Run trusted Windows interactive evidence on Pi 0.80.5 and 0.80.6**

Use a disposable enabled repo and the exact Git checkout. Verify package discovery/origin, trust UX,
persona, every alias catalog entry, H-03/H-05/H-20 final mutation blocks, read/write notices, keyed
status, single/chained/parallel children, cancel/timeout cleanup, prune status/dry/native compaction,
shared-state attribution, and farm preview. The harness must perform no filesystem operation against
the operator's real auth path; Pi may resolve or refresh its own host state, and no path/value/hash
from that state enters the evidence.

- [ ] **Step 2: Run Linux non-interactive evidence on both supported versions**

Use isolated `PI_CODING_AGENT_DIR`, deterministic local provider, `--no-approve`, and the same package
commit. Exercise activation, command discovery, final tool wrappers, child runner, process tree,
compaction, doctor wrapper self-test, and independent active-dispatch evidence. Compare result codes
with Windows; require macOS live execution if
any matrix-only difference remains.

- [ ] **Step 3: Run latest canary without promoting it**

Install npm `latest` externally with `--ignore-scripts`, record version and pass/fail separately, and
leave minimum/last-verified unchanged. A canary failure opens a compatibility task but does not falsify
the 0.80.5/0.80.6 supported matrix.

- [ ] **Step 4: Write sanitized evidence and independently verify it**

Generate `promotion.json` from result codes, then render `promotion.md`. Run the shared secret corpus
and home/path scan over both. A reviewer must reproduce at least the doctor/final-argument/child
result codes from the commands in `docs/pi-parity-testing.md` before marking Task 13 accepted.

```powershell
python .github/scripts/test_pi_security.py --evidence docs/reports/pi-support/promotion.json
python .github/scripts/test_public_pi_docs.py
git diff --check -- docs/reports/pi-support docs/parity.md
```

---

### Task 14: Full repository gate, parity closure, and governed handoff

**Status:** IN_PROGRESS
**Owns:** PI-AC-37, PI-AC-38

**Review ledger from Tasks 1-2:** Derive package-contract version expectations from the nested
manifest, retaining an initial-version literal only in a scoped first-introduction test. Close the
legacy Claude/Codex-only LF-loop note with an explicit Pi assertion. Require the hosted six-cell
supported-version matrix and Task 13 live evidence before final parity closure. The final verifier
must bind DECISION-0018's expansion envelope to both supported Pi versions.

**Files:**
- Create: `.github/scripts/verify_pi_support.py`
- Create: `.github/scripts/test_verify_pi_support.py`
- Modify: `.codearbiter/plans/pi-support.md` task and obligation statuses only as evidence clears.
- Modify: `.codearbiter/specs/pi-support-review.md` never; it remains external review input.

**Interfaces:**
- Produces one read-only verifier that runs every canonical repo/Pi command, checks generated trees,
  validates all 38 obligation-to-test bindings, and returns nonzero on any missing/failed/degraded
  non-exception row.
- No verifier writes markers, versions, changelogs, tags, branches, or evidence.

- [ ] **Step 1: Write verifier self-tests**

```python
def test_verifier_rejects_one_missing_obligation(tmp_repo):
    remove_binding(tmp_repo, "PI-AC-29")
    result = run_verifier(tmp_repo, fixture_mode=True)
    assert result.returncode == 1
    assert "PI-AC-29" in result.stdout

def test_verifier_rejects_partial_or_dirty_generation(tmp_repo):
    mutate(tmp_repo / "plugins/ca-pi/skills/ca-feature/SKILL.md")
    result = run_verifier(tmp_repo, fixture_mode=True)
    assert result.returncode == 1
    assert "generated surface" in result.stdout
```

- [ ] **Step 2: Run verifier tests red**

```powershell
python .github/scripts/test_verify_pi_support.py
```

- [ ] **Step 3: Implement the read-only aggregate verifier**

The verifier reads commands from `.codearbiter/tech-stack.md` plus its fixed Pi groups, streams each
exit/result without shell composition, and checks: branch exactly `feat/pi-support`; all 38 plan
obligations `COVERED`; Tasks 1-14 `ACCEPTED`; no unresolved non-host-impossible parity row; sanitized
promotion evidence; clean second generation; no Pi runtime tree; no forbidden policy duplication;
and no unexpected tracked/untracked files inside generated/package trees.

- [ ] **Step 4: Run every existing and new required suite**

```powershell
python .github/scripts/verify_pi_support.py
python .github/scripts/test_hook_guards.py
python .github/scripts/test_hooks_cold_install.py
python .github/scripts/test_preview_lib.py
python .github/scripts/test_ux_conversion.py
python .github/scripts/test_prune_nudge.py
python .github/scripts/test_migration_backstop.py
python .github/scripts/test_metrics_lib.py
python .github/scripts/test_taskboardlib.py
python .github/scripts/test_taskwriter.py
python .github/scripts/test_release_lib.py
python .github/scripts/test_board_sync.py
python .github/scripts/test_provenancelib.py
python .github/scripts/test_provenance_wiring.py
python .github/scripts/test_readinjectlib.py
python .github/scripts/test_pre_read.py
python .github/scripts/test_hooklib.py
python -m unittest discover -s plugins/ca/hooks/tests -p "test_*.py"
npm --prefix plugins/ca/tools ci --ignore-scripts
npm --prefix plugins/ca/tools run typecheck
npm --prefix plugins/ca/tools test
npm --prefix plugins/ca/tools run build
npm --prefix plugins/ca-pi/tools ci --ignore-scripts
npm --prefix plugins/ca-pi/tools run typecheck
npm --prefix plugins/ca-pi/tools test
npm --prefix plugins/ca-pi/tools run build
python tools/sync-core.py --check
python tools/build-surface.py --check
python tools/build-host-packages.py --check
python .github/scripts/check-plugin-refs.py ca
python .github/scripts/check-plugin-refs.py ca-codex
python .github/scripts/check-plugin-refs.py ca-pi
python .github/scripts/check_license_consistency.py .
git diff --check
```

Expected: every command exits 0; rebuilding `farm.js` and both Pi extensions leaves their checked-in
bytes unchanged.

- [ ] **Step 5: Verify CI and perform the final governed review**

Push only through the later PR path, require every Windows/macOS/Linux, security, generated-surface,
version, prose, and aggregate job green, then route the complete diff through `$ca-review`. Clear all
BLOCK findings and rerun affected suites. Preserve the user's unrelated dirty files and verify no
milestone was merged, tagged, or published.

- [ ] **Step 6: Exit through the sanctioned commit/PR route**

After all task cells are `ACCEPTED` and every obligation is `COVERED`, run `$ca-commit`, then `$ca-pr`.
Do not tag or publish `ca-pi`; release remains a later explicitly authorized action.

---

## Self-review checklist

- [ ] Every spec section maps to at least one task.
- [ ] PI-AC-01 through PI-AC-38 appear exactly once in the obligation ledger and once in an owning
  task's `Owns` row.
- [ ] Every code-producing task begins with a failing observable test and names the expected failure.
- [ ] Interfaces, terminal states, version floors, command spellings, environment rules, and paths are
  consistent across tasks.
- [ ] No placeholder language, unresolved Pi-specific confirmation marker, partial-release path, npm
  publication step, duplicate Pi runtime, real credential fixture, or second governance
  implementation appears. `[CONFIRM-05]` remains ledgered only for future farm stable promotion.
- [ ] The future embedded-farm idea is recorded only as a spike; current farm parity reuses the one
  shared backend contract.

## Approval gate

Approved 2026-07-13 by SUaDtL@users.noreply.github.com. TDD Phase 1 cleared because the ledger is a
one-to-one rendering of the already-approved spec's 38 obligations. Task 1 begins by making
PI-AC-01 through PI-AC-04 red.
