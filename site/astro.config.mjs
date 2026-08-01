// @ts-check
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";
import { unified } from "@astrojs/markdown-remark";
import { readFileSync } from "node:fs";
import { rehypeBaseLinks } from "./scripts/rehype-base-links.ts";
import { rehypeTableShell } from "./scripts/rehype-table-shell.ts";

// Served from https://codearbiter.dev/ — shared by the `base` option below and
// the rehype plugin that base-prefixes markdown links.
//
// MUST be "" for an apex domain, never "/". rehypeBaseLinks prefixes any
// root-absolute href/src with this value, and "/" would turn "/diagrams/x.svg"
// into "//diagrams/x.svg" — a protocol-relative URL pointing at another host,
// which fails silently. Empty string makes the plugin a correct no-op, because
// "/diagrams/x.svg" already starts with `${BASE}/`. Astro's own `base` still
// needs a real path, so it takes `BASE || "/"` below.
// Exported so the tests that assert base-dependent output derive it from here
// instead of re-declaring the literal. Three of them previously kept their own
// copy, which is what turned a one-line base change into a four-test failure.
export const BASE = "";

// Build the reference sidebar groups from the generator's output. `predev` and
// `prebuild` run `npm run gen` first, so sidebar.json exists before this loads.
// The try/catch keeps `astro check`/tooling from hard-failing on a fresh clone
// where the generator has not run yet.
/** @type {Array<{label: string, items: Array<{label: string, slug: string}>}>} */
let referenceGroups = [];
try {
  /** @type {Array<{type: string, label: string, items: Array<{label: string, slug: string}>}>} */
  const sidebarData = JSON.parse(
    readFileSync(new URL("./src/generated/sidebar.json", import.meta.url), "utf8"),
  );
  referenceGroups = sidebarData.map((g) => ({
    label: `${g.type.charAt(0).toUpperCase()}${g.type.slice(1)}s`,
    collapsed: true,
    items: g.items.map((it) => ({
      label: it.label,
      slug: `reference/${g.type}s/${it.slug}`,
    })),
  }));
} catch {
  // sidebar.json not generated yet — reference groups stay empty.
}

