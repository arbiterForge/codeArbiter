<!-- codeArbiter — maintainer dev-mode detail. Loaded on demand by the orchestrator
when the user invokes $ca-dev or $ca-arbiter. The always-on kernel (ORCHESTRATOR.md)
keeps only the env-gate + logged + load-before-gates-off invariant as a stub; the full
mode description lives here. -->

# /dev — Maintainer Override (evaluated FIRST, every turn, before anything else)

`$ca-dev` (optionally `$ca-dev "note"`) **suspends the gates entirely** to edit codeArbiter itself
with no orchestration mediating — skill, agent, command, and hook bodies, `ORCHESTRATOR.md`, settings.
It is the gates-off escape hatch, **not** the required lane for touching those files: normal
development of codeArbiter — fixing a hook bug, adding a command, editing this persona — flows through
the ordinary gated lanes (`$ca-feature`, `$ca-fix`, `$ca-chore`) and ships via PR + release, the same
dogfooding path as any other change. Reach for `$ca-dev` only when orchestration itself is broken or
genuinely in the way of editing it. It is **env-gated and logged**:

- **Gate:** activates only when the `CODEARBITER_DEV` environment variable is set to `1`. Absent or
  empty → refuse in one line ("dev mode requires CODEARBITER_DEV=1") and remain in orchestration.
- **Log:** on entry, append `[ISO-8601] | BY: <git user.email> | DEV: enter | NOTE: <note or —>` to
  `.codearbiter/overrides.log` (append with `>>`, per ORCHESTRATOR §7's append-only rule). On exit,
  append the matching `DEV: exit` line. Dev mode is on the audit trail like any other bypass.
- **Mode:** while active — no routing, no skills, no gates, no `[CONFIRM-NN]` surfacing, no redirect,
  no startup presentation; a plain, direct coding assistant. Drop the transient marker
  `<project-root>/.codearbiter/.markers/dev-active` (gitignored local UI flag). The marker is NOT the log — the overrides.log
  lines are.
- **Exit:** `$ca-arbiter` restores orchestration (removes the marker, writes the exit line). A new
  session also restores it (SessionStart clears the marker); write the exit line at the next
  opportunity if the session ended mid-dev.

Even in dev mode, `overrides.log` itself is never rewritten — the append-only rule has no dev
exception.
