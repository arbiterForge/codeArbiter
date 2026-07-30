# Documentation Product Audit

**Date:** 2026-07-30

**Scope:** the complete built documentation site, its shared presentation system, and the repository README

**Standard:** a reader must be able to move from no prior codeArbiter knowledge to source-backed
power-user operation without reconstructing missing steps from chat history

**Result:** PASS after the repairs and upgrades recorded below

## What was proved

- All **139 built index routes** were opened in a real Chromium renderer at **1440 x 1000** and
  **390 x 844**. The 278 route/viewport checks each returned a final 200 response, one page title,
  one main H1, non-empty main content, zero page-level horizontal overflow, and a semantic overflow
  shell around every Markdown table.
- The custom 404 page was reviewed separately, bringing the reviewed built surface to **140 pages**.
- All **16 unique in-page media assets** returned 200 with the expected image content type.
- Six generated compatibility aliases were followed to their canonical skill pages at both
  viewports.
- The link audit resolved **19,786 internal links across 140 pages**.
- All 37 hand-authored inner-doc pages carry a learning contract: level, expected time, outcome,
  prerequisites, and proof of completion. The landing page uses the separate product-splash
  contract.
- The generated catalogs were assessed through their source-backed family templates and by opening
  every generated route. Commands explain invocation, example, reach point, gates, relationships,
  and source. Skills explain operating context, phases, stops, artifacts, relationships, and source.
  Agents explain role, dispatch ownership, tools, constraints, output, relationships, and source.

## Audit rubric

Every hand-authored route was judged against five questions:

1. **Orientation:** does the page say what portion of codeArbiter it owns and why the reader is here?
2. **Prerequisites:** does it name the state, host, tool, or earlier concept the reader needs?
3. **Action or model:** can the reader either perform the workflow or explain the mechanism?
4. **Proof and recovery:** does it say how success is demonstrated and where failure routes?
5. **Progression:** does the page lead into the next useful guide or source-backed reference?

`PASS` means the route met the rubric without a change in this final audit. `REPAIRED` means the
route failed presentation or navigation and was corrected. `UPGRADED` means it was usable but
received a first-class visual or learning-path improvement.

## Hand-authored route ledger

### Product entry and learning path

| Route | Status | Reader outcome and audit evidence |
|---|---|---|
| `/` | REPAIRED + UPGRADED | Outcome-led product splash, verified direct-hook replay, host posture, guarantees, flow, fit, and CTA. The rendered gate art is fixed behind the scrolling narrative; the replay is real product evidence and does not autoplay. The Starlight skip link now reaches a focusable `_top` target. |
| `/overview/` | REPAIRED | Explains command, route, host-specific role execution, gate, and ship without pretending Claude packaged agents, Codex host-provided threads, and Pi hardened children use one mechanism; names the bounded older-Codex fallback, lane families, and context-minimization model; routes to Concepts and Reference. |
| `/learn/` | REPAIRED | Four-stage curriculum now links through a normalized deployment base, states the honest 3–4 hour module total, includes proof after every stage, and ends with an eight-part capstone that points migration/CI/deployment scope to security controls instead of unrelated environment configuration. |

### Start

| Route | Status | Reader outcome and audit evidence |
|---|---|---|
| `/getting-started/choose-your-host/` | PASS | Compares stability, syntax, distribution, trust, state, UI, and best fit for all three governance hosts. |
| `/getting-started/install/` | REPAIRED | Gives host-specific install and trust steps, prerequisites, activation boundary, verification, update path, and exact next step. Interpreter checks now work in POSIX shells and PowerShell and registration language matches each host. |
| `/getting-started/quickstart/` | PASS | Uses a disposable repository with meaningful source, proves H-03 through doctor, explains expected state, and provides recovery. |
| `/getting-started/claude-code-and-codex/` | PASS | Separates generated parity, hosted packaging checks, and dated manual live-hook evidence; retains the precise core-fanout SVG. |
| `/getting-started/pi/` | REPAIRED | Covers Git-only install, project trust, activation, doctor, footer, security, Windows, pinning, upgrade, and uninstall for the preview host. The prerequisite now matches the exact supported Pi versions and the install begins with mechanical `ca-pi-v*` tag discovery. |
| `/getting-started/compatibility/` | REPAIRED | Distinguishes plugin runtime from docs-development dependencies and records host, platform, interpreter, network, and optional-feature boundaries. Pi's Vitest aggregate prerequisite is explicitly isolated as maintainer-only verification, not adopter setup. |
| `/faq/` | PASS | Answers adoption objections about blocking, bypass, uninstall, speed, data, teams, mixed hosts, misfit gates, and conflict routing with actionable links. |

