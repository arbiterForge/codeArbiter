---
entity: commands/doctor
related: [statusline, preview]
---

## What it does

Proves the install is actually enforcing, rather than just present. codeArbiter's worst failure
shape is silent dormancy: a plugin cache surviving `claude plugin update` unchanged, hooks that
look wired but never fire, and nothing that says so. This command checks in two parts. First a
static pass — interpreter resolution, plugin payload integrity, stale cached versions, repo
activation state, git identity, statusline wiring — reported one `OK`/`WARN`/`FAIL` line per
check. Then, in an arbiter-enabled repo, a live-fire probe: it actually attempts a real,
gate-tripping command (a dry-run `git add --all`) and checks whether the hook layer blocks it. A
healthy install blocks the probe; if the probe instead executes, that is reported as CRITICAL —
the static checks alone cannot catch a hook that's registered but not actually firing.

It is read-only end to end. Because the probe uses `--dry-run`, getting blocked is the outcome it
wants to see — that block is the passing verdict, not a failure to route around.

## Usage

```
/ca:doctor
```

Takes no arguments.

## Example

```text
> /ca:doctor

OK      python3 resolves and runs (/usr/bin/python3)
OK      plugin payload at /home/x/.claude/plugins/ca (version 2.8.11)
OK      hooks.json parses: 6 events, 11 entries
OK      all 6 hook scripts present
OK      single cached plugin version (no stale siblings)
OK      repo is arbiter-enabled (CONTEXT.md frontmatter)
OK      project is initialized (<!--INITIALIZED--> marker present)
OK      git identity for audit attribution: dev@example.com
OK      statusline wired in ~/.claude/settings.json

doctor: 0 FAIL, 0 WARN, 9 OK
verdict: healthy (static checks) — the live-fire probe in /ca:doctor proves hooks actually fire

live-fire probe: git add --all --dry-run
BLOCKED [H-03]: 'git add -A' / 'git add .' / 'git add --all' / 'git add -u' are
prohibited. Stage files explicitly (commit-gate skill).

verdict: healthy — hooks firing
```

## When to reach for it

Statusline wiring only is a narrower question answered by `/ca:statusline status`; scaffold state
alone by `/ca:init --check`; project progress (not install health) by `/ca:status`.
