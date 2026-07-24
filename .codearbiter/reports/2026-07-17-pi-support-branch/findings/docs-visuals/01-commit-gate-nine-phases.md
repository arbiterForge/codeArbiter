# 01 — Commit-gate's nine phases have no diagram

**Value:** High

**Page(s):** `site/src/content/docs/concepts/gated-lanes.md`, `site/src/content/docs/reference/skills/commit-gate.md`

## What to depict

The nine-phase commit-gate sequence — permission, branch, classification, verification
(test/lint/secrets), behavioral proof, diff review, selective stage, message, commit —
is currently only a comma-separated list in prose ("The `commit-gate` skill runs 9:
permission, branch, classification, verification, behavioral proof, diff review,
selective stage, message, commit."). This is the single most-invoked gate in the whole
system (every commit goes through it) and it is inherently sequential/spatial: each
phase is a hard stop that either passes control to the next phase or blocks. A reader
has to reconstruct the order and branching (block vs. proceed) purely from the sentence.

A diagram should show: the nine phases in order, which ones can hard-stop (block with
`BLOCKED [H-NN]`) vs. which are informational, and where `/ca:override` re-enters the
flow as the sanctioned bypass.

## Recommended form

Technical flow/sequence diagram — vertical swimlane or numbered pipeline, matching the
existing house style used by `lane-flow.svg` and `gate-model.svg`.

## GPT image vs. hand-drawn

Hand-drawn SVG (or mermaid flowchart as an interim/authoring step, then exported to SVG
to match the existing `public/diagrams/*.svg` set's visual language). Do **not** use
GPT image generation — this is precise, labeled, technical process content where a
generated illustration would introduce inaccuracy risk (wrong phase count, wrong order,
invented arrows) and would visually clash with the existing flat, technical SVG diagram
set. The project's existing diagrams (`gate-model.svg`, `lane-flow.svg`) are the correct
template to extend.
