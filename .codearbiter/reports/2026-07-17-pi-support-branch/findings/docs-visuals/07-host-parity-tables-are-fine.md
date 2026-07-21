# 07 — Host-parity/compatibility matrices: tables already work, no image needed

**Value:** Low (documenting a non-opportunity, to close off an obvious candidate)

**Page(s):** `site/src/content/docs/getting-started/compatibility.md` (Requirements Matrix), `site/src/content/docs/getting-started/claude-code-and-codex.md` (Intentional host differences table, Verified live table)

## Assessment

These are exactly the "comparison content" the task brief flagged as a candidate for a
styled table/graphic — but on inspection, the existing Markdown tables already do the
job well: two or three columns, short cell contents, scannable, and they render cleanly
in Starlight's default table styling (which the site doesn't override in a way that
looks broken). Converting these to a graphic would mean either (a) a static image that
goes stale the moment a row changes — bad, since this content changes with every
Codex/Claude Code version bump (the page literally carries a dated "Verified live on
2026-07-11" claim) — or (b) reimplementing an interactive comparison widget, which is
disproportionate engineering for the comprehension gain.

## Recommendation

No image or diagram here. If anything, a light CSS pass (zebra striping, a colored
Yes/No/Partial cell treatment) would out-perform an image, since it keeps the content as
live, editable Markdown. Not filing this as a build task — flagging it so it isn't
independently proposed as a GPT-image opportunity later, since tabular comparison data
is a poor fit for a generated image regardless of style.

## GPT image vs. hand-drawn

Neither. This is the clearest "do not spend an image on this" case in the audit.