export default defineConfig({
  // GitHub Pages site on the apex custom domain: served from https://codearbiter.dev/.
  // `base` also applies in local dev — the dev server serves at the root.
  //
  // BASE-PATH-SAFE LINK PATTERN for downstream authors:
  //   - Starlight does NOT rewrite root-absolute markdown links through the
  //     base on its own. Writing [Overview](/overview) in MDX/Markdown would
  //     render a literal `/overview` href and 404 once served from a subpath.
  //   - Instead, the `markdown.processor` below runs our local
  //     `rehypeBaseLinks(BASE)` plugin (scripts/rehype-base-links.ts) over
  //     every rendered page. It walks the HAST tree and prefixes any
  //     root-absolute href/src ("/overview") with BASE, idempotently, so plain
  //     root-relative markdown links stay base-safe. On the apex domain BASE is
  //     "" and the prefixing is a no-op, but the plugin stays wired so the site
  //     survives a future move back to a subpath.
  //   - The plugin is passed to `unified({ ... })` from `@astrojs/markdown-remark`,
  //     NOT to the top-level `markdown.rehypePlugins` key. Astro 7.1 deprecated
  //     `markdown.remarkPlugins` / `rehypePlugins` / `remarkRehype` ("will be
  //     removed in a future major") — see the note on `markdown:` below.
  //   - In Astro component href props (not markdown), still use
  //     import.meta.env.BASE_URL: href={`${import.meta.env.BASE_URL}overview/`}
  //   - Diagram <img> tags in .md/.mdx are the documented exception: raw HTML in
  //     markdown is not walked by rehypeBaseLinks, so those srcs carry the base
  //     literally. test/generator/diagram-href-convention.test.ts is the guard,
  //     and it derives the expected prefix from BASE below rather than repeating
  //     it — when the base moved to "" for the apex domain, 19 such attributes
  //     across 16 pages had to change with it, and a hardcoded guard would have
  //     had to be edited by hand in lockstep.
  site: "https://codearbiter.dev",
  // `BASE || "/"`: Astro needs a real path, while rehypeBaseLinks needs the
  // empty string (see the constant above for why "/" would corrupt links).
  base: BASE || "/",
  // Old `-2` skill URLs from before per-collection slug dedup (see generate.ts):
  // these six skills shared a name with a same-named command, so the combined
  // dedup pass pushed the skill page to a `-2` slug. Redirect the old URLs to
  // the now-clean ones.
  //
  // Astro matches redirect *keys* through `base` itself (base-relative, no
  // BASE prefix). The *destination* value, however, is emitted verbatim as the
  // redirect Location/meta-refresh target — it is NOT base-prefixed
  // automatically — so destinations must carry the base explicitly to land on
  // a real page (built from the shared BASE constant above).
  redirects: {
    "/reference/skills/context-check-2": `${BASE}/reference/skills/context-check`,
    "/reference/skills/debug-2": `${BASE}/reference/skills/debug`,
    "/reference/skills/decompose-2": `${BASE}/reference/skills/decompose`,
    "/reference/skills/refactor-2": `${BASE}/reference/skills/refactor`,
    "/reference/skills/release-2": `${BASE}/reference/skills/release`,
    "/reference/skills/tribunal-2": `${BASE}/reference/skills/tribunal`,
  },
  // Astro 7.1 made Sätteri the default Markdown processor and deprecated the
  // top-level `markdown.remarkPlugins` / `rehypePlugins` / `remarkRehype` keys.
  // Setting `processor` explicitly is the supported replacement: it selects the
  // remark/rehype (`unified`) pipeline and takes the plugin list directly.
  //
  // This is behaviour-neutral versus the deprecated form — Astro's own
  // compatibility shim did exactly this (`md.processor = unified()`, then push
  // the legacy plugin arrays onto it) before emitting its deprecation warning.
  // Doing it here removes the warning and takes the site off an API with a
  // scheduled removal. `@astrojs/markdown-remark` is a direct dependency
  // because of this import — see site/package.json.
  markdown: {
    processor: unified({ rehypePlugins: [rehypeBaseLinks(BASE), rehypeTableShell()] }),
  },
  integrations: [
    starlight({
      title: "codeArbiter",
      description: "Shared enforcement and project-context parity across Claude Code, Codex, and Pi.",
      // A custom StarlightPage-backed src/pages/404.astro owns the production
      // fallback without forcing a phantom docs collection lookup at build time.
      disable404Route: true,
      logo: {
        src: "./src/assets/logo.svg",
        replacesTitle: true,
        alt: "codeArbiter",
      },
      favicon: "/favicon.svg",
      // codeArbiter is dark-only: ThemeProvider forces data-theme="dark" and
      // ThemeSelect renders nothing (the switcher is removed). See theme.css.
      components: {
        // dark-only: force the theme, remove the switcher
        ThemeProvider: "./src/components/ThemeProvider.astro",
        ThemeSelect: "./src/components/ThemeSelect.astro",
        // SPA-like navigation via Astro view transitions
        Head: "./src/components/Head.astro",
        // suppress the duplicate auto-<h1> on the bespoke landing hero
        PageTitle: "./src/components/PageTitle.astro",
        // position-based scroll-spy so the last "On this page" item highlights
        // when scrolled to the bottom (the stock observer misses it)
        TableOfContents: "./src/components/TableOfContents.astro",
        // inline search (live as you type, results drop below the box)
        // replacing Starlight's stock modal-on-click search
        Search: "./src/components/Search.astro",
        // authored navigation groups with the codeArbiter icon language
        Sidebar: "./src/components/Sidebar.astro",
      },
      customCss: [
        "./src/styles/design-system.css",
        "./src/styles/theme.css",
        "./src/styles/callouts.css",
        "./src/styles/landing.css",
      ],
      // Starlight 0.33+ takes an array of link items, not an object.
      social: [
        {
          icon: "github",
          label: "GitHub",
          href: "https://github.com/arbiterForge/codeArbiter",
        },
      ],
      sidebar: [
        {
          label: "Start",
          collapsed: false,
          items: [
            { label: "What Is codeArbiter", slug: "overview" },
            { label: "Learning Path", slug: "learn" },
            { label: "Choose Your Host", slug: "getting-started/choose-your-host" },
            { label: "Install", slug: "getting-started/install" },
            { label: "Protect Your First Repository", slug: "getting-started/quickstart" },
            { label: "Claude Code + Codex", slug: "getting-started/claude-code-and-codex" },
            { label: "Pi", slug: "getting-started/pi" },
            { label: "Compatibility", slug: "getting-started/compatibility" },
            { label: "FAQ", slug: "faq" },
          ],
        },
        {
          label: "Workflows",
          collapsed: true,
          items: [
            { label: "Opt a Repository In", slug: "guides/opt-in-a-repo" },
            { label: "Build a Feature End to End", slug: "guides/feature-lane" },
            { label: "Run an Autonomous Sprint", slug: "guides/autonomous-sprints" },
            { label: "Record an Architecture Decision", slug: "guides/recording-adrs" },
            { label: "Add a Dependency Safely", slug: "guides/adding-a-dependency" },
            { label: "Cut a Release", slug: "guides/releasing-a-version" },
          ],
        },
        {
          label: "Operate",
          collapsed: true,
          items: [
            { label: "Set Up the Statusline", slug: "guides/the-statusline" },
            { label: "Override a Gate Safely", slug: "guides/overriding-a-gate" },
            { label: "Troubleshooting", slug: "guides/troubleshooting" },
            { label: "Uninstall & Disable", slug: "guides/uninstalling" },
            { label: "Explore Untrusted Code", slug: "guides/ca-sandbox" },
          ],
        },
        {
          label: "Understand",
          collapsed: true,
          items: [
            { label: "Concept Map", slug: "concepts" },
            { label: "The Gated-Lane Model", slug: "concepts/gated-lanes" },
            { label: "SMARTS", slug: "concepts/smarts" },
            { label: "Enforcement & Security", slug: "enforcement" },
            { label: "Provenance and Context Drift", slug: "concepts/provenance-drift" },
            { label: "ADRs and the Decision Log", slug: "concepts/adrs" },
            { label: "Just-in-Time Context Injection", slug: "concepts/jit-context-injection" },
            { label: "Checkpoints", slug: "concepts/checkpoints" },
            { label: "The Persona-Register Split", slug: "concepts/persona-and-context" },
            { label: "Auditability", slug: "concepts/auditability" },
            { label: "Selected Hardening Notes", slug: "concepts/hardening-history" },
          ],
        },
        {
          label: "Reference",
          collapsed: true,
          items: [
            { label: "The .codearbiter/ Directory", slug: "codearbiter-directory" },
            { label: "Configuration", slug: "reference/configuration" },
            { label: "Glossary", slug: "glossary" },
            { label: "All Reference", slug: "reference" },
            { label: "Hooks Reference", slug: "hooks" },
            { label: "Hook Gates", slug: "reference/hooks-gates" },
            { label: "Changelog", slug: "changelog" },
            ...referenceGroups,
          ],
        },
        {
          label: "Labs",
          collapsed: true,
          items: [
            { label: "What Is the Feature Forge", slug: "feature-forge/overview" },
            { label: "What's in the Forge", slug: "feature-forge/whats-in-the-forge" },
            { label: "Use a Preview Feature", slug: "feature-forge/using-preview-features" },
          ],
        },
      ],
    }),
  ],
});
