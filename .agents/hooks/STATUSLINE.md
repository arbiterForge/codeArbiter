# codeArbiter Statusline

A custom Claude Code statusline that surfaces project state without commands. Renders as a single ANSI-colored line at the bottom of the Claude Code session.

## What it looks like

```
Clean / initialized / no blockers / fresh context, subscription user:
● stage:3 │ tasks:0 q:0 │ ⎇ main │ over:0 │ ctx:6% 5h:23% 7d:41%
└─┬─┘ └──┬──┘ └────┬────┘ └─┬─┘ └──┬──┘ └────────┬────────┘
  │     │          │        │     │              └─ context window %, plus $cost (API mode)
  │     │          │        │     │                 or 5h/7d rate limits (subscription)
  │     │          │        │     └─ overrides.log entry count (dim when 0, red when >0)
  │     │          │        └────── current git branch; green when clean, yellow + * when dirty
  │     │          └─────────────── open-tasks.md "- " count and open-questions.md CONFIRM-NN count
  │     └────────────────────────── value of .agents/projectContext/stage
  └──────────────────────────────── ● green = CONTEXT.md has <!--INITIALIZED-->; ○ yellow = not yet

API user, context approaching compaction:
○ stage:1 │ tasks:4 q:2 │ ⎇ feature/foo* │ over:1 │ ctx:92% $4.27
```

## Segments

| Segment | Source | Symbol / color logic |
|---|---|---|
| Project state | `.agents/projectContext/CONTEXT.md` sentinel + `.agents/projectContext/stage` | `●` green if `<!--INITIALIZED-->` is present in CONTEXT.md, `○` yellow if not. `stage:N` is the literal contents of the `stage` file. |
| Work queue | `open-tasks.md` (count of `^- ` lines), `open-questions.md` (count of `CONFIRM-\d+`) | `tasks:N` dim when 0, yellow when >0. `q:N` dim when 0, **red** when >0 — `CONFIRM-NN` items are blockers per `AGENTS.md §3`. |
| Git context | `git branch --show-current` + `git status --porcelain` | `⎇ branch` green when clean, yellow with trailing `*` when dirty. Falls back to `⎇ —` when not in a git repo. |
| Overrides | Non-comment lines in `.agents/projectContext/overrides.log` | `over:N` dim when 0, red when >0. Non-zero means at least one gate has been bypassed in this repo's history (audit trail). |
| Usage | Claude Code's statusline stdin JSON (`context_window.used_percentage`, `cost.total_cost_usd`, `rate_limits.{five_hour,seven_day}.used_percentage`), routed through `.agents/hooks/statusline-tokens.py` | `ctx:N%` reflects the current context window load from the latest API response. Color band: dim `<50%`, yellow `50–74%`, bright yellow `75–89%`, red `≥90%`. **API mode** (`$ANTHROPIC_API_KEY` set & non-empty) appends ` $X.XX` from `cost.total_cost_usd` (always dim). **Subscription mode** (no `ANTHROPIC_API_KEY`) appends ` 5h:N% 7d:N%` from `rate_limits.*` when present (Pro/Max only, after the first API response in the session); each window uses the same color band as `ctx:`. Auto-compaction handles the overflow case — the red band is just a heads-up to wrap up cleanly before it kicks in. The whole segment is silently omitted when stdin is empty / malformed, when `python3` is missing, or before the first API response. |

## How it's wired

The script lives at `.agents/hooks/statusline.sh`. It now *uses* (no longer drains) the JSON session blob Claude Code pipes on stdin, fanning it out to `.agents/hooks/statusline-tokens.py` (Python 3 stdlib only — no `jq` dependency). It's invoked via the project-scoped `statusLine` block in `.agents/settings.json` (mirrored to `.claude/settings.json` by symlink):

```json
"statusLine": {
  "type": "command",
  "command": "bash .agents/hooks/statusline.sh",
  "padding": 0
}
```

The script reads `$CLAUDE_PROJECT_DIR` (set by Claude Code) to locate the project root. It captures the JSON blob Claude pipes on stdin and forwards it to `statusline-tokens.py` for the `ctx:` / `$cost` / rate-limit segment. The Python helper uses stdlib only; if `python3` is missing, the usage segment is silently dropped and the rest of the line still renders.

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

The script makes ~4 file reads, 2 `git` invocations, and 1 `python3` exec per render. Target budget: <100ms on a clean repo (measured ~50ms locally with the usage helper active). If you see it lag on a very large repo, the most expensive call is `git status --porcelain`; opening a discussion to replace it with a faster dirty-check is fair game.

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
| No `ctx:N%` segment | (a) `python3` is not on `$PATH`, (b) Claude Code hasn't sent its first API response yet (`context_window` is `null` early in the session and after `/compact`), or (c) the statusline was invoked outside Claude Code so stdin was empty. Confirm with `echo '{"context_window":{"used_percentage":50}}' \| bash .agents/hooks/statusline.sh`. |
| No `$X.XX` in API mode | `cost.total_cost_usd` is 0 (nothing billed yet) or `$ANTHROPIC_API_KEY` is unset. The variable is checked at *render time*, not session start — `export`-ing it after launch takes effect on the next render. |
| No `5h:N% 7d:N%` in subscription mode | The `rate_limits` object appears only for Claude.ai Pro/Max subscribers and only after the first API response in the session. Each window can be independently absent. |
