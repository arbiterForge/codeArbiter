---
status: proposed
date: 2026-08-12
title: Orchestration mode plane with a composed, per-turn persona
decided-by: SUaDtL@users.noreply.github.com
supersedes: 0022-auto-route-unambiguous-safe-intent-into-its-command
governs: core/surface/arbiter.md, core/surface/includes/safety-core.md, core/surface/includes/dangerous-mode.md, core/surface/includes/ops-mode.md, core/pysrc/_modelib.py, core/pysrc/session-start.py, core/pysrc/prompt-submit.py, plugins/*/arbiter.md, plugins/*/includes/safety-core.md, plugins/*/includes/dangerous-mode.md, plugins/*/includes/ops-mode.md
---

# ADR-0030 — Orchestration mode plane with a composed, per-turn persona

## Status
Proposed — authoring approved by SUaDtL@users.noreply.github.com on 2026-08-12 ("approve adr, route
through /ca:adr"). Ratification to `accepted` is pending and is the user's to give; the seven
positions below were each ruled by the user during the #437 session and are recorded, not inferred.

## Context

Issue #437 asked for a new `/ops` command to permit local runtime work in-channel. The user rejected
that framing outright: the goal is to *shrink* command surface, make posture changes deterministic
rather than model-inferred, and stop paying for orchestration frontmatter that a given session will
never use.

Investigation established the situation that makes the reframe possible. Every enforcement hook gates
on `arbiter_active()` — the `.codearbiter/CONTEXT.md` frontmatter (`_activationlib.py:166-171`) —
and **never on the persona**. The `dev-active` marker has zero enforcement readers across
`core/pysrc/`, `plugins/ca-pi/tools/src/`, and all three `hooks/` trees; its only consumers are the
statusline red-shift, a non-blocking staleness warning, and Pi's footer. H-01/H-02, H-03, H-05,
H-09b/H-10b, H-11, H-18, H-19, H-20 and H-22 therefore survive any persona swap. What a persona swap
removes is prose-only rules: TDD Phase 1, the commit gate, red-suite refusal, `[CONFIRM-NN]`
discipline, domain vocabulary, §0's route-never-implement, §7's identity.

That inverts the standing mental model. `ORCHESTRATOR.md` presents itself at `:3` as *"the always-on
core"*, but it is not load-bearing for safety — the hooks are. It is one posture's body among several
that could exist.

## Decision

Introduce an orchestration **mode** plane with three values — `arbiter`, `dangerous`, `ops` — flipped
deterministically at each host's prompt seam, selecting a composed persona. Seven positions:

**1. `ORCHESTRATOR.md` is the arbiter mode's body, not an always-on kernel — renamed `arbiter.md`.**
This contradicts the file's own header and is the architectural change the rest follows from. The
rename is **live surface only**: 751 occurrences span 134 files, of which ~416 sit in files this
repo's own rules forbid rewriting (`gate-events.log` 376 under H-05, `decisions/` 23 under H-11,
`sprint-log.md`, published CHANGELOGs). The header carries `(formerly ORCHESTRATOR.md)` so those
citations stay resolvable. `/ca:dev` and `/ca:arbiter` are deleted — the mode bodies are the surface,
and the catalog drops 40 → 38.

**2. Persona injection moves off `SessionStart` to the per-turn prompt seam.** `SessionStart` fires
once per session (and on `compact`), so a mid-session flip could not change what was injected — the
flip's effect would defer to an unpredictable boundary. Editing that hook cannot fix it; the problem
is *when it fires*. The injection is deduped per session-and-mode, so steady-state cost is one
injection per mode change, not per turn. The injected persona is
**`includes/safety-core.md` + the current mode's body** — composition, not three hand-maintained
copies of the same safety text with no gate comparing them.

**3. ADR-0022's tier-2 confirmation clause is superseded for dangerous-mode entry only.**
The resolving chain matters, because ADR-0022 has now forked twice:

- ADR-0026 superseded **only** ADR-0022's *placement* clause (`0022:31-32` — "the destructive set is
  enumerated in the orchestrator"), explicitly leaving the three-tier decision and the tier-1
  requirement in force.
