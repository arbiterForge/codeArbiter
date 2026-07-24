# 08 — Reference index's command/skill/agent relationship is implicit across three flat tables

**Value:** Low-Medium

**Page(s):** `site/src/content/docs/reference/index.md`

## What to depict

The reference index presents three separate flat tables — Commands (37 rows), Skills
(21 rows), Agents (27 rows) — with no visual indication of how they relate. A reader
new to the project can't tell from this page alone that the relationship is roughly
command → routes to one owning skill → skill dispatches zero or more agents (the
concept explained in prose on `overview.md` via the `lane-flow.svg` figure, and again in
`gated-lanes.md`). Because that routing relationship is already diagrammed elsewhere
(`lane-flow.svg` on the landing page and `overview.md`), a full new diagram here is
lower priority — the marginal opportunity is just a one-line cross-reference/callout at
the top of `reference/index.md` pointing back to the existing lane-flow figure, rather
than a new asset.

## Recommended form

No new diagram recommended. Add a short callout or link at the top of
`reference/index.md`: "See how these three catalogs relate: [Lane flow](/overview/#how-a-request-flows)."
If a visual is still wanted, a small legend icon per table header (not per row) tying
back to the existing lane-flow diagram's step numbers would be the minimal-effort option.

## GPT image vs. hand-drawn

N/A — reuse the existing `lane-flow.svg`, don't generate anything new.
