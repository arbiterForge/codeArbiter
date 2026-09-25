# C04: workflow propagation and cross-surface review

## Scope and identity

C04 implements the final approved diagram-propagation slice of
`site/CONCEPTS-OVERHAUL.md`. The review branch is
`docs/concepts-workflow-propagation`, stacked over the still-open #859 branch
`docs/concepts-decisions-evidence` at `090773ec6aa98687cd7b207985cb29ebb8f9c8e1`.
Main was `28f14f59f1a5e7231ee21d5f75d161ad1c51939a` at discovery. A new PR is required;
this record does not merge either branch or infer release from source.

All source references below are relative to:
`arbiterForge/codeArbiter@090773ec6aa98687cd7b207985cb29ebb8f9c8e1:`.
The map data carries this full revision and per-relationship owning excerpts.
Tests check those excerpts in both the pinned revision and the candidate source.
This is editorial traceability, not a runtime router, semantic proof or recorded host run.

## Independently traced workflows

| Route | Owning sources | Important relationship and real endpoint |
|---|---|---|
| Sprint | `core/surface/SPRINT.md`; `core/surface/includes/sprint-authority.md`; brainstorming, writing-plans, subagent-driven-development, commit-gate and finishing-a-development-branch skills; `commands/pr.md` | Initial HTML pair has one observed, identity-bound reply and native approval/binding transaction. Sprint enters the task engine directly, not the attended checkpoint coordinator. Task proof, scope acceptance and the commit gate precede Open PR. The finisher reuses the PR procedure without invoking its entry again. Sprint never merges. |
| Dependency | `core/surface/commands/add-dep.md`; `core/surface/agents/dependency-reviewer.md` | Direct command-to-reviewer dispatch returns before explicit confirmation and the paired manifest/lockfile edit. No intermediate skill is invented. The lane does not automatically end in a commit or PR. One-time inspection is a separate bounded path, not silent project adoption. |
| ADR | `core/surface/commands/adr.md`; `core/surface/skills/decision-lifecycle/SKILL.md`; `core/surface/skills/commit-gate/SKILL.md` | Attributed drafting and review precede accepted content. Commit that content before binding its exact source; persist the acceptance event in a subsequent commit. Remaining Proposed is valid. Accepted/Planned is not derived Implemented or Verified. |
| Release | `core/surface/commands/release.md`; `core/surface/skills/release/SKILL.md`; commit-gate and finishing-a-development-branch skills; `commands/pr.md` | Preparation creates an ordinary release PR and stops before tagging. The PR must merge before exact-default-head hosted composition. Only the qualifying publisher creates tags after applicable checks. Publication needs explicit cohort permission. A declared provenance receipt has its own review PR and pending-until-merged closeout. |
| Greenfield initialization | `core/surface/commands/init.md`; `core/surface/skills/decompose/SKILL.md` | Six-layer interview, architecture breakdown, phased build plan and task backlog. All three are reviewed before population and the initialized marker. Project Markdown files remain distinct from feature/sprint HTML pairs. No implementation or PR is implied. |
| Brownfield initialization | `core/surface/commands/init.md`; `core/surface/skills/context-creation/SKILL.md`; `core/surface/agents/scout.md`; map-structure/map-deps roles | Six isolated read-only scouts return evidence to the writer. Resolve or explicitly defer gaps; populate supported context, provenance and index before initialized state. Release-target population is conditional on evidence. Do not manufacture the greenfield planning trio. |

The new models contain 17 chapters and 56 stages across six routes. Their role rows
remain Commands, Skills and Agents; the dependency path intentionally uses no skill
node. Sparse chapters retain continuous numbering. The combined initialization
asset presents alternatives with no connector from one into the other.

## Current-source corrections made in derivative guidance

### C04-01: sprint package review is not two unrelated initial approvals

The existing guide's “arms one artifact at a time” description applied a sequential
feature boundary to the new initial sprint-pair protocol. Current `SPRINT.md` and
`sprint-authority.md` instead require `arm-sprint`, the exact observed reply with
`approve-only` or `delegate-methods`, then `sprint-approve` committing both approvals
and binding in one recoverable transaction. `resume-sprint` replays only a matching
already-observed reply. Ordinary feature and later single-artifact review remain
distinct. Guides now distinguish these cases without asserting installed support.

### C04-02: release is PR-first and hosted, not a local tag followed by permission

The old guide/curated examples omitted the mandatory release-PR stop and presented
local tag composition as an ordinary interactive stage. Current release source
requires that PR to merge first, then a qualifying hosted publisher at the exact
fetched default-branch head. The map and prose retain the clean/evidence checks,
asset qualification, authorized cohort, readback and receipt-reconciliation boundary.
An already authorized protected auto-publish cohort does not require redundant
permission; CI success alone cannot grant it.

