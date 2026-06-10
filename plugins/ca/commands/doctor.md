---
description: Verify the install is actually enforcing — interpreter, payload, cache staleness, repo state, and a live-fire hook probe. Read-only.
argument-hint: (none)
---

# /ca:doctor — install health

Silent dormancy is the worst failure shape this plugin has: the gates look installed but never
fire, and nothing says so. It has happened — a stale plugin cache survived `claude plugin update`
because the version string was unchanged, leaving months-old hooks in place. This command proves
the install is healthy, in two parts: a mechanical static check, then a live-fire probe that the
static check cannot perform from the inside.

## Flow

1. **Static checks** — run
   `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/doctor.py" || python "${CLAUDE_PLUGIN_ROOT}/hooks/doctor.py"`
   and present its report verbatim. It checks: interpreter resolution (including the Microsoft
   Store python3 alias stub), plugin payload integrity (plugin.json, hooks.json, all five hook
   scripts), stale sibling versions in the plugin cache, repo activation state (CONTEXT.md
   frontmatter, `<!--INITIALIZED-->`), git identity for audit attribution, and statusline wiring.
2. **Live-fire probe** — only in an arbiter-enabled repo (skip and say so otherwise): attempt
   `git add --all --dry-run` via the Bash tool.
   - **BLOCKED with `[H-03]`** → the hook layer is live. Report: hooks firing.
   - **The command executes** (dry-run output, exit 0 — harmless by construction) → the hook layer
     is NOT firing despite the static checks. Report **CRITICAL: gates dormant** with the
     remediation ladder below.
3. **Verdict** — one line: healthy / degraded (WARNs) / UNHEALTHY (any FAIL or a failed probe),
   followed by the remediation for each non-OK finding.

## Remediation ladder (gates dormant despite a healthy payload)

1. Restart the Claude Code session — hooks register at session start.
2. `claude plugin uninstall ca` then `claude plugin install ca` — `claude plugin update` is NOT
   sufficient when the marketplace version string is unchanged; the cache keeps the old payload.
3. If dormancy was intended (no `.codearbiter/CONTEXT.md`, or frontmatter not `arbiter: enabled`),
   that is not a defect — `/ca:init` opts the repo in.

## When NOT to use

- Statusline wiring only → `/ca:statusline status`.
- Scaffold state only → `/ca:init --check`.
- Project progress, not install health → `/ca:status`.

## Hard gate

Read-only — MUST NOT modify any file, create any marker, or stage anything (the probe is
`--dry-run` by construction and is expected to be blocked). MUST NOT weaken, bypass, or retry a
blocked probe in a different spelling — the block IS the healthy result. MUST surface a failed
probe as CRITICAL, never as a footnote.
