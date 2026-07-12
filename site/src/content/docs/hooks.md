---

The `ca` and `ca-codex` plugins share the same Python guard core and `.codearbiter/` activation
state. Claude Code consumes the guard's exit-2 block directly. Codex routes shell and write events
through `pre-tool-adapter.py`, which returns Codex's structured deny result with the same gate ID and
feedback. Codex has no Read hook, statusline, or Claude-format transcript-pruning engine; see the
[Claude Code + Codex evidence](/getting-started/claude-code-and-codex/).
title: Hooks Reference
description: "A complete per-hook reference for codeArbiter: every registered Claude Code hook, the gates it enforces, its fail posture, and the non-event scripts behind the commands."
---

codeArbiter enforces its gates as Claude Code hooks under `plugins/ca/hooks/`. Every hook is stdlib-only Python, registered in `hooks.json`, and runs only in an arbiter-enabled repo (see [Enforcement & Security](/enforcement) for the activation contract and the fail-loud posture). A blocking hook exits 2; an advisory hook prints a reminder and exits 0.

Every hook is registered **twice** in `hooks.json`: once under `python3`, and once under a `python3 -c "" || python` fallback. On a stock Windows box that has only the `python` interpreter, the gates still fire. The two entries each receive their own stdin, so a real block is never swallowed by the fallback.

For the exact, word-for-word message text a hook prints for every gate ID — generated directly from each `block()`/`remind()` call site, so it can never drift from the narrative summaries below — see the [Hook Gates reference](/reference/hooks-gates/).

## Registered Hooks

| Event | Matcher | Script |
|-------|---------|--------|
| `SessionStart` | (any) | `session-start.py` |
| `PreToolUse` | `Bash\|PowerShell` | `pre-bash.py` |
| `PreToolUse` | `Write` | `pre-write.py` |
| `PreToolUse` | `Edit\|MultiEdit` | `pre-edit.py` |
| `PreToolUse` | `Read` | `pre-read.py` |
| `PostToolUse` | `Write\|Edit` | `post-write-edit.py` |
| `UserPromptSubmit` | (any) | `prune-transcript.py` |
| `PreCompact` | (any) | `prune-transcript.py` |

---

### session-start.py

- **Event:** `SessionStart`.
- **Script:** `session-start.py`.
- **What it does:** Injects the orchestrator persona and the startup state.
  - Clears the per-session `/ca:dev` marker. If a prior session entered `/ca:dev` and ended without `/ca:arbiter`, it first appends a synthetic `BY: session-cleanup | DEV: exit` close line to `overrides.log`, so the dev enter/exit trail is never left half-open.
  - Heals the statusline wiring every session, persisting only on a real change (the wired path is absolute and version-pinned, so a plugin update can leave it stale).
  - Injects `ORCHESTRATOR.md` to plain stdout (the reliable injection path for a plugin-scoped hook).
  - Prints the startup state: stage, blocking `CONFIRM-NN` open questions, and an in-flight task summary. An uninitialized repo is routed to `/ca:create-context` or `/ca:decompose`.
  - Emits a first-of-day standup briefing (working-tree state, ahead/behind annotated as possibly stale, ff-pull eligibility, prune candidates), gated by a per-day marker.
  - Spawns a fully detached `git fetch` that is never awaited, to keep ahead/behind fresh without blocking the hook.
  - Surfaces an **update-available** notice (`update available X → Y`) when the cached check shows a newer published release than the installed plugin, and spawns a fully detached, best-effort, once-daily refresh (`update-refresh.py`) that updates that cache off the hot path. The hook only ever reads the cache; the network fetch never blocks the SessionStart injection.
- **Why:** One always-loaded persona, plus the project state the orchestrator needs to route the first request.
- **Fail posture:** Non-blocking (always exits 0). All git here is read-only and degrades per-field. A dormant or malformed repo prints a breadcrumb and exits.

---

### pre-bash.py

