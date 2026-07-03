---
entity: skills/skill-author
related: [commands/new-skill]
gates:
  - gate: gap evidence
    when: before any authoring begins
    effect: the gap must be proven not already covered by an existing skill, and backed by either three concrete blocked cases or one high-impact traceable one — a hypothetical case does not count
  - gate: scope agreement
    when: before any prose is written
    effect: you must explicitly agree on whether the gap is a routed skill or a dispatched agent, whether it's command-invoked or internal, and its one-sentence single responsibility
  - gate: routing integration
    when: at the end
    effect: a new skill is not finished until it has a catalog entry and a routing-table entry — a skill nothing routes to is dead code
---

## What it does

This is the only sanctioned way a new skill gets written, invoked through the new-skill command
with a stated gap. It first proves the gap isn't already covered, settles the new skill's exact
scope with you, writes it to the house format, self-reviews it against that format, and wires it
into the catalog and routing table so it's actually reachable.

## Phases

1. Restate the gap, check it against the existing skill catalog for overlap, and demand concrete
   evidence — either three specific blocked cases or one high-impact traceable one.
2. Settle scope with you: routed skill or dispatched agent, command-invoked or internal, and a
   single stated responsibility.
3. Write the skill to the house format — frontmatter, an opening description, a pre-flight list,
   numbered gated phases, and hard rules.
4. Re-read the authored skill against the house quality bar, fix every defect found, and present
   the corrected version along with the findings list.
5. Add the skill's catalog entry and routing-table entry, verify every reference it cites
   resolves, and hand the change to the commit gate.

## Exits

A finished skill has a catalog row, a routing entry, and lands only through the commit gate — it
is never committed directly from here. Insufficient evidence in the first phase ends the request
outright rather than producing a speculative skill.
