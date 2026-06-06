---
arbiter: enabled
stage: 2
---
<!--INITIALIZED-->

# Project: codeArbiter

The orchestration framework itself. This `.codearbiter/` directory is the v2
project-state store — root-level, outside `.claude/`, so it survives even if the
codeArbiter plugin is uninstalled. The `arbiter: enabled` frontmatter above is the
single activation flag: it gates both the SessionStart persona injection and the
arbiter statusline segments.

## Identity
A Claude Code plugin that routes work through gated skills and reviewer agents,
enforces spec-driven TDD and commit gates, decides via SMARTS, and keeps an
append-only audit trail. Decisive, terse, high-authority.

## Scope
Framework source: `ORCHESTRATOR.md`, `skills/`, `commands/`, `agents/`, `hooks/`.
Project state lives here in `.codearbiter/`.

## NOT this project
Not a vendored/multi-platform framework. Not an enterprise compliance suite.
Claude Code only. Solo developer. See `legacy/ASSESSMENT.md` for the v2 cut list.
