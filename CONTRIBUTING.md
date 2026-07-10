# Contributing to codeArbiter

Thanks for considering a contribution. codeArbiter is a Claude Code plugin that
enforces development discipline through gates, so it holds itself to the same bar.
This guide explains how to get set up, what the gates expect, and how to get a
change merged.

By participating you agree to abide by our [Code of Conduct](./CODE_OF_CONDUCT.md).

## Ways to contribute

- **Report a bug.** Open an issue. A failing repro (the smallest command sequence
  that reproduces it) is worth a great deal.
- **Run a Feature Forge preview and send data.** This is the fastest way to help a
  preview graduate. See [Feature Forge](./README.md#feature-forge); each preview
  ships a `dry` mode that records what it *would* have done, changing nothing.
- **Improve docs.** Corrections and clarifications are always welcome.
- **Propose or build a feature.** Open an issue first so we can align on scope
  before you invest the work.

## Prerequisites

- **Python 3 on `PATH`.** Every hook is Python (stdlib only; no third-party
  packages). Without it the gates and the startup injection silently don't run.
- **`git config user.email` set.** Overrides and ADRs are attributed to that
  identity; the audit trail depends on a real attribution.
- **Node.js**, only if you touch the cost-arbitrage farm dispatcher under
  `plugins/ca/tools/` (TypeScript + Vitest).

## Getting set up

```sh
git clone https://github.com/arbiterForge/codeArbiter
cd codeArbiter
```

Then load it as a local marketplace in Claude Code to dogfood your changes:

```text
/plugin marketplace add ./codeArbiter
/plugin install ca@codearbiter
```

This repo is itself an arbiter-enabled repo (`.codearbiter/CONTEXT.md` carries
`arbiter: enabled`), so a session here opens with the orchestrator active.

## Running the tests

The hook suite is the heart of the project. Run it before opening a PR:

```sh
cd plugins/ca/hooks
python -m pytest          # the full hook + statusline + standup + prune suite
```

If you touched the farm dispatcher:

```sh
cd plugins/ca/tools
npm install
npm test                  # Vitest
```

CI (`.github/workflows/ci.yml`) runs these on every PR, plus a plugin-reference
check and cold-install hook guards. A red suite blocks merge.

## How development works here

codeArbiter governs its own development. Two things follow from that:

1. **Editing the framework itself** (skill/agent/command/hook bodies,
   `ORCHESTRATOR.md`, settings) goes through **maintainer dev mode**: set
   `CODEARBITER_DEV=1` and run `/ca:dev`. It's env-gated and logged to
   `.codearbiter/overrides.log` on entry and exit. `/ca:arbiter` exits it.

2. **Everything that ships is a payload change and requires a version bump.** The
   two-axis model: **SemVer** versions the whole payload (any change to shipped
   plugin files bumps the version, and CI enforces this), while the **Feature Forge**
   label marks per-feature previews that are off by default until real-world data
   earns promotion. New behavior ships `preview` and opt-in first.

## Submitting a change

1. **Branch** off `main`. Never commit to `main` directly, and never force-push
   (the hooks block both). Use a descriptive branch name (`fix/…`, `feat/…`,
   `docs/…`, `chore/…`).
2. **Write tests first** for behavioral changes. New hook behavior needs a test
   under `plugins/ca/hooks/tests/`; prose/docs changes don't.
3. **Use Conventional Commits**: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`,
   etc. The release tooling derives the SemVer bump from commit history, so the
   prefix matters.
4. **Bump the version** if you changed any shipped payload file, and add a
   `CHANGELOG.md` entry.
5. **Record an ADR** (`/ca:adr`) for an architectural decision. ADRs are
   user-attributed and live under `.codearbiter/decisions/`.
6. **Open a PR** against `main` and fill out the
   [pull request template](./.github/PULL_REQUEST_TEMPLATE.md). Reference any issue
   it closes.

A maintainer reviews; CI must be green. Changes land via PR. `main` moves only
through a merged PR, never a direct write.

## Working with the hooks

If your change touches the hooks, read [`docs/hooks.md`](./docs/hooks.md) first. It
documents every hook, what it reads/writes, and the invariant that **no hook makes a
network call**. Preserve that invariant: hooks are stdlib-only Python, must degrade
safely on failure, and must exit `0` (do nothing) in a repo that hasn't opted in.

Hook Python is canonical in `core/pysrc/` and vendored byte-identically into each
plugin's `hooks/` by `python tools/sync-core.py` (CI gates it with `--check`). Edit
core, re-vendor, commit both — never a vendored copy directly. The only per-plugin
Python file is `hooks/_host.py`.

## Working with the markdown surface (generated)

Commands, skills, includes, `COMMANDS.md`, `SPRINT.md`, and `ORCHESTRATOR.md` of
**both** plugins are rendered from `core/surface/` templates by
`python tools/build-surface.py` — see [`core/surface/README.md`](./core/surface/README.md)
for the token/conditional grammar and the house rules. Never edit a rendered file:
edit the template, run the tool, commit templates and outputs together. CI's
`surface` job (`build-surface.py --check`) fails on drift in either direction.

On Windows, `.gitattributes` pins the generated trees to LF; if a pre-existing
checkout still has CRLF working copies, refresh them (`git checkout-index -f` on the
affected paths, or re-clone) before running `--check` locally.

## Questions

Open a [discussion or issue](https://github.com/arbiterForge/codeArbiter/issues).
For anything security-sensitive, follow the [Security Policy](./SECURITY.md) instead
of opening a public issue.
