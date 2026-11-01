---
title: "Hook Script Reference"
description: "Each codeArbiter hook script: its event, matcher, gates and fail posture, plus the non-event utilities and shared libraries behind them."
journey:
  level: "Reference"
  time: "Lookup"
  outcome: "Find what one hook script or helper does, which event runs it, and how it fails."
  prerequisites:
    - "Hooks & Host Adapters"
  proof: "You can name the event, matcher and fail posture of the script you looked up."
---

One entry per shipped script under `plugins/ca/hooks/`. For how Claude Code, Codex and Pi register
these scripts, and how to trace a live block to source, start with
[Hooks & Host Adapters](/hooks/).

## Event hook scripts

One entry per registered script: its event, matcher, gates and fail posture.

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
  - **H-09b / H-10b:** crypto/secret commit gate. A commit introducing a sensitive line is blocked unless the `security-gate-passed` marker covers those exact lines (per-line digest coverage bound to the file path, with no time window). Scans the staged diff plus the worktree diff for `-a`, in-command `git add`, or a `git commit <pathspec>`.
  - **H-11:** ADRs only via `/ca:adr`. Shell redirects/verbs into `.codearbiter/decisions/` are blocked; reads pass.
  - **H-14:** migration review. A commit staging a migration is blocked unless `migration-gate-passed` covers that file's content digest.
  - **H-18:** the activation switch is protected. A shell write that would flip `.codearbiter/CONTEXT.md` off (`arbiter: disabled` or broken frontmatter) is blocked, so the gates cannot be silenced from inside the repo they govern.
  - **H-19:** gate-pass markers are cooperative attestation on the governed path. Common shell,
    Write, Edit, and patch forge attempts naming `security-gate-passed` or
    `migration-gate-passed` are blocked, while sanctioned recorder scripts bind a pass to content
    digests. This adds friction and an audit record; it does not make a public digest unforgeable to
    a determined same-user process. See the [marker trust boundary](/codearbiter-directory/files/#markers).
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
- **What it does:** Prunes transcript clutter to extend session lifetime, and emits a cold-miss nudge. The live transcript is only ever touched on the hook path; per-session prune state is recorded for the statusline. On `UserPromptSubmit` it also runs an **audit staleness check**: a non-blocking warning when an active `/sprint` flow, or a session holding a non-default mode (`mode --dangerous` / `mode --ops`), has not appended its expected audit-log line within a bounded window (the completeness companion to the H-05 integrity guards; a warn, never a gate).
- **Why:** Keeps long sessions inside the context budget, and surfaces an audit flow that has gone silent.
- **Fail posture:** Non-blocking (always exits 0).

## Non-Event Scripts

These are not registered hooks. They are invoked by skills and slash commands, or wired into settings.

### statusline.py

The settings-wired statusline renderer (installed by `wire-statusline.py`; the rendering concerns are split across thin `_*lib` libraries behind this entry point). Usage segments (folder, git, model, rate limits, context, tokens, cost, burn) and a compact **update-available** indicator render everywhere; the arbiter segments (stage, tasks, questions, overrides) render only in an enabled repo, reusing the same activation parser the hooks use. The update indicator reads the same cache the SessionStart notice does and adds no network call. Cost is the API-equivalent reconstructed from the parent and subagent transcripts at list rates, labelled by coverage (`api≈` complete, `api≥` lower bound, `api≈?` no defensible figure, `host≈` Claude Code's own estimate for Session only when reconstruction is unavailable); per-session accounting state lives under `~/.codearbiter/ledger.json.sessions/`. Never prints a traceback; every segment degrades rather than breaks. **Read-only / display.**

### git-enforce.py

The `pre-commit` / `pre-push` shim installed into the repo's own `.git/hooks/` (idempotently, at `/ca:init` and on session start; never overwriting a pre-existing foreign hook). It enforces the protected-branch, force-push, and crypto/secret/migration gates **at the git operation itself**, below the command spelling: shell indirection (`g=git; $g commit`) that never reaches the `pre-bash.py` matcher is still gated. It resolves the repository it runs in via `git rev-parse --show-toplevel` from its own working directory, reuses the same detection primitives as `pre-bash.py` so the two cannot drift, and is written atomically so a torn install can never leave a sentinel-less partial shim. This backstop is what `pre-bash.py`'s H-20 protects (a `--no-verify` would skip it).

### security-pass.py / migration-pass.py

These record the gate passes that `pre-bash.py` checks. `security-pass.py` is run on PASS by the crypto-compliance / secret-handling skills: it writes the **line digests** of every sensitive line the gate approved to `security-gate-passed`. `migration-pass.py` is run on PASS by the commit gate after `migration-reviewer`: it writes the **content digests** of every approved migration to `migration-gate-passed` (likewise no time window, since a migration is immutable). Both write atomically, so a half-written marker can never read as a valid pass. Binding by digest is what lets H-09b/H-10b/H-14 close the time-of-check / time-of-use window.

### Command Utilities

- **`init-codearbiter.py`** (`/ca:init`). Scaffolds the root-level `.codearbiter/` state store (idempotent; refuses if `CONTEXT.md` already exists). `--check` reports state and writes nothing.
- **`taskwrite.py`** (`/ca:task`). The sanctioned legacy-board mutator (add / start / done / archive and selected work edits), written atomically. Native projects use the selected `work.py` facade.
- **`work.py`**. Selects legacy or native work ownership. New HTML projects receive a portable native project ID when knowledge initialization completes. Native work can carry an optional cycle ID; `cycle-view` derives a bounded HTML overview from canonical work references. `view <WORK-ID> --save` refreshes a local derived page with check, delivery and provider states shown separately.
- **`doctor.py`** (`/ca:doctor`). Read-only health check covering interpreter health (warns loudly if no real interpreter resolves and every gate is dormant), payload integrity, stale-cache detection, repo activation, and statusline wiring. Exits non-zero on any failure but changes nothing.
- **`wire-statusline.py`** (`/ca:statusline`). Writes or removes the absolute `statusLine.command` in `~/.claude/settings.json` (atomically). The `refresh` action is the SessionStart self-heal that rewrites only a stale codeArbiter-owned path; it refuses to overwrite an unparseable settings file.
- **`update-refresh.py`**. The thin, fully detached entry point the SessionStart hook spawns for the once-daily update check. It performs the unauthenticated HTTPS `GET` to the GitHub Releases API and writes the result to the user-global cache; fail-silent, off the hot path, never awaited.
- **`boardsync.py`** (`/ca:task`, commit gate). Reconciles the task-board `[ ]`/`[~]`/`[x]` counters with the work, so a board transition lands atomically with its commit (ADR-0008).
- **`babysit.py`**. Thin entry point for the `/ca:pr`+`/ca:watch` command surface, importing its `_*lib` so the logic is `py_compile`- and test-covered rather than embedded as inline `python -c` in command prose.

### Shared Libraries

The `_*lib.py` files are shared internal libraries imported by the hooks and utilities above: the core `_hooklib`; the statusline stack (`_segmentslib`, `_gitlib`, `_arbiterstatelib`, `_subagentslib`, `_boxlib`, `_colorlib`, `_fmtlib`, `_sessionlib`, `_ledgerlib`); and the feature/utility libs (`_prunelib`, `_taskboardlib`, `_standuplib`, `_sloplib`, `_babysitlib`, `_provenancelib`, `_readinjectlib`, `_updatelib`). `_hooklib` is the core: it owns the activation contract, the `block`/`remind`/`warn` primitives (which also best-effort append every gate decision to the durable, append-only `.codearbiter/gate-events.log`), the centralized crypto/secret/audit-path sets (`AUDIT_LOG_BASENAMES`), and the digest helpers, so the separate hooks never drift on what they enforce.
