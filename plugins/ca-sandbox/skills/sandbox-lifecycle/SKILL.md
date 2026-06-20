---
name: sandbox-lifecycle
description: The lifecycle gate for a local Codespace-equivalent sandbox. Routed to when the user invokes /ca-sandbox:sandbox to pull an untrusted repo into an ephemeral, host-FS-isolated Docker container, or any of the interaction commands (/ca-sandbox:sandbox-shell, /ca-sandbox:sandbox-exec, /ca-sandbox:sandbox-cp, /ca-sandbox:sandbox-destroy) against an existing box. Five gated phases — pre-flight, clone+build, isolated run, interact, teardown. The load-bearing invariant is structural: untrusted code in the box can never reach the host filesystem (no bind mount, no docker socket, never --privileged, cap-drop ALL, non-root, read-only root). Network defaults to offline; egress out is host-initiated only. Every object is labeled ca.sandbox=1 and torn down on exit.
---

# sandbox-lifecycle

Pull an untrusted repo into a throwaway box, explore it without risking the host, then burn the box. This skill owns the whole arc — clone into a named volume, build a dep-cached image, run it under structural isolation, interact (shell / exec / cp out), destroy — and the one invariant that makes it safe: **the code inside the box can never touch the host filesystem.** That guarantee is enforced by construction (no bind mounts, no docker socket, never `--privileged`), not by trusting the repo.

The driver lives in `${CLAUDE_PLUGIN_ROOT}/tools`. The skill never hand-rolls a `docker run` argv — every container is started through `runContainer` in `${CLAUDE_PLUGIN_ROOT}/tools/run.ts`, whose mount argv comes only from `buildMountArgs` in `${CLAUDE_PLUGIN_ROOT}/tools/mounts.ts` (the chokepoint that throws on any bind spec).

## Pre-flight

Read these, or STOP and surface the gap — never guess a Docker capability, a mount layout, or an egress posture:

- `${CLAUDE_PLUGIN_ROOT}/tools/mounts.ts` — the mount-arg chokepoint. Every mount is built here; it throws (`BindMountRejectedError`) on any `type=bind` spec. The structural half of the host-FS invariant.
- `${CLAUDE_PLUGIN_ROOT}/tools/run.ts` — the isolation flags (`--cap-drop ALL`, non-root `--user 1000:1000`, `--read-only`, `--security-opt no-new-privileges`, resource caps) and the `offline` => `--network none` default.
- `${CLAUDE_PLUGIN_ROOT}/tools/network.ts` — the network policies (offline / clone-then-cut / allowlist). The IP allowlist is EXPERIMENTAL (`ALLOWLIST_EXPERIMENTAL`); offline and clone-then-cut are the solid defaults.

