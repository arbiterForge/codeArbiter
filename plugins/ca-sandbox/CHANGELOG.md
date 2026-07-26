# Changelog — ca-sandbox

All notable changes to the **ca-sandbox** plugin are recorded here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/). ca-sandbox is the sibling *infrastructure* plugin to `ca`; the two version and release independently (ADR-0007).

---

## [0.1.5] — 2026-07-24 — Teardown failures are surfaced and fail

### Added
- **`--with-claude` finally has a shipped code path (#377).** The feature was documented, and `runClaudeInside` had zero callers — so esbuild tree-shook it out of `sandbox.js` entirely and the skill told operators to call TypeScript that no install contained. It now ships as `plugins/ca-sandbox/tools/claude-inside.js`, its **own binary rather than a `sandbox` subcommand**. That separation *is* the gate: a subcommand would let anyone start a container holding a live OAuth token with one ungated command, which would turn the `sandbox-claude-inside` skill's five BLOCK phases from enforcement into advice. The entry refuses a `--token` flag outright — an argument list is world-readable, so passing a credential there publishes it to every process on the host — and refuses `--source-volume` at parse time, so the co-mount mistake never reaches docker. Egress is `offline` by default, the only guaranteed posture for a token-bearing box, with `anthropic-only` the sole opt-in alternative.

### Fixed
- **`build.ts`'s own spawn is bounded (#394 follow-up).** #480 gave every invocation through `docker.ts` a finite deadline and its docblock claimed "every docker invocation is bounded". That claim was false: `build.ts` never imports the shared runner — it takes only `DOCKER_ENV` — and had its own `run()` helper with no timeout at all. That helper executes `docker image inspect` and *both* `docker build` calls, so `sandbox create` against a wedged builder or a stalled registry pull hung forever, and `DOCKER_OPERATION_TIMEOUTS_MS.build` / `.pull` were dead constants nothing in production could reach. Build and pull are the two longest operations in the driver, which made them the two most likely to hang and the only ones with no escape. The helper now takes its deadline from the shared per-operation map rather than a second policy invented beside it, kills the child with SIGKILL when it fires, and returns the same typed `timedOut` result `docker.ts` does.
- **`--with-claude`'s `anthropic-only` posture ran NET_ADMIN with no firewall (#377).** `resolveClaudeNetworkArgs` called `applyNetworkPolicy("egress-allowlist", ...)` and took only `.runArgs`, discarding `.firewallScript` — with a comment saying the caller would apply it, and no such caller anywhere in the tree. The result was a container with `--cap-add NET_ADMIN --cap-add NET_RAW` on a custom bridge and no iptables rules: wide-open egress *plus* elevated network capabilities around a live OAuth token, which is strictly worse than plain default networking and the opposite of what an operator selecting that posture is asking for. The flags and the rules now travel together, `runClaudeInside` installs them inside the box after start, and a box whose firewall cannot be applied is **destroyed rather than returned** — handing back the id would tell the caller it is locked down when it is not. `offline`, the guaranteed posture, still execs nothing, because it has no interface to firewall. Unexploitable before this fix only because `runClaudeInside` has no callers yet, which is exactly why it is fixed before it gets one.
- **One unreachable daemon reads as one failure (#433).** Discovery listed containers and volumes, then the post-sweep verification re-listed the same two scopes against the same dead daemon — `DOCKER_HOST=tcp://127.0.0.1:1 node sandbox.js prune` reported `failureCount: 4` for one fact. Listing failures now dedupe on the failure's *shape* rather than its text, because a real daemon returns the same connection error carrying different URLs; two listings failing *differently* still read as two. Removal failures dedupe on the whole identity, so two containers refusing for their own reasons are never collapsed.
- **`prune`'s verification is scoped to what it targeted (#433).** It re-listed the global `ca.sandbox=1` scope, so a sandbox another process created *after* discovery landed in `remainingContainers` and produced "These objects may be running UNTRUSTED code" for something prune never touched. It failed safe, but a scary false positive teaches operators to ignore the signal — which defeats the point of #393. An object prune did target and could not remove is still reported.
- **A deliberately kept volume is never named as a leak (#433).** Under `--keep-volume` no volume is targeted for removal, so none can be remaining. Filtering against `keptVolumes` was not enough: when the *discovery* listing failed that list was empty while the *verification* listing still succeeded, so the volume the operator explicitly asked to keep was reported as remaining — at exactly the wrong moment.
- **The teardown exit code is pinned (#433).** `TEARDOWN_FAILURE_EXIT` is 1 and the usage error is now the exported `USAGE_ERROR_EXIT` (2). Every previous assertion was `not.toBe(0)`, so the teardown code could have drifted onto the usage code — making a leaked untrusted container indistinguishable from a typo — with the suite green.
- **Every docker invocation is bounded (#394).** The single docker chokepoint called `spawnSync("docker", ...)` with no timeout, and `execInSandbox` widened only `maxBuffer` before waiting synchronously — so an in-container `sleep infinity`, a wedged daemon, or a stalled build had no deadline at all. The host process blocked until something external killed it, and untrusted repository code could deterministically wedge `sandbox exec`. Every invocation now carries a finite, per-operation deadline (generous where work is genuinely long — build, pull, exec — and short for a plain client call), and a deadline kill returns a **typed** `timedOut` result rather than a non-zero indistinguishable from an ordinary docker failure.
- **A timed-out `exec` no longer orphans the in-container process (#394).** The deadline kills the docker *client*; the process it started inside the container keeps running, holding the box open. A timed-out exec now reaches back in and stops the container it targeted, with `--time 0` — the graceful window is what the deadline already spent, and a longer grace can itself exceed the runner's deadline and be killed before it lands. Escalation happens **only** on a timeout: doing it on an ordinary non-zero exit would destroy a working box every time a command returned 1. A failed escalation is reported but never masks the original timeout, since a wedged daemon is exactly when the cleanup cannot succeed.
- **A failed teardown can no longer report success (#393).** `destroySandbox` and `prune` wrote `if (r.code === 0) removed.push(x)` and discarded every non-zero docker result; the result types carried no failure field at all, and the CLI returned 0 for both verbs unconditionally. A daemon outage, a permission error, or an in-use object therefore left **untrusted sandbox containers and source volumes running while automation read exit 0** — the advertised teardown guarantee was false on exactly the path where cleanup matters. Both verbs now retain every failed docker operation in a bounded `failures` list (with `failureCount` staying exact past the bound), and `sandbox destroy` / `sandbox prune` exit non-zero whenever anything failed or anything remains.

### Changed
- **Teardown is best-effort but never silent.** A failure no longer influences what else is attempted: every discovered container and volume is still targeted, so a partial teardown reclaims everything it can instead of stopping at the first refusal.
- **Teardown is verified, not assumed.** After the removals, both verbs re-list the same label scope and report what is STILL PRESENT (`remainingContainers` / `remainingVolumes`). A `--keep-volume` volume is a deliberate survivor and is excluded from that set, so keeping a volume is still a clean exit.
- **A failed listing is itself a teardown failure.** Discovery and verification now go through `listContainersResult` / `listVolumesResult` in `registry.ts`, which retain docker's exit code — "listed nothing while the daemon was down" must never read as "nothing is left". `listContainers` / `listVolumes` are unchanged thin wrappers over them.
- **The diagnostic names what was left behind.** On failure the CLI writes a bounded stderr report — each failed operation with docker's own exit code and message, then the ids/names of every object still present and the manual `docker rm -f` / `docker volume rm` needed to clear them. The stdout JSON keeps the full structured result for scripting.

---

## [0.1.4] — 2026-07-24 — Supply-chain hardening: no pipe-to-shell, digest-pinned images

Two tribunal supply-chain findings closed. Both concern EXTERNAL bytes the driver pulled in unpinned.

### Security
- **No remote-fetch-and-execute (#401).** `build.ts` no longer runs `curl -fsSL <installer> | bash` when nixpacks is missing. That branch executed arbitrary remote bytes on the developer host with the developer's privileges, BEFORE any container boundary exists. nixpacks is a documented prerequisite (README / SKILL / command description), so a missing prerequisite now FAILS CLOSED to the pre-existing generated-Dockerfile fallback with an actionable install note. The `curl | bash` declared exception in `security-controls.md` is closed, not merely narrowed.
- **Container inputs pinned by digest (#402).** The throwaway clone image, the generated-Dockerfile fallback base, and the `--with-claude` base image are each bound to a reviewed multi-arch index digest (`name:tag@sha256:<digest>`). A retag or registry compromise can no longer silently change executable code inside a sandbox build — least of all in the Claude box, whose base image co-runs with `CLAUDE_CODE_OAUTH_TOKEN`.

### Added
- **`supply-chain.test.ts`** — structural guards that cannot be stubbed past: they reject pipe-to-shell patterns and digest-free external image references across the shipped driver sources AND the committed `sandbox.js` bundle. The digest scanner reads JOINED file text, so it matches the multi-line declaration style every image constant in this driver uses (`export const CLONE_IMAGE =` / newline / `"<ref>"`); it also flags any namespaced `ns/name:tag` literal regardless of the constant's name, and only accepts a `FROM ${…}` interpolation that demonstrably resolves to a digest-pinned constant in the same file. Test fixtures are exempt (`lifecycle.test.ts` drives docker with a literal tag on purpose).
- **A regression suite for the scanner itself** — synthetic multi-line sources assert the rules actually FIRE. A structural scanner that quietly matches nothing is indistinguishable from a clean codebase, and the first cut of this one was inert against exactly the declaration style it was written to guard.
- **`defaultEnsureNixpacks` is exported with an injectable process seam**, closing a real coverage gap: every other suite stubs `BuildDeps.ensureNixpacks`, so the actual default toolchain-probe path had zero tests. It is now asserted to probe only — never to mutate the host toolchain.

### Documentation
- **`sandbox-claude-inside` SKILL states the base-image pin.** Phase 2 said only "the base is `node:22-slim`"; it now records that the base is digest-bound, why that pin is the highest-stakes one in the driver (the base image's code runs in the same container as `CLAUDE_CODE_OAUTH_TOKEN`), and that an unpinned base fails the phase gate.

---

## [0.1.3] — 2026-07-02 — Single docker primitive + helper-container hardening

Consolidation and hardening of the sandbox driver's container handling (part of the tribunal remediation).

### Changed
- **One shared docker primitive (#180).** Extracted `tools/docker.ts` as the single module every `docker` invocation flows through, replacing duplicated spawn/argv logic across build/run/exec/cp/create/registry/claude-inside — so the argv-array discipline (no `shell: true`) and the container-hardening flags cannot drift between call sites.

### Fixed
- **Helper containers are labeled and time-bound (#173).** The transient helper containers the driver spawns now carry an identifying label and a bounded lifetime, so an interrupted run cannot leak an unlabeled, unbounded container.

---

## [0.1.2] — 2026-07-02 — Tribunal quick-kills

The ca-sandbox portion of the tribunal quick-kill fixes.

### Fixed
- **Robustness and diagnosability hardening (#197).** Atomic provenance/state writes, typed `docker` spawn options (with `shell` omitted from the typed opts), removal of dead re-binds, and fail-closed CI scripts in the sandbox tooling.

---

## [0.1.1] — 2026-06-21 — Dependency bump

Dev-toolchain dependency bump for the sandbox driver (`tools/`). No payload behavior change; consolidates Dependabot #112 and #114 into one synced lockfile.

### Changed
- **`tools/` dev dependencies** — `esbuild` `^0.24.0 → ^0.28.1`, `vitest` `^2.0.0 → ^4.1.9` (transitive `vite` dropped). Regenerated `package-lock.json` so `npm ci` is back in sync.

---

## [0.1.0] — 2026-06-20 — Initial preview

First public release, shipping in the **Feature Forge** as `preview`. A locally-hosted Codespace equivalent: it pulls an untrusted repo into an ephemeral, isolated Docker container with no host-filesystem access and configurable egress, caches dependencies by content hash, then tears the box down. Requires Docker and nixpacks on PATH. Off by default; stays `preview` until real-world runs earn a promotion.

### Added
- **Ephemeral isolated sandbox lifecycle** — `/ca-sandbox:sandbox{,-shell,-exec,-cp,-destroy}` over a labeled (`ca.sandbox=1`) container + named volume. `create → destroy` sweeps to zero; `--keep-volume` retains state; `prune` reclaims leaked labeled objects.
- **Hard host-FS isolation** — no bind mounts (the mount builder rejects all binds; volume/tmpfs only), no `/var/run/docker.sock`, non-root, `--cap-drop ALL`, read-only root. Proven by an in-box canary that can neither read the host abspath nor surface the uuid via a whole-FS grep.
- **Content-hash dependency cache** — `dephash` over the manifest set: identical manifests reuse the image, a manifest/lockfile change rebuilds. Deps are relocated to `/deps` so they survive the `/work/repo` volume mount and source stays live-editable.
- **Multi-stack builds** — nixpacks wrap with a generated-Dockerfile fallback when nixpacks is absent; node / python / go / rust fixtures each build a runnable image deterministically.
- **Configurable network policy** — offline by default, clone-then-cut, and an experimental egress allowlist.
- **exec / cp seams** — `execInSandbox()` JSON contract (exit code, separated stdout/stderr, byte-capped `truncated`); host-initiated `cp` out; the reverse host→container bind is structurally impossible.
- **`--with-claude` (experimental)** — run Claude Code *inside* the box with an env-injected token, state persisted across restarts via a named-volume HOME, offline / Anthropic-only by default.
- **Gated skill + command surface** — `sandbox-lifecycle` and `sandbox-claude-inside` skills; the five `/ca-sandbox:*` commands above.
- **Path-scoped CI** (ADR-0007) — a sandbox-only diff runs the docker-gated tools job and skips every `ca` check; a per-plugin version-bump guard; a `sandbox.js` artifact-freshness gate.

### Notes
- **Preview — not yet blessed.** The automated suite (178 tests, including the docker integration specs) is green, but the plugin has **not been proven in real use**. The `--with-claude` path is verified only against a dummy token (a real `401`), never a live interactive session. Help promote it: explore real repos in the box, run `--with-claude`, and report what you see.
