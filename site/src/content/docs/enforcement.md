---
title: Enforcement & Security
description: "How codeArbiter enforces its gates at the tool-call boundary: the activation contract, the blocking commit-time gates, advisory reminders, and the fail-loud posture."
---

codeArbiter's gates are not advice the model can talk past. They run as Claude Code or Codex
[hooks](/glossary/#hook) at the tool-call boundary, in Python, with no third-party dependencies.
Both plugins vendor the same guard core. Claude Code receives its exit-2 verdict directly; Codex's
`pre-tool-adapter.py` converts the same verdict to a structured deny response so Windows shell exit
handling cannot weaken the block. See the
[Claude Code + Codex evidence](/getting-started/claude-code-and-codex/).

For the per-hook breakdown, see the [Hooks reference](/hooks).

## The Activation Contract

codeArbiter is dormant until a repository opts in. Every enforcement hook calls `arbiter_active()`, which is true only when `.codearbiter/CONTEXT.md` carries `arbiter: enabled` in a properly closed leading YAML frontmatter block. A repo with no such file, or no such line, loads nothing and blocks nothing.

- **Opt-in by file, not by install.** Installing the plugin does not enforce anything. Enforcement begins the moment `CONTEXT.md` declares the repo enabled.
- **Persona injection.** On an enabled repo, the `SessionStart` hook injects the orchestrator persona. That single file is the only always-loaded context.
- **Malformed frontmatter fails loud.** A frontmatter block that opens (`---` on line 1) but never closes is surfaced as a malformed-state error, not silently treated as disabled. A file with no frontmatter at all is simply dormant.

<figure class="ca-diagram">
  <img
    src="/codeArbiter/diagrams/activation-states.svg"
    alt="Activation classification flow: a missing CONTEXT.md or missing leading frontmatter is dormant; an unclosed block is malformed and surfaces an error; a closed block containing arbiter enabled activates the persona and gates."
    loading="lazy"
    width="900"
    height="430"
  />
  <figcaption>One parser, three visible outcomes. A closed block without `arbiter: enabled` remains dormant.</figcaption>
</figure>

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

<figure class="ca-diagram">
  <img
    src="/codeArbiter/diagrams/sandbox-boundary.svg"
    alt="ca-sandbox boundary: the untrusted repository lives in a Docker named volume inside a non-root, read-only container with dropped capabilities, no new privileges, resource limits, and network disabled by default. Host bind mounts and the Docker socket are blocked. Files leave only through host-initiated docker cp."
    loading="lazy"
    width="960"
    height="520"
  />
  <figcaption>The container can work in its named volume, but it has no path into the host filesystem or Docker daemon.</figcaption>
</figure>

## Pi: Project Trust and Child Processes

Pi's activation contract is the same `arbiter: enabled` flag as Claude Code and Codex, plus one
addition: an enabled repository still requires Pi's own affirmative project-trust decision before
repository-aware startup. The parent registers repository-aware dispatch, farm preview, and native
compaction only after the current session reports that trust, the repository is enabled, and the
enforcement lifecycle is ready. A session opened before trust is granted, or before the repo opted
in, stays inert — nothing repository-aware runs.

`codearbiter_dispatch` and `codearbiter_farm_preview` are **parent-only** EXEC tools. A child
process spawned to do author or reviewer work cannot escalate itself into repository-aware dispatch
or farm access. Ordinary child/subagent environments never receive `FARM_API_KEY` or other
governance secrets; that key is scoped to the trusted parent only.

Run `/ca-doctor` to verify this is actually live: it inspects the active package path, command
ownership, Python/core/bridge health, child fingerprint, and the H-03 wrapper self-test. Its
module-identity check proves self-consistency between the operator-launched Pi CLI, imported module,
package root, and reported version — it does **not** prove publisher authenticity. Verify the
installed source separately with `pi list` and `pi config`.

## Fail-Loud, Never Silently Dormant

The hooks fail loud: a blocking gate prints `BLOCKED [H-NN]: …` to stderr and exits 2. The one deliberate fail-*open* is hook-input parsing. A malformed stdin must not brick the session by blocking every subsequent tool call (documented in `_hooklib.read_input()`).

Enforcement is resilient to host interpreter conventions. Claude Code carries its tested
interpreter fallback. Codex registers one OS-specific command per event (`python3` on POSIX,
`python` on Windows), avoiding concurrent handlers with conflicting results.