Dry run is limited to locally evaluable preflight and derivation. It does not fetch,
run commit-gate or declared build/generation/tests, prepare assets, mutate surfaces,
commit or tag. It is not complete release qualification. Corrected the owning
command/skill curated explanations, not generated reference output.

### C04-03: current host authority differs from the original C02 source snapshot

The independently merged #860 source supports verification/review authority on
Claude Code and Codex, while Pi remains unsupported at that boundary. An old C02
source assertion still demanded the removed Codex-only sentence. The initial C04 candidate gave that unused authority entry a current revision.
The integrated parent subsequently removed the unused entry, and this continuation
preserves its removal. Other historical C02 source links and preserved-heading tests
retain their original revision. Existing
installed-capability and exact-artifact qualifications remain, rather than treating
new source as proof of a released package.

### C04-04: acceptance content and acceptance binding are different commits

The ADR guide now explains the exact source commit required by acceptance binding
and the subsequent event commit. Retained prior heading anchors and illustrative
example boundaries; no in-place accepted-history rewrite, gap-free identity promise,
or automatic Implemented/Verified status is taught.

## Preserved unresolved source conflicts

The two C02 runtime findings are still OPEN: `last-checkpoint` is written as an
override count despite other consumers describing a timestamp/gate result; stale
arbitration-hash handling conflicts with append-only history wording. C04 does not
change their runtime producers, invent records or mark them fixed by documentation.
See `CONCEPTS-C02-SOURCES.md` and `CONCEPTS-C03-SOURCES.md` for their source boundaries.

Project bootstrap sources remain historical September 1 snapshots, including old
versions, Academy source and unresolved release/policy observations. They are not
silently updated or promoted to current truth by this website change.

## Presentation, propagation and accessibility

- Retain `lane-feature.svg`, `lane-sprint.svg`, `lane-add-dep.svg`, `lane-adr.svg`,
  `lane-release.svg` and `lane-opt-in.svg`. Add individual greenfield/brownfield
  assets. Replace bucket-style lane rendering with shared source-bound role rows.
- Keep reader-first four-step guide summaries before implementation details.
  Put complete role maps in native disclosures. All chapters remain present
  without JavaScript; print restores the full path, including nested init choices.
- No new runtime command, dependency or persistent preference. Reading controls
  neither transmit data nor grant authority. Source output and command copy text
  remain complete, with no clipping or compressed mobile diagrams.
- Preserve public guide URLs and all previous ADR/release heading anchors through
  MDX source moves. Update each consumer/test rather than leaving retired paths.
- Add the Workflow Routes concept and source-shared endpoint chooser. Connect
  Concepts to guides and curated references; use Pagefind's actual index to verify
  representative discovery, rather than checking source words alone.
- Preserve the corrected arrowhead geometry, content-sized peer layout, forced
  colors, no-script, keyboard, print and enlarged-text requirements from C01-C03.

## Review-specific CI support

Because #859 was open at discovery, the new review is stacked onto its branch.
Both CI workflows originally filtered PR bases and would otherwise execute no
checks for the stack. Add only the exact `docs/concepts-decisions-evidence` PR base
alongside existing allowed bases. Push triggers, permissions, job definitions,
impact selection, tests and deployment conditions are unchanged. A regression
compares executable workflow lines against the parent revision, allowing only
that PR-base addition. Remove the exact campaign entries after the stack lands.
Do not trigger the deployment workflow manually on this branch.

## Acceptance and remaining evidence

The implementation provides each AC01-AC09 structure from the plan: actual ordered
routes/endpoints, decompose outputs, artifact/authority distinctions, shared route
semantics, retained paths, accessible reading alternatives, source/geometry guards,
actual-candidate capture tests and recorded scope/rollback. It does not declare
human task completion or universal accessibility from a set of headings.

Final PR evidence must identify the exact candidate/integration trees, full unit
and browser outcomes, non-root build/link audit, all chapter screenshots and search
results, external review, and aggregate repository gate. Candidate generation,
tests and captures are not independent release or installed-host certification.
Broad screen-reader/multi-browser and moderated reader validation remain distinct
owner acceptance work. Do not call this record a passed test receipt.

## Rollback

Revert C04 models, generalized renderer/component, generated assets, MDX consumers,
curated corrections, navigation and tests together. Preserve public URLs and C01-C03
and earlier guide/mobile fixes. The two exact campaign trigger entries can be
removed after the stack lands. No release receipt, accepted decision, learner state,
main history or runtime qualification is changed by this documentation rollback.

## Continuation on PR #862: reader navigation and CI closure

