import { readFile } from "node:fs/promises";
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
