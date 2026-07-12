---
description: Verify the install is actually enforcing — interpreter, payload, cache staleness, repo state, and a live-fire hook probe. Read-only.
argument-hint: (none)
---

# {{CMD:doctor}} — install health

Silent dormancy is the worst failure shape this plugin has: the gates look installed but never
fire, and nothing says so. It has happened — a stale plugin cache survived `claude plugin update`
because the version string was unchanged, leaving months-old hooks in place. This command proves
the install is healthy, in two parts: a mechanical static check, then a live-fire probe that the
static check cannot perform from the inside.

## Flow

1. **Static checks** — run
   `python3 "{{PLUGIN_ROOT}}/hooks/doctor.py" || python "{{PLUGIN_ROOT}}/hooks/doctor.py"`
{{IF:codex}}
   Codex does not export the plugin-root placeholder into ordinary tool calls. Resolve the active
   plugin root from this loaded skill's path (`skills/ca-doctor/SKILL.md` → two parents up) before
   running the command; do not first attempt an empty environment-variable path.
{{END}}
   and present its report verbatim. It checks: interpreter resolution (including the Microsoft
   Store python3 alias stub), plugin payload integrity (plugin.json, hooks.json, all five hook
   scripts), stale sibling versions in the plugin cache, repo activation state (CONTEXT.md
   frontmatter, `<!--INITIALIZED-->`), git identity for audit attribution{{IF:claude}}, and statusline wiring{{END}}.
2. **Live-fire probe** — only in an arbiter-enabled repo (skip and say so otherwise): attempt
   `git add --all --dry-run` via the Bash tool.
   - **BLOCKED with `[H-03]`** → the hook layer is live. Report: hooks firing.
   - **The command executes** (dry-run output, exit 0 — harmless by construction) → the hook layer
     is NOT firing despite the static checks. Report **CRITICAL: gates dormant** with the
     remediation ladder below.
3. **Verdict** — one line: healthy / degraded (WARNs) / UNHEALTHY (any FAIL or a failed probe),
   followed by the remediation for each non-OK finding.

## Remediation ladder (gates dormant despite a healthy payload)

1. Restart the {{IF:claude}}Claude Code{{ELSE}}Codex{{END}} session — hooks register at session start.
2. {{IF:claude}}`claude plugin uninstall ca` then `claude plugin install ca` — `claude plugin update`
   is NOT sufficient when the marketplace version string is unchanged; the cache keeps the old
   payload.{{ELSE}}`codex plugin remove ca-codex@codearbiter` then
   `codex plugin add ca-codex@codearbiter`; start a fresh thread and approve the changed hook set
   in `/hooks`.{{END}}
3. If dormancy was intended (no `.codearbiter/CONTEXT.md`, or frontmatter not `arbiter: enabled`),
   that is not a defect — `{{CMD:init}}` opts the repo in.

## When NOT to use

{{IF:claude}}
- Statusline wiring only → `{{CMD:statusline}} status`.
{{END}}
- Scaffold state only → `{{CMD:init}} --check`.
- Project progress, not install health → `{{CMD:status}}`.

## Hard gate

Read-only — MUST NOT modify any file, create any marker, or stage anything (the probe is
`--dry-run` by construction and is expected to be blocked). MUST NOT weaken, bypass, or retry a
blocked probe in a different spelling — the block IS the healthy result. MUST surface a failed
probe as CRITICAL, never as a footnote.
