/** verify.ts - fail the build when a capture no longer matches the tool it recorded (AC-06, DEC-04).
 *
 * Every capture lists the sha256 of the entry script and of each repository
 * module its run loaded. `npm run gen` calls assertCapturesFresh(), so a change
 * to any of those files fails with the capture, the changed source and the
 * refresh command named, instead of leaving the guides showing output the tool
 * no longer produces. Run as a script it checks the committed captures:
 *
 *   tsx scripts/capture/verify.ts [--repo DIR] [--captures DIR]
 */

import { existsSync, readFileSync, readdirSync } from "node:fs";
import { basename, isAbsolute, join, relative, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { hashFileLf } from "./normalize";

export const REFRESH_COMMAND = "npm run capture";

export interface StaleFinding {
  /** The capture's id: its file name without `.json`. */
  capture: string;
  file: string;
  /** Repository-relative path of the changed source, when the finding is about one. */
  source?: string;
  problem: "changed" | "missing" | "malformed";
  recorded?: string;
  actual?: string;
  detail?: string;
}

export interface VerifyResult {
  captures: string[];
  findings: StaleFinding[];
}

const SHA256 = /^[0-9a-f]{64}$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function malformed(capture: string, file: string, detail: string): StaleFinding {
  return { capture, file, problem: "malformed", detail };
}

/** Check one capture file against the working tree. */
function verifyOne(repoRoot: string, capturesDir: string, file: string): StaleFinding[] {
  const capture = basename(file, ".json");
  let record: unknown;
  try {
    record = JSON.parse(readFileSync(join(capturesDir, file), "utf8"));
  } catch (error) {
    return [malformed(capture, file, `is not valid JSON (${(error as Error).message})`)];
  }
  if (!isRecord(record)) return [malformed(capture, file, "is not a JSON object")];
  if (record.id !== capture) return [malformed(capture, file, `has id ${JSON.stringify(record.id)}, which must match its file name`)];
  if (typeof record.tool !== "string") return [malformed(capture, file, "has no tool path")];
  if (!Array.isArray(record.sources) || record.sources.length === 0) {
    return [malformed(capture, file, "records no source hashes")];
  }

  const findings: StaleFinding[] = [];
  const recordedPaths: string[] = [];
  for (const entry of record.sources) {
    if (!isRecord(entry) || typeof entry.path !== "string" || entry.path === "") {
      return [malformed(capture, file, "has a source entry without a path")];
    }
    const source = entry.path;
    recordedPaths.push(source);
    const absolute = resolve(repoRoot, source);
    const inside = relative(repoRoot, absolute);
    if (isAbsolute(source) || inside.startsWith("..") || isAbsolute(inside)) {
      findings.push(malformed(capture, file, `lists ${source}, which is outside the repository`));
      continue;
    }
    if (typeof entry.sha256 !== "string" || !SHA256.test(entry.sha256)) {
      findings.push(malformed(capture, file, `records no valid sha256 for ${source}`));
      continue;
    }
    if (!existsSync(absolute)) {
      findings.push({ capture, file, source, problem: "missing", recorded: entry.sha256 });
      continue;
    }
    const actual = hashFileLf(absolute);
    if (actual !== entry.sha256) findings.push({ capture, file, source, problem: "changed", recorded: entry.sha256, actual });
  }
  if (!recordedPaths.includes(record.tool)) {
    findings.push(malformed(capture, file, `does not hash its entry script ${record.tool}`));
  }
  return findings;
}

/** Compare every capture under `capturesDir` with the files it recorded. Never throws for a stale or broken capture. */
export function verifyCaptures(repoRoot: string, capturesDir: string): VerifyResult {
  const files = existsSync(capturesDir) ? readdirSync(capturesDir).filter((name) => name.endsWith(".json")).sort() : [];
  return {
    captures: files.map((file) => basename(file, ".json")),
    findings: files.flatMap((file) => verifyOne(repoRoot, capturesDir, file)),
  };
}

function describe(finding: StaleFinding): string {
  const where = `Capture "${finding.capture}" (${finding.file})`;
  if (finding.problem === "malformed") return `${where} is unusable: it ${finding.detail}.`;
  if (finding.problem === "missing") {
    return `${where} is stale: its source ${finding.source} no longer exists.`;
  }
  return (
    `${where} is stale: its source ${finding.source} changed after the capture was recorded ` +
    `(recorded ${finding.recorded!.slice(0, 12)}, now ${finding.actual!.slice(0, 12)}).`
  );
}

export function formatFindings(findings: readonly StaleFinding[]): string {
  return [
    ...findings.map(describe),
    `Run \`${REFRESH_COMMAND}\` to regenerate the captures from the current tools, review the diff, and commit the updated files.`,
  ].join("\n");
}

/** Throw, with the capture, the source and the refresh command named, unless every capture is fresh. Returns the capture ids. */
export function assertCapturesFresh(repoRoot: string, capturesDir: string): string[] {
  const { captures, findings } = verifyCaptures(repoRoot, capturesDir);
  if (captures.length === 0) {
    throw new Error(
      `No captures found in ${capturesDir}. The guides render their examples from captures, so an empty set ` +
        `would silently disable the stale-capture check. Run \`${REFRESH_COMMAND}\`.`,
    );
  }
  if (findings.length > 0) throw new Error(formatFindings(findings));
  return captures;
}

function option(args: readonly string[], name: string, fallback: string): string {
  const index = args.indexOf(name);
  return index >= 0 && args[index + 1] ? resolve(args[index + 1]) : fallback;
}

function main(args: readonly string[]): number {
  const siteRoot = resolve(import.meta.dirname, "..", "..");
  const repoRoot = option(args, "--repo", resolve(siteRoot, ".."));
  const capturesDir = option(args, "--captures", join(siteRoot, "src", "assets", "captures"));
  try {
    const captures = assertCapturesFresh(repoRoot, capturesDir);
    console.log(`Captures are fresh: ${captures.length} checked against the working tree (${captures.join(", ")})`);
    return 0;
  } catch (error) {
    console.error((error as Error).message);
    return 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  process.exit(main(process.argv.slice(2)));
}
