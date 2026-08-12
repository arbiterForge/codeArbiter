---
title: Hooks & Host Adapters
description: "The shared Python hook core in detail, plus the Claude Code, Codex, and Pi registration surfaces that carry its decisions."
journey:
  level: "Reference"
  time: "10 minutes"
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

---

### session-start.py

- **Event:** `SessionStart`.
- **Script:** `session-start.py`.
- **What it does:** Emits the startup state, but **not** the persona itself (that composes at the
  per-turn seam; see `prompt-submit.py` below, and [The Persona-Register Split](/concepts/persona-and-context/)).
  - Clears the per-session mode marker (`.codearbiter/.markers/mode`), so a new session always
    resolves `arbiter`. If a prior session flipped to a non-`arbiter` mode and ended without
    flipping back, it first appends a synthetic `BY: session-cleanup | MODE: <name> exit` close
    line to `overrides.log` (legacy `DEV: exit` rows from before the mode plane are accepted by
    the same readers), so the enter/exit trail is never left half-open.
  - Heals the statusline wiring every session, persisting only on a real change (the wired path is absolute and version-pinned, so a plugin update can leave it stale).
  - Prints the startup state: stage, the active mode, blocking `CONFIRM-NN` open questions, and an in-flight task summary. An uninitialized repo is routed to `/ca:create-context` or `/ca:decompose`.
  - Emits a first-of-day standup briefing (working-tree state, ahead/behind annotated as possibly stale, ff-pull eligibility, prune candidates), gated by a per-day marker.
  - Spawns a fully detached `git fetch` that is never awaited, to keep ahead/behind fresh without blocking the hook.
  - Surfaces an **update-available** notice (`update available X → Y`) when the cached check shows a newer published release than the installed plugin, and spawns a fully detached, best-effort, once-daily refresh (`update-refresh.py`) that updates that cache off the hot path. The hook only ever reads the cache; the network fetch never blocks the SessionStart injection.
- **Why:** The project state the orchestrator needs to route the first request. Persona injection
  moved off this hook deliberately: `SessionStart` fires once per session boundary, so a
  mid-session mode flip could never change what it injected.
- **Fail posture:** Non-blocking (always exits 0). All git here is read-only and degrades per-field. A dormant or malformed repo prints a breadcrumb and exits.

---

### prompt-submit.py

- **Event:** `UserPromptSubmit` and `PreCompact` (Claude); `UserPromptSubmit` (Codex, no
  `PreCompact` registration).
- **Script:** `prompt-submit.py`.
- **What it does:** The mode-plane's prompt-seam interceptor. On a whole-prompt mode control token
  (`mode`, `mode --arbiter`, `mode --dangerous`, `mode --ops`, matched exactly and never as a substring)
  it flips or reports the mode and the turn never reaches the model. On any other prompt it composes
  `includes/safety-core.md` with the current mode's body and injects the result, deduplicated per
  (session, mode, compaction generation) so a steady session pays for one injection per mode change,
  not per turn. It refuses to compose a non-`arbiter` body the audit trail does not back, falling
  back to `arbiter` with a diagnostic. On `PreCompact` it bumps the compaction generation so the
  first turn after a compaction re-injects.
- **Why:** Composed injection has to live at the per-turn seam, not `SessionStart`, for a
  mid-session flip to take effect on the next turn at all.
- **Fail posture:** A failed flip **into** `dangerous`/`ops` leaves gates on (safe, the default
  direction). A failed flip **back to** `arbiter` must surface rather than silently staying
  gates-off. See [Enforcement & Security](/enforcement/) for the fail-direction rule.

---

### pre-bash.py

