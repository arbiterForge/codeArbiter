---
title: Troubleshooting
description: "Use /ca:doctor or $ca-doctor to diagnose dormant gates, persona loading, trust, payload, and host-specific installation problems."
---

Run `/ca:doctor` in Claude Code or `$ca-doctor` in Codex when codeArbiter is not behaving as
expected. The command is a read-only health check over interpreter, payload, cache, activation, and
live-fire enforcement. Claude also checks statusline wiring. Codex instead requires its hook set to
be trusted through `/hooks`; start a fresh thread after approving a changed set.

## Run the Check

Open the project where the problem appears and run the host-native command:

```text
/ca:doctor
$ca-doctor
```

Doctor prints a result for each check and exits 0 if all pass, non-zero otherwise. Fix failures in the order reported: later failures are often downstream of the first.

## What Doctor Checks

### Interpreter Health

Doctor confirms that at least one Python interpreter resolves. codeArbiter registers every hook twice in `hooks.json`: once under `python3`, and once under a `python3 -c "" || python` fallback. On a stock Windows machine with only `python` on PATH, the fallback fires and the gates still run. If neither name resolves, doctor warns loudly: the gates are dormant and no enforcement is active.

Interpreter failure is the most common cause of a silent install.

**To fix:** add Python 3 to PATH. Verify outside Claude Code with `python3 --version` or `python --version`. At least one must succeed.

### Payload Integrity

Doctor checks that the plugin payload is internally consistent and all expected files are present.

**To fix:** if integrity fails, reinstall or update the plugin.

### Stale-Cache Detection

Cached payload data and settings paths can lag behind a plugin update. Doctor detects outdated entries and reports which ones are stale.

**To fix:** run `/ca:doctor` after every plugin update and follow the remediation it prints.

### Repo Activation

Doctor reads `.codearbiter/CONTEXT.md` and checks three things:

1. The file exists at the repo root.
2. The leading YAML frontmatter opens with `---` on line 1 and closes with a second `---`.
3. The closed block contains `arbiter: enabled`.

A repo without the file is dormant: the gates do not fire and no orchestrator persona is injected. An unclosed frontmatter block surfaces as a malformed-state error rather than silently treating the repo as disabled.

**To fix:** confirm the first three lines of `.codearbiter/CONTEXT.md` read:

```text
---
arbiter: enabled
---
```

If the file is absent, run `/ca:init` to scaffold it.

### Live-Fire Hook Probe

Doctor runs a hook invocation to confirm a hook binary actually executes end-to-end, not just that an interpreter binary is on PATH. A passing interpreter check alongside a failing probe points to a registration or permissions problem with the hook files themselves.

**To fix:** reinstall the plugin to repair hook registration.

### Statusline Wiring

**Claude Code only.** Codex has no statusline surface; do not treat that absence as a failed check.

Doctor checks that the `statusLine.command` entry in `~/.claude/settings.json` points to the current version of `statusline.py`. The stored path is absolute and version-pinned, so a plugin update can leave it pointing at the previous version. The `SessionStart` hook repairs this automatically each session, but doctor will report a stale wire before the first post-update session runs.

**To fix:** run `/ca:statusline` to re-wire explicitly, or open a new Claude Code session to trigger the automatic repair.

## Pi

On Pi, run `/ca-doctor` first — it is the diagnostic entry point, checking the active package path,
canonical Pi CLI and package origin, command ownership, supported-version fingerprints,
Python/core/bridge health, child fingerprint, final mutator wrappers, and the H-03 wrapper
self-test.

Pi has several distinct silent-inactivity states that look alike but have different fixes:

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Nothing enforces, no orchestrator persona | `.codearbiter/CONTEXT.md` missing or `arbiter: enabled` not set | Run `/ca-init`, per [Repo Activation](#repo-activation) above |
| Repo is enabled but still dormant | Pi project trust not granted | Grant Pi project trust for the repo, then start a fresh session |
| Trust was just granted but still dormant | Trust was granted in the current session, not a fresh one | Start a new session after granting trust — the parent registers repository-aware dispatch only on a fresh session that reports the trust decision |
| Mutating calls fail, or an interpreter breadcrumb appears | Python 3 not on `PATH` | Add Python 3 to `PATH`; `ca-pi` blocks mutating calls rather than failing silently when the interpreter is missing |
| `/ca-<name>` doesn't do anything | Wrong invocation syntax | Pi uses `/ca-<name>` generated aliases with `/skill:ca-<name>` as the host-native fallback — this differs from Codex's `$ca-<name>` convention |
| Doctor reports an unsupported version | Pi CLI is not 0.80.5 or 0.80.6 | Only Pi 0.80.5 and Pi 0.80.6 are supported in this release line; see [Compatibility](/getting-started/compatibility/) |

## Symptom Reference

| Symptom | Likely cause | Suggested check |
|---------|--------------|-----------------|
| Gates don't fire in any repo | `python3` and `python` both absent from PATH | Doctor's interpreter section; verify with `python --version` in a shell |
| Gates don't fire in one specific repo | `arbiter: enabled` missing or frontmatter unclosed | Doctor's repo activation section; inspect `.codearbiter/CONTEXT.md` |
| Orchestrator persona not loading | Repo not opted in; `SessionStart` finds no activation flag | Doctor's repo activation section; run `/ca:init` if the file is absent |
| Stale behavior after a plugin update | Cached payload or statusline path is outdated | Doctor's stale-cache and statusline sections |
| Statusline shows wrong stage or stale data | Statusline wired to previous `statusline.py` path | Doctor's statusline section; run `/ca:statusline` to re-wire |
| Malformed-state error on session start | Frontmatter opens with `---` but never closes | Inspect `.codearbiter/CONTEXT.md` line 2 for the closing `---` |
| Merged PR but task still open on board | Merged-but-not-flipped task | Doctor runs a read-only reconciliation sweep and reports any such tasks |

## Related

- [Enforcement and Security](/enforcement/) for the activation contract and dual-interpreter registration
- [Hooks reference](/hooks/) for per-hook behavior and fail postures that doctor inspects
- [doctor command reference](/reference/commands/doctor/) for the full command description