- **Event:** `PreToolUse`, matcher `Bash|PowerShell`.
- **Script:** `pre-bash.py`.
- **What it enforces:**
  - **H-00:** fail-closed backstop. If the guard itself crashes on an unexpected input, or git cannot be read to resolve the branch/diff state, the operation is **blocked** rather than allowed through — a guard that cannot determine whether an operation is safe treats it as unsafe.
  - **H-01:** no direct commit/push to the default branch (`main`/`master` case-insensitive), including a detached HEAD on a protected tip and protected refspecs (`HEAD:main`, `:main`, `refs/heads/main`, `--all`/`--mirror`). The branch is resolved against the repository the git command actually targets (a `git -C <dir>` composes repeated `-C` the way git does), not the session's project dir.
  - **H-02:** no force-push (`--force`, `--force-with-lease`, `--force-if-includes`, `-f`, `+refspec`).
  - **H-03:** no wildcard staging (flag forms `-A`/`--all`/`-u`/`.`; argument forms globs, directories, pathspec magic).
  - **H-05:** append-only audit logs. Shell truncation/rewrite verbs aimed at `overrides.log`/`triage.log`/`sprint-log.md`/`gate-events.log` are blocked. The protected name set is centralized (`_hooklib.AUDIT_LOG_BASENAMES`) so the shell, Write, and Edit flanks cannot drift.
  - **H-09b / H-10b:** crypto/secret commit gate. A commit introducing a sensitive line is blocked unless the `security-gate-passed` marker covers those exact lines (freshness under 30 min **and** per-line digest coverage). Scans the staged diff plus the worktree diff for `-a`, in-command `git add`, or a `git commit <pathspec>`.
  - **H-11:** ADRs only via `/ca:adr`. Shell redirects/verbs into `.codearbiter/decisions/` are blocked; reads pass.
  - **H-14:** migration review. A commit staging a migration is blocked unless `migration-gate-passed` covers that file's content digest.
  - **H-18:** the activation switch is protected. A shell write that would flip `.codearbiter/CONTEXT.md` off (`arbiter: disabled` or broken frontmatter) is blocked, so the gates cannot be silenced from inside the repo they govern.
  - **H-19:** gate-pass markers are unforgeable by hand. Shell redirects/verbs naming `security-gate-passed`/`migration-gate-passed` are blocked; only the sanctioned recorder scripts may write them.
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
- **Why:** Closes the Write flank of the audit-trail, ADR-authoring, activation-switch, and gate-marker integrity rules.
- **Fail posture:** Blocking (exit 2).

---

### pre-edit.py

- **Event:** `PreToolUse`, matcher `Edit|MultiEdit`.
- **Script:** `pre-edit.py`.
- **What it enforces:**
  - **H-05:** on an audit log, MultiEdit is blocked outright (cannot express a verifiable append), an Edit with an empty `old_string` is blocked (it can never be a pure append), a `replace_all` Edit is rejected outright, and an Edit is admitted only as a strict **tail append** — `new_string` must equal the current content plus an appended tail, with `old_string` occurring exactly once. This closes the earlier hole where a mid-file insertion or a multi-site suffix rewrite passed as an "append".
  - **H-11:** the same fresh `adr-authoring-active` marker requirement for `decisions/` `.md` files.
  - **H-18 / H-19:** the same activation-switch and gate-marker protections as the Write flank.
- **Why:** Closes the Edit/MultiEdit flank; an append-only log accepts only verifiable tail appends.
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

The `pre-commit` / `pre-push` shim installed into the repo's own `.git/hooks/` (idempotently, at `/ca:init` and on session start; never overwriting a pre-existing foreign hook). It enforces the protected-branch, force-push, and crypto/secret/migration gates **at the git operation itself**, below the command spelling — so shell indirection (`g=git; $g commit`) that never reaches the `pre-bash.py` matcher is still gated. It resolves the repository it runs in via `git rev-parse --show-toplevel` from its own working directory, reuses the same detection primitives as `pre-bash.py` so the two cannot drift, and is written atomically so a torn install can never leave a sentinel-less partial shim. This backstop is what `pre-bash.py`'s H-20 protects (a `--no-verify` would skip it).

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
