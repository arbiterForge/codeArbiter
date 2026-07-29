import { defineConfig } from "vitest/config";

/**
 * Docs-site test harness.
 *
 * The coverage block exists because of issue #514 / DECISION-0032: `site/` is a
 * fourth tested TypeScript tree, and until now `tdd` Phase 5 reached it with no
 * command to run and took the no-tooling exemption on a tree that has real
 * suites. That is the #507 failure mode - a gate that reads as satisfied
 * without executing.
 *
 * `include` is scoped to `scripts/`, which is what the suites actually exercise:
 * the generator that turns the plugin trees into site content, plus the
 * link-audit and rehype helpers. Deliberately NOT `src/` - those are Astro
 * components rendered at build time, covered by the build and the link audit, so
 * counting them here would report a large permanently-dark surface no test in
 * this tree was ever meant to reach.
 *
 * No `thresholds` here, for the same reason the plugin trees omit them: the
 * maturity floor is applied by the `tdd` and `refactor` skills, reading `stage:`
 * from CONTEXT.md against `includes/maturity-coverage.md`. Encoding the number
 * in four vitest configs would fork one source of truth four ways.
 *
 * Per DECISION-0031 this tree carries no platform fork, so it stays single-host
 * and its figure needs no union.
 */
export default defineConfig({
  test: {
    include: ["test/**/*.test.ts"],
    environment: "node",
    coverage: {
      provider: "v8",
      include: ["scripts/**/*.ts"],
      exclude: ["scripts/**/*.test.ts"],
      reporter: ["text-summary", "html"],
    },
  },
});
