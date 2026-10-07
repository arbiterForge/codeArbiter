# Workflow atlas ownership and maintenance

The native explorer lives on `/concepts/workflow-routes/`. It supplements the
existing Concept Map and six workflow chapters; their URLs, source revisions and
ordinary reading paths remain unchanged. It changes presentation only.

## Inputs and projections

`core/surface/command-routes.json` owns entry identity, visibility and compatibility
submodes. `core/hosts.json` owns each host's spelling and exclusions. Descriptions
come from the owning command frontmatter. A source-catalog entry does not imply
that every installed host can execute every typed workflow.

`site/scripts/execution-maps/model.ts` and `workflows.ts` retain the existing
chapter maps. `atlas.ts` projects their nodes, checks, conditional roles, chapter
boundaries and edges without changing their historical source identities.
`atlas-content.ts` owns the additional context, debug/fix, review/delivery and
Tribunal explanations. Context, state, gate and output nodes are not fake agents.
The complete catalog overview groups entries; groups are not execution phases.
An entry without a dedicated teaching map links to its exact reference procedure.

`atlas-render.ts` emits the static reading path and SVGs from the same model.
`WorkflowAtlas.astro` mounts that reading path in the existing site shell.
The optional client changes visibility, opens native disclosures and follows
explicit links. It does not save progress or authorize any operation.

`generate-atlas.ts`, invoked by `npm run gen`, creates:

- `public/workflow-atlas/<reviewed-commit>/atlas.html`: self-contained offline edition;
- `reading-guide.html`: script-free edition;
- one SVG per view and `sources.json`: the same source bindings as the native page.

These outputs are gitignored. No Python copy of the editorial model is required.
No font file, runtime GitHub request, analytics, iframe or graph-library dependency
is added. The web page uses lazy SVG images instead of embedding every SVG tree.
Offline editions are noindex and excluded from Pagefind indexing. Repeated
reference/catalog text and existing maps are excluded from duplicate indexing;
the owner page and new explanatory material remain searchable.

## Reviewing source changes

`REVIEWED_AT` identifies the catalog and supplemental review. Existing chapter
sources retain their separate historical revisions. The generator compares full
logical source bytes with reviewed Git blobs, not only short matching excerpts.
A changed owner fails generation with its path. CRLF checkout normalization is
allowed; other content changes require review. Missing history fails explicitly.
Use a checkout containing the reviewed commit, as the existing site CI does.

For an affected owner, inspect the complete change and its dependent routes.
Correct the explanation before intentionally advancing the reviewed revision and
any explicit blob pins. Preserve historical chapter sources and relocation
metadata. Never repin merely to make a test green. Lens count comes from the
actual reviewed lens directory; it is not hand-maintained marketing copy.
These checks detect stale explanations, not semantic correctness or live-host
qualification. No release status or organization-wide canon is established.

## Navigation and accessibility

Entry links are `#atlas-<entry>`. View links are `#atlas-view-<view>` and node links
are `#atlas-node-<view>-<node>`. Existing chapter fragments are not intercepted.
Chooser changes do not write history; explicit native links do. Custom-element
connection/disconnection owns event listeners during Astro client navigation.
All text remains in static HTML. At narrow widths read the text first; the optional
full-size vector region scrolls internally. Print includes the complete reading
path. Diagram controls never represent executed or approved steps.

## Verification and rollback

Run in `site/`:

```sh
npm test
npm run typecheck
npm run build
npm run link-audit
npm run test:browser -- workflow-atlas.spec.ts
```

Inspect the built owner page, command-reference links, historical chapter links,
all entry selections, actual host exclusions, downloads, no-script and print
reading, browser Back/reload, client navigation, enlarged text, forced colors and
reduced motion. Check rendered SVG labels as well as graph references. Run the
existing full browser suite before merging because source indexing and shared
navigation can be affected. The new browser tests run against the real built site,
not a substituted fixture. Existing CI jobs are reused without relaxed gates.

Implementation-session local evidence is limited to TypeScript syntax, strict
checking of the pure model/render/client modules, model assertions and Chromium
in-memory component checks. Full repository generation, Astro build and browser
qualification must be established by the PR jobs or a connected development
checkout; a local fixture is not a production-site pass.

After merge, compare the deployed owner page and downloads with the tested build.
Opening this PR does not deploy it. Rollback is an ordinary revert of this site
integration; existing chapters, command procedures and project state are unchanged.
