---
title: Pi
description: "Install codeArbiter for Pi, grant project trust, and verify enforcement — the ca-pi Git-only install, supported versions, and version pinning."
---

codeArbiter ships `ca-pi` as a third sibling plugin, alongside `ca` (Claude Code) and `ca-codex`
(Codex). All three activate from the same `.codearbiter/CONTEXT.md` and read and write the same
checked-in `.codearbiter/` state. `ca-pi` is Git-only: there is no npm release.

## Prerequisites

Confirm all before installing:

- **Node.js 22.19 or later.**
- **Python 3 on `PATH`**: `ca-pi` installs its final TypeScript wrappers before bridge readiness, so
  a missing interpreter blocks mutating calls and points to `/ca-doctor` rather than silently
  disabling governance.
- **`git config user.email` set**: overrides and ADRs are attributed to this identity.
- **A supported Pi host**: Pi 0.80.5 or Pi 0.80.6 for this release line. See
  [Compatibility](/getting-started/compatibility/) for the full matrix.

## 1. Install

Pi distribution is Git-only. Pin the independent `ca-pi` release tag, then inspect the installed
source and enabled resources:

```text
pi install git:arbiterForge/codeArbiter@ca-pi-v<version>
pi list
pi config
```

`pi list` and `pi config` let you verify the installed source before trusting it — see
[Trust and Security](#trust-and-security) below.

## 2. Grant Project Trust

Installing the plugin does not enforce anything. After inspecting the project, grant Pi project
trust, then start a fresh session. The parent only registers repository-aware dispatch, farm
preview, and native compaction once the current session reports affirmative project trust, the
repository is enabled, and the enforcement lifecycle is ready. Nothing repository-aware runs before
that — a session started before trust was granted, or before it opted the repo in, stays inert.

## 3. Scaffold and Activate the Repo

In the target repository, run `/ca-init`:

```text
/ca-init
```

This scaffolds `.codearbiter/` at the repo root and writes the `arbiter: enabled` activation flag,
the same as `/ca:init` on Claude Code or `$ca-init` on Codex. Neither host needs the others' plugin
installed to use existing project state. See [Opt a Repository In](/guides/opt-in-a-repo/) for the
full walkthrough.

Generated aliases use `/ca-<name>`; `/skill:ca-<name>` is the host-native fallback when an alias is
unavailable.

## 4. Verify

Run `/ca-doctor`:

```text
/ca-doctor
```

Doctor inspects the active package path, the canonical Pi CLI and package origin, command ownership,
supported-version expansion fingerprints, Python/core/bridge health, child fingerprint, final mutator
wrappers, and the H-03 wrapper self-test. The module-identity row proves self-consistency between the
operator-launched Pi CLI, imported module, package root, and reported version — it does **not** prove
publisher authenticity. Verify the source separately with `pi list` and `pi config`.

## Trust and Security

See [Enforcement & Security](/enforcement/#pi-project-trust-and-child-processes) for the project-trust
gate, parent-only dispatch tools, and child-process environment minimization.

## Uninstall, Upgrade, and Version Pinning

`ca-pi` is versioned independently as `ca-pi-v<version>` tags, not tied to the `ca`/`ca-codex`
release cadence. See [Uninstall & Disable](/guides/uninstalling/#pi) for pinning, upgrading, and
removing `ca-pi`.

## Windows

Windows is a promoted, tested platform for `ca-pi`. Child Pi processes (author and reviewer work,
dispatched through `codearbiter_dispatch`) are supervised through a Windows-specific helper so
cancellation and timeout cleanup terminate the whole process tree — no zombie processes left behind
on `Ctrl+C` or a dispatch timeout.

## Next steps

- [Compatibility](/getting-started/compatibility/) for the full host requirements matrix
- [Enforcement & Security](/enforcement/) for the activation contract and trust gate
- [Troubleshooting](/guides/troubleshooting/) for Pi-specific dormant states
