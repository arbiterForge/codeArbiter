/** version-facts.test.ts — current versions come from the source that enforces them, or the build fails. */
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  loadVersionFacts,
  remarkVersionFacts,
  repositoryVersionFacts,
  resolveFactTokens,
  type SourceReader,
} from "../../scripts/version-facts";

const repoRoot = resolve(import.meta.dirname, "..", "..", "..");
const real: SourceReader = (path) => readFileSync(join(repoRoot, path), "utf8");

/** Real sources with one file's bytes replaced. */
function withSource(path: string, transform: (text: string) => string): SourceReader {
  return (requested) => (requested === path ? transform(real(requested)) : real(requested));
}

describe("version facts", () => {
  it("reads each fact from its owning source", () => {
    const facts = repositoryVersionFacts();
    expect(facts["pi.supported"].source).toBe("plugins/ca-pi/tools/src/compatibility.ts");
    expect(real("plugins/ca-pi/tools/src/compatibility.ts")).toContain(`"${facts["pi.supported"].value}"`);
    expect(real(".github/workflows/ci.yml")).toContain(`"${facts["codex.minimum"].value}"`);
    expect(real("plugins/ca/hooks/_adrlifecyclegit.py")).toContain(`Git ${facts["git.adrMinimum"].value}+`);
    expect(JSON.parse(real("plugins/ca/.claude-plugin/plugin.json")).version).toBe(facts["ca.version"].value);
    expect(facts["receipt.current"].value).not.toBe(facts["receipt.legacy"].value);
  });

  it("follows a changed declaration instead of keeping the published number", () => {
    const facts = loadVersionFacts(withSource(
      "plugins/ca-pi/tools/src/compatibility.ts",
      (text) => text.replace(/new Set\(\[[^\]]*\]\)/, 'new Set(["9.8.7", "9.8.10"])'),
    ));
    expect(facts["pi.supported"].value).toBe("9.8.7 or 9.8.10");
  });

  it.each([
    ["a missing declaration", (text: string) => text.replace(/SUPPORTED_PI_VERSIONS = /, "RENAMED = ")],
    ["a duplicated declaration", (text: string) => `${text}\nconst SUPPORTED_PI_VERSIONS = new Set(["1.0.0"]);\n`],
    ["a non-SemVer entry", (text: string) => text.replace(/new Set\(\[[^\]]*\]\)/, 'new Set(["latest"])')],
  ])("fails closed on %s", (_case, transform) => {
    expect(() => loadVersionFacts(withSource("plugins/ca-pi/tools/src/compatibility.ts", transform)))
      .toThrow(/pi\.supported/);
  });

  it("rejects a Codex minimum that disagrees with the lowest CI-verified host", () => {
    expect(() => loadVersionFacts(withSource(
      "plugins/ca-codex/.codex-plugin/plugin.json",
      (text) => text.replace(/Codex >= \d+\.\d+\.\d+\./, "Codex >= 0.1.0."),
    ))).toThrow(/codex\.minimum.*lowest CI-verified/);
  });

  it("treats an unreadable release record as an error, not an absent one", () => {
    const read: SourceReader = (path) => {
      if (path === "site/src/generated/release-applicability.json") throw Object.assign(new Error("denied"), { code: "EACCES" });
      return real(path);
    };
    expect(() => loadVersionFacts(read)).toThrow(/denied/);
  });
});

describe("fact tokens", () => {
  const facts = { "pi.supported": { value: "1.2.3", source: "x" } };

  it("replaces known tokens", () => {
    expect(resolveFactTokens("Pi %%fact=pi.supported%% only", facts, "t")).toBe("Pi 1.2.3 only");
  });

  it.each([
    ["unknown", "Pi %%fact=pi.nope%%", /Unknown version fact "pi\.nope"/],
    ["malformed", "Pi %%fact= pi.supported%%", /Malformed version fact token/],
    // A markdown extension (Starlight's text directives took `:name`) can split a token apart.
    ["split", "Pi %%fact", /Malformed version fact token/],
  ])("throws on an %s token instead of publishing it", (_case, text, message) => {
    expect(() => resolveFactTokens(text, facts, "t")).toThrow(message);
  });

  it("resolves prose, inline code, and fenced code in the markdown tree", () => {
    const tree = {
      type: "root",
      children: [
        { type: "paragraph", children: [{ type: "text", value: "Pi %%fact=pi.supported%%" }] },
        { type: "inlineCode", value: "pi@%%fact=pi.supported%%" },
        { type: "code", value: "version %%fact=pi.supported%%" },
      ],
    };
    remarkVersionFacts(facts)()(tree, { path: "page.md" });
    expect(JSON.stringify(tree)).not.toContain("%%fact=");
    expect(JSON.stringify(tree)).toContain("pi@1.2.3");
    expect(JSON.stringify(tree)).toContain("version 1.2.3");
  });
});
