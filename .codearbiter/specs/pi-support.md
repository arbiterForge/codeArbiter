# Pi Harness Support - `ca-pi` Full-Parity Shared-Core Adapter

**Slug:** `pi-support`
**Lane:** `feature`
**Status:** APPROVED - 2026-07-13 by `SUaDtL@users.noreply.github.com`
**Date:** 2026-07-13
**Branch:** `feat/pi-support`
**Decisions:** ADR-0013, ADR-0014
**Governs:** `core/**`, `tools/sync-core.py`, `tools/build-surface.py`, `plugins/ca-pi/**`, root Pi package metadata, `docs/parity.md`, `.github/workflows/**`

## Problem

codeArbiter's governance kernel supports Claude Code and Codex CLI but not the Pi coding-agent
harness. A handwritten Pi port would create a third copy of gates, skills, reviewer behavior, and
audit rules, then repeat that maintenance cost for every later host.

Pi support must therefore remain an extension of the existing arbiter core. `core/` stays
authoritative; `ca-pi` is a generated sibling payload plus a thin adapter. Done means the maximum
behavior Pi can enforce, evidence-backed exceptions only, no separately maintained governance
module, a fully green repository, and live Pi promotion evidence. All work remains on
`feat/pi-support`; internal milestones do not ship, merge, or release independently.

## M0 host preflight - completed 2026-07-13

The design below is based on the installed and source-matched
`@earendil-works/pi-coding-agent@0.80.6`, not API inference.

- Dependency review cleared an exact, external, `--ignore-scripts` Pi host install. Pi is not cleared
  for bundling under `plugins/**`: its shrinkwrap includes `tslib@2.8.1` under a `0BSD` license whose
  codeArbiter approval is currently scoped to `site/` only.
- `pi@0.80.6` is installed globally on the Windows verification host under Node `24.16.0`; Pi
  requires Node `>=22.19.0`.
- A real isolated RPC process discovered and invoked a registered `/ca-probe` command and emitted
  `setStatus` through Pi's extension UI protocol.
- A deterministic local provider exercised Pi's real agent loop without network/model spend:
  `tool_call` argument mutation reached tool execution, `tool_result` middleware replaced the result
  seen by the next turn, and a blocked tool never executed while its reason returned to the agent.
- A fresh child Pi PID emitted structured JSON with `CODEARBITER_SUBAGENT=1`; the parent remained
  unmarked. A second active child terminated with `SIGTERM`, proving the process-isolation and
  cancellation primitives required by the runner.
- Pi source and installed docs expose `session_start`, `before_agent_start`, blocking `tool_call`,
  mutable `tool_result`, `session_before_compact`, `session_compact`, `agent_settled`, command/tool
  registration, RPC/JSON modes, project trust, `ctx.signal`, and composable `setStatus`.
- Five cold persistent-RPC runs of 100 `get_state` requests measured 860.00-965.28 ms total; median
  was 885.37 ms, or 8.854 ms/request amortized including process startup. This is host transport
  evidence, not the promotion performance threshold.
- `agent_settled`, required for reliable terminal status, first appears in the published `0.80.5`
  capability line. The source-derived minimum is therefore Pi `0.80.5`; the current live-verified
  maximum is `0.80.6`.

All disposable probes were removed. M0 added no feature code or repository dependency.

## Scope

### In scope

- Add independently versioned sibling plugin `plugins/ca-pi/`, named `ca-pi`, under ADR-0013.
- Generalize generation from a binary Claude/Codex switch to an N-host descriptor model while
  preserving existing generated behavior.
- Generate Pi skills, command aliases, agent charters, Python core, farm assets, and public catalogs
  from the same sources as Claude and Codex.
- Add thin Pi adapters for lifecycle events, canonical payloads, Python process execution, structured
  results, child Pi processes, compaction entries, UI status, activation, diagnostics, and packaging.
- Require Python 3 and invoke the stdlib-only Python core through a replaceable bridge.
- Expose generated `/ca-*` commands with Pi-native `/skill:ca-*` fallbacks.
- Provide fresh-process single, chained, and parallel author/reviewer dispatch with bounded
  concurrency, depth, timeout, cancellation, output, and environment handling.
- Preserve prune/compaction, preview `--farm`, audit attribution, git backstops, shared-store
  concurrency, doctor, release, and documentation parity.
