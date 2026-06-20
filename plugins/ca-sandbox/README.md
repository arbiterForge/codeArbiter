# ca-sandbox

A locally-hosted GitHub-Codespace equivalent for codeArbiter (ADR-0007). Pull a repo you're curious
about — including untrusted code — into an **ephemeral, isolated container**, explore or run it safely,
then tear it down. The cloned repo and all execution live inside the container; your host filesystem is
never mounted in.

This is an **infrastructure** plugin, a sibling to the `ca` governance plugin in the same marketplace.
It is independent of `ca`: CI is path-scoped and versions bump per-plugin.

## Requirements

- **Docker — required.** A working Docker engine (Linux containers). Docker Desktop on Windows/macOS
  (WSL2 backend) or native Linux all work. ca-sandbox shells out to the `docker` CLI.
- **nixpacks — used to build the sandbox image** from the repo's detected dependencies. On
  Linux/macOS it runs on the host. On Windows it runs via the **WSL bridge** (below). If neither a
  host nixpacks nor a WSL bridge is found, ca-sandbox falls back to a generated Dockerfile that mimics
  nixpacks (node/python only) — the feature still works, just without nixpacks' broader stack coverage.

  > **Windows — the WSL bridge.** nixpacks ships Linux/macOS binaries only (no Windows binary). On
  > Windows, ca-sandbox runs nixpacks inside a WSL distro purely to *generate* the Dockerfile
  > (`nixpacks build --out`, which needs **no** Docker daemon in WSL), then builds it with your **host
  > Docker** — the same engine the driver runs against, so the image is visible. Requirements: Docker
  > Desktop + a WSL distro (e.g. Ubuntu) with `nixpacks` on its PATH or at `~/.local/bin/nixpacks`. No
  > Docker Desktop WSL-integration toggle is needed.

## Security model — the load-bearing invariant

Untrusted code in the box **cannot reach the host filesystem**. Enforced structurally:

- No bind mounts (the mount builder rejects any bind spec); the repo lives on a **named volume** at
  `/work/repo`, deps out-of-tree at `/deps`.
- No `/var/run/docker.sock` mount; never `--privileged`.
- `--cap-drop ALL`, `--security-opt no-new-privileges`, read-only root, non-root user, resource caps.

Getting work **out** is host-initiated only: `sandbox cp <id>:/work/<file> <hostDest>` (a `docker cp`
pull). The container is never given any path back into the host.

## Commands

```
sandbox create <url> [--net offline|clone-then-cut|allowlist]
sandbox shell <id> [--shell sh|bash]
sandbox exec <id> -- <cmd> [args...]
sandbox cp <id>:<containerPath> <hostDest>
sandbox destroy <id> [--keep-volume]
sandbox prune
```

State is label-only: the set of sandboxes IS the set of docker objects labeled `ca.sandbox=1`
(per-instance `ca.sandbox.id=<id>`). There is no JSON state file to drift.

> **Git Bash users:** a bare container path in `exec` (e.g. `exec <id> -- ls /work/repo`) is rewritten
> by MSYS path conversion *before* it reaches the CLI, becoming a Windows path. Wrap the command —
> `exec <id> -- sh -c 'ls /work/repo'` — or set `MSYS_NO_PATHCONV=1`. PowerShell and cmd are unaffected.

## Network policies

- **offline** (default) — `--network none`; the box has no egress.
- **clone-then-cut** — network up for the clone/build, severed for exploration.
- **allowlist** — *experimental*. An iptables egress allowlist (custom bridge + `NET_ADMIN`); brittle
  under CDN IP drift and does not close DNS-layer exfil. Prefer offline/clone-then-cut; a
  hostname-aware forward proxy is the intended replacement.

## Image caching

The image is tagged by a hash of the repo's dependency manifests/lockfiles. An unchanged-deps re-launch
reuses the image; a manifest change rebuilds. Deps install **out-of-tree at `/deps`** (with
`NODE_PATH`/`PYTHONPATH` etc.) so the live source volume mounted at `/work/repo` never shadows them —
deps survive the mount and source stays live-editable.

## `--with-claude` (Claude Code inside the box)

Runs Claude Code inside the container, authenticated via an env-injected `CLAUDE_CODE_OAUTH_TOKEN`
(no host bind of `~/.claude`; session persisted on a named volume). **Caveat:** a token inside a box
running untrusted code is exfiltrable over any egress, so `--with-claude` defaults to offline /
Anthropic-domains-only and never co-mounts the token volume with an untrusted-code run.

## Development

The driver is TypeScript on Node 20, shipped as the built `tools/sandbox.js`.

```
cd tools
npm install
npm run typecheck
npm test          # docker-gated suites run serially (fileParallelism off)
npm run build     # rebuilds sandbox.js; the shipped artifact must be in sync
```
