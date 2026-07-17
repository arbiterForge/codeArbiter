---
title: "Set Up the Statusline"
description: "What codeArbiter's statusline shows, and how to wire it into Claude Code so every session shows usage metrics and enabled repos show the active project state."
---

> **Claude Code only.** Codex has no statusline surface. Its SessionStart briefing presents the
> shared `.codearbiter/` governance state instead; this is an intentional host difference.

codeArbiter ships a token-aware statusline for Claude Code: a compact, full-width box that shows
your session usage in every repo and, in an [arbiter-enabled](/glossary/#arbiter-enabled-flag) one, the live project state. It is
dependency-free (native font glyphs only, no Nerd Font) and renders on every session once wired.

<figure class="ca-diagram">
  <img
    src="/codeArbiter/diagrams/statusline.png"
    alt="The codeArbiter statusline: a folder row; a git row with repo, branch, and a model pill; rate-limit percentages with reset countdowns; an arbiter row (green dot) showing stage, tasks, open questions, and overrides; and session/today token, cost, burn, and context-usage segments."
    loading="lazy"
    width="2174"
    height="406"
  />
  <figcaption>The statusline in an arbiter-enabled repo: usage segments plus the arbiter row (green dot). Rendered from the live `statusline.py` with mock values.</figcaption>
</figure>

**You will need:** the plugin installed (see [Install](/getting-started/install/)).

## Choose a Color Theme

The statusline defaults to its original violet palette. Set `CODEARBITER_THEME` in the
environment that launches Claude Code to select `violet`, `blue`, `green`, `amber`, or `mono`.
Names are case-insensitive. An unrecognized name falls back to `violet`, so a typo cannot break
the renderer.

```text
CODEARBITER_THEME=blue
```

For a custom palette, set `CODEARBITER_THEME=custom`. The renderer reads
`~/.codearbiter/statusline-theme.json` unless `CODEARBITER_THEME_FILE` names another local file.
Both `~` and environment variables in that path are expanded. The file is read-only: rendering
does not write configuration or make network requests.

```json
{
  "accent": {
    "deep": "#6c46b4",
    "mid": "#965ce6",
    "primary": "#b266ff",
    "bright": "#d08cff"
  },
  "text": {
    "muted": "#9696a2",
    "normal": "#e8e8f0",
    "on_accent": "#120e1a"
  },
  "semantic": {
    "ok": "#78dc96",
    "warn": "#ffb84c",
    "danger": "#ff566e"
  },
  "gradient": {
    "from": "#7850c8",
    "to": "#cd8cff"
  }
}
```

Every field is optional and omitted fields inherit from `violet`. Values must use six-digit
`#RRGGBB` notation. Unknown keys and invalid color values are ignored. A missing, unreadable,
oversized, malformed, or non-object file rejects the custom theme as a whole and safely renders
with `violet` instead.

The standard `NO_COLOR` environment variable takes precedence over every built-in and custom
theme. When it is present, the final statusline contains no ANSI color sequences while retaining
the same text, glyphs, spacing, and clipping.

### Built-in Theme Captures

These deterministic, ANSI-free terminal captures show the same subagent row under every built-in
theme. The `accent` annotation records the bright-accent RGB used for the model tag; text stays
identical because theme selection changes color only.

```text
violet  accent #d08cff  | task:Review parser | model:sonnet-4-6 | in:1.2K out:340 age:8s |
blue    accent #7dbeff  | task:Review parser | model:sonnet-4-6 | in:1.2K out:340 age:8s |
green   accent #6fe7a9  | task:Review parser | model:sonnet-4-6 | in:1.2K out:340 age:8s |
amber   accent #ffc768  | task:Review parser | model:sonnet-4-6 | in:1.2K out:340 age:8s |
mono    accent #e2e2e8  | task:Review parser | model:sonnet-4-6 | in:1.2K out:340 age:8s |
```

## What the Bar Shows

The bar has two tiers of segments.

### Usage Segments

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
| **subagents** | Recent tasks with liveness, selected model, input/output tokens, and age; mixed or missing model metadata is explicit |

### Arbiter Segments

These render only when the open repo carries `arbiter: enabled` in `.codearbiter/CONTEXT.md`. The activation check uses the same frontmatter parser the enforcement hooks use, so the bar and the gates always agree on whether a repo is active. See [Enforcement & Security](/enforcement/) for the activation contract.

| Segment | Shows |
|---------|-------|
| **stage** | Current project stage from the `stage` key in `CONTEXT.md` frontmatter |
| **tasks** | In-flight task count from `open-tasks.md`; done tasks are excluded |
| **questions** | Count of open `CONFIRM-NN` questions in `open-questions.md` |
| **overrides** | Override entries logged since the last `/ca:checkpoint` |

A non-zero `questions` or `overrides` count renders in red. A non-zero `tasks` count renders in white. A green dot before the arbiter row confirms the repo is active.

## Wire It In

Run `/ca:statusline` once in any Claude Code session to wire the bar. The command writes an absolute `statusLine.command` entry in `~/.claude/settings.json`, pointing at the renderer for your installed plugin version.

```text
/ca:statusline
```

If a `statusLine.command` already exists in your settings, the current value is backed up before being replaced. Uninstalling restores the backed-up value; if there was none, the key is removed. The command also writes codeArbiter's `spinnerVerbs` set and backs up any prior verbs, restored on uninstall.

To inspect the current state without modifying settings, run `/ca:statusline status`. Output shows whether `settings.json` is present, the renderer path (with a found/MISSING indicator), the active `statusLine.command`, and whether it belongs to codeArbiter.

## Remove the Statusline

```text
/ca:statusline uninstall
```

If a prior `statusLine.command` was backed up at install time, it is restored. Spinner verbs are restored the same way.

## SessionStart Self-Heal

Every session, `session-start.py` runs the `refresh` action automatically. If the wired path points at a previous plugin version, for example after a plugin update moves the renderer, the path is rewritten to the current absolute location. The write happens only when the path actually changed; a steady-state session never modifies `settings.json`.

If the renderer file is absent mid-update, the self-heal skips the write. A later session where the file is present corrects the path.

## Unparseable Settings File

`/ca:statusline` refuses to touch `~/.claude/settings.json` when the file is not valid JSON:

```
REFUSING TO WRITE: ~/.claude/settings.json is not valid JSON (...).
Fix it by hand, then re-run - I will not clobber an unparseable settings file.
```

Open the file in a text editor, restore valid JSON, then re-run `/ca:statusline`.

---

For the `statusline.py` renderer and `wire-statusline.py` script reference, see [Hooks reference: non-event scripts](/hooks/#non-event-scripts).
