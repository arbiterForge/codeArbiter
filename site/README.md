# codeArbiter documentation site

An [Astro Starlight](https://starlight.astro.build/) site for codeArbiter. The
**Overview** and **Concepts** pages are hand-written; the entire **Reference**
section (commands, skills, agents) is **auto-generated from the plugin's own
frontmatter**, so it can never drift from the source.

Everything is JavaScript/TypeScript — the generator is TypeScript, tests run on
[Vitest](https://vitest.dev/), and the package manager is npm (Node LTS).

## Quick start

```bash
cd site
npm install
npm run dev      # generates the reference, then serves at http://localhost:4321
```

| Command | What it does |
| --- | --- |
| `npm run dev` | Run the generator (`predev`), then start the Astro dev server. |
| `npm run build` | Run the generator (`prebuild`), then build the static site to `dist/`. |
| `npm run preview` | Serve the built `dist/` locally. |
| `npm run gen` | Regenerate the reference pages + sidebar only. |
| `npm test` | Run the Vitest suite for the generator. |
| `npm run typecheck` | Type-check the generator with `tsc --noEmit`. |

`npm run gen` is wired into `predev` and `prebuild`, so the reference is always
fresh before the site is served or built.

## How the generator works

The generator lives in `scripts/generator/` and is built as many small,
single-responsibility, independently-tested modules. The pipeline:

1. **`collect-sources`** reads `plugins/ca/commands/*.md`,
   `plugins/ca/skills/*/SKILL.md`, and `plugins/ca/agents/*.md`.
2. **`split-frontmatter` + `parse-fields` → `parse-doc`** parse each file's
   frontmatter (`name`, `description`, `tools`, `model`) into a record. The
   parser is dep-free and tolerant: missing fields are simply absent, extra
   fields are preserved, malformed lines are skipped (never thrown).
3. **`derive-name`** picks a display name (the `name` field, or the filename for
   commands); **`slugify` + `assign-slugs`** produce stable, collision-free slugs.
4. **`render-agent-page` / `render-command-page` / `render-skill-page`** emit one
   Markdown page per source. Agent pages render the model tier (`model-tier`) and
   tools list (`format-tools-list`); commands and skills render name + description.
5. **`build-index`** groups the pages by type for the sidebar and index.
6. **`generate`** orchestrates the above, writes one page per source to
   `src/content/docs/reference/{commands,skills,agents}/<slug>.md`, writes
   `src/content/docs/reference/index.md`, and writes the sidebar data to
   `src/generated/sidebar.json` (consumed by `astro.config.mjs`).

`generate` is **idempotent** — running it twice over the same sources produces
byte-identical output. `INDEX.md` catalog files in the plugin are skipped (they
are routing tables, not documentable entities). Source files are normalized
(CRLF→LF, BOM stripped) at the read boundary so a Windows checkout parses cleanly.

### Adding to the reference

Don't edit `src/content/docs/reference/**` by hand — it's regenerated. To change
the reference, change the frontmatter in `plugins/ca/**` and re-run `npm run gen`.

## Tests

The generator is built test-first: each module has its own Vitest file under
`test/generator/`, with fixtures under `test/fixtures/`. Run `npm test`.

## Deploying to GitHub Pages

The site is wired for GitHub Pages at `https://arbiterforge.github.io/codeArbiter/`.
The pieces are already in place:

- **Base path** — `astro.config.mjs` sets `site` + `base: '/codeArbiter'`. Note this
  also applies in local dev (the dev server serves at `http://localhost:4321/codeArbiter/`).
- **Base-aware links** — Starlight prepends `base` to its own navigation (sidebar,
  next/prev), but **not** to author-written links. So the hand-authored links are
  base-safe explicitly: the home page (`index.mdx`) bakes the base into its links
  (`/codeArbiter/overview/`); the plain-markdown pages use relative links
  (`../concepts/`); the generated reference index links are relative too. (Astro does
  **not** auto-rewrite root-relative links in content, and `import.meta.env.BASE_URL`
  carries no trailing slash — that's why these are explicit. If you change `base`,
  update the hardcoded home links to match.)
- **Workflow** — `.github/workflows/docs.yml` builds with `withastro/action`
  (`path: site`) and deploys via `actions/deploy-pages`. It triggers on push to
  `main` touching `site/**` or `plugins/ca/**`, and can be run manually
  (`workflow_dispatch`). The reference is regenerated in CI, so committing the
  generated output isn't needed.

**To go live:** enable Pages once (Settings → Pages → Source: **GitHub Actions**),
then merge to `main` (or run the workflow manually). Pages and Actions are free for
this public repo.

### Versioning against releases

The reference reflects whatever `plugins/ca/**` is on `main`, and the workflow's
`paths` filter rebuilds the docs whenever the plugin payload changes — so a release
that bumps the payload republishes the reference automatically. Publishing *versioned*
docs (one set per release tag) is a later step: add Starlight multi-version support or
build one site per tag into a versioned subpath, once single-version docs are validated.
