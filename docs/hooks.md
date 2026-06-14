# Hooks reference

> **Why this page exists.** codeArbiter is a Claude Code plugin, and the way it
> stays *active* in your repo is through hooks: small Python scripts Claude Code
> runs at defined points in a session. That deserves transparency, because you are
> letting a plugin run code on your machine. This page documents every hook, what
> triggers it, exactly what it reads and writes, and (explicitly) that **none of
> them send anything off your machine**. Nothing here is obfuscated; every script is
> plain, readable Python under [`plugins/ca/hooks/`](../plugins/ca/hooks/).

## The short version

- **Language:** every hook is Python 3, stdlib only. No third-party packages, no
  compiled binaries, no `pip install`. (`Python 3 on PATH` is the one prerequisite.)
- **Network:** **none.** No hook opens a socket, makes an HTTP request, or contacts
  any server. The one outbound process any hook ever spawns is a local, read-only
  `git fetch` against *your own* configured remote (see
  [session-start](#sessionstart-session-startpy), background fetch), which is the
  same thing you would run by hand.
- **Scope:** every guard hook exits immediately (`exit 0`, does nothing) in any
  repo that has **not** opted in via `.codearbiter/CONTEXT.md` → `arbiter: enabled`.
  Install the plugin globally and it stays dormant everywhere you haven't enabled it.
- **Writes:** hooks write only inside your repo's `.codearbiter/` directory (markers,
  caches, the append-only audit logs), plus, for the statusline only, a ca-owned
  entry in your global `~/.claude/settings.json` (backed up and restored on removal).
  No hook writes to your source files.
- **Fail-safe vs. fail-loud:** activation fails *loud* (a malformed `CONTEXT.md`
  prints a breadcrumb to stderr rather than going silently dormant); everything
  else degrades quietly so a single failing read never crashes your session.

## How Claude Code invokes them

The wiring lives in [`plugins/ca/hooks/hooks.json`](../plugins/ca/hooks/hooks.json).
Each entry registers a script against a Claude Code hook event. Every command is
written twice, `python3 …` with a `|| python …` fallback, so it runs whether your
interpreter is named `python3` or `python`:

| Event | Matcher | Script | Blocking? |
|---|---|---|---|
| `SessionStart` | — | `session-start.py` | no (injects context) |
| `PreToolUse` | `Bash` \| `PowerShell` | `pre-bash.py` | **yes** (can block a command) |
| `PreToolUse` | `Write` | `pre-write.py` | **yes** (can block a write) |
| `PreToolUse` | `Edit` | `pre-edit.py` | **yes** (can block an edit) |
| `PostToolUse` | `Write` \| `Edit` | `post-write-edit.py` | no (advisory reminders) |
| `UserPromptSubmit` | — | `prune-transcript.py` | no (opt-in pruning) |
| `PreCompact` | — | `prune-transcript.py` | no (opt-in pruning) |

A blocking hook signals a block with exit code `2` and a message on stderr; Claude
Code surfaces that message and does not run the tool call. Everything else exits `0`.

---

## Event hooks

### SessionStart: `session-start.py`

**The activation linchpin.** A plugin has no `CLAUDE.md` to load an always-on
persona, so this hook does it. On every session start it:

1. **Clears the per-session dev marker** (`.codearbiter/.markers/dev-active`). A new
   session always restores orchestration after a maintainer `/ca:dev` session.
2. **Self-heals the statusline wiring.** It refreshes a ca-owned, version-pinned
   statusline path in `~/.claude/settings.json`, but *only if it's stale* (a plugin
   update moves the path). It persists only on a real change and degrades silently
   on any failure. This is the one hook that touches a file outside your repo.
3. **Checks the activation flag.** It reads `.codearbiter/CONTEXT.md` frontmatter.
   If `arbiter: enabled` is absent it **exits silently (dormant)**. If the file is
   present but its frontmatter is malformed, it prints a breadcrumb to *stderr* and
   exits dormant (failing loud, not silent).
