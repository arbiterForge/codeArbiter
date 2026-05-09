# SMARTS Framework

The SMARTS framework is FUSION's standardized evaluation framework for architectural decisions. The arbiter applies SMARTS evenhandedly when comparing options.

SMARTS stands for: **S**calable, **M**aintainable, **A**vailable, **R**eliable, **T**estable, **S**ecurable.

This is the project's chosen framework. The arbiter does not propose alternatives.

## The Six Lenses

### Scalable

Does the option support the system's growth in users, data, throughput, or geographic distribution without architectural rewrite?

**Considerations:**
- User scale: 5 users (MVP1) → 50 users (V1) → potentially thousands (V2 SaaS)
- Data scale: handful of solutions → hundreds → potentially tens of thousands
- Throughput scale: bursty deployment activity, low steady-state
- Geographic scale: single AWS region (MVP1) → potentially multi-region (V2)

**Pitfalls:** over-engineering for scale that won't materialize; under-engineering for scale that's on the roadmap; confusing performance with scalability.

### Maintainable

Can the system be understood, modified, and extended by future engineers — including agents — without prohibitive effort?

**Considerations:**
- Codebase comprehensibility (especially for agent-driven contributions)
- Standard patterns vs custom abstractions
- Documentation burden
- Refactoring blast radius
- Onboarding time for new contributors and the post-handoff product team

**Pitfalls:** treating maintainability as single-engineer concern; underestimating bespoke-pattern cost when agents write most code; ignoring eventual hand-off.

### Available

Is the system reachable and functional when users need it, including under partial failure conditions?

**Considerations:**
- Single points of failure
- Bundled-dependency availability (Gitea, Keycloak, OPA all bundled — what happens if one fails?)
- Air-gap and disconnected operation requirements
- Time-to-recovery from common failure modes
- Acceptable downtime windows (FUSION is delivery platform, not 24/7 operations)

**Pitfalls:** conflating availability with high availability; designing for HA when not required; ignoring partial-availability scenarios.

### Reliable

Does the option produce correct, predictable, durable outcomes?

**Considerations:**
- ACID guarantees where they matter (deployment receipts, audit events, decision log)
- Idempotency of operations
- State consistency across components
- Failure recovery without data corruption
- Reproducibility (especially the pin-with-monitoring deployment fidelity)

**Pitfalls:** assuming "the database handles it" without checking; underestimating reliability cost of distributed systems; ignoring long-tail durability concerns.

### Testable

Can the option be validated through tests that are deterministic, fast, and cover meaningful failure modes?

**Considerations:**
- Unit testability
- Integration testability
- Schema-driven test generation (OCSF, Zod, JSON Schema)
- Contract testing between components
- Test data generation and isolation
- Spike-vs-test boundary

**Pitfalls:** patterns difficult to mock; ignoring test infrastructure cost; "we'll add tests later" for foundational components.

### Securable

Does the option enable the project's security posture — Zero Trust, NIST 800-53, FIPS, STIG — without retrofit?

**Considerations:**
- Authentication boundary (who is the actor)
- Authorization boundary (what can the actor do)
- Audit boundary per ADR-0003
- Secret management posture (.env in MVP1 → OpenBao in V1)
- Surface area (every bundled component is a STIG target)
- Default-deny vs default-allow stance
- Supply chain integrity (license checks, image signing, SBOM)

**Pitfalls:** bolting security on after architecture; confusing compliance with security; underestimating bundled-component STIG burden.

---

## Hard Format Constraints for SMARTS Cells

When the arbiter (or grader subagent) produces a SMARTS analysis table, every cell follows these rules. These are not guidelines — they are constraints. Cells that violate them are non-conformant.

**Rule 1 — Length cap:** Each cell is at most 25 words. No exceptions. Counting tools welcome.

**Rule 2 — Verdict-first:** Each cell starts with one of these four verdict words:
- `Strong` — the option performs well on this lens
- `Adequate` — the option performs acceptably on this lens
- `Weak` — the option performs poorly on this lens
- `Indifferent` — this lens does not meaningfully differentiate the options at the current scale or context

**Rule 3 — Justification follows verdict:** After the verdict word, a brief justification of at most 20 words. Together with the verdict, the cell stays under 25 words.

**Rule 4 — No hedging adverbs:** Forbidden in SMARTS cells: "potentially," "might," "arguably," "perhaps," "generally," "tends to," "could be," "may." If uncertain, the verdict is `Indifferent`.

**Rule 5 — Evidence specificity:** Vague claims like "industry standard," "widely adopted," "well-known," "best practice" do NOT count as evidence. Cite either:
- A specific property of the option (e.g., "OPA Rego compiles to WASM")
- A specific FUSION constraint (e.g., "self-contained packaging mandate," "$300K MVP1 budget," "5-user internal scale")
- A specific failure mode (e.g., "synchronous calls block the event loop")

## Worked Example

**Variance:** OPA bundled inside FUSION's Helm chart vs OPA as external service the customer provides.

| Lens | OPA bundled | OPA external |
|---|---|---|
| Scalable | Adequate. Sub-millisecond decisions sufficient for 50-user V1 scale. | Adequate. Same ceiling but adds network hop. |
| Maintainable | Strong. Single Helm chart owns versioning and integration. | Weak. Two release cycles must coordinate; cross-team friction. |
| Available | Strong. Available whenever FUSION is. | Weak. Air-gap depends on customer infrastructure availability. |
| Reliable | Strong. Failure mode contained inside FUSION pod. | Weak. Failure surface includes customer network and service health. |
| Testable | Strong. Local test environment is one Helm install. | Weak. Test environment requires standing up two services. |
| Securable | Strong. Self-contained mandate satisfied; ZT alignment intact. | Weak. Customer OPA may have different policy hygiene; cross-service auditing harder. |

**Dominant lenses:** Securable and Available.

**Recommendation:** Bundle OPA. Strength: strong. Both dominant lenses favor it cleanly; no lens favors external OPA enough to override.

## Strength of Recommendation Levels

When the arbiter (or grader) finishes a SMARTS analysis, the recommendation has exactly one strength label:

- **strong** — multiple dominant lenses align cleanly toward one option; non-SMARTS considerations confirm
- **moderate** — dominant lenses align toward one option but with caveats, or with a single lens dominating
- **tied** — the analysis genuinely produces no preferred option

There is no `weak` level. If the analysis is close but a slight edge exists, the strength is `moderate`. If the analysis is genuinely tied, the strength is `tied` and the user is told plainly that this is a coin flip under SMARTS.

This forces commitment when commitment is warranted and explicit acknowledgment when it is not. The arbiter never hides behind hedged language.

## When SMARTS Doesn't Resolve

If lenses pull in different directions and no clear winner emerges:

1. State plainly that lenses conflict
2. Identify which lens the user has emphasized in prior decisions (project history)
3. Surface that bias as input to the user's choice
4. Mark strength as `tied`
5. Recommend the option that aligns with prior emphasis, with explicit acknowledgment that the choice is contestable

`Tied` strength is a valid outcome. "This is a coin flip under SMARTS — your call" is a legitimate arbiter output.

## SMARTS Limitations

The framework does not directly cover:

- Cost (budget impact)
- Time-to-market
- Team-skill fit
- Vendor lock-in
- Political acceptability (cross-DA dynamics)

When these matter, the arbiter calls them out as **non-SMARTS considerations** alongside the SMARTS analysis. They are evaluated qualitatively and presented to the user. They do not replace SMARTS; they supplement it.
