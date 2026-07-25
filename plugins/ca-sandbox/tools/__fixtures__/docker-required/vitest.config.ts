import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

const HERE = fileURLToPath(new URL(".", import.meta.url));
const TOOLS = fileURLToPath(new URL("../../", import.meta.url));

/**
 * Config for the #406 reproduction fixture ONLY.
 *
 * The root vitest.config.ts excludes `__fixtures__/**`, so `gate.fixture.test.ts`
 * never runs in the normal suite — it exists to be launched as a child process
 * by docker-gate.test.ts with docker masked from PATH, where it is SUPPOSED to
 * fail. `root` is pinned to this directory so the fixture is the only file
 * collected, and `cacheDir` is pushed back up to the real node_modules so a
 * pinned root does not litter the fixture tree with a Vite cache.
 */
export default defineConfig({
  cacheDir: `${TOOLS}node_modules/.vite`,
  test: {
    root: HERE,
    include: ["*.fixture.test.ts"],
    testTimeout: 30_000,
  },
});
