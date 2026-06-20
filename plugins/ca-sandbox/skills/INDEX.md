# skills — catalog (surface scan)

Skill bodies load on routing only. This index is the surface scan; never bulk-read
`skills/*/SKILL.md`. Each skill is a lifecycle routine with gated phases — routed to by a
`/ca-sandbox:` command, never "triggered."

| Skill | Routed to by | Owns |
|---|---|---|
| [sandbox-lifecycle](sandbox-lifecycle/SKILL.md) | `/ca-sandbox:sandbox`, `/ca-sandbox:sandbox-shell`, `/ca-sandbox:sandbox-exec`, `/ca-sandbox:sandbox-cp`, `/ca-sandbox:sandbox-destroy` | The lifecycle gate: five phases — pre-flight & policy, clone & build, isolated run, interact, teardown. The load-bearing invariant is structural — untrusted code in the box can never reach the host FS (no bind mount, no docker socket, never `--privileged`, cap-drop ALL, non-root, read-only root). Network defaults to offline; egress out is host-initiated (`docker cp`) only; every object is labeled `ca.sandbox=1` and torn down on exit. |
| [sandbox-claude-inside](sandbox-claude-inside/SKILL.md) | `/ca-sandbox:sandbox --with-claude` | Run Claude Code INSIDE a box: five phases — posture, image, token, run, teardown. Auth via an env-injected `CLAUDE_CODE_OAUTH_TOKEN` with no host bind of `~/.claude`; HOME on a named volume so state persists across restart. Hard default: offline or Anthropic-domains-only egress, and the token volume is NEVER co-mounted with an untrusted-code run — both enforced, not advised. |
