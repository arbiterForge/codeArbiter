# 06 — SMARTS six lenses could be a compact visual, but risk of slop is real

**Value:** Low-Medium

**Page(s):** `site/src/content/docs/concepts/smarts.md`

## What to depict

The six SMARTS lenses (Scalable, Maintainable, Available, Reliable, Testable,
Securable) are currently a bulleted list, each with a short definition. A reader
building a mental model of "six lenses scored evenhandedly" could benefit from seeing
them as six equal facets at a glance (e.g., a hexagon or six-box grid) rather than
reading six bullet paragraphs top to bottom. This is a genuine but modest comprehension
aid — the list format already communicates "six co-equal things" reasonably well via
parallel bullet structure, so the marginal value of a graphic is lower than the other
findings in this set.

## Recommended form

If pursued: a plain six-box or hexagon label grid (acronym letters + one-word labels),
purely typographic, no iconography per lens. Explicitly flagging the anti-pattern here:
do **not** give each lens its own icon (a checkmark for Testable, a shield for
Securable, a gear for Maintainable, etc.) — that is the canonical slop move for this
kind of content (generic stock-icon-per-concept), and this project's anti-slop doctrine
should treat it as a smell, not a feature.

## GPT image vs. hand-drawn

If built at all, a simple hand-coded SVG/CSS grid — text-only, no illustration. This is
a page where I'd actively recommend **against** any generated image, including
GPT-image output: SMARTS is an abstract scoring rubric, and abstract-concept-to-icon
mapping is exactly where AI-generated illustration tends to produce vague, generic
imagery (scales of justice, lightbulbs, checkmarks) that adds visual noise without
adding information. Given the marginal comprehension value here, it may be reasonable
to leave this page as-is.
