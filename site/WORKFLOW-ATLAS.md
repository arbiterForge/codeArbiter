# Workflow atlas ownership and maintenance

The atlas on `/concepts/workflow-routes/` is the original standalone spatial atlas,
ported into the documentation shell. It is not a command directory, accordion
replacement, or automatic three-column redraw of similar information.

## Preserve the original experience

The nine maps, 213 nodes and 178 routed relationships come from the October 7
standalone atlas at source `9496cff6332fe0b97195b7ebe67b73f62f30e5b3`.
`atlas-data/provenance.json` records the recovered source and per-view geometry
fingerprints. The recovered text representation contains the complete embedded
model and SVGs; it is not represented as an acquired original archive.

`atlas-data/` keeps one readable JSON model per original view plus its command and
source catalog. Node boxes, text breaks, panels, labels and routed polylines are
retained. `atlas-render.ts` changes theme and integration markup, not the spatial
composition. No arrow is replaced with a numbered continuation or prose list.
Complete text handoffs remain an additional reading path, not a substitute.

The native viewer retains map tabs, independent entry highlighting, the side
inspector, node selection, Fit width, Fit all, Read size, zoom, blank-space panning,
source links and full SVG export. Selecting a route does not remove unrelated
nodes or replace the map. Switching maps retains the route. The inspector shows
the original route steps, context, outputs, gates, related entries and evidence.

The page keeps the website header and left navigation. Only this wide map page
omits the usual right-hand contents rail; the atlas inspector needs that space.
The existing result directory, Concept Map, six chapter maps and their published
addresses/source revisions are unchanged. Those chapter maps keep their existing
role-row schema and renderer. They are not copied into a replacement atlas model.

## Owners and source checks

`core/surface/command-routes.json` owns identity, visibility and compatibility
submodes. `core/hosts.json` owns host spelling and exclusions. `atlas-command.ts`
retains the checked SKILL_ENTRY wrapper resolution added during the earlier repair.
The restored inspector is supplemented with those host forms and exact procedures,
not replaced with generated command summaries.

`atlas.ts` compares the full logical product-source files with the reviewed Git
objects. CRLF normalization is allowed; source drift and symlinked paths refuse.
A changed owner names the affected path. Missing history is not replaced with main.
The lens directory is compared with its reviewed inventory. Source-linked workflow
explanations are not runtime, released-artifact or installed-host certification.
Historical site-design references in the source ledger are not product claims and
are not frozen as a condition of this integration changing the site itself.

For an intentional refresh, inspect the changed owner, update its affected route
and check the diagram. Update only the necessary geometry and text wrapping.
Advance the reviewed binding and geometry fingerprint after that review, not to
silence a failing test. Unrelated source commits do not require repinning all maps.

## Theme and exports

`src/styles/design-system.css` remains the only product token owner.
`atlas-theme.ts` resolves those values for SVG and standalone exports; it neither
copies font bytes nor maintains another palette. Native text uses the site's
existing local fonts. Offline documents use the same font stack with its system
fallbacks; no remote fonts or analytics are introduced.

`WorkflowAtlas.astro` mounts the same renderer directly in the existing page.
`generate-atlas.ts`, already invoked by `npm run gen`, emits the self-contained
viewer, script-free reading guide, nine SVGs and source ledger under
`public/workflow-atlas/<reviewed-commit>/`. Outputs are gitignored. Download links
inside an offline package are relative, not links to an unmerged public artifact.

There is one active SVG in the native page. Other diagrams and inspector bodies
are inert templates. This intentionally preserves instant offline view switching
and the original direct node interaction, rather than using noninteractive images.
Templates and duplicate canvas/inspector material do not enter Pagefind's index;
the static text reading path remains searchable. Offline documents are noindex.

## Navigation and lifecycle

Entry addresses remain `#atlas-<entry>`. Explicit map links use
`#atlas-view-<view>~<entry>` when an entry is highlighted; node addresses use
`#atlas-node-<view>-<node>~<entry>` to preserve that independent highlight on reload.
The entry suffix is optional. Previously shared node-only addresses retain their
no-highlight meaning. Atlas-prefixed view aliases remain supported. Bare fragments
such as `#release` and `#context-layers` belong to the containing page and must not
activate the atlas. Text-map addresses use `#atlas-text-<view>` and reveal the
complete reading path. Chooser controls do not write history or storage; explicit
native links do.

Permalink generation encodes identity components and assigns only the anchor's
`hash`, never DOM-derived text to its full `href` or an HTML sink. Because assigning
`hash` serializes an absolute URL, the controller also recognizes its own permalink
when origin, pathname and query still match the document. Other absolute links
retain their native destination. Resolve node targets by exact identity, not by
interpolating a fragment into a CSS selector.

Keep the Astro navigation repair: same-page routing can update history without
hashchange. Read the clicked destination after routing, retain popstate and
page-load handling, and disconnect all listeners/observers on removal. Modified,
canceled, download and new-tab actions must not become atlas selection commands.
Queued focus work belongs to its reading selection; a newer selection supersedes
it. Coalesce resize work and recheck the current fit mode before applying it so
queued automatic fitting cannot undo a later zoom or Read size action.

Cache inert inspector templates once per connection. Reconnecting without an
atlas-owned address resets both the selector and highlight, not just one of them.
Removal cancels pending frames, releases drag capture, closes the source dialog,
and revokes pending download URLs and timers. SVG export serializes the untouched
template vector with `XMLSerializer`, not the highlighted/zoomed live canvas.

Keyboard node activation, zoom shortcuts, native touch scrolling, source-dialog
focus, reduced motion and forced colors remain supported. Narrow screens retain
the actual panning map and move the inspector below it, as in the original viewer.
The Details control moves keyboard focus to that inspector as well as scrolling.
The complete text path is available without JavaScript. Print exposes that full
path and restores the previous selection afterward, including repeated previews.
No control signifies executed work, verification, progress or approval.

## Verification and rollback

Run the existing generator, typecheck, unit, build/link and production-browser
checks. The browser suite must exercise the native page, not only the standalone
export. Inspect actual desktop and mobile captures of the canvas in the site shell.

The regression contract checks the original per-view geometry fingerprints, all
213 boxes, all 178 polyline paths, every entry's highlight membership, real node
inspection, keyboard, drag/zoom, complete clean SVG export, actual Astro round trips,
Back/Forward/reload/repeated fragments, no-script reading, doubled text and repeated
print restoration. Wrapper parsing, source-drift and host-exclusion tests remain.
Do not retain a green accordion test by weakening the original interaction contract.

The quality regressions also cover hostile DOM-source identities at the permalink
boundary, unrelated heading isolation, trace-preserving node links in native and
offline editions, stale navigation/resize callbacks, reconnect synchronization,
and pending export cleanup. Controlled callback fixtures test ordering explicitly;
they supplement, not replace, the real navigation and download tests.

Local in-memory browser rendering can check layout and the controller. It cannot
certify a production Astro route or public deployment. Bind hosted test results and
any downloaded Pages artifact to the actual candidate head. After authorized merge
and deployment, read back the public page and downloads separately.

Rollback is a normal revert of the site integration. No product workflow, package,
authority producer, consumer state or existing chapter model is migrated here.
