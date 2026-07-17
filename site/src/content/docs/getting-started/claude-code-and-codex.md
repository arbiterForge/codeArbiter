---
title: Claude Code + Codex
description: Verified shared enforcement and project-context parity across Claude Code and Codex, including evidence, installation status, and intentional host differences.
---

# Shared enforcement and project-context parity across Claude Code and Codex

**Documentation launch: 2026-07-12.** This page announces the verified 2026-07-11 Codex support
result while retaining the public-marketplace smoke test as a release gate.

Of codeArbiter's four sibling plugins, this page covers two: `ca` for Claude Code and `ca-codex` for
OpenAI Codex (see [Pi](/getting-started/pi/) for the third governance host, and
[ca-sandbox](/guides/ca-sandbox/) for the non-governance infrastructure plugin). Both activate from
the same `.codearbiter/CONTEXT.md`, enforce the same project rules, and read and write the same
checked-in `.codearbiter/` state. One person can alternate between hosts, or two people can use
different hosts in the same repository, without creating parallel governance state.

Parity here has a precise boundary. The enforcement decisions and project context are shared. The
host interfaces are not identical, and this page lists those intentional differences rather than
hiding them behind a broader claim.

## Verified live on 2026-07-11

The promotion test ran on Windows with **Codex CLI 0.144.1** and **ca-codex 0.2.4**. This is a dated
verification record, not a promise that future doctor versions will always contain the same number
of checks.

| Check | Observed result |
|---|---|
| Hook review | The ca-codex hook set was reviewed and trusted through `/hooks`. |
| Session activation | The SessionStart hook completed and injected the codeArbiter persona and startup state. |
| Static doctor | `$ca-doctor` reported **9 OK, 0 WARN, 0 FAIL** for that verification run. |
| Live enforcement | The doctor probe attempted `git add --all --dry-run`; PreToolUse blocked it with **`[H-03]`** and surfaced the exact feedback. |

The detailed repository ledger is [`docs/parity.md`](https://github.com/arbiterForge/codeArbiter/blob/main/docs/parity.md).
The reproducible live procedure is
[`docs/codex-parity-testing.md`](https://github.com/arbiterForge/codeArbiter/blob/main/docs/codex-parity-testing.md).
Those files remain the canonical technical record; this page is the public summary.

## Verified continuously

CI and local verification cover the seams that a one-time live run cannot:

- the pinned Codex 0.144.1 package schema and marketplace shape;
- native Codex payload adaptation for shell and `apply_patch` tool calls;
- the complete hook guard matrix;
- Windows, macOS, and Linux interpreter-launch shapes through the cold-install matrix;
- deterministic generation of both host surfaces from `core/surface/`;
- byte-identical vendoring of the shared Python hook core into both plugins;
- dual-host initialization against one store; and
- controlled concurrent append-only audit writes with host attribution and no lost records.

The live and CI evidence complement each other. CI proves deterministic parity for equivalent
payloads; the live run proves Codex actually discovers, trusts, invokes, and honors the installed
hooks.

## Use one repository from either host

Commit `.codearbiter/` with the repository. It contains project context, plans, decisions, task and
question boards, and append-only audit records. Neither plugin copies that state into a host-owned
directory.

When Claude Code and Codex open the same checkout, they see the same maturity stage, open work,
ADRs, and audit history. A second user on another checkout receives that state through normal Git
collaboration. Initialization is idempotent: the second host observes the existing store instead of
creating another one.

## Install status

The public GitHub-slug Codex commands are **available now**:

```text
codex plugin marketplace add arbiterForge/codeArbiter
codex plugin add ca-codex@codearbiter
```

To develop against an unpublished checkout, use a local clone:

```powershell
git clone https://github.com/arbiterForge/codeArbiter
cd codeArbiter
codex plugin marketplace add .
codex plugin add ca-codex@codearbiter
```

Open `/hooks`, review and trust the `ca-codex` handlers, then start a fresh thread. In the target
repository run `$ca-init` to opt in and `$ca-doctor` to prove the live gate. The expected healthy
probe is a PreToolUse block containing `[H-03]`.

On 2026-07-12, a clean isolated Codex home completed the public marketplace add, installed and
discovered `ca-codex 0.2.4` from release `v2.8.13`, removed the plugin, and confirmed its final
absence. That closes the public-installation gate with the same GitHub-slug commands shown above.

## Intentional host differences

| Surface | Claude Code | Codex |
|---|---|---|
| Entry commands | `/ca:<name>` | `$ca-<name>` |
| Plugin | `ca` | `ca-codex` |
| Hook approval | Claude Code plugin trust flow | Review through `/hooks`; start a fresh thread after approval |
| Project state | Shared `.codearbiter/` store | The same shared `.codearbiter/` store |
| Blocking result | Shared guard exits 2 at the Claude hook boundary | Codex adapter converts the same verdict to structured `decision:block` |
| Statusline | Available | No Codex statusline surface; startup state carries governance status |
| Transcript pruning | Claude transcript-pruning engine available | No transcript pruning; the host-neutral audit-staleness warning remains |
| Governed-file Read hook | Available on Claude's Read tool | No Codex Read hook; reads happen through shell, while write-time notices remain |
| Reviewer roles | Plugin agents can be dispatched | Roles execute inline until Codex agent packaging reaches its later milestone |

These differences are host capabilities and packaging choices. They do not create a second project
context, weaken the blocking shell/write gates, or split the audit trail.

## Next steps

- [Install codeArbiter](/getting-started/install/)
- [Run the quickstart](/getting-started/quickstart/)
- [Review compatibility](/getting-started/compatibility/)
- [Understand enforcement](/enforcement/)
- [Troubleshoot an installation](/guides/troubleshooting/)
