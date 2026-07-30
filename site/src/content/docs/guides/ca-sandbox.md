---
title: "ca-sandbox: Explore Untrusted Code"
description: "What ca-sandbox is, how its isolation model holds, and how to install and use it: a locally-hosted GitHub-Codespace equivalent, not part of the governance kernel."
journey:
  level: Labs
  time: 15–30 min
  outcome: "a disposable offline sandbox you can create, inspect, copy an artifact out of, and tear down while preserving the host-filesystem boundary."
  prerequisites:
    - Docker running Linux containers
    - A repository URL you do not need to trust
  proof: "The box runs without bind mounts or Docker socket access, copied output leaves only through the host command, and destroy reports zero labeled objects remaining."
---

`ca-sandbox` is one of codeArbiter's four sibling plugins (ADR-0007). But unlike `ca`, `ca-codex`,
and `ca-pi`, it is not a governance host. It carries no gates, no `.codearbiter/` orchestration, and
no relationship to the test-first/review/commit-gate pipeline the rest of this site documents. It is
an **infrastructure** plugin with one job: run code you do not trust without exposing your machine.

Give it a repo URL and it clones the code into a Docker named volume (never onto your host
filesystem), builds a dependency-cached image with [nixpacks](https://nixpacks.com/), and starts a
container you can explore, run, and tear down.

## Status

`ca-sandbox` is a [Feature Forge](/feature-forge/overview/) preview plugin. Its automated suite is
green, but the `--with-claude` path (running Claude Code inside the box) is verified only against a
dummy token, not yet a real interactive session. See
[What's in the Forge](/feature-forge/whats-in-the-forge/#ca-sandbox-local-codespace) for the fuller
writeup and how to help promote it.

## Isolation model

The isolation holds by construction, not by trust:

- No bind mounts: the repo lives on a named Docker volume at `/work/repo`, dependencies out-of-tree
  at `/deps`.
- No `/var/run/docker.sock` mount; never `--privileged`.
- `--cap-drop ALL`, `--security-opt no-new-privileges`, read-only root filesystem, non-root user,
  resource caps.
- Getting work back out is host-initiated only (`sandbox cp`, a `docker cp` pull): the container is
  never given a path back into the host.
- Network defaults to **offline** (`--network none`); `clone-then-cut` allows egress for the
  clone/build only, then severs it; an experimental `allowlist` mode exists but is not the recommended
  posture.

## Requirements

- A working Docker engine (Linux containers): Docker Desktop (Windows/macOS, WSL2 backend) or native
  Linux.
- `nixpacks` on `PATH`, or on Windows inside a WSL distro (see the
  [`ca-sandbox` README](https://github.com/arbiterForge/codeArbiter/blob/main/plugins/ca-sandbox/README.md#windows--the-wsl-bridge)
  for the WSL-bridge build path). Without it, `ca-sandbox` falls back to a generated Dockerfile with
  narrower stack coverage.

## Install

```text
/plugin install ca-sandbox@codearbiter
```

The sandbox plugin is Claude Code-specific and has its own `/ca-sandbox:` namespace. It does not
activate through `.codearbiter/`.

## Create an Offline Box

Start with the default offline policy:

```text
/ca-sandbox:sandbox "https://github.com/owner/repository"
```

The command checks Docker, clones into a named volume, builds the dependency-cached image, and
returns a sandbox ID. Save that ID for the remaining commands.

Before running untrusted code, inspect the reported container configuration. It should have no bind
mount, no Docker socket, no privileged mode, all capabilities dropped, a read-only root filesystem,
and `--network none`.

## Explore and Run

```text
/ca-sandbox:sandbox-shell "<id>"
/ca-sandbox:sandbox-exec "<id> -- npm test"
```

Use `sandbox-shell` for interactive exploration. Use `sandbox-exec` for a bounded, scriptable command
that returns separate stdout, stderr, exit code, and a truncation flag.

On Git Bash, wrap container paths to prevent MSYS rewriting:

```text
/ca-sandbox:sandbox-exec "<id> -- sh -c 'ls /work/repo'"
```

PowerShell and cmd do not need that workaround.

## Copy Out and Destroy

Copy only the artifact you intentionally want:

```text
/ca-sandbox:sandbox-cp "<id>:/work/repo/report.json ./review/report.json"
```

The host invokes `docker cp`; the container never receives a host path. Inspect the copied file as
untrusted data before opening it with a privileged application.

Then tear the box down:

```text
/ca-sandbox:sandbox-destroy "<id>"
```

Destroy removes the container and named volume and reports any failed Docker operation. A non-zero
result is not success: use the destroy command's `--prune` recovery path and confirm no objects with
the `ca.sandbox=1` label remain. `--keep-volume` deliberately retains source state and therefore is
not a complete teardown.

## Failure and Recovery

| Symptom | Likely cause | Recovery |
|---|---|---|
| Docker preflight stops | Daemon unavailable or not using Linux containers | Start Docker, confirm `docker info`, retry |
| nixpacks is unavailable | Missing host tool or Windows WSL bridge | Install nixpacks in the documented host/WSL location, or accept the narrower fallback |
| Clone succeeds but later network access fails | Offline or clone-then-cut policy is working | Use the least permissive policy that supports the task; do not jump to experimental allowlist by default |
| Exec times out | Untrusted process exceeded its bounded operation deadline | Inspect captured output, destroy the box, retry only with a justified narrower command |
| Destroy reports failures | Docker could not remove one or more labeled objects | Run the explicit prune recovery and verify the remaining-object count |

## Not part of the governance kernel

`ca-sandbox` shares the marketplace with `ca`, `ca-codex`, and `ca-pi`, and its CI is path-scoped and
versioned independently of them (ADR-0007). It does not read or write `.codearbiter/`, and installing
or removing it has no effect on gate enforcement in any repository. If you're looking for the
governance hosts instead, see [Install](/getting-started/install/), [Claude Code + Codex
evidence](/getting-started/claude-code-and-codex/), or [Pi](/getting-started/pi/).

Full detail, including the Git Bash path-conversion caveat and image-caching behavior, lives in the
[`ca-sandbox` README](https://github.com/arbiterForge/codeArbiter/blob/main/plugins/ca-sandbox/README.md).
