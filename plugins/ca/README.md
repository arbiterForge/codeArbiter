# codeArbiter (`ca`)

An orchestration layer for Claude Code that refuses to freelance. Every intent routes through a
slash command to a gated skill or reviewer agent; nothing commits until the gates are green;
decisions go through SMARTS; the audit trail (`overrides.log`, `triage.log`, ADRs, sprint log) is
append-only and mechanically guarded.

Full documentation, install instructions, and the command catalog live in the
[repository README](https://github.com/arbiterForge/codeArbiter) and in [`COMMANDS.md`](./COMMANDS.md).

Typed-plan approval preflight reads bounded task verification definitions, checks
all declared commands, collects the source snapshot and rechecks plan identity
before arming approval. Proposed tests can be absent; preflight executes no
declared command or test discovery.

## The short version

- **Install:** `/plugin marketplace add arbiterForge/codeArbiter` → `/plugin install ca@codearbiter`.
- **Prerequisites:** Python 3 on `PATH` (all hooks are Python); `git config user.email` set
  (audit attribution). Optional `/ca:statusline` writes to your global `~/.claude/settings.json`
  (backed up; restored on removal).
- **Activation is per-repo and explicit:** `/ca:init` scaffolds `.codearbiter/` with
  `arbiter: enabled`. Without that flag, repository persona delivery, governed repository
  enforcement and governance rows remain dormant. Before this check, SessionStart can settle
  session mode markers and repair an existing ca-owned global statusline pin. It preserves
  user-owned statusline configuration and the existing ownership boundaries.
- **Drive it:** `/ca:feature` (spec-driven, with a logged small lane for small changes),
  `/ca:fix`, `/ca:chore`, `/ca:spike`, `/ca:sprint` (autonomous, every decision logged),
  `/ca:commit`, `/ca:audit`. [`COMMANDS.md`](./COMMANDS.md) lists everything.
- **Local writes:** governance records live in `.codearbiter/`. Opted-in operation also maintains
  managed Git hooks and their Git-common enforcer registry, trusted executable identities and
  bookkeeping. The task-board writer retains its OS-lock sidecar and adds its exact ignore rule
  through Git-common `info/exclude` under an exclusive lock. These existing owners preserve
  foreign hooks and unrelated configuration. Uninstalling leaves your project record intact.

## Feature Forge (preview)

Some features ship in the box but aren't yet *blessed*: off by default, fully dormant until you opt
in, labeled `preview` until real-world data earns them a stable promotion. In the forge now: **live
transcript pruning** (`CODEARBITER_PRUNE`), which trims redundant transcript clutter to extend a
session. Run it in `dry` mode (`export CODEARBITER_PRUNE=dry`) and it logs what it *would* prune,
separating model-context savings from file-only sidecar cleanup (aggregate sizes and verdicts only,
no transcript content), to `~/.codearbiter/metrics/prune-dry.jsonl`. Sending
that log back ([open a prune-data issue](https://github.com/arbiterForge/codeArbiter/issues/new?title=Feature+Forge%3A+prune+data&labels=feature-forge,prune))
is what moves it toward `on`. Also in the forge: the **farm** (`/ca:sprint --farm`, needs
`FARM_API_KEY`), a pluggable backend that runs the *implementation* step on cheap OpenAI-compatible
workers (OpenCode Zen by default); Claude still writes the spec, the failing tests, and the plan, and
every task clears the full review chain. Off by default and `preview` until validated. A third preview,
the `ca-sandbox` container-isolation plugin, ships as a separate marketplace install. Full detail in the
[Feature Forge section of the repo README](https://github.com/arbiterForge/codeArbiter#feature-forge).

## What's in this directory

`ORCHESTRATOR.md` (the persona injected in enabled repos) · `commands/` · `skills/` · `agents/` ·
`hooks/` (SessionStart injection + PreToolUse/PostToolUse gates) · `includes/` (routing table,
reference map, farm setup) · `tools/` (the `--farm` dispatcher) · `SPRINT.md` (the `/ca:sprint`
mode body).