- **Event:** `PreToolUse`, matcher `Bash|PowerShell`.
- **Script:** `pre-bash.py`.
- **What it enforces:**
  - **H-00:** fail-closed backstop. If the guard itself crashes on an unexpected input, or git cannot be read to resolve the branch/diff state, the operation is **blocked** rather than allowed through. A guard that cannot determine whether an operation is safe treats it as unsafe.
  - **H-01:** no direct commit/push to the default branch (`main`/`master` case-insensitive), including a detached HEAD on a protected tip and protected refspecs (`HEAD:main`, `:main`, `refs/heads/main`, `--all`/`--mirror`). The branch is resolved against the repository the git command actually targets (a `git -C <dir>` composes repeated `-C` the way git does), not the session's project dir.
  - **H-02:** no force-push (`--force`, `--force-with-lease`, `--force-if-includes`, `-f`, `+refspec`).
  - **H-03:** no wildcard staging (flag forms `-A`/`--all`/`-u`/`.`; argument forms globs, directories, pathspec magic).
  - **H-05:** append-only audit logs. Shell truncation/rewrite verbs aimed at `overrides.log`/`triage.log`/`sprint-log.md`/`gate-events.log` are blocked. The protected name set is centralized (`_hooklib.AUDIT_LOG_BASENAMES`) so the shell, Write, and Edit flanks cannot drift.
  - **H-09b / H-10b:** crypto/secret commit gate. A commit introducing a sensitive line is blocked unless the `security-gate-passed` marker covers those exact lines (freshness under 30 min **and** per-line digest coverage). Scans the staged diff plus the worktree diff for `-a`, in-command `git add`, or a `git commit <pathspec>`.
  - **H-11:** ADRs only via `/ca:adr`. Shell redirects/verbs into `.codearbiter/decisions/` are blocked; reads pass.
  - **H-14:** migration review. A commit staging a migration is blocked unless `migration-gate-passed` covers that file's content digest.
  - **H-18:** the activation switch is protected. A shell write that would flip `.codearbiter/CONTEXT.md` off (`arbiter: disabled` or broken frontmatter) is blocked, so the gates cannot be silenced from inside the repo they govern.
  - **H-19:** gate-pass markers are cooperative attestation on the governed path. Common shell,
    Write, Edit, and patch forge attempts naming `security-gate-passed` or
    `migration-gate-passed` are blocked, while sanctioned recorder scripts bind a pass to content
    digests. This adds friction and an audit record; it does not make a public digest unforgeable to
    a determined same-user process. See the [marker trust boundary](/codearbiter-directory/#markers).
  - **H-20:** no `--no-verify` bypass. A literal `--no-verify`/`-n` on `git commit` (including bundled and attached-value short-flag clusters like `-nm`, mirroring git's own parsing) and a literal `--no-verify` on `git push` are blocked, because that flag skips the `.git/hooks` git-enforce backstop.
- **Why:** This is the load-bearing commit-time gate. The branch and force-push rules keep the default branch PR-only; the crypto/secret/migration gates keep dangerous content out of the committed artifact.
- **Fail posture:** Blocking (exit 2). Ambiguity resolves **closed**: a spelling indistinguishable from a destructive one is blocked. H-09b/H-10b and H-14 fail **closed** when git cannot read the diff or file list (a `None` sentinel, distinct from an empty diff), and a crash inside the guard itself blocks rather than allows (H-00). `/ca:override` is the sanctioned escape hatch.

---

### pre-write.py

- **Event:** `PreToolUse`, matcher `Write`.
- **Script:** `pre-write.py`.
- **What it enforces:**
  - **H-05:** a Write is a full overwrite, so any Write to an audit log (`overrides.log`/`triage.log`/`sprint-log.md`/`gate-events.log`) is blocked (append with Edit or `>>`).
  - **H-11:** a Write to any `.md` under `decisions/` is blocked unless a fresh `adr-authoring-active` marker is present (set by `/ca:adr`).
  - **H-18 / H-19:** a Write that would disable the `CONTEXT.md` activation switch, or a Write to a `.codearbiter/.markers/` gate-pass token, is blocked (the same integrity rules pre-bash enforces on the shell flank).
  - **H-21:** a host write envelope that cannot be decomposed into guardable per-file operations is blocked. Retry as a plain supported patch or split the operation; an opaque envelope never passes uninspected.
- **Why:** Closes the Write flank of the audit-trail, ADR-authoring, activation-switch, gate-marker, and opaque-envelope integrity rules.
- **Fail posture:** Blocking (exit 2).

---

### pre-edit.py

- **Event:** `PreToolUse`, matcher `Edit|MultiEdit`.
- **Script:** `pre-edit.py`.
- **What it enforces:**
  - **H-05:** on an audit log, MultiEdit is blocked outright (cannot express a verifiable append), an Edit with an empty `old_string` is blocked (it can never be a pure append), a `replace_all` Edit is rejected outright, and an Edit is admitted only as a strict **tail append**: `new_string` must equal the current content plus an appended tail, with `old_string` occurring exactly once. This closes the earlier hole where a mid-file insertion or a multi-site suffix rewrite passed as an "append".
  - **H-11:** the same fresh `adr-authoring-active` marker requirement for `decisions/` `.md` files.
  - **H-18 / H-19:** the same activation-switch and gate-marker protections as the Write flank.
  - **H-21:** an edit operation that cannot be normalized into guarded per-file operations is blocked and must be retried in a supported, decomposable form.
- **Why:** Closes the Edit/MultiEdit flank; an append-only log accepts only verifiable tail appends, and an opaque target set is never assumed safe.
- **Fail posture:** Blocking (exit 2).

---

### pre-read.py

- **Event:** `PreToolUse`, matcher `Read`.
- **Script:** `pre-read.py`.
- **What it does:** On a Read of a governed file, assembles a budgeted (150-token ceiling), freshness-gated note naming the decision, control, or spec that governs that path, and delivers it via `additionalContext` while always allowing the Read. See [Concepts: just-in-time context injection](/concepts/jit-context-injection/) for the four-tier governing map.
  - Searches four tiers in priority order: `security-controls.md` for security-classified files; an accepted ADR whose `governs:` glob matches the path; an approved spec whose `**Governs:**` header matches; a provenance enrichment entry whose stored hash still equals the file's current content.
  - Each `(session, file)` pair is injected at most once. A second Read of the same file in the same session produces no injection.
  - On a Read of a non-governed file, nothing fires. No git call runs; cost is a single index lookup.
- **Why:** Surfaces the governing context the moment a file opens, without requiring the agent's session to have already loaded the full doc set.
- **Fail posture:** Advisory, fail-open (always exits 0). Any error in the governing-map lookup, git call, or budget computation degrades to allow-with-no-injection. A Read is never blocked.

---

### post-write-edit.py

- **Event:** `PostToolUse`, matcher `Write|Edit`.
- **Script:** `post-write-edit.py`.
- **What it enforces (all advisory):**
  - **H-09 / H-10:** crypto/TLS or secret pattern touched; reminds that the commit will block until the gate records a pass.
  - **H-07:** dependency manifest changed; dispatch `dependency-reviewer`.
  - **H-12:** file governed by an accepted ADR (`governs:` glob); route to `/ca:reconcile` or `/ca:adr`.
  - **H-15:** CI/CD workflow changed; dispatch `security-reviewer` before merge.
  - **H-16:** deployment/IaC manifest changed; same.
  - **H-17:** auth/authorization logic touched (narrow, high-signal patterns).
  - **H-13:** anti-slop prose check for an em/en dash used as a prose separator in a user-facing doc.
- **Why:** Surfaces a sensitive touch early so the blocking commit-time gate is not a surprise.
- **Fail posture:** Advisory, non-blocking (`remind`, always exits 0). H-12/H-15/H-16/H-17 are advisory because their trigger is non-deterministic (auth) or their damage only lands downstream at merge/apply, not in the commit; the deterministic commit block is reserved for crypto/secret (H-09b/H-10b) and migrations (H-14).

---

### prune-transcript.py

- **Event:** `UserPromptSubmit` and `PreCompact`.
- **Script:** `prune-transcript.py`.
- **What it does:** Prunes transcript clutter to extend session lifetime, and emits a cold-miss nudge. The live transcript is only ever touched on the hook path; per-session prune state is recorded for the statusline. On `UserPromptSubmit` it also runs an **audit staleness check**: a non-blocking warning when an active `/sprint` or `/dev` flow has not appended its expected audit-log line within a bounded window (the completeness companion to the H-05 integrity guards; a warn, never a gate).
- **Why:** Keeps long sessions inside the context budget, and surfaces an audit flow that has gone silent.
- **Fail posture:** Non-blocking (always exits 0).

---

## Non-Event Scripts

These are not registered hooks. They are invoked by skills and slash commands, or wired into settings.

### statusline.py

The settings-wired statusline renderer (installed by `wire-statusline.py`; the rendering concerns are split across thin `_*lib` libraries behind this entry point). Usage segments (folder, git, model, rate limits, context, tokens, cost, burn) and a compact **update-available** indicator render everywhere; the arbiter segments (stage, tasks, questions, overrides) render only in an enabled repo, reusing the same activation parser the hooks use. The update indicator reads the same cache the SessionStart notice does and adds no network call. Cost reflects the host's authoritative total, with a cumulative cost ledger persisted to `~/.codearbiter/ledger.json`. Never prints a traceback; every segment degrades rather than breaks. **Read-only / display.**

### git-enforce.py

The `pre-commit` / `pre-push` shim installed into the repo's own `.git/hooks/` (idempotently, at `/ca:init` and on session start; never overwriting a pre-existing foreign hook). It enforces the protected-branch, force-push, and crypto/secret/migration gates **at the git operation itself**, below the command spelling: shell indirection (`g=git; $g commit`) that never reaches the `pre-bash.py` matcher is still gated. It resolves the repository it runs in via `git rev-parse --show-toplevel` from its own working directory, reuses the same detection primitives as `pre-bash.py` so the two cannot drift, and is written atomically so a torn install can never leave a sentinel-less partial shim. This backstop is what `pre-bash.py`'s H-20 protects (a `--no-verify` would skip it).

### security-pass.py / migration-pass.py

These record the gate passes that `pre-bash.py` checks. `security-pass.py` is run on PASS by the crypto-compliance / secret-handling skills: it writes the **line digests** of every sensitive line the gate approved to `security-gate-passed`. `migration-pass.py` is run on PASS by the commit gate after `migration-reviewer`: it writes the **content digests** of every approved migration to `migration-gate-passed` (no freshness window, since a migration is immutable). Both write atomically, so a half-written marker can never read as a valid pass. Binding by digest is what lets H-09b/H-10b/H-14 close the time-of-check / time-of-use window.

### Command Utilities

- **`init-codearbiter.py`** (`/ca:init`). Scaffolds the root-level `.codearbiter/` state store (idempotent; refuses if `CONTEXT.md` already exists). `--check` reports state and writes nothing.
- **`taskwrite.py`** (`/ca:task`). The only sanctioned mutator of `open-tasks.md` (add / start / done), written atomically and rerun-safe.
- **`doctor.py`** (`/ca:doctor`). Read-only health check covering interpreter health (warns loudly if no real interpreter resolves and every gate is dormant), payload integrity, stale-cache detection, repo activation, and statusline wiring. Exits non-zero on any failure but changes nothing.
- **`wire-statusline.py`** (`/ca:statusline`). Writes or removes the absolute `statusLine.command` in `~/.claude/settings.json` (atomically). The `refresh` action is the SessionStart self-heal that rewrites only a stale codeArbiter-owned path; it refuses to overwrite an unparseable settings file.
- **`update-refresh.py`**. The thin, fully detached entry point the SessionStart hook spawns for the once-daily update check. It performs the unauthenticated HTTPS `GET` to the GitHub Releases API and writes the result to the user-global cache; fail-silent, off the hot path, never awaited.
- **`boardsync.py`** (`/ca:task`, commit gate). Reconciles the task-board `[ ]`/`[~]`/`[x]` counters with the work, so a board transition lands atomically with its commit (ADR-0008).
- **`babysit.py` / `metrics.py` / `preview.py`**. Thin entry points for the `/ca:pr`+`/ca:watch`, `/ca:metrics`, and `/ca:preview` command surfaces, each importing its `_*lib` so the logic is `py_compile`- and test-covered rather than embedded as inline `python -c` in command prose.

### Shared Libraries

The `_*lib.py` files are shared internal libraries imported by the hooks and utilities above: the core `_hooklib`; the statusline stack (`_segmentslib`, `_gitlib`, `_arbiterstatelib`, `_subagentslib`, `_boxlib`, `_colorlib`, `_fmtlib`, `_sessionlib`, `_ledgerlib`); and the feature/utility libs (`_prunelib`, `_taskboardlib`, `_standuplib`, `_sloplib`, `_metricslib`, `_previewlib`, `_babysitlib`, `_provenancelib`, `_readinjectlib`, `_updatelib`). `_hooklib` is the core: it owns the activation contract, the `block`/`remind`/`warn` primitives (which also best-effort append every gate decision to the durable, append-only `.codearbiter/gate-events.log`), the centralized crypto/secret/audit-path sets (`AUDIT_LOG_BASENAMES`), and the digest helpers, so the separate hooks never drift on what they enforce.
