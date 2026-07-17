---
title: "Uninstall & Disable"
description: "How to turn codeArbiter off in one repository, or remove it entirely: the activation flag, the plugin uninstall command, the statusline, and the git-hooks backstop."
---

codeArbiter's pitch is enforcement, so it documents the exit. This page covers three levels: turning
it off in one repository, removing it globally, and what to check before uninstalling mid-feature.
Claude Code and Codex share `.codearbiter/`, so removing either plugin leaves project context and
audit history available to the other host.

## Disable in One Repository

Enforcement in a repository is controlled by a single flag: `arbiter: enabled` in `.codearbiter/CONTEXT.md`
frontmatter. Every enforcement hook checks that flag through `arbiter_active()` and exits immediately,
without running any gate logic, when it is absent or set to anything other than `enabled`. Turning it
off makes the plugin genuinely dormant in that repository — the orchestrator persona never loads, and
every `PreToolUse`/`PreToolUse`-guarded hook returns before doing anything.

The flag is deliberately hard to flip from inside a session, by design. **H-18** blocks a shell
redirect, `Write`, or `Edit` that would change `arbiter: enabled` to `arbiter: disabled` (or otherwise
corrupt the frontmatter) through `.codearbiter/CONTEXT.md` — the gates cannot silence themselves from
inside the repo they govern. Reads (`cat`, `grep`) still pass through untouched.

Unlike the crypto/secret and migration gates (H-09b/H-10b, H-14), H-18 has no marker-based bypass that
`/ca:override` can unlock. Its block calls in `pre-bash.py`, `pre-write.py`, and `pre-edit.py` are
unconditional — there is no override flag the hook code checks. Running `/ca:override` first does not
make the block go away; the hook still fires on the next Bash/Write/Edit call that touches
`CONTEXT.md`. That's deliberate: the block exists precisely so a session cannot talk itself past it.

The honest, sanctioned path is to make the edit through a channel H-18 doesn't intercept, because it
only subscribes to Claude Code's own `PreToolUse` hook on the Bash, Write, and Edit tools:

