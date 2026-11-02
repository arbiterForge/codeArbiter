/** normalize.ts - make a captured run byte-identical across machines (AC-05).
 *
 * A capture made on Windows and one made on Linux must agree, so everything
 * that varies by machine or by minute is replaced before it is recorded:
 * temporary paths, commit SHAs, timestamps and line endings. The replacements
 * are visible tokens (`<project>`, `<timestamp>`, `<commit>`), never plausible
 * fake values, so a reader can see what was normalized.
 *
 * Source hashing lives here too, because it has the same line-ending concern:
 * CI checks the captures out on Linux while they are made on Windows.
 */

import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

/** A directory whose every spelling in the output becomes `token`. */
export interface PathAlias {
  path: string;
  token: string;
}

export interface NormalizeOptions {
  /** Known roots. Longer paths win, so a project inside a fixture keeps its own token. */
  aliases?: readonly PathAlias[];
}

/** Prefix every capture fixture directory carries; the fallback rule keys on it. */
export const FIXTURE_PREFIX = "codearbiter-capture-";
/** Token for a fixture root no alias named. */
export const FIXTURE_TOKEN = "<fixture>";
export const TIMESTAMP_TOKEN = "<timestamp>";
export const COMMIT_TOKEN = "<commit>";

/** One or two backslashes (JSON-escaped), or a slash. */
const SEPARATOR = String.raw`(?:\\{1,2}|/)`;
/** The rest of a path after a known root: stops at whitespace, quotes, angle brackets and pipes. */
const TAIL = String.raw`((?:(?:\\{1,2}|/)[^\s"'<>|\x60]*)*)`;

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** A regex source matching every spelling of `path`: either slash, doubled backslash, any case, and `/c/` for `C:`. */
function pathSource(path: string): string {
  const drive = /^([A-Za-z]):[\\/]+/.exec(path);
  const segments = path.replace(/^[A-Za-z]:/, "").split(/[\\/]+/).filter(Boolean).map(escapeRegExp);
  const body = segments.join(`${SEPARATOR}+`);
  // Not the middle of a longer word or path, which would make the token swallow a prefix.
  const start = String.raw`(?<![\w.~-])`;
  if (drive) {
    const letter = escapeRegExp(drive[1]);
    return `${start}(?:${letter}:${SEPARATOR}+|/${letter}/)${body}`;
  }
  return `${start}${SEPARATOR}+${body}`;
}

function convertTail(tail: string): string {
  return tail.replace(/\\{1,2}/g, "/");
}

function replaceAlias(text: string, alias: PathAlias): string {
  const expression = new RegExp(`${pathSource(alias.path)}(?![\\w-])${TAIL}`, "gi");
  return text.replace(expression, (_match, tail: string) => `${alias.token}${convertTail(tail)}`);
}

/** A fixture directory nobody named: any path ending in the fixture prefix plus its random suffix. */
const GENERIC_FIXTURE = new RegExp(
  String.raw`(?:(?:[A-Za-z]:)?${SEPARATOR})?(?:[^\s"'<>|\x60\\/]+${SEPARATOR})*${escapeRegExp(FIXTURE_PREFIX)}[A-Za-z0-9_-]+${TAIL}`,
  "g",
);

const TIMESTAMP = /\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?/g;
const COMMIT = /\b[0-9a-f]{40}\b/g;

function normalizeCore(raw: string, options: NormalizeOptions): string {
  let text = raw.replace(/\r\n/g, "\n");
  const aliases = [...(options.aliases ?? [])].sort((a, b) => b.path.length - a.path.length);
  for (const alias of aliases) text = replaceAlias(text, alias);
  text = text.replace(GENERIC_FIXTURE, (_match, tail: string) => `${FIXTURE_TOKEN}${convertTail(tail)}`);
  text = text.replace(TIMESTAMP, TIMESTAMP_TOKEN);
  text = text.replace(COMMIT, COMMIT_TOKEN);
  return text;
}

/** Normalize a captured stream: paths, timestamps, commit SHAs and line endings; trailing blank lines are dropped. */
export function normalizeText(raw: string, options: NormalizeOptions = {}): string {
  return normalizeCore(raw, options).trimEnd();
}

/** Normalize each argv entry with the same rules, leaving surrounding whitespace untouched. */
export function normalizeArgv(argv: readonly string[], options: NormalizeOptions = {}): string[] {
  return argv.map((entry) => normalizeCore(entry, options));
}

/** SHA-256 of the exact bytes. Release applicability digests the hook this way; do not change it. */
export function sha256Raw(bytes: Uint8Array | string): string {
  return createHash("sha256").update(bytes).digest("hex");
}

/** The same bytes with each CRLF pair collapsed to LF. A lone CR is data and is kept. */
export function lfBytes(bytes: Uint8Array): Buffer {
  const out = Buffer.allocUnsafe(bytes.length);
  let length = 0;
  for (let index = 0; index < bytes.length; index += 1) {
    if (bytes[index] === 0x0d && bytes[index + 1] === 0x0a) continue;
    out[length] = bytes[index];
    length += 1;
  }
  return out.subarray(0, length);
}

/** SHA-256 over LF-normalized bytes, so a Windows CRLF checkout and a Linux LF checkout agree. */
export function sha256Lf(bytes: Uint8Array): string {
  return sha256Raw(lfBytes(bytes));
}

export function hashFileLf(path: string): string {
  return sha256Lf(readFileSync(path));
}
