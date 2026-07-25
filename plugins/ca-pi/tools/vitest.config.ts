import { defineConfig } from "vitest/config";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";

const secretCorpus = JSON.parse(readFileSync(fileURLToPath(new URL("../../ca/hooks/secret-detection-corpus.json", import.meta.url)), "utf8")) as { must_match: string[] };
const hosts = JSON.parse(readFileSync(fileURLToPath(new URL("../../../core/hosts.json", import.meta.url)), "utf8")) as {
  hosts: Array<{ name: string; package?: { skill_expansion_fingerprints?: Record<string, string> } }>;
};
const expansionFingerprints = hosts.hosts.find((host) => host.name === "pi")?.package?.skill_expansion_fingerprints;
const childFingerprint = createHash("sha256").update(
  readFileSync(fileURLToPath(new URL("../extensions/codearbiter-child.js", import.meta.url))),
).digest("hex");

export default defineConfig({
  define: {
    __CODEARBITER_SECRET_CORPUS__: JSON.stringify(secretCorpus.must_match),
    __CODEARBITER_PI_SKILL_EXPANSION_FINGERPRINTS__: JSON.stringify(expansionFingerprints),
    __CODEARBITER_PI_CHILD_SHA256__: JSON.stringify(childFingerprint),
  },
  test: {
    environment: "node",
    fileParallelism: false,
    // Issue #464: security-controls.md states that tests use disposable Pi
    // homes and dummy credentials and never inspect the real auth store. This
    // makes that true by construction rather than per test file - the request
    // fixture spreads process.env, so a home redirected here is inherited by
    // every case that does not set its own.
    // Absolute, derived from this config's own URL. A relative entry resolves
    // against vitest's `root`, which is the REPO root when the security
    // contract invokes `vitest run plugins/ca-pi/tools/test/...` from there -
    // and a setup file that silently does not load is worse than none, since
    // the suite then runs against the operator's real home while looking fine.
    setupFiles: [fileURLToPath(new URL("./test/setup-disposable-home.ts", import.meta.url))],
  },
});
