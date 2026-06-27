---
title: The gated-lane model
description: "How codeArbiter assigns every kind of work to a sanctioned path with gates scaled to its risk, and what distinguishes soft gates from hard gates."
---

Every kind of work has a **lane**: a sanctioned path with gates scaled to its risk. A lane
is not a suggestion. It is the only way that kind of change ships. `/ca:fix` and
`/ca:feature` run test-first through the `tdd` gate. `/ca:refactor` must prove behavioral
parity through *unmodified* pre-existing tests. `/ca:chore` carries lighter gates, because
prose edits and dependency bumps don't demand TDD.

Gates come in two strengths. **Soft gates** surface a decision and wait for the user.
**Hard gates** are true stops, never auto-decided, even under autonomous execution:
anything in the security controls, auth/crypto/secret changes, irreversible operations, a
gate bypass, an unresolved decision, or a merge to the default branch. Hard gates are rare
by design. When they trip often, that's a signal the spec was too thin, not an obstacle to
grind past.

<figure class="ca-diagram">
  <img src="/codeArbiter/diagrams/gate-model.svg" alt="Gate model. A soft gate surfaces a decision bubble and waits for the user. A hard gate is a closed cross-bar that is never auto-decided." loading="lazy" />
  <figcaption>Soft gates surface and wait. Hard gates stop, and only the user can clear them.</figcaption>
</figure>
