---
title: "Uninstall & Disable"
description: "How to turn codeArbiter off in one repository, or remove it entirely: the activation flag, the plugin uninstall command, the statusline, and the git-hooks backstop."
journey:
  level: "Practitioner"
  time: "12 minutes"
  outcome: "Disable one repository or remove a host plugin without losing project records or another tool's git hooks."
  prerequisites:
    - "Know whether you want repository dormancy, one-host removal, or complete removal"
  proof: "A fresh session is dormant or the host plugin is absent, retained state is intentional, and git-hook registry entries or shared shims were removed without breaking another installed host."
---

codeArbiter's pitch is enforcement, so it documents the exit. This page covers three levels: turning
it off in one repository, removing it globally, and what to check before uninstalling mid-feature.
Claude Code, Codex, and Pi share `.codearbiter/`, so removing one host plugin leaves project context
and audit history available to the others.

## Choose the exit you actually want

| Goal | Action | Repository records |
|---|---|---|
| Pause governance in one repository | Change only that repository's activation flag | Kept |
| Stop using one host | Uninstall only that host's plugin | Kept and usable by another host |
| Remove codeArbiter from the machine | Remove every installed host plugin, the Claude statusline, and managed git-hook shims | Kept unless you separately archive and delete them |
| Erase project governance history | Archive, review, then delete `.codearbiter/` as a separate destructive action | Deleted |

Do not delete `.codearbiter/` merely to uninstall a plugin. It contains project-owned history, not
plugin cache.

## Disable in One Repository

Enforcement in a repository is controlled by a single flag: `arbiter: enabled` in `.codearbiter/CONTEXT.md`
frontmatter. Every enforcement hook checks that flag through `arbiter_active()` and exits immediately,
without running any gate logic, when it is absent or set to anything other than `enabled`. Turning it
off makes the plugin genuinely dormant in that repository: the orchestrator persona never loads, and
every `PreToolUse`-guarded hook returns before doing anything.

The flag is deliberately hard to flip from inside a session, by design. **H-18** blocks a shell
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
editor or process outside the active host's tool path:

1. Close or step outside the active Claude Code, Codex, or Pi session for that repo. Use a different
   terminal or editor entirely: a plain text editor, `vim`, VS Code, or a shell not mediated by the
   active agent host.
2. Edit `.codearbiter/CONTEXT.md` directly and change the frontmatter line to:

   ```yaml
   ---
   arbiter: disabled
   ---
   ```

3. Log the change for the audit trail, the same way any other gate exception is recorded, by running
   `/ca:override "disabling codeArbiter for this repository"` in a session **after** the edit (or
   before, because the log entry and the edit are independent; only the edit itself needs to happen
   outside the tool-mediated path). This keeps `.codearbiter/overrides.log` an honest record of the
   change even though the hook itself never granted permission.
4. Verify: open a fresh session in the host you use. No orchestrator persona loads, host-specific
   project-state UI stays dormant, and a read-only status check does not report active governance.

There is no hidden bypass inside a session, and this page will not pretend there is one. H-18 guards
the mutating tool flanks each host mediates; an edit outside those host-managed tools was never
something it could stop.

Re-enabling is the same edit in reverse (`arbiter: disabled` → `arbiter: enabled`), no override
required. H-18 only blocks disabling the switch, not re-enabling it.

## Pi

`ca-pi` currently ships as a Feature Forge `preview`. Real use and feedback are
welcome while broader testing continues before stable status.

`ca-pi` is versioned independently from the `ca`/`ca-codex` release cadence. Each
`ca-pi-v<version>` tag is the reproducible evidence channel, while npm is the convenience channel
at `npm:@arbiterforge/ca-pi`. Pi does not auto-update either channel.

List the published tags, then compare them with the exact source shown by `pi list`:

```sh
git ls-remote --tags --refs https://github.com/arbiterForge/codeArbiter.git "ca-pi-v*"
pi list
```

**Upgrade through npm:** reinstall the convenience package:

