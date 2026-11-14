// Original test/coverage population preserved; private output/cache destinations.
import original from "./vitest-project/vitest.config.ts";
export default {
  ...original,
  root: new URL("./vitest-project/", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"),
  cacheDir: new URL("./private-vite-cache/", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"),
  test: {
    ...original.test,
    coverage: { ...original.test.coverage,
      reportsDirectory: new URL("./actual-vitest-coverage/", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"),
      reporter: ["json", "json-summary", "text-summary"],
    },
  },
};
