import { defineConfig } from "vitest/config";

/**
 * ca farm-dispatcher test harness.
 *
 * This tree needed no config until issue #507: the suite runs on vitest's
 * defaults, and an empty config would be noise. The coverage block is the whole
 * reason the file exists.
 *
 * `include` is scoped to this tree's own sources so the report measures
 * farm.ts / exec.ts / mutation.ts / redactor.ts / worktree-fs.ts rather than the
 * test files that exercise them - an unscoped v8 report counts the tests as
 * covered source and inflates every number.
 *
 * No `thresholds` here, deliberately. The maturity floor is applied by the tdd
 * (Phase 5) and refactor (Phase 2/6) skills, which read `stage:` from
 * .codearbiter/CONTEXT.md against plugins/ca/includes/maturity-coverage.md.
 * Encoding the number here would fork that single source of truth across three
 * package configs, and the three would drift the first time the stage moves.
 */
export default defineConfig({
  test: {
    coverage: {
      provider: "v8",
      include: ["*.ts"],
      exclude: ["*.test.ts", "*.config.ts"],
      reporter: ["text-summary", "html"],
    },
  },
});
