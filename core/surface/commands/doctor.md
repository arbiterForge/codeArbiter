---
description: Verify the active host install, package, command ownership, enforcement{{IF:pi}}, wrapper self-test, and active-dispatch coverage gap{{ELSE}}, and harmless live-fire probe{{END}}. Read-only.
argument-hint: (none)
---

# {{CMD:doctor}} — install health

Silent dormancy is the worst failure shape this plugin has: the gates look installed but never fire.
This command proves the active host is healthy and reports every non-OK finding with an exact
remediation.

## Flow

{{IF:claude}}
1. Run `python3 "{{PLUGIN_ROOT}}/hooks/doctor.py" || python "{{PLUGIN_ROOT}}/hooks/doctor.py"`
   and present its report verbatim.
2. In an arbiter-enabled repo, attempt `git add --all --dry-run` via Bash. `[H-03]` means hooks are
   firing; execution means **CRITICAL: gates dormant**.
{{END}}
{{IF:codex}}
1. Resolve the plugin root from this loaded skill path, then run its `hooks/doctor.py` with Python 3
   and present the report verbatim. Do not try an empty plugin-root environment variable first.
2. In an arbiter-enabled repo, attempt `git add --all --dry-run` via the shell tool. `[H-03]` means
   hooks are firing; execution means **CRITICAL: gates dormant**.
{{END}}
{{IF:pi}}
1. The `/ca-doctor` alias has already run the extension's structured Pi doctor report before sending
   this generated skill. Present the `<codearbiter-doctor-report>` block below verbatim.
2. The report inspects, without granting trust: active Git package origin/version, exact Pi CLI and
   module package identity, stable Pi/Node/Python support, shared-core and bridge paths, command and
   native-equivalent skill-expansion ownership, child/ambient-marker state, and final wrapper sources.
3. Its `wrapper-self-test` row submits only `git add --all --dry-run` directly to the stored governed
   Pi bash wrapper. The exact shared-core `[H-03]` block is healthy and cannot stage files; execution
   or a different block is unhealthy. This self-test does not traverse Pi's active dispatcher. Do not
   rerun or respell it.
4. Its `active-dispatch` row remains degraded because supported Pi 0.80.5/0.80.6 public extension
   APIs cannot submit that deterministic call through the active dispatcher. PI-AC-28 remains blocked
   until supported-version real-host promotion/CI evidence closes the gap.
{{END}}

## Remediation ladder

{{IF:claude}}
1. Restart Claude Code so hooks register at session start.
2. Uninstall and reinstall `ca`; an unchanged marketplace version can preserve stale cache bytes.
{{END}}
{{IF:codex}}
1. Restart Codex so hooks register at session start.
2. Remove and re-add `ca-codex@codearbiter`, then approve the changed hook set in `/hooks`.
{{END}}
{{IF:pi}}
1. Restart Pi so package resources and final wrappers register in one fresh process.
2. Reinstall `ca-pi` from the approved pinned Git tag. For project-local packages, inspect `/trust`
   and grant trust only if you accept that source; codeArbiter never grants it.
{{END}}
3. If dormancy was intended, `{{CMD:init}}` opts the repository in.

## When NOT to use

{{IF:claude}}
- Statusline wiring only → `{{CMD:statusline}} status`.
{{END}}
- Scaffold state only → `{{CMD:init}} --check`.
- Project progress, not install health → `{{CMD:status}}`.

## Hard gate

Read-only. MUST NOT create markers, stage files, grant trust, weaken a block, or {{IF:pi}}retry the
wrapper self-test with different spelling. MUST preserve the degraded active-dispatch diagnosis until
supported-version real-host promotion/CI evidence closes PI-AC-28.{{ELSE}}retry the live-fire
probe with different spelling. MUST surface a failed probe as CRITICAL, never as a footnote.{{END}}
