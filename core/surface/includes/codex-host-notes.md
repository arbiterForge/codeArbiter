# Codex host notes — operational deltas from the shared surface

Load this before dispatching review/author roles, editing audit files, or
driving git in a sandboxed session. Everything here is source-verified against
the Codex tree (M0 spike) or ledgered in `docs/parity.md`; the shared skill
bodies name *actions* — this file is where those actions map to this host.

## Tool mapping

- **Shell** — the exec tool is named `Bash` (`{"command": ...}`); the pre-exec
  gate sees every invocation.
- **File edits** — every write/edit arrives as an `apply_patch` envelope; the
  write gate decomposes it per file. There is no separate edit tool.
- **File reads** — there is NO read tool; read files via shell. Governed-file
  notices that Claude receives on Read arrive here after a write instead.
- **Append-only audit logs** (`overrides.log`, `gate-events.log`,
  `sprint-log.md`): patch-based edits are positional and BLOCK outright —
  append via shell redirection (`>>`), which the exec gate permits for
  tail-appends.

## Degraded / pending surfaces (ledgered in docs/parity.md)

- **Subagents are host-provided** — current Codex releases can dispatch and
  inspect agent threads, but this plugin does not yet vendor custom agent
  definitions. Load the named reviewer/author charter, dispatch an available
  host agent with that role, and retain the returned thread ID when a workflow
  needs an exact per-agent receipt. `context-creation` requires isolated scout
  reports and MUST NOT run inline; it blocks if the host exposes no isolated
  subagents. For other workflows on an older host, perform the role inline; a
  review is never skipped because dispatch is unavailable.
- **No statusline** — governance state (stage, overrides-since-checkpoint,
  in-flight tasks) appears in the startup briefing instead.
- **No transcript prune** — the prune engine is Claude-transcript-specific;
  audit-staleness warnings still fire on prompt submit.
- **No `--farm` backend** — the farm worker files (`tools/farm.js`,
  `tools/plan.schema.json`) are not vendored into this plugin yet (M5
  distribution decision). A `--farm` flag degrades to the normal
  premium-subagent path; say so rather than failing quietly.

## Sandbox and git caveats

- A sandboxed workspace may check out a detached HEAD or a linked worktree.
  Before any branch operation, verify `git rev-parse --abbrev-ref HEAD` and
  `git rev-parse --git-common-dir` match your expectation.
- If the sandbox blocks network push or PR creation, stop at a clean local
  commit (through the commit gate as always) and hand the push/PR step to the
  user — never bypass the gate to work around the sandbox.
- Hooks run only after the user trusts the plugin's hook set; if gates appear
  silent, inspect `/hooks`, then invoke `$ca-doctor`. Ordinary tool calls do
  not inherit the hook runner's plugin-root environment; the doctor skill
  derives its root from its own installed `SKILL.md` path.
