---
entity: agents/decision-challenger
related: [skills/decision-lifecycle, skills/decision-variance, grader]
---

## Role

Adversarial red-team reviewer of Architecture Decision Records: builds the strongest case against each
decision under review, names its load-bearing assumptions, and rates confidence 1–5 rather than
rubber-stamping. Read-only and decides nothing itself — dispatched by `decision-lifecycle` (via
`/ca:adr-status`) and optionally by `decision-variance` when a variance warrants adversarial scrutiny;
the user makes the actual call.

## Why this model tier

Ships `model: inherit`, matching whatever reasoning budget the dispatching lane already carries.
Building the strongest case against a decision — not just describing it — is the kind of adversarial
reasoning that benefits from staying at the calling context's tier rather than a fixed cap.

## What it emits

One block per ADR: a confidence rating (1–5), the load-bearing assumptions, the strongest case against
the decision, the evidence that would disprove it, and an UPHOLD / REVISIT / ESCALATE recommendation —
never a decision, only the argument for the user to weigh.
