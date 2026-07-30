/** astro-config.test.ts — the base-path-safety mechanism, pinned.
 *
 * `rehypeBaseLinks` is what stops root-absolute markdown links (`](/overview)`)
 * from 404-ing once the site is served from the `/codeArbiter/` subpath. Its
 * unit test (rehype-base-links.test.ts) proves the plugin transforms a HAST
 * tree; nothing proved the plugin was still *wired into Astro* or that the
 * wiring used a supported API.
 *
 * Astro 7.1 deprecated `markdown.remarkPlugins` / `markdown.rehypePlugins` /
 * `markdown.remarkRehype` ("will be removed in a future major") in favour of
 * `markdown.processor: unified({ ... })` from `@astrojs/markdown-remark`. A
 * silent removal of those keys in Astro 8 would drop the plugin and un-base
 * every markdown link. These cases fail if the config regresses onto the
 * deprecated keys, and fail if the configured processor stops base-prefixing.
 */
import { describe, it, expect } from "vitest";
import { isUnifiedProcessor } from "@astrojs/markdown-remark";
// astro.config.mjs is plain JS outside the tsconfig program; the shape we
// assert on is checked here at runtime instead.
// @ts-expect-error -- untyped .mjs config module
import config from "../astro.config.mjs";

const BASE = "/codeArbiter";

describe("astro.config markdown wiring", () => {
  it("configures no markdown plugins through the deprecated top-level keys", () => {
    expect(config.markdown?.remarkPlugins).toBeUndefined();
    expect(config.markdown?.rehypePlugins).toBeUndefined();
    expect(config.markdown?.remarkRehype).toBeUndefined();
  });

  it("wires both local rehype plugins onto an explicit unified processor", () => {
    const processor = config.markdown?.processor;
    expect(processor).toBeDefined();
    expect(isUnifiedProcessor(processor)).toBe(true);
    expect(processor.options.rehypePlugins).toHaveLength(2);
  });

  it("base-prefixes a root-absolute markdown link through the configured processor", async () => {
    const renderer = await config.markdown.processor.createRenderer({});
    const { code } = await renderer.render("[Overview](/overview)");

    expect(code).toContain(`href="${BASE}/overview"`);
    expect(code).not.toContain(`href="/overview"`);
  });

  it("leaves an external link untouched through the configured processor", async () => {
    const renderer = await config.markdown.processor.createRenderer({});
    const { code } = await renderer.render("[GitHub](https://github.com/arbiterForge/codeArbiter)");

    expect(code).toContain(`href="https://github.com/arbiterForge/codeArbiter"`);
  });

  it("wraps rendered markdown tables through the configured processor", async () => {
    const renderer = await config.markdown.processor.createRenderer({});
    const { code } = await renderer.render("| Reviewer | Checks |\n|---|---|\n| security | gates |");

    expect(code).toContain('<div class="ca-table-shell">');
    expect(code).toContain("<table>");
  });
});
