/**
 * The #406 reproduction, as a real Vitest file.
 *
 * `docker-gate.test.ts` runs this through a child Vitest whose PATH has been
 * masked of docker, with CA_SANDBOX_REQUIRE_DOCKER=1, and asserts the child
 * exits NON-ZERO. That is the acceptance criterion the issue names: masking
 * Docker from PATH must reproduce a non-zero required-mode result rather than
 * the "exit 0, 31 tests skipped" the audit reproduced.
 *
 * It is excluded from the normal suite by the root vitest.config.ts and runs
 * ONLY under this directory's own config.
 */
import { it, expect } from "vitest";
import { dockerGate } from "../../docker-gate.ts";

// Module scope on purpose: this is exactly how every gated suite declares
// itself, so the throw has to happen during collection.
const d = dockerGate("fixture-layer");

d("a layer that must never be silently skipped in required mode", () => {
  it("would have proven containment", async () => {
    expect(true).toBe(true);
  });
});
