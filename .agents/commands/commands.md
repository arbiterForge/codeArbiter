# /commands

## Purpose

Display the Quick Reference table of all available commands. Read-only. No state change. Reads `COMMANDS.md` and outputs the Quick Reference table only.

## Usage

```
/commands
```

No arguments.

## What Happens

1. Reads `COMMANDS.md` (or `${FRAMEWORK_ROOT}/.agents/COMMANDS.md` if that is the canonical location)
2. Outputs the Quick Reference table only — not the full document
3. Done. No side effects.

## Output

The Quick Reference table lists every command with:
- Command name and syntax
- One-line description
- What it routes to

Example format:

```
| Command | Description | Routes To |
|---------|-------------|-----------|
| /feature "desc" | Start a new feature — only path to implementation | tdd skill |
| /fix "desc"     | Fix a confirmed bug with a regression test first   | tdd skill |
| /commit         | Run the full commit gate                           | commit-gate skill |
| /pr             | Open a PR after all BLOCK reviews clear            | pr-ready sequence |
| /review [path]  | Targeted review with severity findings             | reviewer agents |
| /threat-model   | Pre-implementation STRIDE analysis                 | security-architecture skill |
| /adr "title"    | Create a new Architecture Decision Record          | decision-lifecycle skill |
| /adr-status     | Report ADR health — aged, unchallenged, placeholders | decision-lifecycle skill |
| /checkpoint     | Full cross-cutting codebase review                 | all 7 checkpoint agents |
| /stage [N]      | Report or advance project stage                    | stage-gating skill |
| /btw "question" | Lightweight Q&A — no routing occurs                | (none) |
| /status         | Formatted project status report                    | (none) |
| /surface-conflict | Stop all work and surface a contradiction        | (none) |
| /add-dep "pkg"  | Vet and add a dependency                           | dependency-reviewer agent |
| /override "why" | Override a gate with logging                       | (none) |
| /onboard [topic]| Interactive onboarding tour                        | onboard skill |
| /new-skill "name"| Author a new skill (5-phase process)              | skill-author skill |
| /commands       | Show this table                                    | (none) |
| /init           | Re-run initialization or restore sentinel          | (none) |
```

## Hard Gates

- Read-only — no file is modified
- No skill is invoked
- Outputs the Quick Reference table only — not prose explanations
