---
entity: skills/debug
related: [commands/debug, tdd]
gates:
  - gate: symptom and scope
    when: before dependent investigation
    effect: identify the symptom, available expectation, reproduction state, cited evidence or gap, and actual caller authority
  - gate: evidence-led hypotheses
    when: during diagnosis
    effect: retain plausible mechanisms with real discriminators; do not require or cap a number of hypotheses
  - gate: one supported disposition
    when: at exit
    effect: choose confirmed_code_defect, confirmed_noncode_cause, design_question, no_action, or unresolved and keep the next action within its own authority
---

## What it does

The debug skill owns root-cause investigation from a plain-language request or the generated
command entry. It does not edit application code. It starts from an identifiable symptom or cited
failure, even when the trigger is unknown, and records the limits of reproduction and source or
runtime identity. It compares distinct plausible mechanisms against cited evidence, including
capture coverage and contrary evidence. A partial trace or failed replay does not prove that an
event did not happen.

## Phases

1. Capture observed behavior, available expected behavior, reproduction state, caller scope,
   and the source and limits of the evidence. Unknown details stay unknown.
2. Name plausible mechanisms and a distinguishing observation for each. The evidence sets the
   number of hypotheses.
3. Assess each diagnostic action's target, effects, bounds, and authority before running it.
   Mark candidates confirmed, refuted, or inconclusive with applicable citations. If no safe
   useful discriminator is available, stop with `unresolved` and a resume condition.
4. Select one supported disposition for the case while preserving multiple supported causes
   and separate access or authority blockers.
5. Return the evidence, uncertainty, owner, next action, and actual continuation boundary.

## Exits

- `confirmed_code_defect` gives the fix owner a causal trace or reproduction and a concrete
  regression obligation. The fix owner must observe target red before repair and independently
  confirm that the original caller authorized repair.
- `confirmed_noncode_cause` names the operational owner or the absence of a known owner and
  retains any permission blocker.
- `design_question` names the intended-behavior decision and its competing evidence. An ADR
  needs its own attributed owner.
- `no_action` requires positive evidence that the applicable behavior is required or already
  resolved. It closes without a default board write or other state change.
- `unresolved` reports the missing discriminator or prerequisite, next action, and resume
  condition without an invented fix or decision.

For a transfer, the skill resolves the installed private `debug-handoff.py` helper, invokes
Python with `-B` and literal `validate`, and sends one transient packet of at most 65,536 UTF-8
bytes through stdin before closing it. Exit 0 with `valid: true` and no errors permits transfer;
exit 2 rejects input, while exit 3 or an unavailable helper blocks transfer. A refusal is not
retried through another interpreter. A valid structure does not prove evidence or grant
authority. A separately authorized task follow-up is handled by the existing
`/ca:task` owner and installed `taskwrite.py` writer; the debug exit does not call it.
