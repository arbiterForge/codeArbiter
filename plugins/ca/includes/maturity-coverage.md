# Maturity → minimum coverage

The single source of truth for the coverage threshold. Coverage scales with the maturity value
(`stage:` in `CONTEXT.md`) — a rigor knob, not a promotion gate. Referenced by `tdd` Phase 5,
`refactor` Phase 2 and Phase 6, and the `coverage-auditor` agent.

| maturity | minimum coverage |
|---|---|
| 1 | ≥ 60% |
| 2 | ≥ 70% |
| 3 | ≥ 85% |
| 4 | ≥ 90% |

## Which metric (issue #507)

**Lines and branches. Both must clear the threshold.** A report satisfying one and not the other
does not pass.

This was previously unstated, and the omission was load-bearing rather than cosmetic: a coverage
report gives four numbers that disagree, so "≥ 70%" without a column named is not a threshold anyone
can be held to. Measured on codeArbiter itself at the time of writing, one tree sat at 85.37% lines
and 78.73% branches — compliant at maturity 3, or not, depending purely on which column the reader
picked.

- **Lines** catches code no test reaches at all — a `catch` block with zero executions inside a
  passing suite, which no assertion is ever going to surface.
- **Branches** catches the untaken half of a condition a test does reach: the error arm of an `if`,
  the fallback of a `??`. Line coverage alone reports those as covered.
- **Statements** duplicates lines closely enough to add nothing. **Functions** is the noisiest
  column at small counts, where one uncovered helper moves it several points.

**The number is the floor, not the goal.** A test written only to move a percentage is worse than
the gap it closed, because it converts an honest red into a green that asserts nothing. When
backfilling to clear this bar, work the uncovered *report* — error and refusal paths first — and let
the number follow.

## Which host (issue #521)

**A quoted coverage figure is the UNION of the supported hosts' reports for that tree.** Not any
single host's.

The command is identical everywhere; the REPORT is not. Code behind a platform fork cannot execute
off its own platform, so a single-host report scores the other platform's arm as uncovered — and it
stays uncovered no matter how many tests are written for it. Measured on this repo: `exec.ts` reads
87.50% branches on Windows and 76.38% on Linux, an 11-point gap that is entirely `awaitTaskkill` and
the win32 `treeKill` arm on one side and the POSIX arm on the other. Neither number is wrong; both
are incomplete.

That matters beyond arithmetic. `treeKill` is a process-containment path, so under a single-host
rule a GENUINE gap in it is indistinguishable from the platform artifact — the figure stops
measuring test quality and starts measuring how much of the tree is POSIX.

**Applies per tree, and only where it earns its cost.** A tree with platform-forked code is measured
on more than one host and merged; a tree with none stays single-host, because a union of identical
reports is the same report. `tech-stack.md` names which trees are which, and which hosts a tree is
measured on.

**When quoting a figure — in an issue, an ADR, a phase record — name the host or hosts it came
from.** An unattributed number is not reproducible, and this is the ambiguity #521 was filed for.

Where only one host's report is available, that is a legitimate figure: state the host and say the
other's contribution is missing. A partial measurement that says so is worth more than a merged one
that cannot be reproduced.

## The no-tooling exemption — cite it, never assert it

Where a surface has no coverage tooling at all, there is no numeric floor to check. Record that
explicitly; do not invent a command, and do not treat the phase as passed unexamined.

**The record MUST name the surface, and quote from `tech-stack.md` either its whole Coverage section
or the passage that states the absence FOR THAT SURFACE BY NAME.** An agent that could not FIND the
command is indistinguishable, from the inside, from a surface that genuinely HAS none — and the two
demand opposite responses: the first is a STOP, the second is this exemption. Only the citation
separates them, and it is what makes the exemption falsifiable by a reviewer rather than a claim
that closes a BLOCK gate on the word of the agent that wanted through it.

Three readings are excluded deliberately, because each would let the citation pass while proving
nothing:

- **A Coverage section that lists commands is still quotable.** The section does not have to be
  empty; it has to fail to give a command for THIS surface. Quoting a section that names commands
  for other trees is correct and expected.
- **A partial quote that stops before the commands is not a citation.** Quote the section entire, or
  quote the sentence that names this surface as uncovered. Nothing in between.
- **Silence is not evidence.** A section that simply never mentions the surface does not establish
  that no command exists for it — that is the "could not find" case. Quote the section in full so a
  reviewer can see the silence and judge it, and say plainly that the surface is unmentioned.

**Where the record goes:** the phase output, and — because this exemption passes a BLOCK gate — it
travels into the PR description for the change, so the claim is still falsifiable when a human
reviews rather than only while the lane is live.

So: no citation, no exemption. A phase that cannot produce one STOPs and surfaces the gap instead —
the same response the skills' hard rule already requires for a missing test or lint command. This is
deliberately the narrower reading: the failure mode being guarded is a gate that reads as satisfied
without executing, which is what issue #507 found in five suites at once.

Consumers of this rule: `tdd` Phase 5, `refactor` Phase 2 and Phase 6, and the `coverage-auditor`
agent. They point here and MUST NOT restate the exemption's CONDITIONS locally — a local gloss
naming the requirement is fine, a local copy of what satisfies it is not. Divergent copies are how
Phase 2 and Phase 6 start giving different answers about one surface, and how project state can end
up instructing an agent to assert where this file requires it to cite.
