# anti-slop-design · medium: data visualization

Load for dashboards, charts, and technical-review figures. Pair with `core`; add `typography`, `color`,
and `layout` (axis labels, titles, and the annotated-insight sentence are type choices).

The governing principle is **maximize the share of ink that carries information** (Tufte's data-ink
ratio). Slop in charts is decoration mistaken for design.

## 7.B Data visualization

- **Remove chrome:** no 3D, no drop shadows on bars, no gradient fills on series, no heavy gridlines,
  no chartjunk. Light or absent gridlines; let the data shapes carry the figure.
- **Right chart for the question:** bar for category comparison, line for trend over time, scatter for
  correlation, small-multiples for many series. **Avoid pie charts for more than two or three slices**
  (humans read angle poorly). Avoid dual-axis charts that imply false correlation.
- **Honest axes:** bar charts start at zero. Do not truncate an axis to exaggerate a difference. If you
  must zoom a line chart, say so.
- **Direct labeling** beats a legend when it fits; the reader should not bounce between a key and the
  data.
- **Color encodes meaning:** sequential scale for ordered magnitude, diverging for a meaningful
  midpoint, categorical for unordered groups, capped at roughly six hues. Colorblind-safe palettes.
  Color is not decoration here.
- **Sort by value**, not alphabetically, unless the category order is itself meaningful.
- **Annotate the insight.** A good figure tells the reader what to notice. One sentence of takeaway near
  the relevant mark.
- **Data integrity** (`core` 3.D) is non-negotiable in a technical review. A fabricated benchmark in a
  CTO-facing document is a fireable mistake, not a styling choice.

## Tells (data visualization)

- Pie charts with many slices; 3D charts; gradient-filled bars; chartjunk.
- Truncated axes that exaggerate a difference; dual-axis false correlation.
- A legend where direct labels would fit.
- Alphabetical sort where value-sort carries the insight.
- A figure with no annotated takeaway.

## Pre-flight slice (data visualization)

- [ ] Right chart for the question; no pie-with-many-slices, no 3D, no chartjunk.
- [ ] Axes honest (bars from zero, no deceptive truncation).
- [ ] Color encodes meaning; colorblind-safe; direct labels where they fit.
- [ ] The insight is annotated, not left for the reader to hunt.
- [ ] Every figure's data is real and sourced (integrity is correctness here).
