# Documentation design system

This is the contract for codeArbiter's public documentation. It exists so the landing page,
hand-authored guidance, and generated reference feel like one product without turning every page
into a custom layout.

## Product principles

1. **Proof before promise.** A claim about enforcement is paired with a mechanism, transcript,
   dated verification record, or source link.
2. **One page, one reader outcome.** A reader should know why the page matters, how to act on it,
   what success looks like, and where to go next.
3. **Source-visible reference.** Generated pages add reader orientation but retain the exact shipped
   source in a collapsed block. Curated prose never replaces the implementation contract.
4. **Local-first delivery.** Fonts and production assets ship with the static build. The site makes
   no runtime request to a font or analytics service.
5. **Quiet confidence.** Gold identifies decisions, gates, and primary actions. It is not a general
   highlight color. Motion explains sequence and is removed under `prefers-reduced-motion`.

## SMARTS decisions

### Landing shell

| Option | Scalable | Maintainable | Available | Reliable | Testable | Securable |
|---|---|---|---|---|---|---|
| Keep the home page inside the documentation sidebar | Adequate | Strong | Strong | Strong | Strong | Strong |
| Use a full-width Starlight splash and keep the docs shell for inner pages | Strong | Strong | Strong | Strong | Strong | Strong |
| Build a separate marketing application | Strong | Weak | Adequate | Weak | Weak | Adequate |

**Decision:** use Starlight's splash shell. It creates a first-class product entrance while keeping
one build, one navigation system, and one link/search index.

### Typography

| Option | Scalable | Maintainable | Available | Reliable | Testable | Securable |
|---|---|---|---|---|---|---|
| System fonts only | Adequate | Strong | Strong | Strong | Strong | Strong |
| Vendor reviewed variable-font subsets with their licenses | Strong | Strong | Strong | Strong | Strong | Strong |
| Runtime Google Fonts request | Adequate | Adequate | Weak | Weak | Adequate | Weak |

**Decision:** bundle the Latin subsets of Manrope Variable and JetBrains Mono Variable as static
assets, with their complete OFL-1.1 license texts beside them. They add no package or production
network dependency and give product and technical surfaces distinct voices.

### Reference orientation

| Option | Scalable | Maintainable | Available | Reliable | Testable | Securable |
|---|---|---|---|---|---|---|
| Hand-edit generated pages | Weak | Weak | Strong | Weak | Weak | Adequate |
| Keep source embeds only | Adequate | Strong | Strong | Strong | Strong | Strong |
| Add collection-specific orientation in the generator and keep source embeds | Strong | Strong | Strong | Strong | Strong | Strong |

**Decision:** commands state how to invoke them in Claude Code and Codex; skills state that the
orchestrator routes to them; agents state that an owning skill dispatches them. The generator owns
that distinction across the full collection.

## Tokens and primitives

Shared tokens and primitives live in `src/styles/design-system.css`.

- **Typography:** `--ca-font-sans`, `--ca-font-mono`, and the `--ca-text-*` scale.
- **Spacing:** `--ca-space-1` through `--ca-space-9`.
- **Surfaces:** `--ca-bg`, `--ca-bg-raised`, `--ca-bg-panel`, `--ca-line`.
- **Meaning:** `--ca-brand` for gates/actions, `--ca-positive` for verified state,
  `--ca-danger` for blocks, and `--ca-preview` for Feature Forge status.
- **Components:** `.ca-button`, `.ca-panel`, `.ca-pill`, `.ca-eyebrow`, and
  `.ca-reference-lead`.

Page-specific selectors belong in `src/styles/landing.css` or a named component. Do not add
one-off colors, font stacks, or spacing values to content files.

## Page completeness contract

### Getting Started

Answer: what must be installed, what command to run, what the reader should observe, how to verify
enforcement, and where host behavior differs.

### Guides

State the outcome and prerequisites, give an ordered procedure, show observable success, cover the
likely block or recovery path, and link the exact command reference.

### Concepts

Explain the problem, the mental model, one concrete example, how the concept changes real use, its
limits, and the next practical page. A definition alone is incomplete.

### Generated reference

- **Command:** invocation, purpose, example, gates, alternatives, exact source.
- **Skill:** routing context, phases or behavior, exits, gates, related commands, exact source.
- **Agent:** dispatch context, tool/model boundary, output or findings contract, related routes,
  exact source.
- **Hook gate:** tag, condition, effect, exact emitted message, source location.

### Trust and lifecycle

Compatibility, enforcement, privacy/network behavior, uninstall, troubleshooting, changelog, and
license must be findable without reading the landing page top to bottom.

## Required verification

Before documentation changes ship:

1. Generate the reference and build the static site.
2. Run unit tests, typecheck, and the post-build link audit.
3. Crawl every sitemap route for HTTP success, one H1, a description, and image alt text.
4. Inspect the landing, one page from each hand-authored category, and one page from each generated
   collection at desktop and mobile widths.
5. Test keyboard focus, search, reduced motion, and horizontal overflow.

