---
status: accepted
date: 2026-07-31
title: Protected-state registry is a declared executable-input boundary with cooperative, friction-grade markers
decided-by: SUaDtL@users.noreply.github.com
supersedes: none
governs: core/pysrc/_protectedstatelib.py, core/pysrc/_protectedlib.py, core/pysrc/_bashguardlib.py, .codearbiter/release-targets.md
---

# ADR-0024 — Protected-state registry is a declared executable-input boundary with cooperative, friction-grade markers

## Status

Accepted — ratified 2026-07-31 by SUaDtL@users.noreply.github.com. Content pre-approved at the sprint's Phase 1 gate the same day.

## Context

`H-22` introduces a registry of protected project-state files, each carrying a policy — `marker-gated`, `helper-only`, or `append-only` — enforced across `pre-write.py`, `pre-edit.py`, and `_bashguardlib.py`. Its first consumer, `.codearbiter/release-targets.md`, carries per-row `pre-tag` shell commands that `/ca:release` executes before composing a tag (DECISION-0034).

That makes `release-targets.md` **executable input**: a repository file whose contents the framework runs. ADR-0002 already established the trust model for this class in `plan.json` — operator-authored, PR-reviewed, length-capped, with the boundary declared rather than an allowlist imposed. This ADR records where the new case matches that precedent and, more importantly, where it does not.

Three differences from `plan.json` were raised in review and are named here rather than papered over with a citation:

1. **Authorship.** ADR-0002 rests on "operator-authored". Here the model drafts the rows — `context-creation` elicits them, and a back-fill lane proposes a detected shape. Model-drafted shell later executed by the skill is a different trust class than operator-typed shell.
2. **Review discipline.** In a consumer repo nothing guarantees `release-targets.md` edits are PR-reviewed. A third-party PR touching it plants commands the maintainer's next `/ca:release` runs.
3. **Write protection.** It is the only *executable* file under `.codearbiter/`, and the location chosen for it — a separate file rather than a `CONTEXT.md` block, on context-economy grounds — does not inherit `CONTEXT.md`'s existing guard.

## Decision

The registry is a declared executable-input boundary, protected by **write-gating rather than content inspection**.

- `release-targets.md` is registered `marker-gated`. Mutations are admitted only under a fresh `release-targets-authoring` marker, minted immediately before the write and removed at lane exit.
- Each `pre-tag` entry is capped at **1024 characters**, following ADR-0002's precedent.
- `pre-tag` commands are **check-only** and may never mutate the tree (DECISION-0034). The clean-tree assertion is unconditional, so a rogue command's writes surface before tagging.
- The resolved `pre-tag` list is content-hashed; a change forces re-confirmation, so a silently edited command cannot ride an earlier approval.
- **No content predicate ever grants admission.** A guard that reads file content to decide whether to permit a write converts content into an authorization signal, which is launderable by anyone who can write the content.

**The marker is audit friction, not authorization.** It is self-mintable via shell by design, per ADR-0010's cooperative-attestation posture. Its value is the trail and the deliberate pause, not unforgeability. `GATE_MARKER_NAMES` — the shell-flank blocklist — enumerates only markers that convert a BLOCK into an ALLOW, and authoring markers are correctly outside it. Widening that list generically over every registered marker would brick every minting lane while stopping no non-cooperative agent, since such an agent shell-mints regardless.

**Case handling is global, not host-derived.** Both flanks treat registered paths case-insensitively and tolerate a `./` prefix, trailing slash, doubled slash, and surrounding whitespace. Matching the host filesystem was rejected: case-sensitivity varies by platform *and* by volume on the same platform, and `realpath` cannot fold case for a path that does not yet exist — exactly a Write creating a protected file for the first time. A fixed rule both flanks apply without consulting the filesystem only widens what is protected, never narrows it.

## Accepted residuals

Declared here and in `security-controls.md`. Undeclared is not the same as accepted.

- **Shell indirection.** `f=…; sed -i "$f"` and novel interpreter spellings evade the lexical flank. The same residual `CONTEXT.md` already carries under ADR-0010, inherent to a cooperative guard.
- **Lexical false blocks.** The shell flank matches a registered file's bare basename with no directory requirement — forced by the need to catch a bare `tee open-tasks.md`. A description containing a write verb and the filename false-blocks. `/ca:override` is the sanctioned bypass.
- **`touch` is excluded.** Two reviewers split. A security pass traced every mtime consumer under `.codearbiter/` and found none feeding an admission decision — `marker_gated_write_admitted` stats the *marker*, not the protected file, so even back-dating admits nothing. An adversarial pass countered that `DECISIONS_WRITE_RE` *does* include `touch`, because for H-11 creation itself is the violation, and that `touch` on an absent board creates an empty board outside the sanctioned helper. The admission analysis was judged decisive; the creation case is recorded as the known cost.
- **Merge-conflict resolution.** A conflict in a `helper-only` file has no helper verb, so resolution routes through logged `/ca:override`.

## Reopen conditions

- If `gate-events.log` shows board-conflict overrides recurring, build a `taskwrite resolve` verb. Never punch an exception into the guard.
- If `release-targets.md` ever ingests untrusted or third-party content, the operator-authored premise is void and this decision must be revisited — inheriting ADR-0002's own reopen trigger.
- If any registry entry ever needs a non-forgeable marker, that marker joins `GATE_MARKER_NAMES` deliberately and gains a sanctioned producer, as a reviewed one-line widening.

## Alternatives considered

- **A content allowlist on `pre-tag` commands** — rejected for the reason ADR-0002 rejected it: it over-engineers a trusted-operator input and risks refusing legitimate commands.
- **Uniform marker-gating for all three consumers** — rejected. Marker-gating `open-tasks.md` would *admit* an agent hand-composing board markdown under a marker, while its sanctioned helper is already invisible to every flank by construction. The correct policy there is a hard block with no marker path.
- **A disk-loaded registry** — rejected. It would let a consumer repo un-protect its own board by editing a file.
- **Storing the rows in `CONTEXT.md`** to inherit its write guard — rejected on context economy: `CONTEXT.md` is read every session, release configuration only when tagging.

## Consequences

Easier: an explicit trust model, so a reviewer knows `release-targets.md` is executable input and reviews it as such; and one registry that a fourth protected file joins as a row rather than as a new hook branch.

Harder: correctness depends on write-gating and PR-review discipline rather than on content validation, and the lexical flank will occasionally false-block a legitimate command.

## Risks

A malicious or mistaken `pre-tag` entry runs arbitrary shell on the maintainer's host at release time. Accepted because the entry is write-gated, length-capped, check-only, content-hashed against silent change, and surfaced for confirmation. The residual is a cooperative-guard residual, not a sandbox.