4. **Injects the persona and live state** (enabled repos only). It prints
   `ORCHESTRATOR.md` plus the startup state (stage, blocking `CONFIRM-NN` questions,
   in-flight task count) to **stdout**, which Claude Code adds to context. Plain
   stdout is used instead of `additionalContext` because the latter is unreliable
   for plugin-scoped hooks (claude-code #16538).
5. **Emits the daily standup briefing** (first session of the local day only): a
   **read-only** summary of repo hygiene covering working-tree state, ahead/behind
   vs. upstream, merge-able branches, stale worktrees, stashes, and a display-only
   governance line. Later sessions the same day collapse to at most a single offer
   line, or nothing.

**Reads:** `.codearbiter/CONTEXT.md`, `open-questions.md`, `open-tasks.md`;
read-only `git` queries (`status`, `rev-list`, `branch -vv`, `worktree list`,
`stash list`, `rev-parse`). **Writes:** the first-of-day marker
`.codearbiter/.markers/standup-<date>`, and possibly the statusline pin in
`~/.claude/settings.json`. **Network:** it spawns a **detached, read-only
`git fetch --quiet --no-tags`** against your own remote to refresh ahead/behind for
*next* time. That fetch is never awaited, so an offline or slow network never stalls
startup. There is no other process and there are no sockets.

> This is the *only* hook that ever runs in a non-enabled repo, and there it does
> nothing but clear the dev marker and heal the (already-installed) statusline pin.

### PreToolUse(Bash\|PowerShell): `pre-bash.py`

The shell-command gate. It runs **only in enabled repos** (it exits `0` immediately
otherwise). It pattern-matches the command Claude is about to run and **blocks**
(exit `2`) the ones that would violate a hard rule. It never executes your command
itself; it inspects the command and either allows or blocks it. It does run a
read-only `git diff` to inspect what a commit would introduce.

Blocks enforced:

| Tag | What it blocks |
|---|---|
| H-01 | Direct commit to `main`/`master`; push to a protected branch (incl. `HEAD:main` refspecs and bare push from main) |
| H-02 | Force-push in any spelling (`--force`, `--force-with-lease`, `-f`, `+refspec`) |
| H-03 | Wildcard staging (`git add -A`/`.`/`-u`, globs, directories, pathspec magic), because staging must name files |
| H-05 | Truncating, overwriting, or deleting the append-only audit logs (`overrides.log`, `triage.log`) via shell verbs |
| H-11 | Shell writes/edits/deletes to ADR files under `.codearbiter/decisions/` (ADRs are authored only via `/ca:adr`) |
| H-09b / H-10b | A commit that introduces crypto/TLS or secret changes **without** a recorded, line-bound security-gate pass |

Ambiguity resolves **closed**: a few harmless command spellings are blocked because
the destructive spelling is indistinguishable without a full shell parse, and
`/ca:override` is the sanctioned escape hatch. **Reads:** the command string (from
the tool input on stdin); read-only `git branch`/`git diff`; the
`security-gate-passed` marker. **Writes:** nothing. **Network:** none.

### PreToolUse(Write): `pre-write.py`

Guards the `Write` tool. It runs only in enabled repos. It blocks:

- **H-05:** a `Write` to `overrides.log`/`triage.log`. A Write is a full overwrite,
  and the audit logs are append-only (use Edit or `>>`).
- **H-11:** a `Write` to an ADR file unless `/ca:adr` is actively authoring. The
  skill drops a fresh `adr-authoring-active` marker first; a missing or
  >30-min-stale marker blocks.

**Reads:** the target `file_path` and the authoring marker. **Writes:** nothing.
**Network:** none.

### PreToolUse(Edit): `pre-edit.py`

Guards the `Edit` tool with the same two rules as `pre-write.py`, tuned for edits:

- **H-05:** an Edit to an audit log is allowed **only if it's a pure append** (the
  new text starts with the old text, which is how `/ca:override` adds a line). Any
  edit that alters or deletes existing lines is blocked.
