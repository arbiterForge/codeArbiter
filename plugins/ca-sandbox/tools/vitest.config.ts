import { configDefaults, defineConfig } from "vitest/config";

/**
 * ca-sandbox driver test harness.
 *
 * Docker-gated suites declare themselves through `dockerGate()` in
 * docker-gate.ts. On a developer machine an absent daemon still self-skips, so
 * the default run stays green on a host without Docker. Under
 * CA_SANDBOX_REQUIRE_DOCKER=1 — which required CI sets (issue #406) — an absent
 * daemon instead THROWS from module scope, so the run exits non-zero rather
 * than quietly deleting the isolation / mount / network / lifecycle / teardown
 * evidence for a plugin that clones UNTRUSTED repositories.
 *
 * testTimeout is generous because the docker-backed suites build/run real
 * ephemeral containers.
 *
 * fileParallelism is disabled: the docker-gated suites each build/run containers,
 * and running multiple suites concurrently overloads the host and gets containers
 * OOM-killed (exit 137) non-deterministically. Serial files trade wall-clock for a
 * deterministic, green suite — the right call for a docker integration harness.
 * It also keeps the append-only execution sentinel a serial write.
 *
 * `__fixtures__/**` is excluded: it holds the multistack build fixtures and the
 * #406 reproduction (`__fixtures__/docker-required/`), a test file that is
 * SUPPOSED to fail and is launched only as a child process by
 * docker-gate.test.ts.
 */
export default defineConfig({
  test: {
    include: ["**/*.test.ts"],
    exclude: [...configDefaults.exclude, "**/__fixtures__/**"],
    testTimeout: 300_000,
    hookTimeout: 300_000,
    fileParallelism: false,
    // Issue #507. `__fixtures__/**` is excluded for the same reason it is
    // excluded from `include` above: it holds build fixtures and the #406
    // reproduction, none of which is driver source. No `thresholds` - the
    // maturity floor is applied by the tdd/refactor skills from
    // .codearbiter/CONTEXT.md `stage:` against maturity-coverage.md.
    //
    // Note the docker gate interacts with this: on a host without Docker the
    // gated suites self-skip, so a local report reads LOWER than required CI's.
    // Compare against a run with CA_SANDBOX_REQUIRE_DOCKER=1 before concluding
    // this tree regressed.
    coverage: {
      provider: "v8",
      include: ["*.ts"],
      exclude: ["*.test.ts", "*.config.ts", "__fixtures__/**"],
      reporter: ["text-summary", "html"],
    },
  },
});
