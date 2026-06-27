---
title: Enforcement & Security
description: "How codeArbiter enforces its gates at the tool-call boundary: the activation contract, the blocking commit-time gates, advisory reminders, and the fail-loud posture."
---

codeArbiter's gates are not advice the model can talk past. They run as Claude Code hooks at the tool-call boundary, in Python, with no network and no third-party dependencies. A blocking gate exits non-zero, and the tool call never happens. This page states what is enforced, where it fails open versus closed, and the security posture behind it.

For the per-hook breakdown, see the [Hooks reference](/hooks).

## The activation contract

codeArbiter is dormant until a repository opts in. Every enforcement hook calls `arbiter_active()`, which is true only when `.codearbiter/CONTEXT.md` carries `arbiter: enabled` in a properly closed leading YAML frontmatter block. A repo with no such file, or no such line, loads nothing and blocks nothing.

- **Opt-in by file, not by install.** Installing the plugin does not enforce anything. Enforcement begins the moment `CONTEXT.md` declares the repo enabled.
- **Persona injection.** On an enabled repo, the `SessionStart` hook injects the orchestrator persona. That single file is the only always-loaded context.
- **Malformed frontmatter fails loud.** A frontmatter block that opens (`---` on line 1) but never closes is surfaced as a malformed-state error, not silently treated as disabled. A file with no frontmatter at all is simply dormant.

## Blocking commit-time gates

These run in `pre-bash.py` on `PreToolUse(Bash|PowerShell)` (plus the Write/Edit guards for the audit trail and ADRs). Each blocks the tool call outright. Ambiguity resolves **closed**: a spelling that cannot be told apart from a destructive one is blocked, and `/ca:override` is the sanctioned escape hatch.

| Gate | Enforces |
|------|----------|
| **H-01** | No direct commit or push to the default branch. Covers `main`/`master` case-insensitively, a **detached HEAD sitting on a protected branch's tip** (the commit still lands on that history), and protected **refspecs** (`HEAD:main`, `feature:main`, `:main` deletion, `refs/heads/main`), plus `--all`/`--mirror` bulk pushes that publish every ref. |
| **H-02** | No force-push, in any spelling: `--force`, `--force-with-lease`, `--force-if-includes`, bare `-f`, or a forcing `+refspec`. |
| **H-03** | No wildcard staging. Blocks the flag forms (`-A`, `--all`, `-u`, `.`) and the argument forms (globs, directories, pathspec magic). Staging must name files. |
| **H-05** | Append-only audit logs (`overrides.log`, `triage.log`, `sprint-log.md`). Shell truncation/rewrite verbs aimed at a log are blocked; the Write/Edit flank blocks overwrites, an **empty-`old_string` Edit** (not a verifiable append), and MultiEdit on a log. |
| **H-09b / H-10b** | Crypto and secret commit gate. A commit that introduces a crypto/TLS or secret line is blocked unless the crypto-compliance / secret-handling gate has recorded a pass for **those exact lines**. |
| **H-11** | ADRs are authored only via `/ca:adr`. Both the shell flank (redirects, `cp`, `rm`, `sed -i` into `decisions/`) and the Write/Edit flank are guarded; the skill drops a fresh authoring marker first. |
| **H-14** | Migration review. A commit staging a database migration is blocked unless a migration-review pass is recorded for that file's current content. |

### H-09b/H-10b: a digest-bound gate that closes TOCTOU

The crypto/secret gate does not just check freshness. The crypto-compliance and secret-handling skills record a `security-gate-passed` marker holding the **digest of every sensitive line the gate approved**. At commit time, `pre-bash.py` requires both:

- **freshness** (the marker is under 30 minutes old), and
- **coverage** (every sensitive line in the diff being committed hashes to a line in the approved set).

Coverage is what closes the time-of-check / time-of-use window: a pass minted for one diff cannot launder a *different* diff committed inside the freshness window. The scan reads the staged diff, plus the worktree diff when the commit uses `-a`/`--all`, stages files in the same command, or names a `git commit <pathspec>` (whose worktree content the `--cached` scan would miss).

The gate **fails closed when the diff cannot be read.** If git is unavailable or times out, `added_lines()` returns `None` (distinct from an empty diff) and the commit is blocked rather than waved through. The same fail-closed rule governs H-14's file-list read.