### Workflows

| Route | Status | Reader outcome and audit evidence |
|---|---|---|
| `/guides/opt-in-a-repo/` | REPAIRED | Teaches the shared Claude Code, Codex, and Pi repository contract, initialization, brownfield/greenfield routing, activation verification, and safe disable/recovery; retains its exact lane SVG. |
| `/guides/feature-lane/` | PASS | Runs new behavior from intent through spec, plan, TDD, review, commit, and PR with persisted artifacts and completion proof. |
| `/guides/autonomous-sprints/` | PASS | Explains the interactive gate, resumable task state, SMARTS decisions, hard stops, review, and PR boundary. |
| `/guides/recording-adrs/` | PASS | Shows when an ADR is warranted, how it is attributed, how `governs:` affects later reads, and how to verify the record. |
| `/guides/adding-a-dependency/` | PASS | Covers license, provenance, maintenance, vulnerabilities, install timing, and the dependency-review gate. |
| `/guides/releasing-a-version/` | PASS | Gives target-aware release selection, dry run, version/changelog/tag behavior, and proof by target. |

### Operate

| Route | Status | Reader outcome and audit evidence |
|---|---|---|
| `/guides/overriding-a-gate/` | REPAIRED | Defines the narrow authority of an override, identity requirements, append-only record, and what an override cannot authorize, including H-18's deliberately non-overridable in-session boundary. |
| `/guides/ca-sandbox/` | REPAIRED | Explains the isolated repository boundary, creation and extraction flow, network posture, Windows/WSL notes, and recovery; retains the security-boundary SVG and now includes the marketplace-registration prerequisite. |
| `/guides/the-statusline/` | PASS | Annotates a real captured statusline PNG rather than inventing a UI; explains every segment, enabled-repo behavior, cost source, and removal. |
| `/guides/troubleshooting/` | PASS | Symptom-driven diagnosis covers dormant activation, malformed context, interpreter failures, stale cache, trust, hooks, status UI, and host-specific recovery. |
| `/guides/uninstalling/` | REPAIRED | Separates disable from uninstall, preserves the shared three-host `.codearbiter/` store, covers Claude Code, Codex, and Pi activation protection accurately, turns Pi version removal into a tag/list-driven action, and distinguishes per-host git-enforcer registry cleanup from sentinel-only shared-shim removal after the last host is gone. |

### Understand

| Route | Status | Reader outcome and audit evidence |
|---|---|---|
| `/concepts/` | REPAIRED | The broken-feeling raw table was replaced with ten purpose-built concept cards keyed by reader question, domain, icon, and destination. |
| `/concepts/gated-lanes/` | REPAIRED | Explains why work types take different paths, soft versus hard gates, the nine-phase commit gate, and how to choose a lane without overclaiming override authority over H-18. |
| `/concepts/smarts/` | PASS | Defines all six lenses, verdicts, recommendation strengths, precedent, user authority, sprint reuse, and audit evidence. |
| `/enforcement/` | REPAIRED | Separates activation, advisory and blocking behavior, fail-loud interpreter posture, commit-time controls, trust, and child-process boundaries. H-19 is now described as cooperative attestation rather than unforgeability. |
| `/concepts/provenance-drift/` | PASS | Explains tracked derivations, stale detection, SessionStart reporting, commit-gate healing, and verification; retains the provenance-flow SVG. |
| `/concepts/adrs/` | PASS | Explains accepted decisions, supersession, attribution, governed files, and the difference between an ADR and ordinary documentation. |
| `/concepts/jit-context-injection/` | PASS | Shows the four-tier priority model, token budget, read-time pointer behavior, and how to confirm the controlling artifact. |
| `/concepts/checkpoints/` | REPAIRED | The reviewer fleet remains a semantic data grid, now inside the shared responsive table shell; the page explains fleet, funnel, run, report, and tribunal boundary. |
| `/concepts/persona-and-context/` | PASS | Separates the orchestrator register from project-owned facts and shows why authors, reviewers, and routing remain distinct. |
| `/concepts/auditability/` | PASS | Traces commits, ADRs, questions, overrides, sprint decisions, checkpoints, and audit packets into a reconstructable record. |
| `/concepts/hardening-history/` | PASS | Explains selected controls through the failure mode that caused each one and routes operators to the current source-backed contract. |

