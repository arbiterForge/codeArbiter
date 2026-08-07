# Sprint spec — recorded-intent + kernel-slim campaign (rev 2)

**Slug:** `recorded-intent-kernel-campaign` · **Date:** 2026-08-07 · **Lane:** `/ca:sprint`
**Source:** 2026-08-07 session — full ORCHESTRATOR.md review + recorded-intent design discussion.
**Rev 2:** incorporates the three-lens adversarial review (feasibility / governance / blast-radius),
11 surviving findings applied. Rev-1 defects worth naming: an unscoped Step-0 that would have
inverted the decision-variance authority order; an arithmetically unreachable AC-13; a T-13 that
cited a harness which no longer exists.

## Problem

Two related gaps found in the same session:

1. **Recorded intent is invisible at decision time.** SMARTS scores quality, not conformance to
   the project's own record. Two surfaces decide without checking whether the record already
   answers or constrains the question: `/sprint` auto-decisions and `brainstorming`'s approach
   choice. A sprint can contradict a Layer-4 forced trade-off overnight and nothing catches it.
   (The arbitration lanes — decision-variance, grader, decision-challenger — are NOT gaps: there
   the variance IS the recorded-intent check, and the Phase 4 authority order ranks the record.)
2. **The always-on kernel carries removable redundancy** (§6/§7), one routing rule is stranded in
   a file tier-1 never loads (`redirect.md`'s interrogative-phrasing rule), and ADR-0022's own
   preferred refinement (destructive set declared in the routing table) is now viable.

## Goal

Ship both: recorded intent precedes and constrains autonomous scoring and spec shaping (ADR-0025),
and the kernel slimmed/restructured per the session review — validated by a NEW pre-registered
A/B run per the #609 *protocol* (ADR-0026 governs the destructive-set relocation).

## User rulings (2026-08-07, this session — not re-decidable in-flight)

- **Lane:** `/ca:sprint`, all three streams in scope.
- **Intent source = the approved record**: `decisions/decision-log.md` (rank 2 in the
  decision-variance Phase 4 authority order), accepted ADRs (rank 3), `plans/01–03` (rank 4),
  plus `CONTEXT.md` and `open-questions.md` (including its Deferred-decisions sections). The raw
  `.decompose-draft/` layers stay deleted. No `decompose` change in this campaign.
- **Sprint contradiction = hard gate**: an auto-decision that would contradict an accepted ADR or
  a recorded deferral rationale is NEVER auto-decided. (The stale-record valve below does not
  weaken this: a pre-ruling captured at the interactive Phase 1 gate is a USER decision, and a
  deferral whose recorded re-evaluation trigger has occurred is the record working as designed.)

## Decided parameters (SMARTS-logged at execution; recorded here for approval visibility)

- Two ADRs: ADR-0025 (recorded-intent precedence, scoped) and ADR-0026 (destructive set declared
  in the routing table, amending ADR-0022 per its own §Alternatives). Numbering 0025/0026 verified
  free. Both ADR files commit in the Lane-2 PR — a ratified ADR never sits uncommitted across a
  lane boundary (audit-trail exposure, per the external-agent governance incident).
- **Step-0 scope (governance F1, CRITICAL):** the recorded-intent check applies to `/sprint`
  autonomous scoring and `brainstorming` ONLY. `decision-variance`, `grader`, and
  `decision-challenger` are exempt by name in the Step-0 text — arbitration surfaces rank the
  record via the Phase 4 authority order, and a "conform" rule there would invert it (a rank-4
  artifact defeating a rank-1 user steer) and install the grader's own anti-pattern #2. "Answered"
  is defined BY the authority order: an explicit user decision this session (including the
  approved sprint spec) outranks a log decision, which outranks an accepted ADR, which outranks
  plans/01–03. Conformance is owed to the highest-ranked source only; a lower-ranked record
  answering against a higher-ranked steer follows the steer and logs the divergence with both
  citations.
- **Stale-record valve (governance F2):** (a) the sprint-start intent read runs BEFORE Phase 1
  spec approval, surfacing every accepted ADR / open deferral the planned scope plausibly touches
  at the interactive gate — a ruling recorded in the approved spec pre-decides later collisions;
  (b) a deferral whose recorded re-evaluation trigger has occurred is reopened and surfaced, not
  treated as a contradiction; (c) one stop per record per sprint — the first stop's answer is
  logged and later identical collisions cite it; (d) SPRINT.md's repeated-trip diagnostic gains
  "…or the record itself is stale — route it to supersession in the summary".
- Lane order: ADRs → recorded-intent → kernel. Regeneration (`tools/build-surface.py`, write
  mode) runs INSIDE each lane before any task that verifies or measures generated files
  (feasibility #2).
- **Consumer cost bound (blast F-4):** every new read is index-first and it is normative text,
  not implementation preference: consult the ADR index (`decision-log.md` or filename listing)
  and plan section headings only; load a body only after the index names it relevant; never
  bulk-read `plans/` or `decisions/` (cite ORCHESTRATOR §3's no-bulk-reads rule). Pinned by the
  structural test.
- **Fail-soft is normative on all three surfaces** (smarts Step-0, SPRINT.md read, brainstorming
  pre-flight): an absent `plans/` or `decisions/` is not a gap to surface and never a STOP —
  record `intent: silent — no decomposition record` and proceed. Brownfield is the DOMINANT
  consumer path (`/ca:init` and `context-creation` never write `plans/01–03`; this repo itself
  has none), not an edge case. Pinned by the structural test.
- **`intent:` log field position is pinned** (governance F7 / feasibility #4): after the
  `confidence:` token on the heading line, or on a body line — never before it
  (`_taskboardlib.extract_low_confidence` takes the title as everything before
  `· confidence: low`). An `intent: per <source>` (answered) decision logs `confidence: high`
  with the citation written in the SMARTS-verdict slot.
- Kernel validation follows the **#609 protocol, not its instrument** (blast F-3): the #609
  scenario set targeted different surfaces and its artifacts are gone. T-13 authors a NEW
  pre-registered scenario set + rubric targeting the changed behaviors, including the two known
  regression seeds: a #598-shaped tier-misroute scenario and the #609 menu-not-a-briefing fork
  scenario. Sealed runners; grader non-blindness mitigated by rubrics written before any output.
- **Red is pre-defined; the stopping rule is enforceable** (blast F-6): red = any
  hard-requirement fail in the candidate arm, or a soft-failure class present in candidate and
  absent in incumbent. A revision re-runs the FULL candidate arm (incumbent results carry over);
  single-cell retests do not clear the gate. Budget ceiling: 3 full arms, then S1 ships alone.
- The kernel keeps a resident destructive set regardless of ADR-0026; the routing table becomes
  the authority and the kernel copy is CI-checked against it.

## Streams

### S1 — Recorded-intent package (ADR-0025)

- **A** `includes/smarts/core.md`: "Step 0 — recorded-intent check" with the scope header above
  (applies-to and exempt-by-name lists), the authority-order definition of "answered", three
  outcomes — **answered** (conform to the highest-ranked source, or in interactive lanes route
  the contradiction to `/ca:reconcile` / supersession; under `/sprint` an answered-but-
  contradicting outcome IS the contradiction hard gate, never a mid-sprint reconcile dispatch,
  per SPRINT.md's Rule-1 override), **constrains** (cite into cells per the evidence-specificity
  rule), **silent** (proceed, state `intent: silent`) — the index-first loading rule, and the
  fail-soft sentence.
- **B** `SPRINT.md`: intent read (decision-log + ADR index + plans/01–03 headings +
  open-questions deferred sections) BEFORE Phase 1 spec approval, surfacing touched records at
  the gate; contradiction + valve wording in the hard-gate list; `intent:` field (position as
  pinned above); repeated-trip diagnostic extension; fail-soft explicit.
- **C** `agents/grader.md`: assignment format gains one INFORMATIONAL line — check the ADR index,
  cite any accepted decision touching the variance in the analysis. The grader remains exempt
  from Step-0 (it scores; it never conforms or routes).
- **D** `skills/brainstorming/SKILL.md`, four touches, placed per the skill's own structure
  (governance F5/F6): **pre-flight** gains a separate fail-soft block ("Recorded intent
  (fail-soft): also consult, when present…" — exempt from the existing 'Read these, or STOP'
  contract); **Phase 1** folds the deferral/backlog resurrection check into the existing
  CONTEXT.md framing bullet (a resurrection is a fork to ask); **Phase 2** checks candidates
  against the ADR index — a contradicting candidate is surfaced with the ADR citation, never
  silently dropped, and may not be recommended except paired with a supersession fork via
  `/ca:adr`; when the contradicting candidate is the only sane approach, that IS the fork
  (user rules under `/feature`; under `/sprint` brainstorming runs inside the interactive
  Phase 1 gate where the user is present); **Phase 5** review bullet (no criterion contradicts
  an accepted ADR / plans/01).
- `writing-plans` untouched: the chain is record→spec→plan→code, each stage checking one level up.

### S2 — Kernel compression (existing ADRs; A/B-validated)

- §6: tier rule stated once; asking discipline stated once; phrasing-channel clause added
  (relocated from `redirect.md`, where tier-1 classification can never see it — no pin blocks
  the trim, verified). §7: identity-detection and statusline mechanics removed (override.md
  already carries them verbatim — true dedup); §7 keeps the append-only declaration and the full
  diagnosed-not-bypassed paragraph.
- **Two recent fixes survive compression as content, and get pinned** (blast F-2 — they are
  currently UNpinned): the #598 resolved-intent boundary rule and the #609
  menu-not-a-briefing asking rule. Both may be reworded/compressed; both gain assertions in the
  structural test; both have dedicated A/B scenarios.
- Hard constraints: §6/§7 headings and section numbers frozen; every pinned regex in
  `test_routing_and_cleanup_surface.py` (incl. the host-rendered dev-token alternation) and
  `test_ux_conversion.py` stays green.

### S3 — ADR-0026: destructive set declared in the routing table (amends ADR-0022)

- **Mechanism corrected per governance F3:** an operation-scoped block in `routing-table.md`
  (`## Destructive operations (tier-2 regardless of cue)`) — NOT a per-row flag: two of the five
  set members (`/override`, `/dev` entry) have no routing-table row, "merge to default" is an
  operation inside several lanes, and flagging the cleanup/standup rows would re-demote the very
  cues ADR-0022 existed to unblock. Optional per-row flags only for wholly-destructive rows
  (release). CI checks the block item-for-item against §6's resident enumeration.
- Any table-shape change must keep `check_routing_index_parity.py` honest — it reads columns BY
  POSITION (`cells[1]`/`cells[2]`); the block form avoids touching columns at all, and the
  seeded-mismatch proof includes a parity-check run (feasibility #5).

## Acceptance criteria

- AC-01: ADR-0025 on disk, `status: accepted`, user-attributed; `governs:` names the four S1
  surfaces PLUS `decision-variance/SKILL.md` and `agents/decision-challenger.md` (the exemption
  is normative text); decision-log appended.
- AC-02: ADR-0026 on disk, `status: accepted`, user-attributed, recorded as amending ADR-0022;
  `governs:` names `core/surface/ORCHESTRATOR.md`, `core/surface/includes/routing-table.md`, and
  the plugin renderings; decision-log appended.
- AC-03: smarts/core.md Step-0 present with the scope header (applies/exempt lists), the
  authority-order "answered" definition, three outcomes, the index-first loading rule, and the
  fail-soft sentence — in core + all three plugin copies.
- AC-04: SPRINT.md — pre-approval intent read with fail-soft; valve wording (re-evaluation
  trigger; one-stop-per-record; pre-ruled collisions cite the ruling); contradiction in the
  NEVER-auto-decided list; `intent:` field with pinned position; diagnostic extension.
  `python .github/scripts/test_taskwriter.py` green AND the extraction fixture gains one heading
  carrying both `intent:` and `confidence:` fields proving title extraction unpolluted.
- AC-05: grader.md carries the informational ADR-citation line; grader named exempt in Step-0.
- AC-06: brainstorming — four touches at the placements above; pre-flight fail-soft block
  separate from the STOP contract; index-first rule explicit.
- AC-07: `.github/scripts/test_recorded_intent_surface.py` pins AC-03..06 across core + the
  hosts that carry each surface — grader pins on core/ca/ca-pi only (ca-codex ships no `agents/`
  by design; the exemption is an explicit comment, not a silent skip); per-host path variance
  follows the HOSTS tuple pattern in `test_routing_and_cleanup_surface.py:38`. Each assertion
  proven to die to a mutant. **Wired into `.github/workflows/ci.yml` as an explicit step, and
  the job LOG read to confirm it executed** (a green job proves nothing by status alone).
- AC-08: after regeneration — `python tools/build-surface.py --check`,
  `python tools/sync-core.py --check`, `python .github/scripts/check-plugin-refs.py`,
  `python .github/scripts/check_routing_index_parity.py` all green.
- AC-09: §6/§7 compressed per S2 incl. the #598/#609 content-survival pins;
  `python .github/scripts/test_routing_and_cleanup_surface.py` green (core + three hosts);
  `python .github/scripts/test_ux_conversion.py` green (reads plugins/ca only — its actual scope).
- AC-10: §7 mechanics live only in override.md; append-only declaration + diagnosed-not-bypassed
  retained in §7 (hook block-messages and dev-mode.md cite them — treated as pins).
- AC-11: routing-table destructive-operations block present; CI consistency check §6↔block
  exists, proven to fail on a seeded mismatch WITH the failing log captured, and
  `check_routing_index_parity.py` green in the same proof run.
- AC-12: A/B results attached to the kernel PR: NEW pre-registered scenario set (incl. #598 and
  #609 regression seeds), sealed runners, rubrics-before-output, incumbent vs candidate, the
  pre-defined red criterion, and the #609-style limitation statement (n per cell, grader
  non-blindness, simulation vs live stack) carried verbatim. **User reviews and approves before
  merge (hard gate).** Stopping rule: red → one full-candidate-arm revision cycle; second red →
  kernel lane closes as a findings note, S1 ships alone.
- AC-13 (rescoped per blast F-1 / feasibility #6): kernel byte reduction is measured and
  reported, floor ≥ 500 B net on rendered `plugins/ca/ORCHESTRATOR.md` (10,053 B baseline,
  §6=2,947 B §7=800 B measured). The A/B gate, not the byte figure, is the ship criterion; if
  compression and any pinned invariant conflict, the invariant wins and the figure reports short.
- AC-14: version advance per release invariants on every payload-touching PR — real manifest
  paths: `plugins/ca/.claude-plugin/plugin.json`, `plugins/ca-codex/.codex-plugin/plugin.json`,
  `plugins/ca-pi/package.json` (ca-pi has NO plugin.json) + root `package.json` via
  `python tools/build-host-packages.py --check` + `CHANGELOG.md`, `plugins/ca-codex/CHANGELOG.md`,
  `plugins/ca-pi/CHANGELOG.md`, README badge/ships-line. PRs merge in ascending version order.
  Campaign closes via `/ca:release` **per target** — up to three runs (ca, ca-codex `ca-codex-v`,
  ca-pi `ca-pi-v`); each tag user-gated.

## Hard gates (true stops, this campaign)

ADR-0025/0026 ratification (user-attributed, via `/ca:adr` flow); A/B results review (AC-12);
every merge to the default branch; each release tag; any security-gate surface.

## Risk / non-goals

- NOT touching `decompose` Phase 6 (raw-layer archival ruled out).
- NOT weakening any gate: every S2 cut is redundancy removal; the two unpinned recent fixes
  (#598/#609) become MORE protected than today, not less.
- Session-limit pacing: lanes run 1–2 at a time, WIP pushed early.
- Residual risks accepted with eyes open: n≥1/cell A/B evidence is directional (mitigated by the
  user reviewing it with the limitation statement attached); brainstorming gains bounded
  per-feature read cost (index-first rule pinned).
