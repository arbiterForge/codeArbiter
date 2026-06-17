# Spec — UX conversion trio: "Make enforcement land as value"

**Issues:** #82 + #84 + #83 · **Effort:** M (M+S+S) · **Posture:** cashes the promise PR 86 wrote into
the README — "the gates read as protection, not ceremony." Conversion mechanic under ADR-0006: SHOW a
gate catching a real mistake, then reflect the prevention back.

## Problem

The product enforces well but never reflects its value back. Shipping a feature ends in silence
(`skills/finishing-a-development-branch/SKILL.md` ends at "the merge is not yours to take"). Gate
blocks state the *rule*, not the *stakes* ("coverage below threshold"), so friction reads as "blocked
again" with no felt payoff. And `ORCHESTRATOR.md` mandates "decisive and terse" *globally*, which is
right for routing/gating but turns the close into a vending-machine interaction. Three small,
coherent changes fix the two moments where value is earned: **the close** and **the caught finding**.

## Scope

**In:** prose/skill-body edits to six framework files that reflect prevention back at the close and at
substantive finding-blocks. No new command, no new runtime code path, no statusline change.

- **#82 Receipt close.** `finishing-a-development-branch` gains a **Receipt**: obligations covered,
  gates that fired and what they caught, the SMARTS decisions the user made, secrets/regressions
  prevented, suite time. Drawn ONLY from the Phase-1 state the skill already assembles plus
  `last-checkpoint` — never a fresh audit-trail crawl (avoids a slow terminal step). `SPRINT.md`'s
  existing Phase-3 summary (`:104`) is aligned to the same Receipt field shape.
- **#84 Stakes on substantive blocks.** A one-line **consequence-avoided** statement (state the
  consequence avoided, not the rule violated) is required on exactly the *finding* blocks: tdd
  coverage/`MISSING` (Phases 4 & 5), secret-handling caught secret, commit-gate Phase 5
  behavioral-proof mismatch, commit-gate Phase 6 diff-review scope/credential finding.
- **#83 Register split.** `ORCHESTRATOR.md:9-11` keeps the terse default for routing/gating but
  permits **exactly one** warm synthesizing sentence at each close and at each genuine *caught* finding
  the user then fixed. The permission is wired at the real close/finding points, not only stated.

**Verification model:** a new structural test `.github/scripts/test_ux_conversion.py` (stdlib-only per
ADR-0004) asserts the required content markers are present and the forbidden ones are absent. This
turns the otherwise-inspectable prose obligations into executable red→green tests wired into CI —
enforcement-not-trust applied to this sprint's own output. Assertions are coarse (durable marker
phrases / section anchors), not exact-wording, to avoid brittleness.

**Out of scope (explicit — rejected under challenge):** a global rolling "saves ledger", a per-gate
counter, or a new statusline segment (gameable junk-signal; statusline is column-rationed). A fresh
audit-trail crawl at the close. Stakes lines on *mechanical* gates — protected branch, missing
`tech-stack.md`, wildcard staging, subject >72 chars (a "this would have bitten you" line there is
noise). Warmth on routine green commits; emojis; flattery. No change to gate *logic*, to
`security-controls.md`, or to any crypto/secret/auth enforcement — copy only.

## Acceptance criteria

1. **Receipt exists.** `finishing-a-development-branch` prints a Receipt close listing all five fields:
   obligations covered, gates fired + what each caught, SMARTS decisions the user made,
   secrets/regressions prevented, suite time.
2. **Receipt sourcing.** The Receipt text draws only from Phase-1 state + `last-checkpoint`; the skill
   explicitly forbids a fresh audit-trail crawl.
3. **Sprint summary aligned.** `SPRINT.md` Phase 3 summary uses the same Receipt field shape.
4. **No ledger/counter/statusline.** No saves-ledger, per-gate counter, or new statusline segment is
   introduced in any touched file.
5. **Stakes on finding blocks.** A one-line consequence-avoided statement is present on each of: tdd
   coverage/`MISSING` (Phase 4 & 5), secret-handling caught secret, commit-gate Phase 5
   behavioral-proof mismatch, commit-gate Phase 6 diff-review finding.
6. **Mechanical gates stay terse.** No stakes line is added to the protected-branch, missing
   `tech-stack.md`, wildcard-staging, or subject-over-72 blocks.
7. **Register split.** `ORCHESTRATOR.md` retains the terse default for routing/gating and permits
   exactly one warm synthesizing sentence at each close and each genuine caught finding the user fixed.
8. **Warmth bounded.** The register text forbids warmth on routine green commits and forbids
   emojis/flattery.
9. **Warmth wired, not abstract.** The one-warm-sentence permission is referenced at the actual close
   points (Receipt, `/sprint` summary) and at the caught-finding points (tdd/secret/commit-gate), not
   only declared in `ORCHESTRATOR.md`.
10. **Reference graph green.** `python .github/scripts/check-plugin-refs.py` passes; no broken refs.
11. **Test wired.** `test_ux_conversion.py` runs in CI and is listed in `tech-stack.md`; it encodes
    ACs 1–9 as executable assertions (positive markers present, negatives absent).

## Notes

- **No version bump:** `plugin.json` is `2.4.3`, unpublished (no `v2.4.3` tag), so further `plugins/ca/**`
  payload changes pass the version-bump gate as-is.
- **No hard-gate surface:** every edit is user-facing copy on existing gates; gate logic,
  `security-controls.md`, and crypto/secret/auth enforcement are untouched. Editing the
  `secret-handling`/`commit-gate` skill *prose* is not a secrets/crypto operation.
