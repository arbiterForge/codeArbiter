---
title: "What Uninstall Leaves Behind"
description: "Why a session cannot disable codeArbiter, what each host's uninstall removes, and what survives an uninstall in the middle of a feature."
journey:
  level: "Reference"
  time: "Lookup"
  outcome: "Understand what an exit removes, what it keeps, and why the disable switch sits outside the session."
  prerequisites:
    - "Uninstall & Disable"
  proof: "You can say what your chosen exit removes and what it keeps."
---

Background for [Uninstall & Disable](/guides/uninstalling/). The commands are on that page; this
page explains what they leave in place and why.

## Why a session cannot disable itself

The activation flag (`arbiter: enabled` in `.codearbiter/CONTEXT.md` frontmatter) is deliberately
hard to flip from inside a session. **H-18** blocks a shell
redirect, `Write`, or `Edit` that would change `arbiter: enabled` to `arbiter: disabled` (or otherwise
corrupt the frontmatter) through `.codearbiter/CONTEXT.md`. The gates cannot silence themselves from
inside the repo they govern. Reads (`cat`, `grep`) still pass through untouched.

Unlike the crypto/secret and migration gates (H-09b/H-10b, H-14), H-18 has no marker-based bypass
that `/ca:override` can unlock. The shared guard's activation block is unconditional, whether the
host reaches it through Claude's Python hooks, Codex's adapter, or Pi's wrappers. Running an
override first does not make the next governed mutation to `CONTEXT.md` pass. That is deliberate:
the block exists precisely so a session cannot talk itself past it.

The honest, sanctioned path is to make the edit through a channel H-18 does not intercept. Across
Claude Code, Codex, and Pi, the protected boundary is the same: Claude Code guards Bash, Write, and
Edit; Codex guards shell and patch/write adapters; Pi guards its final
mutator wrappers. All three protect the same activation boundary, but none can police an external
editor or process outside the active host's tool path.

There is no hidden bypass inside a session, and this page will not pretend there is one. H-18 guards
the mutating tool flanks each host mediates; an edit outside those host-managed tools was never
something it could stop.

## What each host's uninstall removes

Each host's uninstall command has a different effect:

- **Claude Code removes** the plugin payload (hooks, commands, agents, and skills) from its plugin
  cache. Hooks and commands stop loading from the next session onward. Statusline wiring lives in
  `~/.claude/settings.json`, outside the plugin, so uninstall leaves it behind: run
  `/ca:statusline uninstall` first, or remove the entry by hand afterward
  ([Remove the Claude Code Statusline](/guides/uninstalling/#1-remove-the-claude-code-statusline)).
  `claude plugin update` is **not** sufficient for a full removal: it can leave a stale cached payload
  behind when the marketplace version string has not changed, so `uninstall` is the clean path.
- **Codex removes** the `ca-codex@codearbiter` plugin registration and stops discovering its packaged
  skills and hooks in subsequent sessions.
- **Pi removes** the selected npm or pinned-Git package source from Pi's installed packages. New
  sessions stop loading the codeArbiter extension, skills, prompts, and theme from that source.

The marketplace entry (`codearbiter`) itself was added at install time with
`/plugin marketplace add arbiterForge/codeArbiter`. If you want that gone too, you can manage it
through the `/plugin` command's interactive marketplace management screen in any Claude Code session.

## What survives a mid-feature uninstall

**Survives uninstall, because it lives in the repo, not the plugin:**

- The feature branch and every commit on it.
- The spec and plan files under `.codearbiter/specs/` and `.codearbiter/plans/`.
- The selected work owner: a legacy task board or portable native records under
  `.codearbiter/work/`, including their local progress and pending provider intent.
- The decision log and any ADRs the feature recorded.
- The overrides and gate-events audit logs.

**Does not survive, because it's session/tool state, not repo state:**

- Any in-flight gate context held only in the current host session (a half-finished TDD phase or an
  open commit-gate walk). Nothing was committed to `.codearbiter/` for that step, so there is
  nothing to lose except needing to redo that step by hand or with a different tool.
