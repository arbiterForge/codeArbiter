# codeArbiter (`ca`)

An orchestration layer for Claude Code that refuses to freelance. Every intent routes through a
slash command to a gated skill or reviewer agent; nothing commits until the gates are green;
decisions go through SMARTS; the audit trail (`overrides.log`, `triage.log`, ADRs, sprint log) is
append-only and mechanically guarded.

Full documentation, install instructions, and the command catalog live in the
[repository README](https://github.com/SUaDtL/codeArbiter) and in [`COMMANDS.md`](./COMMANDS.md)
(`/ca:commands` in-session).

## The short version

- **Install** — `/plugin marketplace add SUaDtL/codeArbiter` → `/plugin install ca@codearbiter`.
- **Prerequisites** — Python 3 on `PATH` (all hooks are Python); `git config user.email` set
  (audit attribution). Optional `/ca:statusline` writes to your global `~/.claude/settings.json`
  (backed up; restored on removal).
- **Activation is per-repo and explicit** — the plugin is dormant everywhere until you run
  `/ca:init` in a repo, which scaffolds `.codearbiter/` with `arbiter: enabled`. No `.codearbiter/`,
  no behavior: hooks exit immediately, nothing is injected, nothing is blocked.
- **Drive it** — `/ca:feature` (spec-driven, with a logged small lane for small changes),
  `/ca:fix`, `/ca:chore`, `/ca:spike`, `/ca:sprint` (autonomous, every decision logged),
  `/ca:commit`, `/ca:audit`. `/ca:commands` lists everything.
- **What it writes to your repo** — `.codearbiter/` only. Uninstalling the plugin leaves your
  project state intact and yours.

## Feature Forge (preview)

Some features ship in the box but aren't yet *blessed* — off by default, fully dormant until you opt
in, labeled `preview` until real-world data earns them a stable promotion. In the forge now: **live
transcript pruning** (`CODEARBITER_PRUNE`), which trims redundant transcript clutter to extend a
session. Run it in `dry` mode (`export CODEARBITER_PRUNE=dry`) and it logs what it *would* prune —
sizes and verdicts only, no transcript content — to `~/.codearbiter/metrics/prune-dry.jsonl`. Sending
that log back ([open a prune-data issue](https://github.com/SUaDtL/codeArbiter/issues/new?title=Feature+Forge%3A+prune+data&labels=feature-forge,prune))
is what moves it toward `on`. Full detail in the [Feature Forge section of the repo README](https://github.com/SUaDtL/codeArbiter#feature-forge).

## What's in this directory

`ORCHESTRATOR.md` (the persona injected in enabled repos) · `commands/` · `skills/` · `agents/` ·
`hooks/` (SessionStart injection + PreToolUse/PostToolUse gates) · `includes/` (routing table,
reference map, farm setup) · `tools/` (the `--farm` dispatcher) · `SPRINT.md` (the `/ca:sprint`
mode body).