Host prerequisites: **Docker** and **nixpacks** on `PATH` (the plugin's `description` states this). If `docker info` fails, STOP and report "Docker is not available" — do not proceed to clone or build. If the user supplies no repo URL to `/ca-sandbox:sandbox`, ask for one — do not guess a repo.

## Phase 1 — Pre-flight & policy · gate: BLOCK

Establish what is being sandboxed and under what egress posture before any clone:

- **Target** — the repo URL (or local path) to pull. One source, stated explicitly.
- **Network policy** — `offline` (default), `clone-then-cut` (fetch deps at build, cut egress at run), or `allowlist` (EXPERIMENTAL — name it as experimental every time it is selected). Default to `offline` unless the user names another.
- **Docker reachable** — `docker info` returns 0. If not, STOP here.
- **`--with-claude`** — if requested, route to the `sandbox-claude-inside` skill (`${CLAUDE_PLUGIN_ROOT}/skills/sandbox-claude-inside/SKILL.md`) for its hardened defaults; it is NOT enabled on the default path.

Gate: a named target, a named network policy, and a reachable Docker. A sandbox with no stated target or an unreachable Docker cannot be built — do not improvise either. If `allowlist` is chosen, the BLOCK is conditional on the user acknowledging it is experimental.

## Phase 2 — Clone & build · gate: BLOCK

Clone the target into a docker **named volume** (never onto the host FS, never a bind), then build a dep-cached image:

- Clone into the named volume via `createSandbox` (`${CLAUDE_PLUGIN_ROOT}/tools/create.ts`); the source lives at `/work/repo` inside the box.
- Build through `${CLAUDE_PLUGIN_ROOT}/tools/build.ts`: nixpacks wraps the repo, deps are relocated **out of tree to `/deps`** (exported via `NODE_PATH`/`PYTHONPATH`/`GOPATH`/`CARGO_HOME`), and the image is tagged `ca-sbx:<repo>-<dephash>`.
- The dephash comes from `computeDepHash` (`${CLAUDE_PLUGIN_ROOT}/tools/dephash.ts`) over the manifest/lockfile set. An unchanged dep set is a **cache hit** — no rebuild, identical tag. A manifest/lockfile change bumps the dephash and forces a rebuild; a source-only edit does not.

Gate: a built (or cache-hit) image tagged `ca-sbx:<repo>-<dephash>`, with deps at `/deps` (out of tree). The naive "mount the volume over the app dir" layout shadows baked deps and is forbidden — the volume mounts ONLY at `/work/repo`. If nixpacks is not installed, STOP with the install hint, not a stack trace.

## Phase 3 — Isolated run · gate: BLOCK

Start the container through `runContainer` (`${CLAUDE_PLUGIN_ROOT}/tools/run.ts`) — never a hand-written `docker run`. The run carries the structural isolation set, all by construction:

- **No host bind mount, no `/var/run/docker.sock` mount, never `--privileged`** — the three negative guarantees. The mount argv is built only by `buildMountArgs`, which throws on any bind.
- `--cap-drop ALL`, `--user 1000:1000` (non-root), `--read-only` root, `--security-opt no-new-privileges`, resource caps (`--pids-limit`, `--memory`, `--cpus`).
- The live source named volume mounts ONLY at `/work/repo`; `/tmp` is a tmpfs (writable scratch, no host backing).
- Network per Phase 1: `offline` => `--network none`; the richer policies are applied by `${CLAUDE_PLUGIN_ROOT}/tools/network.ts`.
- Every object carries the `ca.sandbox=1` label (the teardown/registry anchor).

Gate: `docker inspect` on the started container shows no `"Type":"bind"` mount, no docker-socket mount, and not `Privileged:true`. If any of the three appears, the run is rejected — there is no override; the chokepoint failed and that is a bug, not a policy decision.

## Phase 4 — Interact · gate: BLOCK

Explore the running box. Each interaction routes to its own command but funnels through this skill's seams:

- **Shell** (`/ca-sandbox:sandbox-shell`) — an interactive shell into the box at `/work/repo`.
- **Exec** (`/ca-sandbox:sandbox-exec`) — a single command via `execInSandbox` (`${CLAUDE_PLUGIN_ROOT}/tools/exec.ts`), returning a JSON contract: `exitCode`, separate `stdout`/`stderr`, and a `truncated` flag past the byte cap.
- **Copy out** (`/ca-sandbox:sandbox-cp`) — host-initiated egress ONLY, via `cpOut` (`${CLAUDE_PLUGIN_ROOT}/tools/cp.ts`): `cp <id>:/work/<f> ./dest` over `docker cp`. The reverse — a host→container bind — is impossible: the mount builder rejects it.

Gate: every file leaving the box is host-initiated (`docker cp` out), never a mount the container could write through to the host. No interaction re-introduces a bind, a socket, or a privilege the run dropped. Exec output honors the byte cap and reports `truncated` rather than streaming unbounded data.

## Phase 5 — Teardown · gate: BLOCK

A sandbox is ephemeral by contract. On exit (`/ca-sandbox:sandbox-destroy`, or the close of an interactive session):

- `destroySandbox` (`${CLAUDE_PLUGIN_ROOT}/tools/destroy.ts`) removes the container and its named volume. `--keep-volume` leaves the volume (for a deliberate re-run); nothing else survives.
- `prune` (`${CLAUDE_PLUGIN_ROOT}/tools/destroy.ts`) reclaims any leaked `ca.sandbox=1`-labeled object — the safety net for a box whose driver died mid-run.
- Cached images (`ca-sbx:<repo>-<dephash>`) are intentionally retained for the next cache hit; they are excepted from teardown.

Gate: after a `create → interact → destroy` cycle, zero `ca.sandbox=1`-labeled containers or volumes remain (cached images excepted). A run that leaves a labeled object behind without `--keep-volume` is a leak — `prune` must be able to find and reclaim it via the label alone.

## Hard rules

- MUST NOT give a sandbox container a host bind mount — every mount is built through `buildMountArgs`, which throws on any `type=bind`. The driver never hand-rolls a `-v` or `type=bind`.
- MUST NOT mount `/var/run/docker.sock` into a sandbox container, and MUST NOT run one with `--privileged`. These are non-negotiable structural guarantees, not defaults to override.
- MUST start every container through `runContainer` with `--cap-drop ALL`, non-root `--user`, `--read-only` root, and `--security-opt no-new-privileges`. A run missing any of these is rejected.
- MUST mount the live source named volume ONLY at `/work/repo`; deps live out of tree at `/deps`. MUST NOT mount the volume over the app dir — that shadows baked deps (Spike A) and is the one layout that does not work.
- MUST default the network policy to `offline`. The IP egress allowlist is EXPERIMENTAL — name it experimental every time it is selected; offline and clone-then-cut are the solid defaults.
- MUST treat all egress out of the box as host-initiated (`docker cp` out) only. A host→container bind is impossible and MUST NOT be introduced as a "convenience."
- MUST label every container and volume `ca.sandbox=1`, and MUST tear them down on exit (cached images excepted). `prune` reclaims a leaked labeled object via the label alone.
- MUST NOT enable `--with-claude` on the default path — it routes to `sandbox-claude-inside`, and MUST NEVER co-mount the token volume with an untrusted-code run.
- MUST STOP rather than guess when Docker or nixpacks is absent — report the missing dependency, never a stack trace.
