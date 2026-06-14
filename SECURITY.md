# Security Policy

> This is the GitHub repository security policy — how to report a problem with the
> codeArbiter plugin. It is distinct from `.codearbiter/security-controls.md`, which
> is the in-repo governance doc the plugin's gates enforce on *your* code.

## What codeArbiter runs on your machine

codeArbiter is a Claude Code plugin. It activates through hooks — small Python
scripts Claude Code runs during a session. For full transparency about what each
hook reads, writes, and runs, see **[`docs/hooks.md`](./docs/hooks.md)**. In short:

- Hooks are stdlib-only Python — no third-party packages, no compiled binaries.
- No hook makes a network call. The only outbound process is a local, read-only
  `git fetch` against your own configured remote.
- Guard hooks do nothing in a repo that has not opted in (`arbiter: enabled`).
- Hooks write only inside your repo's `.codearbiter/` directory, plus a ca-owned
  statusline entry in `~/.claude/settings.json` (backed up and restored on removal).

## Supported versions

codeArbiter ships from a single plugin in this repository. Fixes are made against
the latest release on `main`; please reproduce on the current version before
reporting. The previous v1 framework on the `archive/v1` branch is unmaintained and
receives no fixes.

| Version | Supported |
|---|---|
| Latest release on `main` | yes |
| Older 2.x releases | upgrade to latest |
| v1 (`archive/v1`) | no |

## Reporting a problem

Please report security issues **privately** — do not open a public issue for a
suspected vulnerability.

- Preferred: open a [private security advisory][advisory] on GitHub
  (Security → Advisories → "Report a vulnerability").
- Or email **brennonhuff@gmail.com** with the details.

Helpful details to include:

- The plugin version and your OS / Python version.
- A clear description and the smallest steps to reproduce.
- The impact you observed (for example: a guard that fails to block, an audit-log
  write that should have been rejected, or any data written outside `.codearbiter/`).

[advisory]: https://github.com/arbiterForge/codeArbiter/security/advisories/new

## What to expect

- **Acknowledgement** within a few days.
- An assessment and, for confirmed issues, a fix and a coordinated release.
- Credit in the release notes if you'd like it.

Because the threat surface is local (hooks run on the contributor's own machine,
with no network calls and no privilege escalation), most reports will be about a
guard behaving incorrectly rather than a remote vulnerability. Those still matter —
a gate that fails open is a real bug — and are very welcome.
