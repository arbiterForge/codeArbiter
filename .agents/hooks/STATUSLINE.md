# codeArbiter Statusline

A custom Claude Code statusline that surfaces project state without commands. Renders as a single ANSI-colored line at the bottom of the Claude Code session.

## What it looks like

```
Clean / initialized / no blockers:
● stage:3 │ tasks:0 q:0 │ ⎇ main │ over:0
└─┬─┘ └──┬──┘ └────┬────┘ └─┬─┘ └──┬──┘
  │     │          │        │     └─ overrides.log entry count (dim when 0, red when >0)
  │     │          │        └────── current git branch; green when clean, yellow + * when dirty
  │     │          └─────────────── open-tasks.md "- " count and open-questions.md CONFIRM-NN count
  │     └────────────────────────── value of .agents/projectContext/stage
  └──────────────────────────────── ● green = CONTEXT.md has <!--INITIALIZED-->; ○ yellow = not yet

Pre-init, dirty tree, blockers present:
○ stage:1 │ tasks:4 q:2 │ ⎇ feature/foo* │ over:1
```

## Segments

| Segment | Source | Symbol / color logic |
|---|---|---|
| Project state | `.agents/projectContext/CONTEXT.md` sentinel + `.agents/projectContext/stage` | `●` green if `<!--INITIALIZED-->` is present in CONTEXT.md, `○` yellow if not. `stage:N` is the literal contents of the `stage` file. |
| Work queue | `open-tasks.md` (count of `^- ` lines), `open-questions.md` (count of `CONFIRM-\d+`) | `tasks:N` dim when 0, yellow when >0. `q:N` dim when 0, **red** when >0 — `CONFIRM-NN` items are blockers per `AGENTS.md §3`. |
| Git context | `git branch --show-current` + `git status --porcelain` | `⎇ branch` green when clean, yellow with trailing `*` when dirty. Falls back to `⎇ —` when not in a git repo. |
| Overrides | Non-comment lines in `.agents/projectContext/overrides.log` | `over:N` dim when 0, red when >0. Non-zero means at least one gate has been bypassed in this repo's history (audit trail). |

## How it's wired

The script lives at `.agents/hooks/statusline.sh`. It's invoked via the project-scoped `statusLine` block in `.agents/settings.json` (mirrored to `.claude/settings.json` by symlink):

```json
"statusLine": {
  "type": "command",
  "command": "bash .agents/hooks/statusline.sh",
  "padding": 0
}
```

The script reads `$CLAUDE_PROJECT_DIR` (set by Claude Code) to locate the project root. It drains stdin (Claude pipes a JSON session blob) but doesn't parse it — no `jq` dependency.

## Turning it off

Two mechanisms, in priority order:

### 1. Env-var toggle (per-shell, transient)

```sh
export CODEARBITER_STATUSLINE=off
```

The script exits with empty output. Useful when running in a terminal where ANSI rendering is broken, or when you want a quiet session.

### 2. User-scope override (per-user, persistent)

Drop a competing `statusLine` block into `.claude/settings.local.json` (which is gitignored by Claude Code convention):

```json
{ "statusLine": null }
```

Or replace it with your own command:

```json
{
  "statusLine": {
    "type": "command",
    "command": "my-own-statusline.sh"
  }
}
```

User-scope settings beat project-scope, so this wins without modifying the committed config.

## Performance

The script makes ~4 file reads and 2 `git` invocations per render. Target budget: <100ms on a clean repo. If you see it lag on a very large repo, the most expensive call is `git status --porcelain`; opening a discussion to replace it with a faster dirty-check is fair game.

## Portability note

This doc lives under `.agents/` so it travels with the framework when consumed as a `git submodule`, `git subtree`, or future Claude Code plugin. The root `README.md` references this file but is not authoritative — root files don't follow imports.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Statusline shows `stage:?` | `.agents/projectContext/stage` is missing or empty. |
| Statusline shows `⎇ —` | Not running inside a git working tree, or `git` not on `$PATH`. |
| All segments dim | `$CLAUDE_PROJECT_DIR` points somewhere without a `.agents/` tree. Check Claude Code's CWD. |
| Garbled symbols (e.g. `\033[32m●`) | Terminal isn't interpreting ANSI escapes. Use `CODEARBITER_STATUSLINE=off`. |
| Statusline missing entirely | `bash .agents/hooks/statusline.sh < /dev/null` from a TTY to reproduce. Check that the file is executable and the JSON in `.agents/settings.json` parses. |
