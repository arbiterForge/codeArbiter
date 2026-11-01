---
title: Hooks & Host Adapters
description: "The shared Python hook core, the Claude Code, Codex, and Pi registration surfaces that carry its decisions, and how to trace one live block to source."
journey:
  level: "Reference"
  time: "5 minutes"
  outcome: "Locate a hook by event, entry point, or gate id and trace it to source."
  prerequisites:
    - "Enforcement & Security"
  proof: "You can take one live hook message and find its event, implementation file, and detailed gate entry."
---

The `ca`, `ca-codex`, and `ca-pi` plugins share the same Python guard core and `.codearbiter/`
activation state. Claude Code consumes the guard's exit-2 block directly. Codex routes shell and write events
through `pre-tool-adapter.py`, which returns Codex's structured deny result with the same gate ID and
feedback. Codex has no Read hook, statusline, or Claude-format transcript-pruning engine; see the
[Claude Code + Codex evidence](/getting-started/claude-code-and-codex/).

Pi composes the shared guard through a parent extension rather than Claude hook
events. Its rich footer is global to interactive parent sessions; the governance
row requires an enabled and affirmatively trusted repository, and rate-window
telemetry is omitted. Execute mode asks before governed mutations or external
side effects. Plan mode is read-only except for the current canonical spec,
plan, and plan ledger. Background jobs are session-only, never restored from Pi
session entries, and an unverified cleanup blocks later launches with a
`/ca-doctor` direction. These UI and job capabilities are parent-interactive
only and never enter hardened children.

The complete `ca-pi` adapter currently carries Feature Forge `preview` status.
Its documented matrix is green and real use is welcome, while broader testing
continues before stable status or a claim of 100% validation.

The shared guard core lives under `plugins/ca/hooks/`, but the three hosts register it differently.
Claude Code consumes Python hook exits directly. Codex uses an adapter that translates the same
decision into its structured hook result. Pi wraps its native tools and sends normalized events to
the bridge. Every surface checks the same repository activation state; see
[Enforcement & Security](/enforcement/) for the activation contract and fail posture.

## Trace One Live Decision

Use a disposable repository or the quickstart's live-fire probe. Do not manufacture a destructive
case in active work just to exercise a gate.

1. Record the **host**, complete verdict, and gate id, for example `BLOCKED [H-03]`.
2. Open the generated [Hook Gates reference](/reference/hooks-gates/) and search for that id. The
   entry names the current message, source file, source line, event, and matcher.
3. Find that event in the registration surface below: Claude Code's `hooks.json`, Codex's adapter
   registrations, or Pi's wrapper lifecycle.
4. Follow the source link into the shared guard and read its fail posture. A blocking pre-tool hook,
   an advisory post-write reminder, and a SessionStart diagnostic do not make the same promise.
5. Confirm the durable effect. A block or reminder may append to `gate-events.log`; an approved
   override writes `overrides.log`; a read-context injection deliberately writes neither.

For H-03, that trail is: doctor or a denied broad-stage attempt, the `H-03` Hook Gates entry,
`pre-bash.py`, the host's shell registration, and an explicit-file staging remediation. If any
link in that chain is missing, the result is not proven end to end.

For the exact message text emitted at each shared guard call site, see the generated
[Hook Gates reference](/reference/hooks-gates/). That page is generated from the Python
`block()`/`remind()` calls. The host tables below explain how each host reaches those guards.

## Registered enforcement surfaces

### Claude Code registrations

`plugins/ca/hooks/hooks.json` registers the shared scripts at Claude Code lifecycle and tool
boundaries. Each logical registration includes a direct `python` command and a compatibility
command that falls back to `python3` when `python` is not a usable Python 3 interpreter. They are
compatibility entries for the same script, not separate gate definitions. Run `/ca:doctor` to prove
the interpreter and live hook path on the machine actually in use.

| Event | Matcher | Script |
|-------|---------|--------|
| `SessionStart` | (any) | `session-start.py` |
| `PreToolUse` | `Bash\|PowerShell` | `pre-bash.py` |
| `PreToolUse` | `Write` | `pre-write.py` |
| `PreToolUse` | `Edit\|MultiEdit` | `pre-edit.py` |
| `PreToolUse` | `Read` | `pre-read.py` |
| `PostToolUse` | `Write\|Edit` | `post-write-edit.py` |
| `UserPromptSubmit` | (any) | `prune-transcript.py` |
| `UserPromptSubmit` | (any) | `prompt-submit.py` |
| `PreCompact` | (any) | `prune-transcript.py` |
| `PreCompact` | (any) | `prompt-submit.py` |

### Codex adapter registrations

`plugins/ca-codex/hooks/hooks.json` uses OS-specific `command` and `commandWindows` entries. Shell
and write calls enter `pre-tool-adapter.py`, which normalizes the event, calls the shared guard, and
returns a Codex-native deny result when blocked.

| Event | Matcher | Script |
|---|---|---|
| `SessionStart` | (any) | `session-start.py` |
| `PreToolUse` | `Bash\|shell_command\|exec_command\|unified_exec` | `pre-tool-adapter.py` |
| `PreToolUse` | `apply_patch\|Write\|Edit` | `pre-tool-adapter.py` |
| `PostToolUse` | `apply_patch\|Write\|Edit` | `post-write-edit.py` |
| `UserPromptSubmit` | (any) | `prune-transcript.py` |
| `UserPromptSubmit` | (any) | `prompt-submit.py` |

Codex does not register the Claude-only Read injection, `PreCompact`, or statusline surfaces.
`prompt-submit.py`'s compaction-generation bump is Claude-only for the same reason (Codex registers
no `PreCompact` hook at all).
The [host evidence page](/getting-started/claude-code-and-codex/) records that boundary.

### Pi wrapper events

Pi has no `hooks.json`. Its parent extension installs final wrappers around native and
codeArbiter-owned mutating tools, then uses Pi lifecycle events for the rest:

| Pi surface | What enters the shared core |
|---|---|
| Wrapped `bash`, `write`, `edit`, and governed custom tools | Normalized `tool_call` before execution |
| `read` and `tool_result` | Advisory context/result handling; reads do not become blocking Claude hooks |
| `session_start` / `before_agent_start` | Trust, activation, bridge readiness, and injected orchestration context |
| `session_before_compact` / `session_compact` | Native compaction validation and governance-state preservation |
| `session_shutdown` | Cleanup, background-job verification, and native-footer restoration |

Pi registers repository-aware dispatch only in an affirmatively trusted, enabled project. Hardened
children do not receive the parent-only footer, background-job, or nested-dispatch surfaces.

## Hook scripts

Each registered script's event, matcher, gates and fail posture, plus the non-event utilities and
shared libraries, are in the [hook script reference](/hooks/scripts/).