The detection corpus is shared. `CRYPTO_RE` and `SECRET_RE` live once in `_hooklib.py`, so the redactor and the gate cannot drift on what counts as crypto or a secret.

## Commit-gate board transitions (ADR-0008)

`open-tasks.md` has one sanctioned writer: `/ca:task`. No other agent, hook, or workflow is permitted to modify that file directly. The three mutations it performs are a queued add (a new task in `[ ]` state), the start-flip (`[ ]` to `[~]` with a stamped date), and the done-flip (`[~]` to `[x]`).

The commit gate is the single board-sync chokepoint. Phase 6 of the commit-gate skill identifies a schema-valid board transition and exempts it from the scope-creep check; Phase 7 stages it alongside the work. The board flip therefore lands atomically with the code it describes: an abandoned PR abandons the flip with it, and there is no window where the board reads done while the corresponding work is not yet merged.

This replaces the old pattern of a separate, lagging `chore(board)` PR. Cross-session board drift (a task left open after its work lands) is eliminated by construction rather than by process discipline. See ADR-0008 for the full design rationale.

`/ca:standup` and `/ca:doctor` each run a read-only reconciliation sweep and surface any merged-but-not-flipped task. They report; they do not write.

## Advisory, non-blocking reminders

`post-write-edit.py` (`PostToolUse(Write|Edit)`) surfaces reminders right after a write. These **never block**. They nudge so the blocking gate is not a surprise at commit time.

- **H-09 / H-10:** crypto/TLS or secret pattern touched. Run the gate now; the commit will block until a pass is recorded.
- **H-12:** the file is governed by an accepted ADR (`governs:` glob). Route to `/ca:reconcile` or `/ca:adr` rather than drift.
- **H-15:** CI/CD workflow changed. Dispatch `security-reviewer` before the PR merges.
- **H-16:** deployment / IaC manifest changed. Same.
- **H-17:** authentication/authorization logic touched (narrow, high-signal patterns only).
- Plus H-07 (dependency manifest changed) and an anti-slop prose check on user-facing docs.

These are advisory **because they bite at a later boundary, not at commit.** A bad CI workflow, IaC manifest, or auth change does damage only once merged or applied, and `security-reviewer` is the real enforcement point at the PR. The dangerous crypto and secret primitives, which land the moment code ships, stay hard-blocked by H-09b/H-10b.

## 2.5.2 hardening

- **Broader crypto detection.** `CRYPTO_RE` flags `rc2` and `blowfish` alongside MD5, SHA-1, DES, 3DES, and RC4, and TLS-disable forms (`rejectUnauthorized: false`, `NODE_TLS_REJECT_UNAUTHORIZED`, `verify=False`, `InsecureSkipVerify`).
- **Compound-name secret detection.** `SECRET_RE` matches compound keys (`aws_secret_access_key`, `client_secret`, `private_key`) and known token shapes (`AKIA…`, `ghp_…`, `sk-ant-…`).
- **Atomic, digest-bound gate-pass markers.** Passes are bound to line digests, so an unrelated edit inside the freshness window does not inherit the approval.
- **Centralized audit-path sets.** `AUDIT_LOG_NAMES` and the decisions-path tokens live once in `_hooklib`, so the shell, Write, and Edit flanks never disagree on which files are append-only.
- **ca-sandbox isolation.** The sandbox that runs untrusted repositories is non-root (`--user 1000:1000`), `--read-only` root, `--cap-drop ALL`, `--security-opt no-new-privileges`, with a **fail-closed network policy** (default `--network none`; an unknown policy is a hard error, never a silent pass-through). No host bind mounts; the docker socket is never mounted.

## Fail-loud, never silently dormant

The hooks fail loud: a blocking gate prints `BLOCKED [H-NN]: …` to stderr and exits 2. The one deliberate fail-*open* is hook-input parsing. A malformed stdin must not brick the session by blocking every subsequent tool call (documented in `_hooklib.read_input()`).

Enforcement is also resilient to a missing interpreter. Every hook is registered twice in `hooks.json`: once under `python3`, and once under `python` as a fallback. On a stock Windows install that ships `python` but not `python3`, the gates still fire. codeArbiter never falls silently dormant because of an interpreter name.
