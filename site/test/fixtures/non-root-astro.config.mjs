import { unified } from "@astrojs/markdown-remark";
import { rehypeBaseLinks } from "../../scripts/rehype-base-links.ts";
import { rehypeTableShell } from "../../scripts/rehype-table-shell.ts";
import currentConfig from "../../astro.config.mjs";
import { fileURLToPath } from "node:url";

export default {
  ...currentConfig,
  base: "/docs/",
  // The alternate base must reach the Markdown processor too, not only Astro routes.
  markdown: { ...currentConfig.markdown, processor: unified({
    rehypePlugins: [rehypeBaseLinks("/docs"), rehypeTableShell()],
  }) },
  root: fileURLToPath(new URL("../../", import.meta.url)),
  outDir: fileURLToPath(new URL("../../.academy-non-root-dist/", import.meta.url)),
};
