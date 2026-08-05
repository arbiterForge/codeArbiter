---
description: Verify the active host install, package, command ownership, enforcement, and harmless live-fire probe. Read-only.
argument-hint: (none)
---

# /ca:doctor — install health

Silent dormancy is the worst failure shape this plugin has: the gates look installed but never fire.
This command proves the active host is healthy and reports every non-OK finding with an exact
remediation.

## Flow

1. Resolve the interpreter once by presence — `PY=python3; { command -v python3 >/dev/null 2>&1 && python3 --version >/dev/null 2>&1; } || PY=python` — never `python3 X || python X`, which reruns X on any nonzero exit and reports the second run's code instead of the first's (#577). Run
   `"$PY" "${CLAUDE_PLUGIN_ROOT}/hooks/doctor.py"` and present its report verbatim.
2. In an arbiter-enabled repo, attempt `git add --all --dry-run` via Bash. `[H-03]` means hooks are
   firing; execution means **CRITICAL: gates dormant**.

## Remediation ladder

1. Restart Claude Code so hooks register at session start.
2. Uninstall and reinstall `ca`; an unchanged marketplace version can preserve stale cache bytes.
3. If dormancy was intended, `/ca:init` opts the repository in.

## When NOT to use

- Statusline wiring only → `/ca:statusline status`.
- Scaffold state only → `/ca:init --check`.
- Project progress, not install health → `/ca:status`.

## Hard gate

Read-only. MUST NOT create markers, stage files, grant trust, weaken a block, or retry the live-fire
probe with different spelling. MUST surface a failed probe as CRITICAL, never as a footnote.
