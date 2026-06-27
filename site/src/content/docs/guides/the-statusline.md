---
title: "Set up the statusline"
description: "Wire codeArbiter's statusline into Claude Code so every session shows usage metrics, and enabled repos show the active project state."
---

Run `/ca:statusline` once in any Claude Code session to wire the bar. The command writes an absolute `statusLine.command` entry in `~/.claude/settings.json`, pointing at the renderer for your installed plugin version.

**You will need:** the plugin installed (see [Install](/getting-started/install/)).

## 1. Wire the statusline

Open any Claude Code session and run:

```text
/ca:statusline
```

If a `statusLine.command` already exists in your settings, the current value is backed up before being replaced. Uninstalling restores the backed-up value; if there was none, the key is removed. The command also writes codeArbiter's `spinnerVerbs` set and backs up any prior verbs, restored on uninstall.

To inspect the current state without modifying settings, run `/ca:statusline status`. Output shows whether `settings.json` is present, the renderer path (with a found/MISSING indicator), the active `statusLine.command`, and whether it belongs to codeArbiter.

## 2. What the bar shows

The bar has two tiers of segments.

### Usage segments

These render in every Claude Code session, regardless of whether the open repo is arbiter-enabled.

| Segment | Shows |
|---------|-------|
| **folder** | Active working directory, abbreviated to key path components |
| **git** | Repo owner/name and current branch, with a dirty-state marker when uncommitted changes are present |
| **model** | Model display name and effort level as a colored pill |
| **rate limits** | 5-hour and 7-day API usage percentages, with reset countdowns when the host supplies them |
| **context** | Context window usage bar, used percentage, and remaining headroom before auto-compaction |
| **tokens** | Session and daily in/out token counts, deduplicated by request ID across transcript entries |
| **cost** | Cumulative API-equivalent cost from Claude Code's authoritative session total, persisted across sessions in `~/.codearbiter/ledger.json` |
| **burn** | Per-message token sparkline built from recent transcript calls |

### Arbiter segments

These render only when the open repo carries `arbiter: enabled` in `.codearbiter/CONTEXT.md`. The activation check uses the same frontmatter parser the enforcement hooks use, so the bar and the gates always agree on whether a repo is active. See [Enforcement & Security](/enforcement/) for the activation contract.

| Segment | Shows |
|---------|-------|
| **stage** | Current project stage from the `stage` key in `CONTEXT.md` frontmatter |
| **tasks** | In-flight task count from `open-tasks.md`; done tasks are excluded |
| **questions** | Count of open `CONFIRM-NN` questions in `open-questions.md` |
| **overrides** | Override entries logged since the last `/ca:checkpoint` |

A non-zero `questions` or `overrides` count renders in red. A non-zero `tasks` count renders in white. A green dot before the arbiter row confirms the repo is active.

## 3. Remove the statusline

```text
/ca:statusline uninstall
```

If a prior `statusLine.command` was backed up at install time, it is restored. Spinner verbs are restored the same way.

## SessionStart self-heal

Every session, `session-start.py` runs the `refresh` action automatically. If the wired path points at a previous plugin version, for example after a plugin update moves the renderer, the path is rewritten to the current absolute location. The write happens only when the path actually changed; a steady-state session never modifies `settings.json`.

If the renderer file is absent mid-update, the self-heal skips the write. A later session where the file is present corrects the path.

## Unparseable settings file

`/ca:statusline` refuses to touch `~/.claude/settings.json` when the file is not valid JSON:

```
REFUSING TO WRITE: ~/.claude/settings.json is not valid JSON (...).
Fix it by hand, then re-run - I will not clobber an unparseable settings file.
```

Open the file in a text editor, restore valid JSON, then re-run `/ca:statusline`.

---

For the `statusline.py` renderer and `wire-statusline.py` script reference, see [Hooks reference: non-event scripts](/hooks/#non-event-scripts).
