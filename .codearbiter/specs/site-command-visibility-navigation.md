# Spec: Command visibility navigation

**Status:** APPROVED 2026-09-12 by the user's explicit `yes`
**Lane:** `/ca:feature` full lane
**Slug:** `site-command-visibility-navigation`
**Governs:** `site/scripts/generator/build-index.ts`, `site/scripts/generator/types.ts`, `site/astro.config.mjs`, `site/src/components/Sidebar*.astro`, `site/test/generator/**`, `site/test/**/*sidebar*`

## Problem

The public reference sidebar presents all 38 command routes as one alphabetical list, so a reader
looking for the normal day-to-day lanes must scan advanced operations, compatibility aliases,
internal protocol, and a deprecated route at the same visual weight. The affected caller is a
codeArbiter documentation reader navigating command reference pages; done means the existing
registry taxonomy visibly organizes the sidebar without making any route harder to reach.

This is a bounded presentation residual from the approved RA-11 catalog model. It does not reopen
that model's command classifications, compatibility policy, or direct-route contract.

## Approach

Project nested Command groups from the existing generated command catalog into Starlight's existing
sidebar data, then let the canonical `SidebarSublist` render native disclosure elements. This keeps
`core/surface/command-routes.json` as the sole authority and reuses current-page expansion, keyboard,
focus, mobile, and branded homepage-rail behavior. The trade-off is one extra navigation level in
exchange for a much shorter initial list and no new stateful UI system.

The rejected alternative is a separate conventional header/menu or a bespoke homepage command
navigator: either would fork the canonical sidebar and duplicate navigation state. A flat list with
visual separators is also insufficient because it leaves all 38 links initially exposed.

## Scope

- Extend the generated sidebar shape only as needed to represent nested Command visibility groups.
- Group all command links exactly once in the catalog's canonical visibility order: Core, Advanced,
  Compatibility aliases, Internal, and Deprecated.
- Keep Core initially expanded and the other visibility groups collapsed; when a command page is
  current, its containing group opens through the existing current-link rule.
- Preserve every direct command URL, deployment-base handling, nested disclosure keyboard behavior,
  visible focus, sidebar scrolling, mobile Menu behavior, and the homepage's branded docs rail.
- Add focused generator/config regressions first, followed by direct rendered checks at wide,
  standard, and compact widths.

Explicitly out of scope: command names, aliases, host projections, visibility classifications,
workflow classifications, compatibility retention, slugs, routes, the reference-index taxonomy,
Academy grouping, last-visited/progress persistence, and any new header or navigation system.

## Decided parameters

- Visibility order and membership come only from the validated generated catalog; no fallback
  classification or second registry is introduced.
- Labels are exactly `Core`, `Advanced`, `Compatibility aliases`, `Internal`, and `Deprecated`.
- Links remain alphabetical within each visibility group, preserving the current list's local order.
- The Command collection remains one top-level `Commands` group; visibility groups are its immediate
  children. Workflow does not add another sidebar nesting level.
- `Core` has `collapsed: false`; every other visibility group has `collapsed: true`.
- The existing `hasCurrentLink` behavior overrides an initial collapsed value for the active page's
  ancestors. No last-visited or cross-page expansion state is added.
- Normal docs pages and the branded homepage docs rail continue to render the same canonical
  `Sidebar`/`SidebarSublist` components.
- Missing, duplicated, or unknown command visibility remains a generation failure, never an
  ungrouped fallback.

## Acceptance criteria

1. Given command pages and a validated generated catalog, one focused generator test observes a
   `Commands` sidebar group whose immediate children are Core, Advanced, Compatibility aliases,
   Internal, and Deprecated in that order; every command link occurs exactly once, links are
   alphabetical within each child, and the production inventory totals 18, 13, 5, 1, and 1.
2. Given that generated nested data, one focused configuration test observes unchanged
   `reference/commands/<slug>` destinations, `collapsed: false` for Core, `collapsed: true` for the
   other four groups, and no alternate registry, persisted expansion state, workflow nesting, or
   route rewrite; the active command remains discoverable through the existing current-link ancestor
   expansion.
3. Given a Core command page and a non-Core command page, one rendered browser-matrix test at wide,
   standard, and compact widths observes the active page inside its open group, all five groups
   reachable, native disclosure keyboard operation, visible focus, scroll reachability, mobile Menu
   operation, deployment-base-correct links, and the same behavior in the homepage's branded docs
   rail.

## Validation boundary

Focused tests must establish RED before production changes. Completion additionally requires the
site typecheck, production build, link/route audit, exact generated counts, wide/standard/compact
browser checks, secret and diff checks, independent review, and the governed commit/PR gates recorded
by checkpoint 031. No release, tag, publication, merge, Pages deployment, or destructive cleanup is
authorized by this spec.

## Negative-space check

If every criterion passes and nothing else changes, this feature's defect is closed: the supported
command model is progressively disclosed, every route remains reachable, and both sidebar shells
share one behavior. Academy track grouping remains a separate accepted campaign checkpoint rather
than a missing criterion here.

## Open questions

None. `[CONFIRM-05]` concerns Feature Forge promotion and is unrelated to this feature.
