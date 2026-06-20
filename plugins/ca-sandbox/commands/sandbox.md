---
description: Pull an untrusted repo into an ephemeral, host-FS-isolated Docker container — clone into a named volume, build a dep-cached image, run under structural isolation. Network defaults to offline. Requires Docker and nixpacks.
argument-hint: "<repo url> [--network offline|clone-then-cut|allowlist] [--with-claude] [--keep-volume]"
---

# /ca-sandbox:sandbox — create an isolated sandbox

The entry point to a local Codespace equivalent. Give it a repo you're curious about and it clones the
code into a docker **named volume** (never onto your host filesystem), builds a dependency-cached image,
and starts an isolated container you can explore. The box is ephemeral and the host is never exposed:
no bind mount, no docker socket, never `--privileged`.

The repo runs under structural isolation built by construction, not by trust — `--cap-drop ALL`,
non-root, read-only root, `--security-opt no-new-privileges`, the live source volume mounted ONLY at
`/work/repo`, deps baked out of tree at `/deps`. Network defaults to `offline`; `clone-then-cut`
fetches deps at build then cuts egress; `allowlist` is EXPERIMENTAL (IP-based, brittle on CDN drift —
prefer offline or clone-then-cut). `--with-claude` runs Claude Code inside the box under hardened
defaults and is handled by a separate, gated routine.

## Flow

1. **Pre-flight** — confirm Docker (`docker info`) and nixpacks are on `PATH`, and a repo URL was
   given. STOP and report the gap if either is missing.
2. **Clone & build** — clone into a named volume at `/work/repo`; build via nixpacks with deps
   relocated to `/deps`; tag `ca-sbx:<repo>-<dephash>`. An unchanged dep set is a cache hit (no
   rebuild); a manifest/lockfile change rebuilds.
3. **Isolated run** — start the container through the driver's `runContainer` with the full isolation
   set and the chosen network policy. `docker inspect` confirms no bind, no docker socket, not
   `Privileged`.
4. **Report the box id** — print the sandbox id and the interaction commands
   (`/ca-sandbox:sandbox-shell`, `-exec`, `-cp`, `-destroy`).

## Routes to

`sandbox-lifecycle` (`${CLAUDE_PLUGIN_ROOT}/skills/sandbox-lifecycle/SKILL.md`) — Phases 1–3 (pre-flight,
clone & build, isolated run). When `--with-claude` is set, it routes onward to `sandbox-claude-inside`
(`${CLAUDE_PLUGIN_ROOT}/skills/sandbox-claude-inside/SKILL.md`) for the hardened token path.

## When NOT to use

- Acting on an already-running box → `/ca-sandbox:sandbox-shell`, `/ca-sandbox:sandbox-exec`,
  `/ca-sandbox:sandbox-cp`.
- Tearing a box down or reclaiming leaked objects → `/ca-sandbox:sandbox-destroy`.
- Editing codeArbiter itself, or a trusted local repo on the host → this plugin is for *untrusted*
  code in throwaway isolation, not a general devcontainer manager.

## Hard gate

- MUST NOT give the container a host bind mount, a `/var/run/docker.sock` mount, or `--privileged`.
  `docker inspect` MUST show no `"Type":"bind"` mount, no docker-socket mount, and not `Privileged:true`.
- MUST mount the live source named volume ONLY at `/work/repo` (deps at `/deps`); MUST NOT mount the
  volume over the app dir.
- MUST default the network policy to `offline`; MUST name `allowlist` as EXPERIMENTAL whenever selected.
- MUST start the container only through the driver's `runContainer` (the mount chokepoint), never a
  hand-rolled `docker run`.
- MUST STOP rather than guess when Docker or nixpacks is absent.
- MUST NOT enable `--with-claude` without routing to `sandbox-claude-inside`, and MUST NEVER co-mount
  the token volume with an untrusted-code run.
