# codeArbiter documentation site

The public documentation for codeArbiter, built with
[Astro Starlight](https://starlight.astro.build/). It combines:

- a purpose-built product splash page;
- hand-authored onboarding, guide, concept, and operations pages;
- generated command, skill, agent, hook-gate, configuration, and changelog reference; and
- curated explanations layered over the exact plugin source.

The visual and content contract lives in [`DESIGN-SYSTEM.md`](./DESIGN-SYSTEM.md). Read it before
adding a component or documentation page.

## Local development

Use Node LTS and npm:

```bash
cd site
npm ci
npm run dev
```

The development URL is `http://localhost:4321/codeArbiter/` because the production site is a
GitHub Pages project site.

| Command | Purpose |
|---|---|
| `npm run dev` | Regenerate reference content, then start Astro's development server. |
| `npm run gen` | Regenerate command, skill, agent, hook, configuration, changelog, and sidebar artifacts. |
| `npm test` | Run generator, content-contract, and landing-page tests. |
| `npm run typecheck` | Type-check the generator and site support code. |
| `npm run build` | Regenerate content, build every route, and create the Pagefind index. |
| `npm run preview` | Serve the current production build locally. |

Generated files are deterministic. If two runs against the same source produce a diff, the
generator has a defect.

## Content ownership

Choose the owner before editing:

| Content | Owner | Where to change it |
|---|---|---|
| Splash, onboarding, guides, concepts, operations | Human-authored page | `src/content/docs/` |
| Command behavior | Plugin source + curated explanation | `../plugins/ca/commands/` and `src/curated/commands/` |
| Skill behavior | Plugin source + curated explanation | `../plugins/ca/skills/` and `src/curated/skills/` |
| Agent behavior | Plugin source + curated explanation | `../plugins/ca/agents/` and `src/curated/agents/` |
| Hook gate messages and source links | Hook call sites | `../plugins/ca/hooks/*.py` |
| Configuration variables | Typed configuration catalog | `scripts/generator/configuration-reference.ts` |
| Release history | Repository changelog | `../CHANGELOG.md` |
| Navigation | Hand-authored IA + generated reference groups | `astro.config.mjs` and `src/generated/sidebar.json` |
| Visual tokens and component rules | Design system | `DESIGN-SYSTEM.md` and `src/styles/design-system.css` |

Do not edit generated pages under `src/content/docs/reference/{commands,skills,agents}/` or the
generated `reference/hooks-gates.md`, `reference/configuration.md`, and `changelog.md`. Run
`npm run gen` after changing their source.

### Generated reference pipeline

`scripts/gen.ts` coordinates small modules under `scripts/generator/`:

1. collect the plugin source files;
2. parse and normalize their frontmatter and source;
3. assign stable, collision-free slugs;
4. combine a host-aware orientation lead, curated explanation, and exact source disclosure;
5. emit pages and reference sidebar data;
6. extract hook gates from literal `block()` and `remind()` call sites;
7. emit the typed, maintainer-reviewed configuration catalog; and
8. transform the repository changelog for Starlight.

Every command, skill, and agent must have a curated explanation. The coverage test fails when a
new source entity ships without one.

## Writing a usable page

A page is complete when a reader can tell:

1. what outcome it provides;
2. what must be true before they start;
3. which host-native syntax to use;
4. what inputs and defaults apply;
5. what to do and what successful output looks like;
6. how to verify the result independently;
7. where the workflow stops and how to recover;
8. whether the action is reversible; and
9. what to read or invoke next.

Concept pages adapt the same contract: explain the mental model, show a concrete example, state
where the model matters in practice, and link to the workflow and exact reference.

Use root-absolute content links such as `/guides/feature-lane/`. The local
`rehype-base-links` processor prefixes the configured project-site base. In Astro component props,
use `import.meta.env.BASE_URL`. Never hard-code `/codeArbiter/` in a link.

## Verification

Before opening a documentation pull request:

```bash
npm test
npm run typecheck
npm run build
```

Then crawl the built sitemap and inspect the splash, one page from every hand-authored section,
and representative command, skill, agent, hook, configuration, and changelog pages at desktop and
mobile widths. Check response status, one visible H1, descriptions, image alt text, keyboard
navigation, focus visibility, horizontal overflow, contrast, reduced motion, and useful Pagefind
results.

## Deployment

`.github/workflows/docs.yml` builds the site from `site/` and deploys GitHub Pages when relevant
changes land on `main`, or when started manually. The site and deployment use only repository and
GitHub Pages resources; no paid service is required.
