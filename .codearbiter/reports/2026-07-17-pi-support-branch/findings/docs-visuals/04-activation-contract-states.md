# 04 — Activation contract's three states (dormant / enabled / malformed) aren't visualized

**Value:** Medium

**Page(s):** `site/src/content/docs/enforcement.md` (## The Activation Contract), `site/src/content/docs/guides/troubleshooting.md` (Repo Activation section), `site/src/content/docs/codearbiter-directory.md` (CONTEXT.md section)

## What to depict

The same three-state logic is explained in prose three separate times across three
pages: no `CONTEXT.md` or no frontmatter → dormant (nothing loads, nothing blocks);
frontmatter opens but never closes → malformed (surfaced as an error, not silently
disabled); frontmatter closed with `arbiter: enabled` → active. This is a small, clean
state machine that keeps getting re-explained in words because there's no shared visual
to point to. A single small state diagram (three states, the transitions between them)
referenced from all three pages would replace three redundant prose explanations with
one diagram plus a link.

## Recommended form

Small state diagram (three nodes: Dormant, Malformed, Enabled; labeled transitions).
Mermaid is a good fit here specifically — the content is a genuine state machine, low
visual complexity, and doesn't need the bespoke illustration treatment of the other
`public/diagrams/*.svg` assets. This is also the one candidate in this audit where an
inline mermaid state diagram (rendered natively, no image asset) is arguably the better
tool than a static SVG, since it's simple enough not to need hand-tuned layout.

## GPT image vs. hand-drawn

Neither — mermaid (text-based, versionable, trivially reviewed in a PR diff) is the
right tool for a three-node state machine. Do not spend an image asset (GPT-generated or
hand-drawn SVG) on something this simple; that would be over-investment for the content.
