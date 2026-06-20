---
description: Copy a file OUT of a running sandbox box to the host — host-initiated egress only (docker cp). The reverse, a host→container bind, is impossible by construction.
argument-hint: "<sandbox id>:/work/<file> ./dest"
---

# /ca-sandbox:sandbox-cp — copy a file out of the box

The one sanctioned way to get a file out of an isolated box. Copy is **host-initiated egress only**: the
host pulls a file from the box via `docker cp`. There is no path for the box to push files to the host,
and there is no host→container bind to copy *in* — the mount builder rejects every bind spec, so the
reverse direction is impossible by construction, not by policy.

Use it to extract a build artifact, a generated report, or a file you produced while exploring — without
ever giving the untrusted code a writable window onto your filesystem.

## Flow

1. **Resolve the box** — find the running `ca.sandbox=1` container for the id. STOP if absent.
2. **Copy out** — call `cpOut` in `${CLAUDE_PLUGIN_ROOT}/tools/cp.ts`: `cp <id>:/work/<f> ./dest`
   over `docker cp`. The source is inside the box; the destination is a host path.
3. **Confirm** — report the host destination the file landed at.

## Routes to

`sandbox-lifecycle` (`${CLAUDE_PLUGIN_ROOT}/skills/sandbox-lifecycle/SKILL.md`) — Phase 4 (interact),
via the `cpOut` seam in `${CLAUDE_PLUGIN_ROOT}/tools/cp.ts`.

## When NOT to use

- Browsing or running things in the box → `/ca-sandbox:sandbox-shell`, `/ca-sandbox:sandbox-exec`.
- Tearing the box down → `/ca-sandbox:sandbox-destroy`.
- No box exists yet → `/ca-sandbox:sandbox`.

## Hard gate

- MUST be host-initiated egress (`docker cp` OUT) only. MUST NOT establish a host→container bind to copy
  files in — the mount builder rejects every bind, and this command MUST NOT route around it.
- MUST copy only from a running `ca.sandbox=1`-labeled container; MUST NOT mount, create, or modify any
  container or volume.
- MUST NOT grant the box write access to a host path under cover of a copy; the only data flow is the
  host reading one file out.
