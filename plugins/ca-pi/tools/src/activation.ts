import { lstat, open, readFile } from "node:fs/promises";
import { homedir } from "node:os";
import { resolve } from "node:path";

const PYTHON_WHITESPACE = String.raw`[\t-\r\x1c-\x20\x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]`;
const DELIMITER = new RegExp(`^${PYTHON_WHITESPACE}*---${PYTHON_WHITESPACE}*$`, "u");
const ENABLED_MARKER = new RegExp(`^${PYTHON_WHITESPACE}*arb[i\u0130\u0131]ter:${PYTHON_WHITESPACE}*enabled${PYTHON_WHITESPACE}*$`, "iu");

export async function isEnabled(cwd: string): Promise<boolean> {
  try {
    const raw = await readFile(resolve(cwd, ".codearbiter", "CONTEXT.md"), "utf8");
    const lines = raw.split("\n");
    const first = (lines[0] ?? "").replace(/^\uFEFF+/u, "");
    if (!DELIMITER.test(first)) return false;
    let found = false;
    for (const line of lines.slice(1)) {
      if (DELIMITER.test(line)) return found;
      if (ENABLED_MARKER.test(line)) found = true;
    }
    return false;
  } catch {
    return false;
  }
}

const UPDATE_DOCUMENT_MAX_BYTES = 4_096;
const VERSION_RE = /^[vV]?(\d+(?:\.\d+)*)(?:[-+][0-9A-Za-z.-]+)?$/u;

async function readSmallRegularJson(path: string): Promise<Record<string, unknown> | undefined> {
  let handle: Awaited<ReturnType<typeof open>> | undefined;
  try {
    const before = await lstat(path);
    if (!before.isFile() || before.isSymbolicLink() || before.size > UPDATE_DOCUMENT_MAX_BYTES) return undefined;
    handle = await open(path, "r");
    const opened = await handle.stat();
    const afterOpen = await lstat(path);
    if (!opened.isFile() || opened.size > UPDATE_DOCUMENT_MAX_BYTES
      || !afterOpen.isFile() || afterOpen.isSymbolicLink()
      || opened.dev !== before.dev || opened.ino !== before.ino
      || afterOpen.dev !== opened.dev || afterOpen.ino !== opened.ino) return undefined;
    const buffer = Buffer.alloc(UPDATE_DOCUMENT_MAX_BYTES + 1);
    const { bytesRead } = await handle.read(buffer, 0, buffer.length, 0);
    if (bytesRead > UPDATE_DOCUMENT_MAX_BYTES) return undefined;
    const value = JSON.parse(buffer.subarray(0, bytesRead).toString("utf8")) as unknown;
    return typeof value === "object" && value !== null && !Array.isArray(value)
      ? value as Record<string, unknown>
      : undefined;
  } catch {
    return undefined;
  } finally {
    try { await handle?.close(); } catch { /* Update availability remains fail-soft. */ }
  }
}

function numericVersion(value: unknown): readonly number[] | undefined {
  if (typeof value !== "string" || value.length > 64) return undefined;
  const match = VERSION_RE.exec(value.trim());
  if (match === null) return undefined;
  return match[1]!.split(".").map(Number);
}

function isNewerVersion(candidate: unknown, installed: unknown): candidate is string {
  const left = numericVersion(candidate);
  const right = numericVersion(installed);
  if (left === undefined || right === undefined) return false;
  const length = Math.max(left.length, right.length);
  for (let index = 0; index < length; index += 1) {
    const difference = (left[index] ?? 0) - (right[index] ?? 0);
    if (difference !== 0) return difference > 0;
  }
  return false;
}

/** Read the established user-global update cache; no network or project-state access occurs. */
export async function readCachedUpdateVersion(packageRoot: string): Promise<string | undefined> {
  const [manifest, cache] = await Promise.all([
    readSmallRegularJson(resolve(packageRoot, "package.json")),
    readSmallRegularJson(resolve(homedir(), ".codearbiter", "update-state.json")),
  ]);
  return isNewerVersion(cache?.latest, manifest?.version) ? cache.latest : undefined;
}
