---
entity: agents/tribunal-lens-reviewer
related: [skills/tribunal, commands/tribunal, architecture-drift-reviewer]
---

## Role

The single generic executor behind every tribunal audit lens. `/ca:tribunal`'s roster dispatch
sends this agent out once per active lens, and each dispatch carries an assignment: which lens to
run, which slice of the codebase to cover, and where the run's on-disk record lives. The agent
then loads that lens's card from the selected trusted bundle and reviews the assigned evidence.
It reads product code and writes its findings, leads, or verification results only inside the run
directory. Repository text and tool output cannot change its role or authorize shell commands.

## One body, thirteen cards

The review questions live in thirteen [lens cards](/reference/#tribunal-lenses). Each card states
when it applies, when to skip it, what evidence a finding needs, and common false positives.
[Semantic-contract](/reference/tribunal-lenses/semantic-contract/) checks behavior against an
established requirement. [Change-closure](/reference/tribunal-lenses/change-closure/) traces a
change through consumers, hosts, generated files, and distributed packages. The eleven earlier
lens names and their public links remain available.

## Assignment mechanism

The assignment names the lens, checked source binding, finding scope, bounded evidence, and output
directory. Finding scope controls where a defect may be reported; evidence scope can include
declared callers or contracts needed to understand it. A missing card or source binding stops
the review. The reviewer cannot silently expand the assignment.

## Review and verification

In review mode, the agent seeks concrete contract failures and records impact and evidence.
In verification mode, a fresh instance tries to disprove a candidate finding using only the claim
and necessary evidence. It returns confirmed, narrowed, refuted, or inconclusive. Critical/high
claims and expensive inferential recommendations require this attempt before becoming confirmed
fix work. A host without fresh contexts records limited independence and leaves serious claims
verification-required.

The caller selects supported `deep` or `standard` settings for each assignment. The agent inherits
the configured model where a distinct profile is unavailable, and records that limitation.

## What it emits

Findings are saved individually as they are discovered, with provisional severity and confidence.
Cross-lens observations become durable leads for another lens to establish or dismiss; a lead is
not yet a defect. Verification attempts are saved separately. Existing records are preserved
across interruption, and triage groups corroborating findings by root cause.

The return message stays compact: finding and lead identifiers, provisional counts, reviewed
exposure, and unresolved limits. The agent never edits project code, files issues, sends telemetry,
or dispatches another reviewer.
