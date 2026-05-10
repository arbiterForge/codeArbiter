---
description: Run the stage-promotion checklist from current stage to next stage
argument-hint: "<target-stage 2|3|4>"
---

Run the stage promotion checklist to advance to Stage `${1:?target stage required}`.

1. Read `.fusion/stage` — current stage. Verify `${1}` is exactly current+1.
   No skipping stages.

1a. **Checkpoint gate** — glob `docs/checkpoints/*.md` for any file that contains
    the string `AWAITING SIGN-OFF`. If any unsigned checkpoint exists, STOP immediately:
    > "Stage promotion blocked: unsigned checkpoint(s) found in docs/checkpoints/.
    > Sign off on all checkpoints before running /promote-stage.
    > Unsigned files: [list them]"
    Do NOT proceed past this point until the gate clears.
2. Read CLAUDE.md §1 promotion triggers for stage `${1}`.
3. Read `docs/cicd.md` — verify all gates that become enforcing at stage `${1}` currently pass.
4. Read `docs/open-questions.md` — list every `[CONFIRM-NN]` that blocks stage `${1}`. If any are unresolved, STOP.
5. Read `docs/risks.md` — for any risk with `Target Closure: Stage ${1}`, verify status is `Closed` (with ADR link). If not, STOP.
6. Run `make ci` with stage temporarily set to `${1}` (export `FUSION_STAGE=${1}` for the run, do NOT modify `.fusion/stage` yet).
7. If `make ci` passes:
   - Draft an ADR in `docs/decisions/NNNN-promote-to-stage-${1}.md` documenting the promotion.
   - Update `.fusion/stage` to `${1}`.
   - Update `docs/risks.md` for any risk now requiring action at the new stage.
8. If `make ci` fails: emit the verbatim failure list. Do NOT update `.fusion/stage`.

Stage promotion authority — see `[CONFIRM-09]` in `docs/open-questions.md`.
The agent MUST NOT promote stages without the named approver's PR comment:
`Approved by <name> for stage ${1} promotion`.
