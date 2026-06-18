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

## Deploying (not yet enabled)

The site builds to a static `dist/` and is ready for GitHub Pages. To deploy:

1. **Set the base path.** In `astro.config.mjs` add:
   ```js
   site: 'https://arbiterforge.github.io',
   base: '/codeArbiter',
   ```
   (This also silences the sitemap warning.) Internal links already use
   root-relative paths, which Astro rewrites under `base` at build time.
2. **Add a GitHub Pages workflow** — `.github/workflows/docs.yml` using the
   official Astro action:
   ```yaml
   name: Deploy docs
   on:
     push:
       branches: [main]
       paths: ['site/**', 'plugins/ca/**']   # rebuild when the plugin changes too
   permissions:
     contents: read
     pages: write
     id-token: write
   jobs:
     build:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: withastro/action@v3
           with:
             path: site
     deploy:
       needs: build
       runs-on: ubuntu-latest
       environment:
         name: github-pages
         url: ${{ steps.deployment.outputs.page_url }}
       steps:
         - id: deployment
           uses: actions/deploy-pages@v4
   ```
   Then enable Pages (Settings → Pages → Source: GitHub Actions).
3. **Version against releases.** The reference reflects whatever `plugins/ca/**`
   is on the deployed branch. Because the `paths` filter includes `plugins/ca/**`,
   a release that changes the plugin payload triggers a docs rebuild. To publish
   versioned docs (one set per release tag), add Starlight's
   [versioning](https://starlight.astro.build/) via a multi-version setup or build
   one site per tag into a versioned subpath — deferred until single-version docs
   are validated.
