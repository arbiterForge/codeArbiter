# anti-slop-design · medium: documents

Load for reports, memos, whitepapers, resumes, PR descriptions, CHANGELOG sections, tables, and spec
sheets. For a laid-out document pair with `core` + `typography` + `images`. For PR/CHANGELOG Markdown
prose (§7.A.1), `core` + this leaf is enough — those are copy-law deliverables, not composed pages.

## 7.A Documents (reports, memos, whitepapers, resumes)

- **Hierarchy through type and space**, not heavy rules and shaded boxes on everything. A horizontal
  hairline under a section title beats a filled banner.
- **Serif or humanist-sans body** for sustained reading (see `typography` 4.A). Body size 10-12pt for
  print, 16-18px for screen.
- **No clip art, no rainbow section colors, no decorative icons** scattered for "visual interest."

### Resume specifics (the dominant tells in this medium)

- No skill-proficiency bars ("Python: 85%"). They are meaningless, unverifiable, and read as template.
  List skills plainly or, better, demonstrate them through quantified accomplishments.
- Reverse-chronological, consistent date format throughout, one page unless senior or academic.
- Quantify every bullet that can be quantified, with real numbers (`core` 3.D applies hard here).
  "Reduced deploy time 40%" beats "improved deployment efficiency."
- No photo unless the regional hiring norm expects one. No two-column layout if an ATS will parse it,
  unless you know the target system handles it.
- Active voice, concrete verbs, no filler (`core` 3.B). Cut the "Objective" statement; cut "References
  available on request."

## 7.A.1 PR descriptions and CHANGELOG (Markdown render target)

These are documents rendered as Markdown on a platform (GitHub, a release page), not laid-out pages,
so layout/typography/color do not apply. What matters:

- **Write for the render, not the source.** Use real Markdown structure (headings, lists, fenced code)
  that renders cleanly; do not hand-align columns that the renderer will collapse.
- **The copy laws carry the weight.** core §3.A (no prose separator dashes) and §3.B (no marketing
  filler) are the whole game here. A PR body says what changed, why, and how it was verified, in plain
  declarative prose.
- **Lead with the point.** First line / summary states the change; details follow. A reviewer reads the
  first two lines and the test plan.
- **Link, do not paste.** Reference issues, ADRs, and commits by link/id; do not inline large blobs.
- **CHANGELOG:** keep entries terse, grouped (Added / Fixed / Performance), user-facing, and in the
  project's existing format. Real version numbers only (core 3.D); no invented metrics.

## 7.E Tables and spec sheets

Long structured lists fail the same way everywhere: a default `<ul>` or a row-per-line table with a
hairline under each row.

- **Minimal rules.** Horizontal hairlines between logical groups, not under every row. No vertical
  lines unless the data demands them.
- **Align numbers.** Right-align or decimal-align numeric columns.
- **No zebra striping** unless the table is genuinely dense.
- For more than five items, reach for a different component: grouped 2-3 clusters with sparse dividers,
  a card-per-item grid, tabs or an accordion if categorizable, or a featured-few-plus-collapsed-rest
  disclosure. The list itself is rarely the answer to a long list.

## Tells (documents)

- Skill-proficiency bars on resumes.
- Hairline under every table row; row-per-line spec sheets.
- Office-default body face (Calibri, Times New Roman) chosen by reflex.
- Decorative icons / rainbow section colors scattered for "interest."
- Filled section banners where a hairline would do.

## Pre-flight slice (documents)

- [ ] Body face deliberate (serif/humanist for long reading), not an Office default by reflex.
- [ ] Hierarchy from type and space, not boxes and rules on everything.
- [ ] Tables: minimal rules, aligned numbers, grouped not row-striped.
- [ ] Resume: no skill bars, quantified bullets with real numbers, consistent dates, ATS-safe if
  needed.