## Human-operable guides and product demonstrations

A guide is complete when a reader can identify the inputs, permission and repository state needed
to begin; the actor and surface for each important action; the resulting artifacts; the facts to
review; observable completion; safe recovery; and the next useful step. This is an editorial and
reader-task contract, not a requirement to repeat eight headings in every reference entry.

Keep project-level greenfield planning distinct from typed feature/sprint pairs, preserved legacy
Markdown pairs and inline small-lane work. Use the owning implementation for exact names and
boundaries. Compatibility aliases remain addressable; primary navigation follows reader journeys.

The product tour uses one scenario and explicitly distinguishes native-generated draft artifacts,
actual local fixture test results, illustrative conversations, and installed-host evidence. No tour
control grants authority or mutates project state. Real artifacts are immutable capture outputs;
curated projections never replace native validation or make a digest an authentication claim.

Demonstrations must have a static reading path, keyboard-operable controls, no compulsory autoplay,
no remote font or analytics requests, reduced-motion and forced-colors support, and constrained
horizontal scrolling for code. Reuse the site's tokens while preserving product-specific exceptions,
including the statusline's violet default. The six header destinations and sidebar order share
`site/scripts/journey-navigation.ts`; generated reference classification still owns reference groups.

Before merging changes to demonstrations, run the fixture integrity tests, actual Python example
checks, the existing site checks and the production-browser tests. Inspect desktop and narrow
screens. Browser accessibility automation is not screen-reader or real-user certification. The
human acceptance task is to perform the guide without the author supplying an omitted step.


## Peer cards and reader-first workflow maps

Opt a component's peer list or grid into `data-ca-layout="peers"` when its `gap`
owns sibling spacing. The shared rule removes direct-child block margins only.
Do not apply Markdown's adjacent-sibling spacing as well: it offsets later cards
and reduces their stretched border-box height while the first fills the row.
Keep equal column widths and aligned card boundaries within a row. In a single
column, different amounts of content may produce different heights. Do not hide
content, truncate warnings, or impose fixed heights merely to make cards equal.
Intentional split layouts and prose spacing are not peer-card defects.

Workflow guides introduce what readers receive, what they must inspect or decide,
and what evidence permits continuation before exposing implementation routing.
Use `ReaderJourney` for a static, ordered four-step map; label its lane and host
boundary. It is an explanatory sequence, never live status, an execution trace,
or evidence that any step has completed. Keep the detailed implementation diagram
in a native disclosure and retain the full operating procedure below it.

Verify peer geometry from computed browser styles at desktop, tablet and narrow
widths, including expanded Academy lists and every selectable exhibit state.
Check reading order, keyboard disclosure, no-script access, forced colors, print,
and non-root links. Inspect actual captures, not only a green overflow test.


## Task-oriented guide discovery

The guide directory reads titles, descriptions, outcomes, levels and estimates from the same
content collection that renders each guide. `scripts/guide-directory.ts` owns only task grouping
and reading order. Add each new guide there; missing, duplicate and unclassified routes fail the
build rather than silently disappearing. Retain section anchors when reorganizing the landing page.

Filtering is a progressive enhancement over the complete static directory. It makes no request
and persists no query or selection. Hidden results must leave keyboard navigation as well as the
visual layout; clearing restores the full list and input focus. Printing restores all guides, even
when the screen is filtered. Keep main site search distinct from this metadata-only finder.

Reuse peer spacing, tokens and content-sized cards. Verify combined filters, empty results,
client-navigation reattachment, no JavaScript, keyboard, print and non-root paths against rendered
output. Card labels and estimates are guidance, not release or compatibility claims.


## Readable tables in guides

Simple Markdown/MDX guide tables are enhanced at build time by `rehype-table-shell.ts`.
Their presentation lives in `src/styles/guide-tables.css`, registered with the site styles.
On content columns up to 40rem, each row stacks its labelled fields so the complete instruction
and every host entry are visible without lateral scrolling. The original cell nodes exist once.
Column headers retain native associations and explicit table roles; additional visible labels are
hidden from assistive technology and search indexing. No JavaScript or saved preference is needed.

Keep the existing scroll presentation for Academy, reference, complex headers, spans, nested tables
and authored header associations. Do not flatten those relationships by guessing at labels.
Desktop guide tables retain columns when space permits. Code/path values in stacked rows wrap
without changing their copied text. Do not shrink fonts, clip values or omit a host to make them fit.

Page-level overflow checks cannot establish cell readability. Test each rendered text range against
its cell and viewport, compare desktop/mobile content, and inspect all table rows. Verify retained
semantics, no-script reading, text enlargement, forced colors, print and base-prefixed links.
Screenshots are reading evidence, not full screen-reader or cross-browser certification.


## Concepts and execution-order maps

`CONCEPTS-OVERHAUL.md` owns the approved program and its remaining slices. Concepts explain
why a mechanism exists, its place in actual work, the record it owns, a concrete example and
common misinterpretations. Page length is not evidence that a reader can use the model.