- Add a separate Pi TypeScript build/test boundary and cross-platform CI without changing the
  existing Node-20 `plugins/ca/tools` boundary.
- Complete a `ca-threat-model` pass before implementation code begins.

### Out of scope

- Publishing `ca-pi` to npm in this feature. `[NEEDS-TRIAGE]` Add npm publication and gallery
  distribution later from the generated `plugins/ca-pi/` payload.
- Promoting `--farm` from `preview` to stable; `[CONFIRM-05]` remains the promotion decision.
- Raising the shared `.codearbiter/` concurrency guarantee above ADR-0012's same-host-parity bar.
- Fixing the cross-host MCP file-write residual tracked by issue #270.
- Adding another harness, rewriting the Python kernel in TypeScript, or maintaining host-specific
  copies of governance rules.
- Replacing Pi's complete footer or reproducing host visuals pixel-for-pixel.
- Publishing, tagging, merging, or releasing without the later governed ship gates.
- `[NEEDS-TRIAGE]` Future spike: determine whether Pi's session/process APIs can support a more
  embedded `--farm` and subagent execution path while retaining the shared contracts and avoiding a
  Pi-specific governance implementation.

## Locked design

### Shared-core and generation invariant

`core/pysrc/` and `core/surface/` remain the only governance sources of truth. The generator gains a
data-driven host descriptor for Claude, Codex, and Pi instead of adding another hardcoded branch map.
Host selectors become N-host-capable, with compatibility fixtures proving the existing Claude and
Codex renderings retain their behavior.

Pi receives generated skills, commands, agents, Python modules, farm assets, and catalogs. Handwritten
Pi code may translate host data and manage host processes; it may not define H-rules, workflow phases,
reviewer policy, SMARTS, or command bodies. Any core edit may legitimately regenerate all affected
host payloads. The clean-generation invariant is: generated outputs match their shared sources and a
second generation run produces no diff.

The large pruning module is split by responsibility: host-neutral selection/policy stays shared;
Claude and Pi transcript codecs stay thin. This is extraction for reuse, not a Pi fork.

### Runtime bridge and failure direction

The Pi extension starts one bounded Python 3 process per governed event and exchanges one canonical
JSON request/response. The bridge interface hides process strategy so a later optimization can change
transport without changing governance behavior.

- Unknown or untranslatable mutating payload, unavailable Python, timeout, crash, or malformed core
  response blocks `bash`, `write`, and `edit` and points to `/ca-doctor`.
- Read, post-event, status, and advisory bridge failures continue with a visible warning and an
  attributed audit event.
- A valid canonical payload receives the same core verdict and rule identifiers on every host.
- Child stdout is protocol-only. Bounded stderr is redacted before display or audit. Raw task text,
  prompts, auth material, and provider payloads are never logged.
- The adapter uses absolute executable/bridge paths, argv arrays with `shell: false`, bounded
  input/output, explicit cwd, a minimal provider-specific environment built without unrelated
  codeArbiter secrets, and cross-platform process-tree termination.

Performance is relative, not an arbitrary absolute promise. The promotion benchmark compares Pi's
adapter-only p50/p95 with Claude and Codex over the same warm 100-event corpus on each platform. Pi
passes when its p95 is no worse than the slower existing host plus the larger of 25% or 10 ms. Shared
Python core time is reported separately. A failure blocks promotion and triggers design review; it
does not silently authorize a second governance implementation.

### Pi surfaces

- `session_start` and `before_agent_start` provide the generated persona, startup state, and prompt
  refresh behavior.
- `tool_call` maps built-in and declared extension tools into canonical `EXEC`, `WRITE`, `EDIT`,
  `READ`, or `OTHER`, then returns structured blocks for mutating failures. An undeclared tool is
  potentially mutating and blocks until the generated host descriptor explicitly classifies it as
  read-only or maps it to a governed operation.
- `tool_result` applies generated post-read/post-write notices and nudges.
- `session_before_compact` and `session_compact` invoke shared prune policy through a Pi codec.
- `agent_settled` closes transient status only after automatic retry/compaction continuations finish.
- `ctx.ui.setStatus("codearbiter", ...)` publishes the shared line without replacing the footer.
- Generated `/ca-*` aliases are primary; `/skill:ca-*` remains the native fallback.

### Subagents

