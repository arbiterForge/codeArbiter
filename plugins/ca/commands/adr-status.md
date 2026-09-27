---
description: "Inspect ADR health read-only; optionally select one ADR with --adr N."
argument-hint: "(none) | --adr N"
disable-model-invocation: true
---

# /ca:adr-status — read-only mode adapter

Load `${CLAUDE_PLUGIN_ROOT}/skills/decision-lifecycle/SKILL.md` in **status only** mode,
passing the unchanged arguments. The owner validates `(none) | --adr N` before
any authoring prerequisite. Return its report; do not invoke `/ca:adr` or
continue to authoring. Read-only — MUST NOT modify any file.
