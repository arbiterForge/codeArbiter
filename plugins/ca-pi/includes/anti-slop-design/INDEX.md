# anti-slop-design — bundle router (surface scan)

A lazy-loaded design reference for any codeArbiter producer that emits a human-facing,
formatted deliverable. Load this router first, then pull only the leaves the medium needs.
Never bulk-read the whole bundle: a website task pulls the web leaf and never sees slide design.

**Scope of authority:** generated, user-facing artifacts only (UI, PR descriptions, CHANGELOG,
and any report/slide/chart a producer is told to render). This bundle does NOT govern codeArbiter's
own internal framework docs (`ORCHESTRATOR.md`, the `INDEX.md` files, skill/agent bodies), whose
house style is set elsewhere.

## How to use the bundle

1. Establish the **Design Read** (see `core.md` §1): one line naming medium, audience, register,
   aesthetic family. The **medium** picks your row in the load map below.
2. Always load `core.md` (the decision layer: philosophy, dials, universal laws, universal tells,
   the core pre-flight check).
3. Load **exactly** the leaves your medium's row lists. The map is mandatory and medium-driven, not a
   judgment call — two agents on the same artifact must load the same leaves, so the review is
   reproducible. Do not bulk-read leaves your row does not name.
4. Before delivering, run the core pre-flight plus the loaded medium leaf's pre-flight slice.

## Load map

Match your medium to one row and load every leaf it names (after `core.md`).

| Medium | Load (after `core.md`) |
|---|---|
| Web / UI / landing / component / portfolio | `typography` + `color` + `layout` + `images` + `medium-web` |
| Report / memo / whitepaper / resume | `typography` + `images` + `medium-documents` |
| PR description / CHANGELOG (Markdown) | `medium-documents` (§7.A.1) — copy-laws focus, no craft leaves |
| Dashboard / chart / data figure / technical review | `typography` + `color` + `layout` + `medium-dataviz` |
| Slide deck / presentation | `typography` + `color` + `layout` + `images` + `medium-slides` |
| CLI / terminal output | `medium-cli` |
| Diagram (architecture / flow / sequence / entity) | `color` + `layout` + `medium-diagram` |
| Table / spec sheet (standalone) | `medium-documents` (§7.E) |

**Not yet covered** (no dedicated leaf — apply `core` laws and the nearest medium leaf, and flag the
gap): HTML email, forms / input UI beyond `medium-web`, notifications / toasts, and social / OG cards.

## Leaves

| Leaf | Holds |
|---|---|
| [core](core.md) | Why slop happens, the Design Read, the four Dials, universal anti-slop laws, universal tells, the core pre-flight. **Always loaded.** |
| [typography](typography.md) | Body and display type, hierarchy, measure, italic descenders. Medium-aware. |
| [color](color.md) | Palette defaults to avoid, accent discipline, contrast and accessibility. |
| [layout](layout.md) | First-impression law, grid and rhythm, anti-center bias, cards and elevation. |
| [images](images.md) | Real images first, logos, last-resort placeholders. |
| [medium-documents](medium-documents.md) | Reports, memos, whitepapers, resumes, PR/CHANGELOG prose, tables, spec sheets. Doc pre-flight slice. |
| [medium-dataviz](medium-dataviz.md) | Dashboards, charts, technical-review figures. Chart pre-flight slice. |
| [medium-slides](medium-slides.md) | Presentations and slide decks. Slide pre-flight slice. |
| [medium-web](medium-web.md) | Web and interactive interfaces. Web pre-flight slice. |
| [medium-cli](medium-cli.md) | Terminal / CLI output: status, reports, logs, TUI. CLI pre-flight slice. |
| [medium-diagram](medium-diagram.md) | Architecture / flow / sequence / entity diagrams. Diagram pre-flight slice. |
