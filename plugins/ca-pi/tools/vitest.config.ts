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
  },
});
