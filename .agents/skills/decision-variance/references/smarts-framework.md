# SMARTS Framework

The SMARTS framework is the standardized evaluation framework for architectural decisions. This skill applies SMARTS evenhandedly when comparing options.

SMARTS stands for: **S**calable, **M**aintainable, **A**vailable, **R**eliable, **T**estable, **S**ecurable.

This is the project's chosen framework. This skill does not propose alternatives.

## The Six Lenses

### Scalable

Does the option support the system's growth in users, data, throughput, or geographic distribution without architectural rewrite?

**Considerations:**
- User scale: prototype (few users) → pilot → production (potentially thousands)
- Data scale: few records → hundreds → potentially tens of thousands
- Throughput scale: bursty activity, low steady-state
- Geographic scale: single region → potentially multi-region

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
- Bundled-dependency availability (what happens if a bundled service fails?)
- Air-gap and disconnected operation requirements
- Time-to-recovery from common failure modes
- Acceptable downtime windows

**Pitfalls:** conflating availability with high availability; designing for HA when not required; ignoring partial-availability scenarios.

### Reliable

Does the option produce correct, predictable, durable outcomes?

**Considerations:**
- ACID guarantees where they matter (deployment receipts, audit events, decision log)
- Idempotency of operations
- State consistency across components
- Failure recovery without data corruption
- Reproducibility (especially for pinned deployment fidelity)

**Pitfalls:** assuming "the database handles it" without checking; underestimating reliability cost of distributed systems; ignoring long-tail durability concerns.

### Testable

Can the option be validated through tests that are deterministic, fast, and cover meaningful failure modes?

**Considerations:**
- Unit testability
- Integration testability
- Schema-driven test generation
- Contract testing between components
- Test data generation and isolation
- Spike-vs-test boundary

**Pitfalls:** patterns difficult to mock; ignoring test infrastructure cost; "we'll add tests later" for foundational components.

### Securable

Does the option enable the project's security posture — as defined in `${PROJECT_ROOT}/.agents/projectContext/security-controls.md` and `${PROJECT_ROOT}/.agents/projectContext/trust-zones.md` — without retrofit?

**Considerations:**
- Authentication boundary (who is the actor)
- Authorization boundary (what can the actor do)
- Audit boundary
- Secret management posture
- Surface area (every bundled component is a potential attack surface)
- Default-deny vs default-allow stance
- Supply chain integrity (license checks, image signing, SBOM)

**Pitfalls:** bolting security on after architecture; confusing compliance with security; underestimating bundled-component hardening burden.

---

## Hard Format Constraints for SMARTS Cells

When this skill (or grader subagent) produces a SMARTS analysis table, every cell follows these rules. These are not guidelines — they are constraints. Cells that violate them are non-conformant.

**Rule 1 — Length cap:** Each cell is at most 25 words. No exceptions. Counting tools welcome.

**Rule 2 — Verdict-first:** Each cell starts with one of these four verdict words:
- `Strong` — the option performs well on this lens
- `Adequate` — the option performs acceptably on this lens
- `Weak` — the option performs poorly on this lens
- `Indifferent` — this lens does not meaningfully differentiate the options at the current scale or context

**Rule 3 — Justification follows verdict:** After the verdict word, a brief justification of at most 20 words. Together with the verdict, the cell stays under 25 words.

**Rule 4 — No hedging adverbs:** Forbidden in SMARTS cells: "potentially," "might," "arguably," "perhaps," "generally," "tends to," "could be," "may." If uncertain, the verdict is `Indifferent`.

**Rule 5 — Evidence specificity:** Vague claims like "industry standard," "widely adopted," "well-known," "best practice" do NOT count as evidence. Cite either:
- A specific property of the option (e.g., "policy engine compiles to WASM")
- A specific project constraint (e.g., "self-contained packaging mandate," "5-user internal scale")
- A specific failure mode (e.g., "synchronous calls block the event loop")

## Worked Example

**Variance:** Authorization engine bundled inside the deployment package vs provided by the customer environment.

| Lens | Bundled | External / Customer-provided |
|---|---|---|
| Scalable | Adequate. Sub-millisecond decisions sufficient for 50-user scale. | Adequate. Same ceiling but adds network hop. |
| Maintainable | Strong. Single package owns versioning and integration. | Weak. Two release cycles must coordinate; cross-team friction. |
| Available | Strong. Available whenever the system is. | Weak. Air-gap depends on customer infrastructure availability. |
| Reliable | Strong. Failure mode contained inside the deployment boundary. | Weak. Failure surface includes customer network and service health. |
| Testable | Strong. Local test environment is one package install. | Weak. Test environment requires standing up two services. |
| Securable | Strong. Self-contained mandate satisfied; zero trust alignment intact. | Weak. Customer engine may have different policy hygiene; cross-service auditing harder. |

**Dominant lenses:** Securable and Available.

**Recommendation:** Bundle the authorization engine. Strength: strong. Both dominant lenses favor it cleanly; no lens favors the external option enough to override.

## Strength of Recommendation Levels

When this skill (or grader) finishes a SMARTS analysis, the recommendation has exactly one strength label:

- **strong** — multiple dominant lenses align cleanly toward one option; non-SMARTS considerations confirm
- **moderate** — dominant lenses align toward one option but with caveats, or with a single lens dominating
- **tied** — the analysis genuinely produces no preferred option

There is no `weak` level. If the analysis is close but a slight edge exists, the strength is `moderate`. If the analysis is genuinely tied, the strength is `tied` and the user is told plainly that this is a coin flip under SMARTS.

This forces commitment when commitment is warranted and explicit acknowledgment when it is not. This skill never hides behind hedged language.

## When SMARTS Doesn't Resolve

If lenses pull in different directions and no clear winner emerges:

1. State plainly that lenses conflict
2. Identify which lens the user has emphasized in prior decisions (project history)
3. Surface that bias as input to the user's choice
4. Mark strength as `tied`
5. Recommend the option that aligns with prior emphasis, with explicit acknowledgment that the choice is contestable

`Tied` strength is a valid outcome. "This is a coin flip under SMARTS — your call" is a legitimate output from this skill.

## SMARTS Limitations

The framework does not directly cover:

- Cost (budget impact)
- Time-to-market
- Team-skill fit
- Vendor lock-in
- Political acceptability (cross-team or cross-stakeholder dynamics)

When these matter, this skill calls them out as **non-SMARTS considerations** alongside the SMARTS analysis. They are evaluated qualitatively and presented to the user. They do not replace SMARTS; they supplement it.
