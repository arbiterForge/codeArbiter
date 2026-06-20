import { defineConfig } from "vitest/config";

/**
 * ca-sandbox driver test harness. Docker-gated tests guard themselves behind a
 * `docker info` probe at runtime (see individual *.test.ts), so the default run
 * stays green on a host without Docker. testTimeout is generous because the
 * docker-backed suites build/run real ephemeral containers.
 *
 * fileParallelism is disabled: the docker-gated suites each build/run containers,
 * and running multiple suites concurrently overloads the host and gets containers
 * OOM-killed (exit 137) non-deterministically. Serial files trade wall-clock for a
 * deterministic, green suite — the right call for a docker integration harness.
 */
export default defineConfig({
  test: {
    include: ["**/*.test.ts"],
    testTimeout: 300_000,
    hookTimeout: 300_000,
    fileParallelism: false,
  },
});
