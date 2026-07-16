import { build } from "esbuild";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const descriptor = JSON.parse(await readFile(resolve("../../../core/hosts.json"), "utf8"));
const secretCorpusDocument = JSON.parse(await readFile(resolve("../../ca/hooks/secret-detection-corpus.json"), "utf8"));
const piHost = descriptor.hosts?.find((host) => host.name === "pi");
const toolClasses = piHost?.tool_classes;
const expansionFingerprints = piHost?.package?.skill_expansion_fingerprints;
const categories = new Set(["EXEC", "WRITE", "EDIT", "READ", "OTHER"]);
if (
  toolClasses === null
  || typeof toolClasses !== "object"
  || Array.isArray(toolClasses)
  || Object.entries(toolClasses).some(([name, category]) => name === "" || !categories.has(category))
) {
  throw new Error("core/hosts.json has no valid Pi tool_classes descriptor");
}
if (!Array.isArray(secretCorpusDocument.must_match) || secretCorpusDocument.must_match.some((item) => typeof item !== "string" || item === "")) {
  throw new Error("shared secret-detection-corpus.json has no valid must_match corpus");
}
if (
  expansionFingerprints === null
  || typeof expansionFingerprints !== "object"
  || Array.isArray(expansionFingerprints)
  || JSON.stringify(Object.keys(expansionFingerprints).sort()) !== JSON.stringify(["0.80.5", "0.80.6"])
  || Object.values(expansionFingerprints).some((value) => typeof value !== "string" || !/^[a-f0-9]{64}$/u.test(value))
) {
  throw new Error("core/hosts.json has no exact Pi skill expansion fingerprint matrix");
}

const external = [
  "@earendil-works/pi-coding-agent",
  "@earendil-works/pi-ai",
  "@earendil-works/pi-agent-core",
  "@earendil-works/pi-tui",
  "typebox",
];

const shared = {
  bundle: true,
  external,
  format: "esm",
  logLevel: "info",
  platform: "node",
  sourcemap: false,
  target: "node22",
  define: {
    __CODEARBITER_PI_TOOL_CLASSES__: JSON.stringify(toolClasses),
    __CODEARBITER_SECRET_CORPUS__: JSON.stringify(secretCorpusDocument.must_match),
    __CODEARBITER_PI_SKILL_EXPANSION_FINGERPRINTS__: JSON.stringify(expansionFingerprints),
  },
};

await build({
  ...shared,
  entryPoints: ["src/windows-supervisor.ts"],
  outfile: "../helpers/windows-supervisor.js",
});

await build({
  ...shared,
  entryPoints: ["src/child-extension.ts"],
  outfile: "../extensions/codearbiter-child.js",
});
const childBytes = await readFile("../extensions/codearbiter-child.js");
const childFingerprint = createHash("sha256").update(childBytes).digest("hex");
await build({
  ...shared,
  define: {
    ...shared.define,
    __CODEARBITER_PI_CHILD_SHA256__: JSON.stringify(childFingerprint),
  },
  entryPoints: ["src/extension.ts"],
  outfile: "../extensions/codearbiter.js",
});
