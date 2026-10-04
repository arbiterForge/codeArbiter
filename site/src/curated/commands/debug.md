---
entity: commands/debug
related: [fix, adr, skills/debug]
gates:
  - gate: identifiable symptom
    when: at entry
    effect: record observed behavior, available expectation, reproduction state, caller scope, and cited failure or evidence gap; an unknown trigger can remain unknown
  - gate: discriminating hypotheses
    when: before and during evidence gathering
    effect: use distinct plausible mechanisms and real discriminators; there is no required hypothesis count
  - gate: bounded diagnosis
    when: throughout the investigation
    effect: assess effects and authority before diagnostics; do not change application code or turn a finding into repair permission
  - gate: supported disposition
    when: at handoff
    effect: select one supported case result from the five defined below; keep any next action within its own authority
---

## What it does

`/ca:debug` investigates an unexplained symptom and returns a cited diagnosis or a bounded
`unresolved` result. It records what was observed, what the current contract supports, the
reproduction state, and the source or runtime identity where known. A cited failure with an
unknown trigger can enter as `not_yet_reproduced`; a failed replay describes only the conditions
tested. Candidates follow the evidence. Each plausible mechanism needs an observation that could
distinguish it from the others. Environmental or configuration causes are considered when they fit,
without adding them to meet a quota. Capture limits and contrary evidence remain visible.

## Usage

A plain-language diagnosis request selects the same owning skill. `/ca:debug` is its generated
explicit entry, not a second procedure.

```
/ca:debug <observed symptom>
```

Give the observed failure and any known expectation, trace, or reproduction. The trigger can
remain unknown when a cited failure identifies the case.

## Example

```text
Illustrative investigation entry, not a captured run:
> /ca:debug export returns no CSV for one saved search

Observed: no CSV for the saved search.
Expected: a header and one row, if the current export contract requires it.
Reproduction: not yet reproduced; trigger unknown.
Evidence: the reported failure needs its source and time or revision context.
Candidate checks: export path, input selection, and running build identity,
where each has a distinguishing observation.
Result: pending evidence; no cause or exit is claimed by this example.
```

Every case receives one supported result. The values are `confirmed_code_defect` for a code
repair candidate, `confirmed_noncode_cause` for an operational finding, `design_question` for
an intended-behavior decision, `no_action` for positive closure, and `unresolved` for an evidence
gap. A case may have multiple supported contributing causes. A code-defect handoff carries cited
causal evidence and a concrete regression obligation;
`/ca:fix` still has to observe target red before repair. A non-code cause identifies the operational
owner or records that none is known. A design question goes to an attributed decision owner, without
automatically creating an ADR. No action needs positive closure evidence and makes no default board
write. Unresolved names the missing discriminator, next action, and resume condition.

A recommendation does not grant authority. The receiving owner checks the original caller's scope
and any access or approval blocker before acting. An active authorized fix may use one bounded
internal diagnostic return and resume its own gates; the public commands do not call each other
recursively. A separately authorized concrete task follow-up belongs to the existing `/ca:task`
owner and its installed writer. The debug result itself does not write the board.

When a handoff packet is used, the owner resolves the private validator from the loaded installed
package and invokes Python with `-B`, its absolute path, and `validate`. The packet is at most
65,536 UTF-8 bytes, sent once through stdin and closed. Only exit 0 with `valid: true` and no
errors permits transfer. Exit 2 rejects the packet; exit 3 or an unavailable helper blocks
validated transfer. Do not retry a refusal through another interpreter. Structural validation
does not prove evidence truth, freshness, or authority. The packet stays transient; no fixed
report file is promised. See [Investigate and fix a defect](/guides/investigate-and-fix/) for the
operator procedure.

## When to reach for it

Reach for `/ca:debug` when the cause isn't known yet. If the cause and a reproduction are already
in hand, go straight to `/ca:fix`.