### Reference and Labs

| Route | Status | Reader outcome and audit evidence |
|---|---|---|
| `/codearbiter-directory/` | PASS | Comprehensive artifact-by-artifact reference names creator, reader, lifecycle, authority, and recovery for repository-owned state. |
| `/glossary/` | REPAIRED | Defines every terminology-locked term promised by its proof—command, skill, agent, phase, stage, layer, gate, and severity—and records the H-18 override exception. |
| `/hooks/` | REPAIRED | Traces the shared Python core and non-event scripts while separately mapping real Claude Code registrations, Codex adapter registrations, and Pi wrapper/lifecycle events. Interpreter compatibility and marker trust language now match source. |
| `/feature-forge/overview/` | UPGRADED | Adds rendered forge atmosphere for identity while retaining the exact two-axis SVG for SemVer versus feature maturity; the decorative image uses empty alt because its caption carries the meaning. |
| `/feature-forge/whats-in-the-forge/` | PASS | Generated from the same preview allowlist as reference badges; every preview names opt-in, dependency, evidence gap, and graduation signal. |
| `/feature-forge/using-preview-features/` | PASS | Teaches deliberate opt-in, least-consequential mode, fresh-session handling, off-switch verification, and defect reporting. |

## Generated route ledger

The generated surface is reviewed by family because one generator controls every page in the
family. Every individual route was still rendered at both audit viewports.

| Family | Routes | Status | Contract checked |
|---|---:|---|---|
| Reference entry | 1 | REPAIRED | catalog purpose, source-backed provenance, counts, and command → skill → agent usage; regenerated facts are distinguished from hand-reviewed guidance that can drift |
| Commands | 40 | UPGRADED | host syntax, availability, example, owning skill, gates, related surfaces, and exact source; redundant journey cards are suppressed on direct entity landings |
| Skills | 23 | UPGRADED | context, invocation ownership, phases, hard stops, durable artifacts, related surfaces, and source; redundant journey cards are suppressed on direct entity landings |
| Skill aliases | 6 | PASS | meta-refresh and canonical link resolve to the intended current skill page |
| Agents | 28 | REPAIRED | role, dispatch ownership, model/tool constraints, emitted result, relationships, and source; every deep landing repeats Claude packaged-agent, current-Codex host-thread with bounded fallback, and Pi hardened-child semantics, translates Claude-only path placeholders in reader copy, and uses compact mobile orientation |
| Configuration | 1 | PASS | typed groups, defaults, accepted values, effects, safe testing, undo, and source-presence contract |
| Hook gates | 1 | PASS | generated from actual `block()` and `remind()` call sites with gate ID, event, message, and source |
| Changelog | 1 | REPAIRED | accurately labeled as the core `ca` timeline, linked to the three independently versioned sibling changelogs, and classified as Reference |

The six alias routes checked were:

- `/reference/skills/context-check-2/` → `/reference/skills/context-check`
- `/reference/skills/debug-2/` → `/reference/skills/debug`
- `/reference/skills/decompose-2/` → `/reference/skills/decompose`
- `/reference/skills/refactor-2/` → `/reference/skills/refactor`
- `/reference/skills/release-2/` → `/reference/skills/release`
- `/reference/skills/tribunal-2/` → `/reference/skills/tribunal`

## Adversarial follow-up

The first clean renderer sweep was not accepted as sufficient. A second reviewer pass read all 38
hand-authored routes and sampled every generated family as a novice entering from search. It
blocked sign-off on accessibility, time honesty, cross-host accuracy, mobile legibility, and
generated-reference framing. Every block was repaired before this ledger returned to PASS:

