# 02 — Three-host build-time generation from core/surface/ is asserted but not shown

**Value:** High

**Page(s):** `site/src/content/docs/getting-started/claude-code-and-codex.md` (the "Verified continuously" bullet list); relevant background also in `site/src/content/docs/codearbiter-directory.md` and repo docs (`core/surface/`, `plugins/ca/`, `plugins/ca-codex/`).

## What to depict

The page claims "deterministic generation of both host surfaces from `core/surface/`"
and "byte-identical vendoring of the shared Python hook core into both plugins" as a
single bullet in a list of seven other claims. This is exactly the kind of
inherently-spatial build/data-flow relationship prose struggles with: one source
(`core/surface/`) fans out at build time into two generated, host-specific plugin
payloads (`ca` for Claude Code, `ca-codex` for Codex), while a shared hook core is
vendored byte-identically into both. Readers evaluating "is this really one shared
system or two forked copies" have to trust a bullet point instead of seeing the
generation boundary.

This is a good candidate for a new diagram because it is currently the least-visualized
of the "inherently spatial" flows named in this audit — nothing in `public/diagrams/`
covers source → generator → dual-host output.

## Recommended form

Technical build/data-flow diagram: one box (`core/surface/` + shared hook core) with two
arrows labeled "generate" fanning out to two boxes (`ca` plugin, `ca-codex` plugin),
each annotated with what's identical (hook core, guard verdicts) vs. host-specific
(command spelling, adapter).

## GPT image vs. hand-drawn

Hand-drawn SVG matching the existing diagram set's flat style (see `four-tier-map.svg`
for a similar "one source, multiple consumers" pattern already in the docs). Not a GPT
image — this is a factual architecture claim; an AI-generated illustration cannot be
trusted to render the fan-out relationship correctly, and doing so undermines the page's
own "evidence, not marketing claims" tone.