`ca-pi` owns a thin runner and adds no companion subagent package. Each dispatch starts a fresh Pi
process with JSON output, exact provider/model/tool selection, `--no-approve`, `--no-extensions`,
`--no-skills`, `--no-prompt-templates`, `--no-themes`, `--no-context-files`, and `--no-session`, then
explicitly loads only the trusted enforcement-only `ca-pi` child adapter plus generated skill and
charter paths. `CODEARBITER_SUBAGENT=1` disables recursive dispatch only; enforcement remains active,
and the parent process remains unmarked. An ambient marker outside a validated runner launch fails
closed with a doctor direction.

Task content is delivered over stdin rather than exposed in argv, environment, or temporary files.
The child environment starts from a minimal OS/runtime baseline, excludes `FARM_API_KEY` and
`CLAUDE_CODE_OAUTH_TOKEN`, and admits only declared runtime and selected-provider configuration. Pi's
auth store, provider environment resolution, and credential commands remain opaque host behavior:
`ca-pi` never reads, copies, snapshots, logs, or reimplements them. The runner parses schema-validated
bounded JSONL, returns the shared structured result, caps model-visible output while retaining bounded
redacted diagnostics, propagates cancellation, and terminates the full process tree after timeout.
Single, chained, and parallel modes obey shared concurrency/depth policy. Inline author/reviewer
execution is a degraded fallback and cannot satisfy promotion.

### Pruning and compaction

The shared policy retains protected-tail, tier, dry-run, audit, metrics, opt-in, and idempotency
semantics. Claude keeps its JSONL codec. Pi operates on semantic session entries and returns native
custom compaction results for the active session. Neither host rewrites an active transcript through
manual `run`; destructive actions remain limited to inactive copies under the existing rules.

### Packaging, activation, and versions

The first distribution is Git-backed and pinned with `ca-pi-v*` tags. Pi's Git installer requires
package metadata at repository root, so a minimal generated root `package.json` points only to the
`plugins/ca-pi/` extension and generated skills. It is private distribution metadata, not a new root
JavaScript workspace, and declares no runtime Pi dependencies. `plugins/ca-pi/` owns the independent
version; generation keeps root metadata synchronized from that single version source.

Build/typecheck dependencies live only in a separate `plugins/ca-pi/tools` workspace. The shipped
extension is built JavaScript and imports Pi's host-provided APIs, preventing duplicate Pi module
identity. No root or plugin runtime dependency on `@earendil-works/pi-coding-agent` is added.

Global install is the documented default. Pi may discover and load that user extension before it
grants project trust; loading is discovery, not authorization. The adapter first reads only the
canonical `.codearbiter/CONTEXT.md` activation marker without Python or Git. It remains dormant and
silent when the marker is absent. When the marker is enabled, the adapter requires
`context.isProjectTrusted?.() === true` before Python/Git resolution, bridge or shared-core startup,
enforcement installation, hook discovery, repository Git reads, or fetch. Missing or false trust
keeps mutation blocked, delegates native reads through fresh untrusted settings, and directs the
operator to Pi's trust workflow and a new session. Project-local install remains supported under
Pi's own load-time trust rules and the same adapter authorization check.

- Minimum supported Pi: `0.80.5` (source-derived capability floor; must pass the matrix).
- Last live-verified Pi: `0.80.6`.
- Latest-canary lane: current npm `latest`, non-blocking until explicitly promoted to last-verified.
- Minimum Node: `22.19.0` for Pi surfaces; existing Node-20 tools remain unchanged.
- Python: supported Python 3 interpreters already covered by the cold-install matrix.
- Platforms: Windows, macOS, Linux.

### Shared state and farm

Pi inherits ADR-0012: cross-host concurrency must be no worse than same-host concurrency, and this
feature adds no independent locking/CAS system. Every Pi audit line is host-attributed. `--farm`
ships with the same generated assets, contract, and `preview` label as Claude; `[CONFIRM-05]` still
blocks stable promotion.

### Security boundary

The pre-implementation threat model covers untrusted project-local Pi resources, arbitrary extension
execution, canonical payload spoofing, protected-path writes, subprocess argv/env/stdin, recursion,
process-tree cleanup, secret-bearing provider environments, stderr/JSONL injection, task output caps,
and Git package provenance.