- the landing skip target now exists and accepts programmatic focus;
- the learning path's fixed module estimates and capstone destinations are honest;
- Pi support and tag selection are mechanically actionable;
- all 17 `.ca-diagram` figures retain at least a 672px readable canvas inside a local horizontal
  scroll region at 390px, with zero page-level overflow; the separately styled real statusline map
  uses a wider 864px canvas;
- hook and uninstall language follows the actual Claude Code manifest, Codex adapter manifest, and
  Pi extension events;
- repository opt-in and role execution now state all three host contracts without collapsing their
  different dispatch mechanisms;
- Pi's platform-aggregate dependency setup is labeled maintainer verification rather than an adopter
  prerequisite;
- marker language states the cooperative same-user threat boundary;
- the terminology lock is complete;
- generated entity landings remove the redundant journey card, compact their direct-entry context,
  and explain host dispatch semantics;
- the changelog states exactly which independently versioned release line it covers.

A final read-only advisor recheck after these repairs returned PASS with no remaining contradiction.
The commit review fleet then caught and repaired two last source-of-truth drifts: current Codex role
dispatch versus its older inline fallback, and the ordered multi-host uninstall contract for the
shared hook shim. Architecture, security, and coverage rechecks all returned PASS after those
repairs.

## Media decision: SMARTS

Three strategies were considered:

- **A. Rasterize every SVG.** Maximum atmosphere, weakest precision and maintainability.
- **B. Keep every surface vector.** Maximum precision, weakest brand differentiation on decorative
  surfaces.
- **C. Use a hybrid evidence hierarchy.** Rendered art for atmosphere, SVG for explanatory systems,
  and real capture for claims about shipped UI or runtime behavior.

| Lens | A: all raster | B: all vector | C: hybrid |
|---|---|---|---|
| Scalable | Weak: repeated art generation for every diagram. | Strong: small, responsive assets. | Strong: each medium is used only where it pays. |
| Maintainable | Weak: text and logic become pixels. | Strong: diagrams remain editable. | Strong: operational diagrams stay editable; decorative assets are few. |
| Available | Adequate: local assets, but heavier payload. | Strong: compact and dependency-free. | Strong: optimized local WebP plus compact SVG. |
| Reliable | Weak: image generation can invent or blur semantics. | Strong: deterministic geometry and labels. | Strong: only non-semantic atmosphere is generated. |
| Testable | Weak: semantic drift is hard to assert. | Strong: source text and geometry are inspectable. | Strong: asset roles are contract-tested and captures retain provenance. |
| Securable | Adequate: local output, but larger opaque artifacts. | Strong: transparent source. | Strong: no remote runtime assets; proof remains source-digested. |

**Decision:** C, hybrid. **Strength:** strong.

Consequences:

- The fixed landing backdrop and Feature Forge atmosphere use optimized rendered WebP.
- The header brand and navigation icons use crisp project-owned SVG because they must scale and
  remain recognizable at small sizes.
- Gate, lane, activation, provenance, fan-out, sandbox, and maturity diagrams remain SVG because
  their exact relationships are the content.
- The statusline remains a real captured PNG.
- The hook proof remains a real source-digested replay in MP4/WebM with an exact text transcript.
- No fictional training GIF or video was introduced.

## README alignment

The README was reduced from a drifting long-form manual to a professional adoption surface:

- rendered product and Feature Forge artwork replace the legacy decorative SVG banners;
- host choice, prerequisites, install, trust, first-repository proof, and the docs learning path
  appear before architecture internals;
- the complete command catalog remains available in a collapsed section for release-consistency
  checks, while the generated site reference remains authoritative;
- Pi, Codex, network, preview, license, and Build Week evidence contracts remain explicit;
- detailed configuration, troubleshooting, hook, and workflow material now routes to the site
  instead of being duplicated.

## Verification commands

Run from `site/` unless a command shows otherwise:

```text
npm test
npm run typecheck
npm run coverage
npm run build
npm run link-audit
python ../.github/scripts/check_badge_consistency.py
python ../.github/scripts/test_public_codex_docs.py
python ../.github/scripts/test_public_pi_docs.py
python ../.github/scripts/test_license_consistency.py
```