The feature execution map is an editorial projection under `scripts/execution-maps/`, not a
runtime router, new tool or approval protocol. The model pins its reviewed source and gives
nodes and handoffs explicit owners. Source-excerpt checks catch drift in those anchors; they
are not automated proof of complete runtime equivalence. Re-review changed behavior before
updating the pin or its excerpts. Do not make the image match new source by weakening a test.

Commands, skills and agents are role rows, not sequential categories. Draw execution across
those rows in order. Preserve caller returns, task repetition, applicable reviewers, human
acknowledgements and the actual final outcome. In particular, the finishing skill reuses the
PR procedure in place; drawing a fresh `/pr` invocation would misrepresent the contract.

`ExecutionMap.astro` uses the same data for chapter diagrams and an equivalent ordered HTML
reading path. Chapter selection does not run product actions, persist state or grant authority.
All chapters remain readable without JavaScript and in print. On narrow content columns,
use full-sized reading steps instead of shrinking the desktop graphic until it is illegible.
Optional review roles are visibly conditional, and detailed returns remain inspectable.

The Concepts navigator and sidebar share grouping and order. Curated reference text links to
explanations; generated pages remain generator-owned. Existing diagram addresses remain stable.
Check actual rendered text bounds, all selections, source links, desktop label sizes, keyboard,
no-script reading, text enlargement, forced colors and exact-candidate screenshots. Do not
confuse a passing diagram check with installed-host, runtime, release or human approval evidence.


## Concepts decision and evidence exhibits

C02 uses a shared, source-bound teaching record rather than a second authority model. SMARTS
comparisons label hypothetical constraints, keep both options visible for each lens and preserve
verdict/strength distinctions. Decision handoffs compare caller authority, not a universal lane.
The periodic checkpoint map retains its command/skill/agent result sequence and its real report
endpoint; it is not the typed acceptance checkpoint.

Evidence-view controls only change reading visibility. Use separate fields for supported claim,
unproved claim and next inspection, never an Approve/Verify button on illustrative data. Reconnect
controls after client navigation; make no request or persistent write. Without JavaScript and in
print, retain all cases. Pair foreground/background tokens for forced colors and test every state,
not only the first card. Preserve full-text content and labels under enlarged text and narrow
widths. Existing guide-table and peer-spacing rules still apply.


## Recorded context observations

`ContextExplorer` presents a checked capture, not an emulator or live governance console.
The capture producer runs real read/provenance helpers and Git content hashing only in a
disposable repository. Retain exact inputs, source identity and hashes, the emitted text,
observed deduplication and hash-call scope. A helper observation is not host activation,
end-to-end execution, authority or verification of the reader's project.

The prose, optional static diagrams and actual observations must distinguish all matching
candidates from the bounded result. Never display first-match routing when the owning helper
composes tiers. Distinguish the estimated pointer budget from a model tokenizer or complete
workflow cost. Do not convert silent, stale, absent or unverifiable results into an all-clear.

All observations are statically readable; selection hides only reading sections and must not
persist state, change the URL or run a tool. Print restores every case. Serve the machine-readable
capture from the same JSON import rather than maintaining an independent copy. Historical
research and hardening notes retain attribution without asserting current efficacy.

Test each state, actual text bounds, enlarged text, normal/forced colors, keyboard focus,
no-script and print paths, navigation/back and base-prefixed links. Inspect real rendered
captures after the final build. Keep arrowheads in explicit user-space units with their tips
centred on the path endpoint; their shafts must approach straight without crossing the head.


## Workflow-specific execution maps

The six C04 route definitions in `scripts/execution-maps/workflows.ts` own their
ordered role nodes, handoffs, conditional paths, important results and actual endpoint.
`WorkflowMap` supplies the same model to the existing `ExecutionMap` component;
`renderExecutionSvg` uses it for retained public diagram URLs. A guide's four-step
reader orientation is not replaced by the implementation map. Keep the map behind
a native disclosure, with a full ordered reading path for narrow screens and no JavaScript.

Chapter numbering is cumulative, not a hard-coded four-step offset. An empty role
row can be meaningful: dependency review does not acquire an invented intervening
skill just to fill the picture. Greenfield and brownfield are independent routes,
not phases joined by a connector. Command labels also identify owning procedures;
they do not tell the user to repeatedly invoke the same command at each node.

The source record must identify simplifications, current-source versus installed
capability, approval boundaries, review returns, publication prerequisites and
real alternate exits. No diagram endpoint may imply release or PR creation where
the owning route ends in context, a decision record or a dependency change.
Keep known source contradictions separate from presentation repairs.

Before publishing map changes, validate canonical excerpts, source identities,
endpoints, continuous numbering, unchanged public URLs, all map selections and
base-prefixed links. Inspect actual desktop/mobile captures, arrow endpoints,
text bounds, expanded disclosures, no-script reading, doubled text, forced colors,
print and useful full-text search results. Source excerpts and successful rendering
are not proof of an installed workflow or a universal accessibility certification.