```text
pi install npm:@arbiterforge/ca-pi
```

**Upgrade or pin through Git:** choose an exact tag from the first command and re-run `pi install`
with that full tag:

```text
pi install git:github.com/arbiterForge/codeArbiter@ca-pi-v<new-version>
```

**Uninstall:** copy the exact installed source from `pi list` so the removal target matches. Remove
the npm package or the pinned Git source, whichever is listed.

For an npm install:

```text
pi remove npm:@arbiterforge/ca-pi
```

For a pinned-Git install:

```text
pi remove git:github.com/arbiterForge/codeArbiter@ca-pi-v<version>
```

Replace `<version>` with the installed tag's numeric suffix; `pi uninstall` is the equivalent
alias. Confirm removal with `pi list`.

Uninstalling `ca-pi` does not touch `.codearbiter/` in any repository: that state survives, the
same as for Claude Code and Codex, and another governance host can pick it up.

## Full Uninstall

Removing codeArbiter entirely has five pieces. Order matters because the first two use files inside
the installed payload.

### 1. Remove the Claude Code Statusline

If you wired the statusline with <kbd>/ca:statusline</kbd>, remove it **before** uninstalling the
plugin (the command needs the plugin's `wire-statusline.py` to run):

```text
/ca:statusline uninstall
```

This restores whatever `statusLine.command` was in `~/.claude/settings.json` before you wired
codeArbiter in (or removes the key entirely if there was none), and restores any prior `spinnerVerbs`
the same way. See [Set Up the Statusline](/guides/the-statusline/#remove-the-statusline) for the full
behavior.

If you already uninstalled the plugin first, `/ca:statusline uninstall` is no longer available. Edit
`~/.claude/settings.json` by hand and remove the `statusLine` entry that points at
`hooks/statusline.py` under the plugin's cache path.

### 2. Remove Each Host's Git-Backstop Registration

An activated host may install one shared POSIX-shell shim at `pre-commit` and `pre-push` (under the
repository's effective Git hooks directory). The shim reads each
`<git-common-dir>/codearbiter-hooksd/<plugin>.path` entry, runs **every live registered enforcer**,
and allows Git to continue only when every one allows. That closes shell-indirection gaps without
making one host's plugin cache path the shared hook's owner.

Before uninstalling a host package, run that host's own `_githooks.py uninstall` against every
repository where it was active. This removes only that host's registry entry and its owned
trusted-identity record. It deliberately leaves the shared shims because another installed host may
still depend on them.

From a codeArbiter checkout, run the command for each host you are removing. Replace
`C:\path\to\repo` with the target repository:

```powershell
python plugins/ca/hooks/_githooks.py uninstall C:\path\to\repo
python plugins/ca-codex/hooks/_githooks.py uninstall C:\path\to\repo
python plugins/ca-pi/hooks/_githooks.py uninstall C:\path\to\repo
```

Run only the rows for hosts that were installed. The commands are safe to repeat: a host with no
entry reports no change. Run `git rev-parse --git-common-dir` inside the target repository and append
`codearbiter-hooksd` to locate the shared registry. The common directory is intentional: linked
worktrees share the same host registrations.

### 3. Uninstall the Host Packages

Claude Code:

```sh
claude plugin uninstall ca
```

Codex:

```sh
codex plugin remove ca-codex@codearbiter
```

Pi (use `pi list` to copy the installed npm or pinned-Git source, then run exactly one matching
command; see [Pi](#pi) above):

```sh
pi remove npm:@arbiterforge/ca-pi
```

```sh
pi remove git:github.com/arbiterForge/codeArbiter@ca-pi-v<version>
```

The effect is host-specific:

- **Claude Code removes** the plugin payload (hooks, commands, agents, and skills) from its plugin
  cache. Hooks, commands, and statusline wiring stop loading from the next session onward.
  `claude plugin update` is **not** sufficient for a full removal: it can leave a stale cached payload
  behind when the marketplace version string has not changed, so `uninstall` is the clean path.
- **Codex removes** the `ca-codex@codearbiter` plugin registration and stops discovering its packaged
  skills and hooks in subsequent sessions.
- **Pi removes** the selected npm or pinned-Git package source from Pi's installed packages. New
  sessions stop loading the codeArbiter extension, skills, prompts, and theme from that source.

The marketplace entry (`codearbiter`) itself was added at install time with
`/plugin marketplace add arbiterForge/codeArbiter`. If you want that gone too, you can manage it
through the `/plugin` command's interactive marketplace management screen in any Claude Code session.

### 4. Remove the Shared Git Shims After the Last Host

Skip this step when any codeArbiter governance host remains installed. For a complete uninstall,
first resolve the directory Git actually reads:

1. Run `git config --get core.hooksPath`.
2. If it prints a path, use that directory. Resolve a relative value from the repository root
   reported by `git rev-parse --show-toplevel`.
3. If it prints nothing, run `git rev-parse --git-path hooks` and use that directory.

Inspect `pre-commit` and `pre-push` inside that directory. Delete a hook only when its first lines
contain the exact sentinel `# codeArbiter-managed git hook (#161)`. A hook without that sentinel
belongs to another tool and must remain. After both sentinel shims are gone, remove
`<git-common-dir>/codearbiter-hooksd` only if you have already removed every installed host's
registry entry. An empty registry fails closed, so do not leave the shared shim pointing at an empty
directory after a complete uninstall.

### 5. Decide What Happens to `.codearbiter/`

Uninstalling the plugin does **not** touch `.codearbiter/` in any repository. That directory is your
repo's state (specs, plans, ADRs, the decision log, tribunal reports, and the append-only overrides
audit trail), and it survives the plugin by design, the same way it's meant to survive a plugin update.
Deleting it is a separate, deliberate act:

```text
rm -rf .codearbiter/
```

Consider whether the audit trail in `.codearbiter/overrides.log` and `.codearbiter/decisions/` has
value to keep even after you stop using the plugin day to day: it's a plain-file record, readable
without codeArbiter installed.

Before deletion, confirm `git rev-parse --show-toplevel` names the intended repository, inspect
`git status --short -- .codearbiter`, and copy any audit or decision records you must retain. On
Windows PowerShell the scoped equivalent is `Remove-Item -LiteralPath .codearbiter -Recurse` from
the verified repository root. This deletion is not required for dormancy or plugin removal and is
not recoverable unless Git or your archive contains the files.

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

- Any in-flight gate context held only in the current host session (a half-finished TDD phase or an
  open commit-gate walk). Nothing was committed to `.codearbiter/` for that step, so there is
  nothing to lose except needing to redo that step by hand or with a different tool.

**Before you uninstall mid-feature, check:**

1. Run <kbd>/ca:status</kbd> to see the current stage, open tasks, and any unresolved `CONFIRM-NN`
   questions. Resolve or note anything open before losing the orchestrator's view of it.
2. Confirm the branch is pushed or otherwise backed up if you're also about to remove local state.
3. If a commit is staged but hasn't cleared `commit-gate`, either finish the commit through the plugin
   first or be aware you're now committing without the gate's verification, secret-scan, and
   behavioral-proof checks. Nothing enforces those once the plugin is gone.

## Final verification

Start a fresh session after the chosen exit:

- for repository dormancy, confirm no orchestrator startup state appears and a read-only status check
  does not report an active arbiter;
- for one-host removal, confirm that host no longer lists the plugin and that another installed host
  can still read the retained `.codearbiter/` state;
- for full removal, confirm Claude's optional statusline no longer points into the plugin cache,
  Codex no longer lists or trusts the adapter, Pi no longer lists the Git source, and inspect
  `pre-commit` and `pre-push` before removing only files with the codeArbiter sentinel.

The proof is a fresh-session observation plus an intentional decision about retained repository
state, not merely a successful uninstall command.
