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
  tail-appends. **On Windows PowerShell 5.1, do not use bare `>>` (or
  `Add-Content`) against an existing UTF-8 log.** PowerShell 5.1's default
  redirection/cmdlet encoding is UTF-16LE, not UTF-8 — appending with `>>`
  writes the NEW tail as UTF-16LE while the EXISTING file stays UTF-8,
  introducing NUL bytes and forcing a destructive H-05 override to repair
  (#594). Use an explicit UTF-8-no-BOM append instead:

  ```powershell
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::AppendAllText('.codearbiter/sprint-log.md', $entry, $utf8NoBom)
  ```

  This is a plain PowerShell statement (no `powershell`/`pwsh` sub-invocation
  token on the line), so it reads as an ordinary append to the exec gate —
  exactly like `>>` — while forcing the encoding the file already uses.
  **Verify before trusting the write**: a UTF-16LE tail introduces a NUL
  byte after every ASCII character, so `Select-String -Path
  .codearbiter/sprint-log.md -Pattern "\x00" -Encoding Byte` returning no
  match confirms the file stayed single-byte UTF-8 end to end.

## Degraded / pending surfaces (ledgered in docs/parity.md)

- **Subagents are host-provided** — current Codex releases can dispatch and
  inspect agent threads. Resource charters are Markdown resources, never
  native custom-agent registrations. Ordinary Markdown routes resolve their
  resources from the current generated file by normalized relative link; only
  hook configuration receives the native `PLUGIN_ROOT` token. The legacy
  `CLAUDE_PLUGIN_ROOT` hook alias is matching corroboration only and emits a
  non-disruptive deprecation diagnostic. Dispatch an available host agent with
  the loaded charter and retain the returned thread ID when a workflow
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
