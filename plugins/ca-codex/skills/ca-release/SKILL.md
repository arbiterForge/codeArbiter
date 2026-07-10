---
name: ca-release
description: Cut a release the only sanctioned way — SemVer bump from the commit log, a CHANGELOG section, an annotated tag. The only path to a version tag.
argument-hint: ["<version>"] | --auto | --dry-run
---

# $ca-release — tagged release

The only permitted path to a version tag. A release is a deployment-readiness assertion: the codebase at this SHA satisfies the bar for shipping. `$ca-release` aggregates existing compliance — it does not duplicate it.

## Flow

Routes to the `release` skill. `$ca-release` targets the **`ca`** plugin only (ADR-0007): `LAST_TAG`
is the newest `ca` SemVer tag (`v*`, never the sibling `ca-sandbox-v*`), and the release window is the
`plugins/ca/`-scoped commit set — a `ca-sandbox` tag or commit never bumps `ca` or lands in its
changelog.

1. **Pre-flight** — working tree clean, on the configured release branch, suite green, no blocking
   `[CONFIRM-NN]` open, HEAD not produced via `$ca-override`. Identify `LAST_TAG` and the release window.
2. **Version bump (SemVer)** — classify every commit in `LAST_TAG..HEAD` by Conventional Commits type
   and apply the highest-precedence bump (major beats minor beats patch). An explicit version that
   disagrees with the classification BLOCKS — the bump is never silently up- or downgraded.
3. **Changelog** — roll up the `CHANGELOG:` footers from `feat`, `fix`, and `perf` commits into a new
   section. BLOCK if any `feat`/`fix` commit lacks the footer; never auto-fill it.
4. **Tag** — compose the annotated tag. Never push it to a remote without explicit user
   authorization — publication is a separate decision.

`--dry-run` runs every gate and surfaces the readiness report, then STOPs before composing the tag.

## Arguments

- **`<version>`** (e.g. `"1.2.3"`) — explicit version; Phase 2 still classifies the window and BLOCKs
  on disagreement.
- **`--auto`** — derive the version from the commit log (default when no version is given).
- **`--dry-run`** — run all gates, compose nothing. Combines with `--auto` or an explicit version.
  An explicit version never combines with `--auto` — they are mutually exclusive.

## Routes to

`release` (`${CLAUDE_PLUGIN_ROOT}/routines/release/SKILL.md`).

## When NOT to use

- Tagging an in-progress branch → land work first via `$ca-feature` / `$ca-fix`.
- Pushing an already-composed tag → that is a separate user-authorized step.
- A changelog only → it is a phase output, not a standalone deliverable.

## Hard gate

MUST NOT compose a tag on a red suite. MUST NOT silently up- or downgrade the SemVer classification —
an explicit version that disagrees with the commit log BLOCKS. MUST NOT auto-fill a missing
`CHANGELOG:` footer. MUST NOT write to the default branch or force-push. MUST NOT push the tag without
explicit user authorization. Any BLOCK may be bypassed only via `$ca-override`.