The owner requested the next slice on the same PR after the initial browser run.
The original candidate `a0eec5035c31d804146cc9480324879f1e928856` had 151 browser
passes and three failures. Two older tests assumed exactly one disclosure containing
an image; initialization now has two independent maps inside an outer chooser, and
sprint has an inline map. The tests now open every actual native disclosure and
inspect complete source-shared stages and endpoints, including without JavaScript.
The third failure queried ancestors before Astro finished replacing the document on
Back. It now waits for the destination map before inspecting and opening its ancestors.
No sleep, retry, skipped assertion or publication-gate relaxation is used.

The same continuation completes the cross-surface reader handoff: procedure links
remain distinct from direct map links; each chapter has an explicit address and
previous/next reading links. Opening a chapter address reveals that chapter and only
its enclosing disclosures. The initialization alternatives remain independent.
Ordinary chapter buttons still do not change URLs or save state. Explicit native
links change only the address fragment; a visible chapter is not product completion.
Malformed fragments are ignored and resolved as literal IDs, never CSS selectors.

All six route destinations are owned alongside the workflow metadata and checked
against built output. This is C04's already-approved navigation and cross-surface
completion, not a new runtime workflow or a new Concepts program. The record does
not equate the diagram's reading state with approval, execution or verification.

The current parent was integrated at
`703abc9ed45b68d075ff867c75bc81ea06084b6f`, preserving its unrelated main work and
Codex metadata-path correction. Its intentional removal of the unused old C02
`authority` citation is retained. The conflict with C04's replacement of that same
unused entry was resolved by keeping the removal; live authority explanations still
trace their real owning sources. The workflow allowlist regression compares against
this actual parent, permitting only the campaign's exact PR-base addition. No parent
branch or main write, history rewrite, tag change or release was performed.

Capture tests now take chapter regions from the page at scroll position zero, rather
than letting locator screenshots scroll a chapter underneath the sticky navigation.
The page's CSS and content are not modified for screenshots. This corrects evidence
presentation, not the application in order to satisfy an image comparison.

Exact final-head CI, visual artifacts and review outcomes belong in PR #862's
verification comment. Local browser navigation is administratively blocked; no local
browser pass or relaxed network policy is claimed. Broader browser/screen-reader
coverage and moderated reader-task acceptance remain separate.


### Final navigation acceptance correction

At `ee95688bfb2a0f1243d60dddc0b19726bf447859`, repository CI passed and the website
suite had 163 passes and one failure. The failure compared all browser storage
before and after a full reload. The pinned Starlight sidebar writer stores
`sl-sidebar-state` when the document becomes hidden; that framework lifecycle write
was incorrectly attributed to the map's in-document fragment navigation.

The corrected test keeps complete storage equality assertions on each side of the
reload, using the reloaded document's own baseline. Six additional route tests
observe `setItem`, `removeItem` and `clear` without changing their behavior, reject
all writes (including temporary writes removed before the final snapshot), and
assert no requests during explicit chapter links. No storage key is allowlisted,
no browser setting is changed, and the original Back/Forward/reload behavior checks
remain. The next reading slice also moves keyboard focus to explicit chapter-link
destinations; ordinary selection buttons retain focus and do not create history.

This closes navigation-specific implementation and regression work within the
approved C04 continuation. Final candidate, hosted results, screenshots and the
still-open parent PR dependency belong in #862's completion evidence; the source
record does not invent final hashes or claim deployment.

The CodeQL review also identified a first-occurrence bracket replacement in the
stack-trigger regression. That test now constructs both literal branch lists from
the expected allowlist instead of rewriting a closing bracket. Its whole-workflow
comparison remains unchanged: only the exact additional PR base is permitted.


### Native browser traffic is not an application request

The stricter six-route tests at `49151a49e7715b0a664f3ef3bf36e109b5aaa788`
confirmed all storage and focus assertions. Five failed their blanket network
assertion because Chrome revalidated the unchanged `/favicon.svg` after native
fragment navigation. The retained HTTP traces identify same-origin GETs with image
fetch destinations, no request body and no query. The greenfield trace also exposed
Starlight's automatic hover prefetch of a newly revealed reference link.

Map links now explicitly opt out of that speculative prefetch. Actual clicks still
navigate normally; no global prefetch or network policy is changed. The observer
classifies only the exact published favicon GET with the recorded browser resource
and fetch metadata. Fetch/XHR requests, changed URLs, query strings, bodies, other
methods, origins and resource types remain failures, with negative unit fixtures.
All storage mutations and WebSockets remain prohibited by these reading tests.
Observed icon reads are attached to the test result instead of silently discarded.
This distinguishes a native browser resource fetch from map telemetry; it is not a
claim that ordinary page navigation makes no network requests.