- ADR-0022`:46-49` — *"Anything irreversible or gate-bypassing — `/ca:override`, merge to the default
  branch, branch or worktree deletion, release and tag publication, `/ca:dev` entry — drops to tier 2
  and asks… There the confirmation is the gate, not friction"* — was therefore **unsuperseded until
  this ADR**.
- This ADR supersedes that clause **for dangerous-mode entry alone**. A control token that must be
  typed exactly, whole-prompt anchored, is friction — deliberately hard to produce by accident — and
  ADR-0022's own wording distinguishes friction from a gate. Removing the tier-2 stop for this one
  member is legitimate precisely because it is a stop that was doing friction's job.
- **Every other member of the set is untouched**: `/ca:override`, merge to the default branch, branch
  or worktree deletion, and release/tag publication all remain tier 2. So do ADR-0022's three-tier
  decision and its tier-1 dual requirement.

The chain now forks — ADR-0026 and this ADR each supersede a different clause of ADR-0022. Per the
canonical template that fork is correct and must not be "repaired"; `supersedes:` names a document,
and only prose can carry the scope.

**4. The flip is unaudited at the interception point; the transition is not.** The flip turn produces
no model turn, so nothing narrates it. What is recorded is the *transition*: entry and exit each
append exactly one `MODE: <name> enter|exit` row, routed through the existing write-ahead ledger
(`session-start.py:551-810`, the #396 mechanism) and never a bare append. Readers accept legacy
`DEV:` rows so history stays parseable. The statusline red-shift remains the unmistakable live
signal.

**5. Fail direction: ADR-0020's fail-open is rebutted here, not inherited.** ADR-0020`:52-58` records
that a *guard* which cannot parse its input fails open while a *router* fails closed, because a
router cannot prove safe what it cannot route. A prompt-seam interceptor is a router. But the
symmetry breaks on direction: a failed flip **into** dangerous mode leaves gates on, which is safe; a
failed flip **out of** it leaves gates off, which is not. The return path therefore requires a
verified write, and must surface its failure rather than wedging the session or silently remaining
dangerous.

**6. The mode plane is transient and session-scoped; the durable seam is specified, not built.**
Issue #247 nominates guarded `CONTEXT.md` frontmatter as `profile:`'s home. Scored via SMARTS,
implementing both layers now is penalised on **Reliable** (two sources for one fact — a split-brain
class already found once in this repo) and on **Securable**. Strength: `moderate`. So: session plane
only, but the precedence rule and the frontmatter key are fixed here so #247 slots in without
redesign. Values are session postures; lifecycle and rigor properties stay in guarded frontmatter.
**A committed profile may never default to a gates-off posture** — that is a hard rule of this ADR,
not a recommendation, because a committed default would persist one contributor's posture into a
shared repository where no one chose it.

**7. The ops supervision half of #437 is deferred as sequencing, not as ADR-0007 deference.** ADR-0007
puts runtime infrastructure in `ca-sandbox`, and ops ships advisory-only here — no supervisor, no PID
tracking, no readiness probes, no scoped stop. That boundary is untouched, but it is **not** the
reason for the deferral. The user's ruling was explicit: the supervision problem deserves a fresh,
dedicated scoping pass rather than being tacked onto the mode work. ADR-0007 is as movable as
ADR-0022, which this ADR does supersede. A later reader must not mistake a scheduling decision for a
governance boundary.

## Alternatives considered

- **Add `/ops` as issue #437 proposed** — rejected by the user: it grows command surface in the
  direction opposite the stated goal, and leaves the posture change model-inferred.
- **Collapse `/dev` + `/arbiter` + `/ops` into one `/ca:mode` command** — the user's own first
  counter-proposal, then rejected in favour of the token: a command still costs a catalog row and
  still routes through model inference on the turn it is issued.
- **Session-scoped mode with injection left on `SessionStart`** — rejected on arithmetic. Every
  session would start `arbiter` and inject the full body; a mid-session flip *adds* a second body on
  top. The byte delta goes negative, which is the opposite of the advertised saving.
- **Suppress the startup block wholesale in non-arbiter modes** — rejected via SMARTS (strength
  `strong`). The block is eight independent emitters with different audiences; wholesale suppression
  scores weak on Scalable, Maintainable, Reliable and Securable, because the lines it removes —
  `[CONFIRM-NN]` surfacing and the override count — are precisely the ones a gates-off session most
  needs. Decomposed into per-mode composable emitters instead.
- **A full body swap for `ops`** — rejected: it discards all of §3's hard rules to relax one §0
  clause. Ops ships as a scoped carve-out keyed on the durable artifact produced (start/observe/
  exercise permitted; mutation of tracked files, the index, git history, or published state still
  refused), which is the same axis the surviving hooks already use.
- **Implement `profile:` frontmatter now alongside the session plane** — rejected; see position 6.
- **Keep a Codex-only command because Codex cannot intercept** — rejected on evidence. The Codex
  binary embeds `user-prompt-submit.command.output` with a `BlockDecisionWire` enum, `continue:false`,
  and exit-2 paths. The earlier "Codex cannot block" claim was absence of evidence read as evidence
  of absence; the catalog is 38 on all three hosts.

## Consequences

A session's persona now matches its posture, which it did not before: `/dev` previously loaded
`dev-mode.md` *in addition to* the full 10,053-byte arbiter body, so the most gates-off posture
carried the most orchestration text. Composition removes the duplication tax that made three
standalone bodies restate ~60% of the same safety prose.

Two commands leave the catalog. The safety floor is unchanged in every mode — no hook reads the mode
file, and nothing joins `GATE_MARKER_NAMES` (membership requires converting a BLOCK into an ALLOW,
`_protectedlib.py:127-130`, and widening it is warned against at `:139-144`).

Rule *loss* becomes explicit rather than implicit: each mode body restates the non-suspendable subset,
so the failure mode is a loud downstream BLOCK rather than a silent bypass. `arbiter.md`'s §2 conflict
ladder, §7's *"a gate that looks wrong is diagnosed, not bypassed"*, §6's irreversible-action set, and
the anti-circumvention sentence all move into `safety-core.md` and are therefore carried in **every**
mode. Three of §6's five irreversible actions have no hook backing at all — the persona is their only
carrier, which is why they cannot live in the arbiter body alone.

`ORCHESTRATOR.md:27` (no raw secret in repo, log, image, or prompt) is floored only at *commit* time;
`pre-write.py` classifies by path, never content, so nothing floors a secret written to a log, an
untracked file, or a prompt. It must be restated in `safety-core.md` and is.

Two quiet registries must move with the rename or they go permanently silent with a green suite:
`_hooklib._STALE_FLOWS` (a WARN, not a gate) and `session-start.py:~906`, which stamps
`cmd_ref("arbiter")` into append-only `overrides.log` — deleting the command without fixing that line
writes a permanent dangling reference into a file H-05 forbids rewriting.

## Risks

**The return path is the sharp edge.** Position 5 states the direction; the implementation has to
honour it. A verified write that fails must surface loudly, because the unsafe direction is the one
where nothing is obviously wrong from inside the session.

**Composition is one file two modes depend on.** `safety-core.md` becoming wrong is worse than any
single body becoming wrong. Proven wrong if a mode ships whose body silently omits a rule
`safety-core.md` was assumed to carry.

**The token must be whole-prompt anchored.** A substring match would let a pasted diff containing the
token flip the mode. This is a one-line property with a large blast radius.

**The compaction hole.** `SessionStart` fires on `compact`, which is why the persona survives
compaction today. A naive per-session dedup marker leaves a session permanently persona-free after
its first compaction — with a green suite, because no test spans a compaction. The marker must key on
a compaction generation.

**The token saving is still unmeasured.** Every figure in the planning record was an estimate, and an
earlier draft carried two mutually exclusive numbers for its own headline metric. The
non-negotiable wins are coherence and surface reduction; the byte delta is a claim that must be
measured against composed output before it is stated anywhere.

This decision is proven wrong if a gates-off session is found to have bypassed a rule that was
believed hook-backed — that would mean the persona was load-bearing for safety after all, and the
premise of the whole plane fails.
