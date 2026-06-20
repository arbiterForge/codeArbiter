/**
 * Trivial smoke test: proves the vitest+tsx+esbuild toolchain runs at all and
 * can import a local .ts module. This is the harness enabler for T-01; the real
 * driver units (mounts/dephash/build/run/...) land in later tasks.
 */
import { describe, it, expect } from "vitest";
import { toolchainOk } from "./smoke.ts";

describe("ca-sandbox toolchain", () => {
  it("imports a local .ts module and runs a function", () => {
    expect(toolchainOk()).toBe(true);
  });
});