ADR-0014 resolves Pi authentication as opaque external trusted runtime state, requires enforcement-
only child loading and minimal provider-specific environments, and makes unknown tools fail closed.
For parent activation, a global extension's presence is not evidence of repository authorization:
every enabled `session_start` requires an affirmative current Pi project-trust result before any
repository-aware startup. An enabled-but-untrusted doctor is side-effect-free: it performs no bridge
probe or wrapper self-test and reports Python, bridge, and final-wrapper checks as intentionally
withheld. A later false-to-true trust retry in the same process invalidates cached identities and
performs a normal fresh activation.
Same-process trusted extensions remain an ADR-0010 cooperative residual, but live proof that `ca-pi`
sees and governs final tool arguments is a promotion gate; inability to prove it reopens ADR-0013.

The Pi workspace receives the same secret-detection corpus expectations as existing hosts. CodeQL or
the repository's successor static-analysis gate must include the new TypeScript adapter and runner.
No secret may enter a fixture, snapshot, log, audit line, child result, or failure message.

## One-branch milestone sequence

1. **M0 - host preflight:** complete; evidence recorded above.
2. **M1 - generator seam:** N-host descriptors/selectors, clean regeneration, root Pi metadata.
3. **M2 - adapter foundation:** package discovery, activation, canonical codec, Python bridge, doctor.
4. **M3 - enforcement parity:** lifecycle/tool mappings, failure direction, git backstop, status.
5. **M4 - isolated agents:** child runner, recursion guard, structured modes, timeout/cancellation.
6. **M5 - prune/farm/state:** host-neutral prune policy, Pi codec/compaction, preview farm, concurrency.
7. **M6 - promotion:** version/platform matrix, relative benchmark, docs/parity, live evidence, full suite.

Every milestone is test-first and remains on `feat/pi-support`. No milestone is a partial release or
permission to lower full-parity acceptance.

## Acceptance criteria

1. **N-host generation:** One data-driven generator supports Claude, Codex, and Pi without a new
   host-specific governance source or binary host switch.
2. **Clean regeneration:** After an expected all-host regeneration, generated payloads match shared
   sources and an immediate second run leaves the worktree unchanged.
3. **Shared Python core:** Every shared Python file in all three payloads is byte-identical to
   `core/pysrc/`, excluding only declared thin adapters.
4. **No governance duplication:** A structural check fails when handwritten Pi code defines an
   H-rule, workflow phase, reviewer policy, SMARTS rule, or generated command body.
5. **Root Git package:** A pinned Git fixture discovers only the generated `ca-pi` extension and
   skills through synchronized root package metadata.
6. **No runtime Pi dependency:** Distribution manifests contain no bundled/direct Pi runtime
   dependency and a module-identity test proves adapter imports resolve to the host Pi instance.
7. **Version contract:** Pi `0.80.5` and `0.80.6` pass; an older Pi, Node below `22.19.0`, or missing
   Python returns an explicit diagnosis instead of partial activation. Latest-canary results report
   separately.
8. **Dormancy:** A repo without enabled context receives no persona, enforcement, audit mutation, or
   scaffold.
9. **Activation and trust authorization:** A trusted enabled repo injects the generated persona and
   reports `host: pi` with current project state. An enabled repo with a missing or false trust result
   performs no Python/Git resolution, bridge/shared startup, enforcement or hook installation, Git
   read, or fetch; mutation remains fail-closed, native reads use fresh untrusted settings, and a
   fixed trust direction is shown. False-to-true same-process retry activates with fresh identities.
10. **Command parity:** The shared catalog maps one-to-one to generated `/ca-*` aliases and
    `/skill:ca-*` fallbacks with valid host-native references.
11. **Canonical mapping:** Representative Pi `bash`, `read`, `write`, `edit`, and declared extension
    tools emit the specified canonical category/payload; an undeclared tool blocks until the generated
    descriptor classifies it read-only or maps it to a governed operation.
12. **Verdict parity:** The shared enforcement corpus produces identical allow/block/remind verdicts
    and rule identifiers wherever hosts expose equivalent operations.
13. **Mutation fail-closed:** Unknown or opaque mutation, missing Python, timeout, crash, malformed
    response, or protocol overflow blocks the Pi tool and names `/ca-doctor`.
14. **Advisory fail-open:** The same failures during read/post/status handling continue, warn visibly,
    and record a redacted attributed audit event.
15. **Read/write notices:** Governed reads and H-07/H-09/H-10/H-12/H-13/H-15/H-16/H-17 write fixtures
    receive the same de-duplicated context/reminders as shared core.
