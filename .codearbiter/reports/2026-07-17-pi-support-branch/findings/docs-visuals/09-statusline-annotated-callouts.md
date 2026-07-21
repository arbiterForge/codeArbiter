# 09 — Statusline screenshot exists but isn't annotated to its own reference table

**Value:** Low-Medium

**Page(s):** `site/src/content/docs/guides/the-statusline.md`

## What to depict

`the-statusline.md` already has a real, correct screenshot (`statusline.png`, a
genuine capture from the live renderer with mock values — good practice, not
AI-generated) directly under the intro. Immediately below it, the page has two full
tables (Usage Segments: folder/git/model/rate limits/context/tokens/cost/burn/
subagents; Arbiter Segments: stage/tasks/questions/overrides) that describe, in words,
what each visual segment in that same screenshot shows. The reader has to mentally map
each table row back to a region of the image with no visual aid.

An annotated version of the same screenshot — thin leader lines or numbered callouts
from each segment in the image to its row/label — would let the two tables double as a
legend instead of a disconnected wall of text below an unlabeled picture. This is a
comprehension win but modest: the page is already usable as-is (it's a guide page, not
critical-path), so it's ranked below the higher-value gaps in this audit.

## Recommended form

Take the existing `statusline.png` (or its live source capture) and produce an annotated
overlay version — numbered/lettered callout markers on the image tied to the two
tables below it, similar to how software documentation typically annotates a UI
screenshot.

## GPT image vs. hand-drawn

Neither an illustration nor GPT-generated — this must stay a real screenshot (already
is) with a precise SVG/CSS annotation overlay added on top, hand-built to match the
exact pixel positions of the real render. GPT image generation is explicitly wrong here:
it would either regenerate the statusline itself (introducing inaccuracy in a UI that
must match the actual renderer exactly) or produce a decorative annotation style that
clashes with the terminal-monospace aesthetic the real capture already has.
