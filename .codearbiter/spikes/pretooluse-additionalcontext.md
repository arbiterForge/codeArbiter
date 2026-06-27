# Spike — PreToolUse:Read additionalContext reachability (plugin vs settings scope)

**Branch:** `spike/pretooluse-additionalcontext` (never merges) · **Status:** PROBE WIRED — awaiting one post-restart observation.

## Question

On the current Claude Code build, does a **plugin-scoped** `PreToolUse:Read` hook's
`hookSpecificOutput.additionalContext` actually reach the model — or does claude-code
**#16538** (plugin-scoped `additionalContext` broken on SessionStart, closed "Not Planned")
extend to PreToolUse? Control: a **settings-scoped** hook with a distinct sentinel.

This gates AC-01 of `specs/file-scoped-context-injection.md`. Go → ship as a plugin hook
(zero install). No-go → ship a `/ca:statusline`-style settings.json installer.

## What was wired

A disposable probe (`.codearbiter/spikes/probe/inject_probe.py`, fail-open, emits
`allow` + a scope-tagged sentinel) registered on `PreToolUse` matcher `Read` in BOTH scopes:

| Scope | Registered in | Sentinel token |
|---|---|---|
| Plugin | `~/.claude/plugins/cache/codearbiter/ca/2.6.0/hooks/hooks.json` (added `Read` matcher) | `CA_SPIKE_PLUGIN_7F3A` |
| Settings (control) | `<repo>/.claude/settings.json` (added `hooks.PreToolUse` `Read` matcher) | `CA_SPIKE_SETTINGS_9B2C` |

Both JSON files validated as parseable. Hooks load at **session start**, so the probe
cannot fire in the session that wired it.

## RESUME PROCEDURE (do this after a restart/resume)

1. Restart or `--resume` the Claude Code session (forces hooks to reload).
2. Trigger **one Read** of any file (e.g. ask Claude to read a file).
3. Inspect the model-visible context attached to that Read for the sentinel tokens:
   - `CA_SPIKE_PLUGIN_7F3A` present → **plugin-scope WORKS** → AC-01 = GO (ship plugin hook).
   - only `CA_SPIKE_SETTINGS_9B2C` present → **#16538 extends to PreToolUse** → AC-01 = NO-GO
     (ship settings installer).
   - both → both work (prefer plugin hook).
   - neither → PreToolUse:Read injection not firing at all — investigate matcher/registration
     before concluding.
4. Record the result under "## Answer" below.

## Answer

**GO — plugin-scope works.** After a resume, a single Read surfaced BOTH sentinels in the
model's context as `PreToolUse:Read hook additional context` system reminders:

- `CA_SPIKE_PLUGIN_7F3A` (plugin-scoped, `~/.claude/plugins/cache/.../hooks.json`) — **REACHED**
- `CA_SPIKE_SETTINGS_9B2C` (settings-scoped, `<repo>/.claude/settings.json`) — **REACHED**

**Conclusion:** plugin-scoped `PreToolUse:Read` `hookSpecificOutput.additionalContext` reaches
the model on this Claude Code build. **claude-code #16538 is SessionStart-specific and does NOT
extend to PreToolUse.** A `permissionDecision:"allow"` + `additionalContext` payload injects while
allowing the Read, observed directly.

**Implication for `specs/file-scoped-context-injection.md`:** AC-01 = **GO** → ship as a plugin
`hooks.json` `PreToolUse` matcher `Read` (zero install). The settings.json installer fallback
(AC-02 no-go branch) is **not needed** and can be dropped from the implementation scope.

## CLEANUP CHECKLIST (run regardless of outcome — these edits are OUTSIDE the spike branch)

- [ ] Remove the `Read` matcher block from
      `~/.claude/plugins/cache/codearbiter/ca/2.6.0/hooks/hooks.json`.
- [ ] Remove the `hooks` key from `<repo>/.claude/settings.json` (restore to just `spinnerVerbs`).
- [ ] Delete branch `spike/pretooluse-additionalcontext` and the `.codearbiter/spikes/probe/` probe.
- [ ] `.claude/settings.local.json` (the `FARM_API_KEY`) was NOT touched — verified git-ignored,
      never committed. No action.

## Implication

Either result keeps the feature alive — the spec already branches on AC-01. This spike only
decides **which wiring** ships, not **whether** to build. On answer, hand findings to
`/ca:feature` against `specs/file-scoped-context-injection.md`.