- **H-11:** ADR edits require the active, fresh `/ca:adr` authoring marker.

**Reads:** the `file_path`, `old_string`/`new_string`, the authoring marker.
**Writes:** nothing. **Network:** none.

### PostToolUse(Write\|Edit): `post-write-edit.py`

**Advisory only; it never blocks.** After a write/edit lands, it surfaces reminders
so a relevant gate isn't a surprise later. It runs only in enabled repos.

| Tag | Reminder |
|---|---|
| H-12 | The file is governed by an accepted ADR with a `governs:` glob; route changes through `/ca:reconcile` or `/ca:adr`, don't drift silently |
| H-07 | A dependency manifest changed; dispatch `dependency-reviewer` before committing |
| H-09 | A crypto/TLS pattern appeared; run `crypto-compliance` (the commit will block until it records a pass) |
| H-10 | A possible hardcoded secret appeared; run `secret-handling` (same) |

**Reads:** the touched `file_path` and its content; ADR frontmatter under
`.codearbiter/decisions/`. **Writes:** a `governs-cache.json` under
`.codearbiter/.markers/`. That cache is a pure optimization, an mtime-keyed index of
the ADR `governs:` globs, rebuilt whenever the decisions change. **Network:** none.

### UserPromptSubmit / PreCompact: `prune-transcript.py`

The session-transcript pruner. It is **opt-in and off by default**, part of the
Feature Forge (`CODEARBITER_PRUNE`; see the README). When off, it does nothing.
When on, it trims redundant clutter from the session transcript so a long session
lives longer before compaction; gains land at resume/compaction, never mid-turn.
Dry-run is the default mode and writes nothing but a local metrics log. Stdlib only.

**Reads:** the session transcript JSONL (local, under `~/.claude/projects/…`).
**Writes:** only when explicitly enabled, namely the transcript itself (`on` mode)
and/or a local metrics file. **Network:** none.

---

## Non-event helper scripts

These live alongside the hooks but are **not** registered in `hooks.json`. They are
invoked by slash commands / skill prose, not by Claude Code events, and are listed
here for completeness.

| Script | Invoked by | What it does |
|---|---|---|
| `security-pass.py` | `crypto-compliance` / `secret-handling` skills, `/ca:override` | Records a security-gate pass **bound to the exact lines** it approved (it hashes the matching added lines), closing the TOCTOU window H-09b/H-10b would otherwise leave |
| `statusline.py` | the statusline command in `settings.json` | Renders the token-aware statusline (folder, git, rate limits, usage, cost, context, and, in enabled repos, the arbiter governance row). Read-only |
| `wire-statusline.py` | `/ca:statusline`, and the SessionStart self-heal | Installs/refreshes/removes the ca-owned statusline entry in `~/.claude/settings.json`, backing up and restoring any prior statusline |
| `doctor.py` | `/ca:doctor` | Verifies the install is actually enforcing: interpreter, payload, cache staleness, a live-fire hook probe. Read-only |
| `init-codearbiter.py` | `/ca:init` | Scaffolds the repo's `.codearbiter/` state store |
| `prune-transcript.py` | `/ca:prune` (CLI mode) | The same engine as the hook, driven manually with `status`/`dry`/`run`/`audit` subcommands |

Shared, dependency-free library modules (`_hooklib.py`, `_standuplib.py`,
`_prunelib.py`, `_babysitlib.py`) hold the pure logic the scripts above import; they
have no side effects of their own. Everything under `plugins/ca/hooks/tests/` is the
unit-test suite for these scripts. Run it with `pytest` from `plugins/ca/hooks/`.

## Verifying for yourself

```sh
# Confirm no hook makes a network call (no socket/http/urllib/requests):
grep -rEn 'socket|urllib|http\.client|requests\.|urlopen' plugins/ca/hooks/*.py

# See exactly what gets wired into Claude Code:
cat plugins/ca/hooks/hooks.json

# Prove the install is enforcing, with a live-fire probe:
/ca:doctor
```

The first command returns nothing, because there is no network code in any hook.
