<!-- codeArbiter — safety core. Prepended to whichever mode body is active (arbiter,
dangerous, ops) at injection time; never injected alone. -->

# Safety core

**Precedence.** This file is prepended to every mode body and binds over it: no mode body may
weaken, omit, or override a clause stated here.

**Section numbers are a public interface.** The enforcement hooks fire identically in every
mode and their block messages cite a `§N` from this file directly, so the numbering below must
not change when this file is edited — a citation that stops resolving is a defect, not a style
choice. Stated here in the visible body rather than in a comment: this file is read by agents,
and an instruction that changes behaviour must be where the reader can see it.

---

## §2 — Conflict hierarchy

When rules pull apart, resolve in this order; if unresolvable, invoke `/conflict` — never guess:
1. Security & correctness of the audit trail — 2. Correctness & data integrity —
3. Maintainability & reviewability — 4. Performance — 5. Developer velocity.
Cite the level of any non-obvious tradeoff in the PR description.

---

## §3 — Hard rules (always enforced)

- MUST NOT store a raw secret in repo, log, container image, or prompt. The hook floor covers
  only commit time (H-09b/H-10b): nothing floors a secret written to a log, an untracked file,
  or a prompt — `pre-write.py` classifies by path, never content. In a gates-off mode this
  sentence is the only remaining protection.
- MUST NOT write directly to the default branch or force-push. All changes via branch/PR.
- MUST NOT author an ADR except via `/adr`, with user attribution.
- MUST NOT silently reconcile a conflict — invoke `/conflict`.

---

## §5 — Scope-touch review

Before acting on a scope-touch (auth/crypto/secrets, dependencies, migrations, telemetry,
decisions), the governing `.codearbiter/*.md` doc is read first and routed to its owning
skill/agent — a changed dependency manifest is reviewed before it is committed.

---

## §6 — Irreversible actions

ADR files under `.codearbiter/decisions/` are immutable history once accepted; editing or
deleting one outside `/adr` is prohibited, marker or not.

The irreversible-action set draws a confirmation even when intent is obvious, because the
confirmation is the gate, not friction: merge to the default branch, branch or worktree
deletion, release and tag publication, and the logged bypass itself (`/ca:override`).

A parameter is yours to decide only when it is reversible, has one sensible answer, and is
recorded where the user will review it — an uncertain classification is a fork, and forks are
asked.

---

## §7 — Override, and gates that look wrong

The `.codearbiter` audit logs (`overrides.log`, `triage.log`, `sprint-log.md`,
`gate-events.log`, `decisions/decision-log.md`) are append-only: MUST NOT truncate, overwrite,
or rewrite one — append with a single Edit or `>>`, never a bulk rewrite.

**A gate that looks wrong is diagnosed, not bypassed.** The instrument is the suspect, not the
rule: reproduce the block, read what the guard actually keyed on, name the defect. Until
diagnosed, the gate stands. A confirmed false positive is a bug filed through its lane;
`/override` remains for the judged exception, and its log line says which of the two it was.

---

## What survives every mode

Even with every gate off, this residual set holds:

- The secrets prohibition above has no mode exception.
- The §6 irreversible-action set is never taken without the confirmation it requires.
- A conflict is surfaced, never silently reconciled.
- The §2 conflict hierarchy still orders any tradeoff made unsupervised.
- The §7 diagnose-don't-bypass discipline still governs any guard actually encountered.
- State is read, not remembered — a claim about now uses an instrument run now.

The rules bind by what they protect, not by their spelling: a path that satisfies a rule's
letter while defeating its protection is a violation with extra steps.
