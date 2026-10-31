/** version-literal-drift.test.ts — hand-authored site content may not type a current version.
 *
 * A current version requirement belongs to the code that enforces it and reaches
 * the site through `%%fact=<name>%%` (scripts/version-facts.ts). Every other
 * version literal must be allowlisted with its category and the line context it
 * appears in: a dated historical record, an illustrative example, an external
 * third-party fact, or a sentinel. Allowlist entries that no longer match fail
 * too, so the list cannot quietly outgrow the content it describes.
 */
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { repositoryVersionFacts } from "../../scripts/version-facts";

const siteRoot = resolve(import.meta.dirname, "..", "..");

interface AllowedLiteral {
  file: string;
  literal: string;
  context: string;
  category: "historical" | "illustrative" | "external" | "sentinel";
  reason: string;
}

const allowlist = JSON.parse(
  readFileSync(join(siteRoot, "test", "content", "version-literal-allowlist.json"), "utf8"),
) as AllowedLiteral[];

/** Hand-authored surfaces. Generated pages are gitignored and owned by their sources. */
const SCANNED = /^(src\/content\/docs\/.*\.mdx?|src\/curated\/.*\.md|src\/components\/.*\.astro|src\/pages\/.*|src\/data\/.*\.json|src\/[^/]+\.ts|scripts\/[^/]+\.ts|scripts\/generator\/[^/]+\.ts)$/;
const VERSION = /(?<![\w.])v?(\d+\.\d+\.\d+(?:-[0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*)?)(?!\.?\d)|(?<![\w.])(\d+\.\d+)(?=\+| or (?:newer|later))/g;
const SVG_GEOMETRY = /\s(?:d|points|viewBox|transform)="[^"]*"/g;

function scannedFiles(): string[] {
  return execFileSync("git", ["ls-files", "--cached", "--others", "--exclude-standard"], {
    cwd: siteRoot,
    encoding: "utf8",
  }).split("\n").filter((path) => SCANNED.test(path) && !/\.test\.ts$/.test(path));
}

interface Occurrence {
  file: string;
  line: number;
  literal: string;
  text: string;
}

function occurrences(): Occurrence[] {
  const found: Occurrence[] = [];
  for (const file of scannedFiles()) {
    let source = readFileSync(join(siteRoot, file), "utf8");
    if (file.endsWith(".astro")) source = source.replace(SVG_GEOMETRY, "");
    source.split(/\r?\n/).forEach((text, index) => {
      for (const match of text.matchAll(VERSION)) {
        found.push({ file, line: index + 1, literal: match[1] ?? `${match[2]}+`, text });
      }
    });
  }
  return found;
}

function allows(entry: AllowedLiteral, occurrence: Occurrence): boolean {
  return entry.file === occurrence.file
    && entry.literal === occurrence.literal
    && occurrence.text.includes(entry.context);
}

describe("version literal drift gate", () => {
  const found = occurrences();

  it("scans the hand-authored site surfaces", () => {
    expect(scannedFiles().length).toBeGreaterThan(50);
  });

  it("allows no untokenized current-version literal in hand-authored content", () => {
    const offenders = found
      .filter((occurrence) => !allowlist.some((entry) => allows(entry, occurrence)))
      .map(({ file, line, literal }) => `${file}:${line} ${literal}`);
    expect(
      offenders,
      "Use %%fact=<name>%% (scripts/version-facts.ts) for a current version, or allowlist a dated "
        + "historical, illustrative, external, or sentinel literal in version-literal-allowlist.json",
    ).toEqual([]);
  });

  it("keeps every allowlist entry categorized, reasoned, and still in use", () => {
    for (const entry of allowlist) {
      expect(["historical", "illustrative", "external", "sentinel"]).toContain(entry.category);
      expect(entry.reason.trim().length).toBeGreaterThan(10);
    }
    const unused = allowlist
      .filter((entry) => !found.some((occurrence) => allows(entry, occurrence)))
      .map(({ file, literal, context }) => `${file} ${literal} "${context}"`);
    expect(unused).toEqual([]);
  });

  it("references only version facts that exist", () => {
    const facts = repositoryVersionFacts();
    const unknown: string[] = [];
    for (const file of scannedFiles()) {
      // Syntax descriptions such as `%%fact=<name>%%` are not references; the build rejects malformed tokens.
      for (const match of readFileSync(join(siteRoot, file), "utf8").matchAll(/%%fact=([a-zA-Z][\w.-]*)%%/g)) {
        if (!Object.hasOwn(facts, match[1])) unknown.push(`${file} ${match[1]}`);
      }
    }
    expect(unknown).toEqual([]);
  });
});
