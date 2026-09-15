import currentConfig from "../../astro.config.mjs";
import { fileURLToPath } from "node:url";

export default {
  ...currentConfig,
  base: "/docs/",
  root: fileURLToPath(new URL("../../", import.meta.url)),
  outDir: fileURLToPath(new URL("../../.academy-non-root-dist/", import.meta.url)),
};