16. **Git backstop:** A trusted enabled Pi fixture installs the shared hook backstop and rejects
    prohibited commit operations with the expected identifier; an enabled-untrusted global session
    performs no hook discovery or installation and no repository fetch.
17. **Subagent isolation:** Each generated author/reviewer dispatch has a distinct Pi PID/context,
    exact provider/model/tools, explicit enforcement/skill/charter inputs, discovery/session loading
    disabled, `CODEARBITER_SUBAGENT=1` suppressing recursion but not gates, and canonical output.
18. **Subagent orchestration:** Single, chained, parallel, cancelled, timed-out, over-depth, oversized,
    malformed-JSONL, and child-crash fixtures return deterministic shared terminal states.
19. **Process-tree cleanup:** Timeout/cancel tests prove no child or grandchild Pi process survives on
    Windows, macOS, or Linux.
20. **No inline promotion:** Missing isolation classifies Pi as degraded even when inline review ran.
21. **Composable status:** The adapter uses only the `codearbiter` status key and never replaces the
    full footer.
22. **Settled lifecycle:** Status clears at `agent_settled`, not early `agent_end`, including retry and
    auto-compaction continuation fixtures.
23. **Host-neutral prune policy:** Equivalent Claude/Pi transcript fixtures select the same protected
    tail, tiers, markers, dry-run metrics, and audit outcomes.
24. **Pi compaction safety:** Active Pi compaction returns a policy-compliant native result without
    rewriting the active session file.
25. **Prune command parity:** `status`, `dry`, `run <inactive-copy>`, `audit`, `on`, and `off` preserve
    opt-in and inactive-target rules.
26. **Farm preview parity:** Generated Pi assets route `--farm` through the shared contract and retain
    the `preview` label.
27. **Shared-store attribution:** Claude/Pi, Codex/Pi, and Pi/Pi concurrency fixtures record
    `HOST: pi` without corruption beyond ADR-0012's same-host baseline.
28. **Doctor coverage:** Healthy and individually broken package/trust/version/core/command/bridge/
    subagent fixtures report the exact remediation; enabled-untrusted diagnosis is side-effect-free
    and truthfully marks withheld bridge/wrapper checks; a harmless live-fire probe observes a real
    block after trust.
29. **Secret safety:** Isolated-home environment, argv, stdin, stderr, JSONL, task output, and audit
    fixtures prove `ca-pi` never inspects real auth state, unrelated secrets are absent, provider
    inputs are minimized, and every observable channel uses the shared redaction corpus.
30. **Static analysis:** The new TypeScript adapter/runner is included in CodeQL/static analysis with
    no unresolved high-severity result.
31. **Relative performance:** On each supported platform, Pi adapter p95 satisfies the relative
    slower-host-plus-25%-or-10-ms rule; shared-core and cold-start measurements report separately.
32. **Cross-platform contract:** Windows, macOS, and Linux pass discovery, path, encoding, process,
    cancellation, parity, prune, and benchmark suites.
33. **Independent release guard:** Changed `plugins/ca-pi/**` payload already covered by a tag cannot
    pass CI until its independent version/changelog and generated root metadata advance together.
34. **Documentation parity:** Project vocabulary, install guidance, host notes, command catalogs, and
    parity ledger include Pi and label every evidence-backed exception.
35. **Live promotion evidence:** Trusted Windows interactive and Linux non-interactive runs prove
    activation, aliases, mutation blocking, isolated agents, status, and compaction on the supported
    version bounds before promotion; macOS live testing becomes mandatory if matrix behavior differs.
36. **Threat-model gate:** ADR-0014 is reflected in the implementation plan; final-argument ordering,
    unknown-tool fail-closed behavior, opaque auth handling, minimal child environments, and
    enforcement-only discovery have no unresolved blocking finding before mutating adapter code.
37. **Repository regression gate:** Every existing required repository test and every new Pi test
    passes with clean/idempotent core and surface generation.
38. **Single-branch/full-parity gate:** No partial milestone ships; the branch advances to PR only
    when all non-host-impossible parity criteria pass and every exception has live evidence.

## Open questions

- `[CONFIRM-05]` remains unresolved only for promoting shared `--farm` from `preview` to stable. It
  does not block shipping Pi with the existing preview label.

No blocking Pi-specific design question remains.

## Approval gate

No implementation plan, TDD Phase 1 obligation set, or feature code begins until the maintainer
explicitly approves this revised spec. Approval also routes immediately through `ca-threat-model`
before implementation planning.
