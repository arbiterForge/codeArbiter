# Docs overhaul: reader layer, one front door, quieter design

## Approval and authority

- Approved by the product owner in the work-session conversation on 2026-10-30, replying to the six
  design and content recommendations with: "Do it all".
- Branch: `claude/doc-site-design-content-2bfd65`, stacked on the version-drift fix `1ea5a008`.
- Approval covers the six moves below. It does not authorize merging, deployment, a release,
  Academy curriculum changes (`academy-source/` is separately owned), runtime or gate changes, or
  invented evidence.

## Thesis

The site's rule of proof before promise has turned into caveats before content. Starlight, the
generator, the tokens and public URLs stay. The problems are density and information architecture.

## Moves and done-criteria

### M1 Reader layer over an evidence layer

- A `LimitsAndEvidence` component wraps qualifications, receipts and version-scoped claims in a
  native `<details>`: readable without JavaScript, expanded in print, visible in forced colors.
- The Get started path (`overview`, `getting-started/choose-your-host`, `getting-started/install`,
  `getting-started/quickstart`, `guides/first-feature`) and the landing page carry no
  evidence-register phrasing in body text outside that component. `test/content/reader-layer.test.ts`
  enforces it with the disclaimer and jargon patterns from the 2026-10-30 audit.
- The repeated Codex reviewer-charter paragraph (0.7.5 / 0.9.4) has one canonical home on
  `getting-started/claude-code-and-codex`; every other page links to it. The version allowlist loses
  those entries.
- `VOICE.md` states where caveats belong.

### M2 One front door

- The Get started sidebar group is one linear path: What is codeArbiter, Choose your host, Install,
  Protect your first repository, Complete one feature, FAQ.
- The Learning Path stays at `/learn/` (Academy pages are generated) and moves into the Academy
  group as the self-guided path, beside the product tour. The Academy overview and 404 page point to it.
- No destination is listed twice in the sidebar, and Guides lists guides, not command reference.
- The header keeps its six destinations.

### M3 Landing in five sections

- Exactly five top-level sections: hero with the blocked-action replay, outcomes, entry points,
  hosts, closing call to action (which absorbs fit). Only the hero carries an eyebrow.
- Digests, the publication commit and the applicability statement sit inside the replay's
  disclosure; all remain in the DOM for the rendered release-applicability checks.
- SEO strings, the two primary buttons (one above the fold), page-relative links and the replay's
  evidence boundary are unchanged.

### M4 Lighter page furniture

- The journey card becomes a one-line strip (level, time, outcome). Prerequisites and proof move
  into a disclosure in the same strip; none are deleted.
- On narrow screens the splash docs rail becomes a compact horizontal control that keeps the
  drawer's keyboard and focus-restore contract.

### M5 Quieter visual style

- Cards only where the reader chooses (entry points, hosts, guide and concept directories).
  Outcomes render as a plain three-column list.
- `DESIGN-SYSTEM.md` records the card rule, the evidence component and the landing structure.

### M6 Split the four longest pages

| Task page (URL kept) | New reference page |
|---|---|
| `/codearbiter-directory/` | `/codearbiter-directory/files/` |
| `/hooks/` | `/hooks/scripts/` |
| `/getting-started/compatibility/` | `/getting-started/compatibility/runtime/` |
| `/guides/uninstalling/` | `/guides/uninstalling/details/` |

- Every inbound fragment link resolves after the split (link audit plus a fragment check).
- Each pair links to its partner, and the new pages are in the sidebar.
- Claims that CI suites under `.github/scripts/` bind to a page stay on the task page, as do the
  anchored sections other pages and the generator link to (`#host-differences`, `#network-calls`,
  `#release-applicability-heading`, and the Pi uninstall section). The reference pages take the
  per-file, per-script, runtime and rationale detail; the uninstall commands stay on the guide.

## Verification

Site typecheck, full `npm test` (build, vitest, Academy base, rendered release applicability),
link audit, `.github/scripts/test_ci_impact.py`, `.github/scripts/test_public_codex_docs.py`,
`.github/scripts/test_public_pi_docs.py`, `.github/scripts/check_site_voice.py`, and inspected desktop and mobile captures of the landing and one page from each category.
Browser automation that cannot run locally is reported as unverified, not passed.