1. Close or step outside the active Claude Code session for that repo (or use a different terminal /
   editor entirely — a plain text editor, `vim`, VS Code, a shell outside Claude Code's Bash tool).
2. Edit `.codearbiter/CONTEXT.md` directly and change the frontmatter line to:

   ```yaml
   ---
   arbiter: disabled
   ---
   ```

3. Log the change for the audit trail, the same way any other gate exception is recorded, by running
   `/ca:override "disabling codeArbiter for this repository"` in a session **after** the edit (or
   before — the log entry and the edit are independent; only the edit itself needs to happen outside
   the tool-mediated path). This keeps `.codearbiter/overrides.log` an honest record of the change even
   though the hook itself never granted permission.
4. Verify: open a new Claude Code session in the repo. No orchestrator persona loads, the statusline's
   arbiter row (stage · tasks · questions · overrides) does not render, and any tool call proceeds
   without a gate check.

There is no hidden bypass inside a session, and this page will not pretend there is one — H-18 guards
exactly the tool flanks Claude Code mediates, and an edit outside those tools was never something it
could stop.

Re-enabling is the same edit in reverse (`arbiter: disabled` → `arbiter: enabled`), no override
required — H-18 only blocks disabling the switch, not re-enabling it.

## Pi

`ca-pi` is distributed Git-only, versioned independently as `ca-pi-v<version>` tags — not tied to
the `ca`/`ca-codex` release cadence. There is no npm release and no auto-update.

**Upgrade or pin a version:** re-run `pi install` with the new pinned tag:

```text
pi install git:arbiterForge/codeArbiter@ca-pi-v<new-version>
```

**Uninstall:**

```text
pi remove git:arbiterForge/codeArbiter@ca-pi-v<version>
```

(`pi uninstall` is the equivalent alias.) Confirm removal with `pi list`.

Uninstalling `ca-pi` does not touch `.codearbiter/` in any repository — that state survives, the
same as for Claude Code and Codex, and another governance host can pick it up.

## Full Uninstall

Removing codeArbiter entirely has four independent pieces. Do them in this order.

### 1. Uninstall the Plugin

Claude Code:

```sh
claude plugin uninstall ca
```

Codex:

```sh
codex plugin remove ca-codex@codearbiter
```

Pi (Git-only; see [Pi](#pi) above for pinning and version-specific removal):

```sh
pi remove git:arbiterForge/codeArbiter@ca-pi-v<version>
```

This removes the plugin payload (hooks, commands, agents, skills) from Claude Code's plugin cache.
Hooks, commands, and the statusline wiring stop loading from the next session onward. `claude plugin
update` is **not** sufficient for a full removal — it can leave a stale cached payload behind when the
marketplace version string hasn't changed; `uninstall` is the clean path.

You can also manage the marketplace entry (`codearbiter`) itself — added at install time with
`/plugin marketplace add arbiterForge/codeArbiter` — through the `/plugin` command's interactive
marketplace management screen in any Claude Code session, if you want it gone too.

### 2. Decide What Happens to `.codearbiter/`

Uninstalling the plugin does **not** touch `.codearbiter/` in any repository. That directory is your
repo's state — specs, plans, ADRs, the decision log, tribunal reports, and the append-only overrides
audit trail — and it survives the plugin by design, the same way it's meant to survive a plugin update.
Deleting it is a separate, deliberate act:

```text
rm -rf .codearbiter/
```

Consider whether the audit trail in `.codearbiter/overrides.log` and `.codearbiter/decisions/` has
value to keep even after you stop using the plugin day to day — it's a plain-file record, readable
without codeArbiter installed.

### 3. Remove the Statusline

If you wired the statusline with <kbd>/ca:statusline</kbd>, remove it **before** uninstalling the
plugin (the command needs the plugin's `wire-statusline.py` to run):

```text
/ca:statusline uninstall
```

This restores whatever `statusLine.command` was in `~/.claude/settings.json` before you wired
codeArbiter in — or removes the key entirely if there was none — and restores any prior `spinnerVerbs`
the same way. See [Set Up the Statusline](/guides/the-statusline/#remove-the-statusline) for the full
behavior.

If you already uninstalled the plugin first, `/ca:statusline uninstall` is no longer available — edit
`~/.claude/settings.json` by hand and remove the `statusLine` entry that points at
`hooks/statusline.py` under the plugin's cache path.

### 4. Remove the `.git/hooks` Backstop

Every session, codeArbiter installs a small POSIX-shell shim into each repo's `.git/hooks/pre-commit`
and `.git/hooks/pre-push` (or wherever `core.hooksPath` points), which calls `git-enforce.py` at the
git operation itself. This closes the gap where a shell command constructed to dodge the `PreToolUse`
Bash hook's literal-string match (`g=git; c=commit; $g $c`) would otherwise slip past enforcement
entirely.

These shims are managed only in repositories you opened with the plugin active, and only removed
automatically the next time codeArbiter runs there — which won't happen once the plugin is
uninstalled. Remove them by hand, per repository:

```sh
python plugins/ca/hooks/_githooks.py uninstall .
```

(Run this from a checkout that still has the plugin's hook files present — for example, before you
uninstall the plugin, or from a fresh clone of the codeArbiter repo pointed at your target repo's path
as the second argument.) `_githooks.py uninstall` removes only shims that carry codeArbiter's sentinel
comment; a pre-existing hook from another tool (husky, pre-commit-framework) is left untouched.

If that script isn't available, remove the files directly — they only exist if codeArbiter installed
them (check for the sentinel comment `# codeArbiter-managed git hook (#161)` at the top):

```sh
rm .git/hooks/pre-commit .git/hooks/pre-push
```

Only do this for a hook file that carries that sentinel; a hook without it belongs to something else.

## Mid-Feature Uninstall

If you uninstall while a `/ca:feature` or `/ca:sprint` run is in progress, here's what survives and
what to check first.

**Survives uninstall, because it lives in the repo, not the plugin:**

- The feature branch and every commit on it.
- The spec and plan files under `.codearbiter/specs/` and `.codearbiter/plans/`.
- The task board (`.codearbiter/open-tasks.md`) and its in-progress/done state.
- The decision log and any ADRs the feature recorded.
- The overrides and gate-events audit logs.

**Does not survive, because it's session/tool state, not repo state:**

- Any in-flight gate context held only in the current Claude Code session (a half-finished TDD Phase,
  an open `/ca:commit` gate walk). Nothing was committed to `.codearbiter/` for that step, so there's
  nothing to lose except needing to redo that step by hand or with a different tool.

**Before you uninstall mid-feature, check:**

1. Run <kbd>/ca:status</kbd> to see the current stage, open tasks, and any unresolved `CONFIRM-NN`
   questions — resolve or note anything open before losing the orchestrator's view of it.
2. Confirm the branch is pushed or otherwise backed up if you're also about to remove local state.
3. If a commit is staged but hasn't cleared `commit-gate`, either finish the commit through the plugin
   first or be aware you're now committing without the gate's verification, secret-scan, and
   behavioral-proof checks — nothing enforces those once the plugin is gone.
