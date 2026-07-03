---
title: Enforcement & Security
description: "How codeArbiter enforces its gates at the tool-call boundary: the activation contract, the blocking commit-time gates, advisory reminders, and the fail-loud posture."
---

codeArbiter's gates are not advice the model can talk past. They run as Claude Code hooks at the tool-call boundary, in Python, with no network and no third-party dependencies. A blocking gate exits non-zero, and the tool call never happens. This page states what is enforced, where it fails open versus closed, and the security posture behind it.

For the per-hook breakdown, see the [Hooks reference](/hooks).

## The Activation Contract

codeArbiter is dormant until a repository opts in. Every enforcement hook calls `arbiter_active()`, which is true only when `.codearbiter/CONTEXT.md` carries `arbiter: enabled` in a properly closed leading YAML frontmatter block. A repo with no such file, or no such line, loads nothing and blocks nothing.

- **Opt-in by file, not by install.** Installing the plugin does not enforce anything. Enforcement begins the moment `CONTEXT.md` declares the repo enabled.
- **Persona injection.** On an enabled repo, the `SessionStart` hook injects the orchestrator persona. That single file is the only always-loaded context.
- **Malformed frontmatter fails loud.** A frontmatter block that opens (`---` on line 1) but never closes is surfaced as a malformed-state error, not silently treated as disabled. A file with no frontmatter at all is simply dormant.

## Blocking Commit-Time Gates

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

H-09b/H-10b is digest-bound: a recorded pass covers only the exact sensitive lines it approved, which closes a time-of-check / time-of-use gap between approval and commit. The board-sync behavior implied by the commit gate (only `/ca:task` writes `open-tasks.md`) follows from ADR-0008. For the design rationale behind both, see [Hardening History](/concepts/hardening-history/).

## Advisory, Non-Blocking Reminders

`post-write-edit.py` (`PostToolUse(Write|Edit)`) surfaces reminders right after a write. These **never block**. They nudge so the blocking gate is not a surprise at commit time.

- **H-09 / H-10:** crypto/TLS or secret pattern touched. Run the gate now; the commit will block until a pass is recorded.
- **H-12:** the file is governed by an accepted ADR (`governs:` glob). Route to `/ca:reconcile` or `/ca:adr` rather than drift.
- **H-15:** CI/CD workflow changed. Dispatch `security-reviewer` before the PR merges.
- **H-16:** deployment / IaC manifest changed. Same.
- **H-17:** authentication/authorization logic touched (narrow, high-signal patterns only).
- Plus H-07 (dependency manifest changed) and an anti-slop prose check on user-facing docs.

These are advisory **because they bite at a later boundary, not at commit.** A bad CI workflow, IaC manifest, or auth change does damage only once merged or applied, and `security-reviewer` is the real enforcement point at the PR. The dangerous crypto and secret primitives, which land the moment code ships, stay hard-blocked by H-09b/H-10b.

## Sandbox Isolation for Untrusted Repositories

codeArbiter runs untrusted repositories inside `ca-sandbox`, isolated as non-root (`--user 1000:1000`), with a `--read-only` root, `--cap-drop ALL`, `--security-opt no-new-privileges`, and a fail-closed network policy (default `--network none`; an unknown policy is a hard error, not a silent pass-through). No host bind mounts; the docker socket is never mounted. For how this posture evolved release over release, see [Hardening History](/concepts/hardening-history/).

## Fail-Loud, Never Silently Dormant

The hooks fail loud: a blocking gate prints `BLOCKED [H-NN]: …` to stderr and exits 2. The one deliberate fail-*open* is hook-input parsing. A malformed stdin must not brick the session by blocking every subsequent tool call (documented in `_hooklib.read_input()`).

Enforcement is also resilient to a missing interpreter. Every hook is registered twice in `hooks.json`: once under `python3`, and once under `python` as a fallback. On a stock Windows install that ships `python` but not `python3`, the gates still fire. codeArbiter never falls silently dormant because of an interpreter name.
