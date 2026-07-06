---
description: Run a single command inside a running sandbox box and capture a JSON result — exitCode, separate stdout/stderr, and a truncated flag past the byte cap. The scriptable exec seam.
argument-hint: <sandbox id> -- <command> [args...]
---

# /ca-sandbox:sandbox-exec — exec a command in the box

Run one command inside a running sandbox and get back a structured result. Unlike the interactive
shell, exec is the scriptable seam: it returns a JSON contract — `exitCode`, separated `stdout` and
`stderr`, and a `truncated` flag that trips when output exceeds the byte cap — so the result is machine-
consumable. The command runs under the box's isolation; it cannot reach the host filesystem.

This is the seam the farm dispatcher's deferred process-level sandbox (`item-3`) is shaped to use; it is
also callable directly from a test via `execInSandbox`.

## Flow

1. **Resolve the box** — find the running `ca.sandbox=1` container for the id. STOP if absent.
2. **Exec** — call `execInSandbox` in `${CLAUDE_PLUGIN_ROOT}/tools/exec.ts` with the argv after `--`.
   `exec <id> -- sh -c 'exit 7'` returns `exitCode: 7`.
3. **Report the JSON result** — `exitCode`, `stdout`, `stderr` (kept separate), and `truncated` (true
   when output passed the byte cap). The exit code is surfaced, never swallowed.

## Routes to

`sandbox-lifecycle` (`${CLAUDE_PLUGIN_ROOT}/skills/sandbox-lifecycle/SKILL.md`) — Phase 4 (interact),
via the `execInSandbox` seam in `${CLAUDE_PLUGIN_ROOT}/tools/exec.ts`.

## When NOT to use

- Interactive browsing → `/ca-sandbox:sandbox-shell`.
- Pulling a produced artifact out to the host → `/ca-sandbox:sandbox-cp`.
- No box exists yet → `/ca-sandbox:sandbox`.

## Hard gate

- MUST run only inside a running `ca.sandbox=1`-labeled container; MUST NOT introduce a bind, a
  docker-socket mount, or a dropped privilege.
- MUST return the real `exitCode` and keep `stdout`/`stderr` separate; MUST NOT collapse a non-zero
  exit into success.
- MUST honor the output byte cap — set `truncated` rather than streaming unbounded output.
- MUST NOT use exec to copy host files in or grant the box host-FS access; file egress is host-initiated
  `docker cp` out only.
