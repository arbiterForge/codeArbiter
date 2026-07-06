---
description: Open an interactive shell inside a running sandbox box at /work/repo. Read-only root, non-root user, no host-FS access — explore the untrusted code interactively, then exit.
argument-hint: <sandbox id>
---

# /ca-sandbox:sandbox-shell — interactive shell in the box

Drop into a shell inside a running sandbox to poke at the code by hand. The shell lands at
`/work/repo` as a non-root user, on a read-only root filesystem, with the same structural isolation the
box was started under — nothing you do in the shell can reach the host filesystem.

This is the interactive sibling of `/ca-sandbox:sandbox-exec`: use the shell to browse and experiment,
use exec for a single scripted command with a captured JSON result.

## Flow

1. **Resolve the box** — find the running container for the given sandbox id (labeled `ca.sandbox=1`).
   STOP if no such box is running.
2. **Attach a shell** — `docker exec -it <id> sh` (or the box's shell) at `/work/repo`, inheriting the
   container's non-root user and read-only root.
3. **Exit cleanly** — leaving the shell returns to the host; the box keeps running until
   `/ca-sandbox:sandbox-destroy`.

## Routes to

`sandbox-lifecycle` (`${CLAUDE_PLUGIN_ROOT}/skills/sandbox-lifecycle/SKILL.md`) — Phase 4 (interact).
The shell attaches through the same isolation the run established; it introduces no new mount, socket,
or privilege.

## When NOT to use

- A single scripted command with a captured exit code / JSON result → `/ca-sandbox:sandbox-exec`.
- Pulling a file out to the host → `/ca-sandbox:sandbox-cp`.
- No box exists yet → `/ca-sandbox:sandbox`.

## Hard gate

- MUST attach only to a running `ca.sandbox=1`-labeled container; MUST NOT create or mount anything new.
- MUST NOT re-introduce a host bind, a docker-socket mount, or any dropped privilege when attaching.
- The shell runs as the container's non-root user on the read-only root — MUST NOT elevate to root or
  remount the root writable.
- MUST NOT copy host files into the box via the shell session; egress and ingress remain host-initiated
  `docker cp` (out only), handled by `/ca-sandbox:sandbox-cp`.
