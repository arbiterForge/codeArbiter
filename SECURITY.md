# Security Policy

> This is the GitHub repository security policy: how to report a problem with the
> codeArbiter product. It is distinct from `.codearbiter/security-controls.md`, which
> is the in-repo governance doc the adapters' gates enforce on *your* code.

## What codeArbiter runs on your machine

codeArbiter provides host adapters for Claude Code, Codex, and Pi from one shared
governance core. Each adapter connects the host's lifecycle and tool events to the
generated hook payload. For full transparency about what each hook reads, writes,
and runs, see **[`docs/hooks.md`](./docs/hooks.md)**. In short:

- Hooks are stdlib-only Python, with no third-party packages and no compiled binaries.
- Hooks make exactly two bounded, nonblocking background network operations: a
  detached `git fetch` against your configured remote, which never modifies the
  remote but may update local Git metadata and objects through your configured
  transport and credential helpers; and an at-most-daily, fail-silent,
  unauthenticated HTTPS GET to the GitHub Releases API.
- Guard hooks do nothing in a repo that has not opted in (`arbiter: enabled`).
- Hooks write governance state inside your repo's `.codearbiter/` directory and may
  install or refresh the repository's `pre-commit` and `pre-push` backstops under
  its Git common directory. Hook-owned user-global state under `~/.codearbiter/`
  includes the bounded update-check cache. Host-specific setup may also install
  ca-owned integration state, such as the Claude Code statusline entry in
  `~/.claude/settings.json` (backed up and restored on removal). Hooks do not write
  source files.

## Supported versions

The Claude Code, Codex, and Pi adapters are independently packaged and versioned
from the same canonical source. Fixes target the latest published release in the
affected adapter's supported channel; please reproduce there before reporting.
The previous v1 framework on the `archive/v1` branch is unmaintained and receives
no fixes.

| Version | Supported |
|---|---|
| Latest Claude Code or Codex marketplace release | yes |
| Latest `ca-pi-v*` tag and matching npm release | yes |
| Older adapter releases | upgrade within the same channel |
| v1 (`archive/v1`) | no |

## Reporting a problem

Please report security issues **privately**. Do not open a public issue for a
suspected vulnerability.

- Preferred: open a [private security advisory][advisory] on GitHub
  (Security → Advisories → "Report a vulnerability").
- Or email **brennonhuff@gmail.com** with the details.

Helpful details to include:

- The host and adapter version, plus your OS / Python version.
- A clear description and the smallest steps to reproduce.
- The impact you observed (for example: a guard that fails to block, an audit-log
  write that should have been rejected, or any data written outside `.codearbiter/`).

[advisory]: https://github.com/arbiterForge/codeArbiter/security/advisories/new

## What to expect

- **Acknowledgement** within a few days.
- An assessment and, for confirmed issues, a fix and a coordinated release.
- Credit in the release notes if you'd like it.

Because the threat surface is primarily local (hooks run on the contributor's own
machine, expose no inbound network service, and perform no privilege escalation),
most reports will be about a guard behaving incorrectly rather than a remote
vulnerability. Those still matter (a gate that fails open is a real bug) and are
very welcome.
