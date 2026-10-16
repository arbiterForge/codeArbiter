---
entity: skills/tdd
related: [commands/feature, commands/fix, commands/refactor, commit-gate]
gates:
  - gate: verification approach
    when: before changing code
    effect: map required behavior and applicable constraints to meaningful proving checks, selecting the approach appropriate to the work
  - gate: regression baseline
    when: repairing a confirmed code defect
    effect: observe a named regression failing for the target defect before repair, then passing with unchanged assertions
  - gate: verification
    when: assessing the completed change
    effect: required behavioral checks, coverage metrics and applicable lint/type checks must pass; missing or failed evidence remains outstanding
---

## What it does

Verifies feature, fix and refactor work against explicit obligations. Select the verification
approach before changing code and report the sequence actually observed.

| Work | Evidence |
|---|---|
| Confirmed fix | A named regression fails for the defect before repair and passes afterward. Reuse an adequate current failing test. |
| Feature | Prefer test-first checks; existing implementation can be assessed with current criterion-focused tests and meaningful negative controls where needed. |
| Refactor or coverage backfill | Run characterization tests before restructuring; initially passing tests establish the baseline. |
| Documentation or non-executable change | Use relevant reference, generation, schema or rendering validation, and explain inapplicable test or coverage phases. |

## Phases

1. Map each required claim to its source and proving check, including applicable contract and
   security boundaries.
2. Run the selected baseline. For a fix, an import, setup or unrelated failure is not target RED.
   Use isolated negative controls when useful; never damage correct production behavior to get RED.
3. Implement the scoped change and run affected checks. For fixes, keep assertions unchanged
   between RED and GREEN; material fixture or setup changes require renewed target RED against
   the broken source. Preserve characterization assertions through refactors.
4. Check the obligations against actual results and review the combined change at the scope its
   risks warrant. Reuse results only while the relevant source and inputs still match.
5. Apply the project's coverage profile, required metrics and critical-path requirements. Report
   unavailable hosts as unmeasured and use the declared no-tooling rule when applicable.
6. Run applicable lint and type checks. Return commands, working directories, observed results
   and pending checks to the caller.

## Exits

Unexplained failures and untested requirements remain outstanding. Correct affected work and rerun
its checks without weakening assertions, lowering coverage requirements or suppressing security
checks. The commit owner uses this evidence for the selected changes; exact-head hosted CI remains
required before merge. Implementation, verification, review and release are distinct results.

Use the available host for relevant live checks; ordinary work does not require installing or
switching to another host. Maintainer CI checks adapter compatibility. Report a host denial once
and continue unaffected authorized work; do not keep retrying or search for a host that will pass.

[Test-first evidence](/concepts/test-first/) follows verification within a change and its delivery
handoff. Direct implementation reads relevant context; actual delegation receives a bounded
packet. An advisory delivery result does not require another retry.
