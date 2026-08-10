---
title: Pi
description: "Install codeArbiter for Pi, grant project trust, and verify enforcement. Covers the ca-pi Git-only install, supported versions, and version pinning."
journey:
  level: "Foundation"
  time: "12 minutes"
  outcome: "Install a pinned ca-pi preview, trust the project, opt in a repository, and verify a real gate."
  prerequisites:
    - "Pi 0.80.5 or Pi 0.84.1"
    - "Node.js 22.19 or newer"
  proof: "Pi reports the pinned extension and a disposable broad-stage probe is blocked by H-03."
---

codeArbiter ships `ca-pi` as a third sibling plugin, alongside `ca` (Claude Code) and `ca-codex`
(Codex). All three activate from the same `.codearbiter/CONTEXT.md` and read and write the same
checked-in `.codearbiter/` state. Install `ca-pi` from npm (`@arbiterforge/ca-pi`) or as a pinned
Git tag: the Git tag is the reproducible pin, and npm is the convenience channel.

<div class="ca-callout ca-callout--preview"><p class="ca-callout__label">Feature Forge preview</p><p><code>ca-pi</code> is available for real use now. You are welcome to install it, use it in your repositories, and report what you find. Its automated and hosted promotion matrix is green, but broader real-world testing is still required before codeArbiter claims 100% validation or stable status.</p></div>

## Prerequisites

Confirm all before installing:

- **Node.js 22.19 or later.**
- **Python 3 on `PATH`**: `ca-pi` installs its final TypeScript wrappers before bridge readiness, so
  a missing interpreter blocks mutating calls and points to `/ca-doctor` rather than silently
  disabling governance.
- **`git config user.email` set**: overrides and ADRs are attributed to this identity.
- **A supported Pi host**: Pi 0.80.5 or Pi 0.84.1 for this release line. See
  [Compatibility](/getting-started/compatibility/) for the full matrix.

## 1. Install

Pi distribution is Git-only. First list the repository's published Pi tags; do not guess a version
or substitute the core plugin's release number:

```sh
git ls-remote --tags --refs https://github.com/arbiterForge/codeArbiter.git "ca-pi-v*"
```

For the convenience channel, install straight from npm and inspect the installed source and
enabled resources:

```text
pi install npm:@arbiterforge/ca-pi
pi list
pi config
```

To pin an exact release instead (the reproducible channel this site's runbooks verify against),
choose an exact tag from the listing above and pin it in the install source:

```text
pi install git:github.com/arbiterForge/codeArbiter@ca-pi-v<version>
```

Replace `<version>` with only the numeric suffix from the chosen tag. For example, the tag
`ca-pi-v0.1.32` maps to `@ca-pi-v0.1.32`; keep the full tag in the source. `pi list` and
`pi config` let you verify the installed source before trusting it. See
[Trust and Security](#trust-and-security) below.

## 2. Grant Project Trust

Installing the plugin does not enforce anything. After inspecting the project, grant Pi project
trust, then start a fresh session. The parent only registers repository-aware dispatch, farm
preview, and native compaction once the current session reports affirmative project trust, the
repository is enabled, and the enforcement lifecycle is ready. Nothing repository-aware runs before
that: a session started before trust was granted, or before it opted the repo in, stays inert.

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
operator-launched Pi CLI, imported module, package root, and reported version. It does **not** prove
publisher authenticity. Verify the source separately with `pi list` and `pi config`.

## Rich Footer

In an interactive, trusted session, `ca-pi` installs a rich footer that preserves Pi's native
session information and adds codeArbiter state and usage metrics. There is no separate wiring
command. Non-interactive modes do not install footer UI.

On session shutdown, the extension restores Pi's native footer. If custom-footer initialization
fails or the required interactive UI surface is absent, it also restores the native footer and
prints a bounded direction to run `/ca-doctor`; governance does not depend on the footer rendering.

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
cancellation and timeout cleanup terminate the whole process tree: no zombie processes are left
behind on `Ctrl+C` or a dispatch timeout.

## Next steps

- [Compatibility](/getting-started/compatibility/) for the full host requirements matrix
- [Enforcement & Security](/enforcement/) for the activation contract and trust gate
- [Troubleshooting](/guides/troubleshooting/) for Pi-specific dormant states
