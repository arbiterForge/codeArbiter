---
title: "ca-sandbox: Explore Untrusted Code"
description: "What ca-sandbox is, how its isolation model holds, and how to install and use it — a locally-hosted GitHub-Codespace equivalent, not part of the governance kernel."
---

`ca-sandbox` is one of codeArbiter's four sibling plugins (ADR-0007) — but unlike `ca`, `ca-codex`,
and `ca-pi`, it is not a governance host. It carries no gates, no `.codearbiter/` orchestration, and
no relationship to the test-first/review/commit-gate pipeline the rest of this site documents. It is
an **infrastructure** plugin with one job: run code you do not trust without exposing your machine.

Give it a repo URL and it clones the code into a Docker named volume (never onto your host
filesystem), builds a dependency-cached image with [nixpacks](https://nixpacks.com/), and starts a
container you can explore, run, and tear down.

## Status

`ca-sandbox` is a [Feature Forge](/feature-forge/overview/) preview plugin. Its automated suite is
green, but the `--with-claude` path (running Claude Code inside the box) is verified only against a
dummy token, not yet a real interactive session — see
[What's in the Forge](/feature-forge/whats-in-the-forge/#ca-sandbox-local-codespace) for the fuller
writeup and how to help promote it.

## Isolation model

The isolation holds by construction, not by trust:

- No bind mounts — the repo lives on a named Docker volume at `/work/repo`, dependencies out-of-tree
  at `/deps`.
- No `/var/run/docker.sock` mount; never `--privileged`.
- `--cap-drop ALL`, `--security-opt no-new-privileges`, read-only root filesystem, non-root user,
  resource caps.
- Getting work back out is host-initiated only (`sandbox cp`, a `docker cp` pull) — the container is
  never given a path back into the host.
- Network defaults to **offline** (`--network none`); `clone-then-cut` allows egress for the
  clone/build only, then severs it; an experimental `allowlist` mode exists but is not the recommended
  posture.

## Requirements

- A working Docker engine (Linux containers) — Docker Desktop (Windows/macOS, WSL2 backend) or native
  Linux.
- `nixpacks` on `PATH` (or, on Windows, inside a WSL distro — see the
  [`ca-sandbox` README](https://github.com/arbiterForge/codeArbiter/blob/main/plugins/ca-sandbox/README.md#windows--the-wsl-bridge)
  for the WSL-bridge build path). Without it, `ca-sandbox` falls back to a generated Dockerfile with
  narrower stack coverage.

## Install

```text
/plugin install ca-sandbox@codearbiter
```

Then, in the target repository:

```text
/ca-sandbox:sandbox create <repo-url>
```

## Commands

```text
sandbox create <url> [--net offline|clone-then-cut|allowlist]
sandbox shell <id> [--shell sh|bash]
sandbox exec <id> -- <cmd> [args...]
sandbox cp <id>:<containerPath> <hostDest>
sandbox destroy <id> [--keep-volume]
sandbox prune
```

## Not part of the governance kernel

`ca-sandbox` shares the marketplace with `ca`, `ca-codex`, and `ca-pi`, and its CI is path-scoped and
versioned independently of them (ADR-0007). It does not read or write `.codearbiter/`, and installing
or removing it has no effect on gate enforcement in any repository. If you're looking for the
governance hosts instead, see [Install](/getting-started/install/), [Claude Code + Codex
evidence](/getting-started/claude-code-and-codex/), or [Pi](/getting-started/pi/).

Full detail, including the Git Bash path-conversion caveat and image-caching behavior, lives in the
[`ca-sandbox` README](https://github.com/arbiterForge/codeArbiter/blob/main/plugins/ca-sandbox/README.md).
