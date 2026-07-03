/** extract-hook-gates.ts — scans `plugins/ca/hooks/*.py` for `block()`/`remind()`
 * call sites whose gate tag is a literal `"H-<digits><letter?>"` string, and
 * extracts the user-visible message text those calls print.
 *
 * Hooks are code, not prose (see the docs-site-overhaul spec, decision d): the
 * hooks reference page is generated from these call sites rather than
 * hand-transcribed, so it can never drift from what a hook actually prints.
 *
 * `_hooklib.py` defines `block(tag, msg)` / `remind(tag, msg)` themselves —
 * those definition sites take `tag` as a parameter, never a string literal, so
 * the literal-tag regex below never matches them; no special-case exclusion is
 * needed for the definition file itself.
 */
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

/** One `block()`/`remind()` call site with a literal `"H-xx"` tag. */
export interface HookCallSite {
  tag: string;
  kind: "block" | "remind";
  file: string;
  line: number;
  message: string;
}

/** A `block()`/`remind()` call whose first argument was NOT a literal tag string. */
export interface SkippedCallSite {
  file: string;
  line: number;
}

export interface ExtractResult {
  callSites: HookCallSite[];
  skipped: SkippedCallSite[];
}

/** 1-based line number of `index` within `content`. */
function lineOf(content: string, index: number): number {
  let line = 1;
  for (let i = 0; i < index && i < content.length; i++) {
    if (content[i] === "\n") line++;
  }
  return line;
}

/** True iff `content[idx..]` starts a Python string literal (optional prefix
 * letters — f/F/r/R/b/B/u/U, up to two — followed by a quote char). Returns
 * the literal's quote-run length (1 or 3) and the index just past the opening
 * quote(s), or null if this is not a string start. */
function matchStringStart(
  content: string,
  idx: number,
): { quote: string; quoteLen: number; contentStart: number } | null {
  let i = idx;
  let prefixLen = 0;
  while (prefixLen < 2 && /[fFrRbBuU]/.test(content[i + prefixLen] ?? "")) {
    prefixLen++;
  }
  const q = content[i + prefixLen];
  if (q !== '"' && q !== "'") return null;
  const tripleStart = i + prefixLen;
  const isTriple =
    content[tripleStart + 1] === q && content[tripleStart + 2] === q;
  const quoteLen = isTriple ? 3 : 1;
  return { quote: q, quoteLen, contentStart: tripleStart + quoteLen };
}

/** Unescape the common escape sequences inside a Python string literal body. */
function unescapePython(raw: string): string {
  return raw
    .replace(/\\n/g, "\n")
    .replace(/\\t/g, "\t")
    .replace(/\\"/g, '"')
    .replace(/\\'/g, "'")
    .replace(/\\\\/g, "\\");
}

/** Consume one string literal starting at `content[idx]` (which must satisfy
 * `matchStringStart`). Returns the literal's unescaped body and the index
 * just past the closing quote(s). */
function consumeString(
  content: string,
  idx: number,
): { body: string; endIdx: number } {
  const start = matchStringStart(content, idx);
  if (!start) {
    throw new Error(`consumeString called at non-string position ${idx}`);
  }
  const closer = start.quote.repeat(start.quoteLen);
  let i = start.contentStart;
  while (i < content.length) {
    if (content[i] === "\\") {
      i += 2;
      continue;
    }
    if (content.slice(i, i + closer.length) === closer) {
      return {
        body: unescapePython(content.slice(start.contentStart, i)),
        endIdx: i + closer.length,
      };
    }
    i++;
  }
  // Unterminated literal (malformed source) — consume to EOF rather than loop forever.
  return {
    body: unescapePython(content.slice(start.contentStart)),
    endIdx: content.length,
  };
}

/**
 * Scan a `block(`/`remind(` call's argument list starting just after the
 * `tag,` prefix already matched by the caller (so we are one `(` deep),
 * concatenating every literal string segment found at that depth into the
 * message. Non-literal glue (`+`, whitespace, a trailing function call like
 * `_read_err_hint()`) is walked over for correct paren-depth tracking but
 * contributes nothing to the message text.
 */
function scanMessage(content: string, startIdx: number): { message: string; endIdx: number } {
  let depth = 1;
  let i = startIdx;
  let message = "";
  while (i < content.length && depth > 0) {
    const ch = content[i];
    if (ch === '"' || ch === "'" || /[fFrRbBuU]/.test(ch)) {
      const strStart = matchStringStart(content, i);
      if (strStart) {
        const { body, endIdx } = consumeString(content, i);
        if (depth === 1) message += body;
        i = endIdx;
        continue;
      }
    }
    if (ch === "(") {
      depth++;
      i++;
      continue;
    }
    if (ch === ")") {
      depth--;
      i++;
      continue;
    }
    i++;
  }
  return { message, endIdx: i };
}

const LITERAL_TAG_CALL_RE = /\b(block|remind)\(\s*"(H-\d+[a-z]?)"\s*,/g;
const ANY_CALL_RE = /\b(block|remind)\(/g;

/**
 * Build a per-index "is real code" mask for a whole file: `false` inside a `#`
 * comment or any string/docstring literal, `true` everywhere else.
 *
 * `_hooklib.py`'s own module docstring and inline comments mention
 * `block(tag, msg)` / `block()`/`remind()` in prose while documenting the
 * public API — without this mask those textual mentions look like call sites
 * with a non-literal (variable) tag and would pollute the `skipped` census.
 */
function computeCodeMask(content: string): boolean[] {
  const mask = new Array<boolean>(content.length).fill(true);
  let i = 0;
  while (i < content.length) {
    const ch = content[i];
    if (ch === "#") {
      const start = i;
      while (i < content.length && content[i] !== "\n") i++;
      mask.fill(false, start, i);
      continue;
    }
    if (ch === '"' || ch === "'" || /[fFrRbBuU]/.test(ch)) {
      const strStart = matchStringStart(content, i);
      if (strStart) {
        const start = i;
        const { endIdx } = consumeString(content, i);
        mask.fill(false, start, endIdx);
        i = endIdx;
        continue;
      }
    }
    i++;
  }
  return mask;
}

/** Extract every `block(`/`remind(` call site from one file's raw content. */
function extractFromFile(file: string, content: string): ExtractResult {
  const callSites: HookCallSite[] = [];
  const claimedSpans: Array<[number, number]> = [];
  const codeMask = computeCodeMask(content);

  LITERAL_TAG_CALL_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = LITERAL_TAG_CALL_RE.exec(content)) !== null) {
    const kind = m[1] as "block" | "remind";
    const tag = m[2];
    const matchStart = m.index;
    const argsStart = LITERAL_TAG_CALL_RE.lastIndex;
    const { message, endIdx } = scanMessage(content, argsStart);
    claimedSpans.push([matchStart, endIdx]);
    callSites.push({
      tag,
      kind,
      file,
      line: lineOf(content, matchStart),
      message,
    });
    // scanMessage may have consumed past lastIndex (multi-line call); keep the
    // regex cursor from re-scanning inside the call we just extracted.
    LITERAL_TAG_CALL_RE.lastIndex = Math.max(LITERAL_TAG_CALL_RE.lastIndex, endIdx);
  }

  const skipped: SkippedCallSite[] = [];
  ANY_CALL_RE.lastIndex = 0;
  while ((m = ANY_CALL_RE.exec(content)) !== null) {
    const matchStart = m.index;
    // A textual mention inside a comment or docstring (e.g. _hooklib.py's own
    // API-listing prose) is not a call site — skip.
    if (!codeMask[matchStart]) continue;
    // Definition sites ("def block(tag, msg):") are not calls — skip.
    const before = content.slice(Math.max(0, matchStart - 4), matchStart);
    if (before === "def ") continue;
    // Already captured as a literal-tag call site above — skip.
    if (claimedSpans.some(([s, e]) => matchStart >= s && matchStart < e)) continue;
    skipped.push({ file, line: lineOf(content, matchStart) });
  }

  return { callSites, skipped };
}

/**
 * Scan every top-level `*.py` file under `hooksDir` (non-recursive — the
 * `tests/` subdirectory is deliberately excluded) for `block()`/`remind()`
 * call sites with a literal `"H-xx"` tag.
 */
export function extractHookGates(hooksDir: string): ExtractResult {
  const files = readdirSync(hooksDir)
    .filter((f) => f.endsWith(".py"))
    .sort((a, b) => a.localeCompare(b));

  const callSites: HookCallSite[] = [];
  const skipped: SkippedCallSite[] = [];
  for (const file of files) {
    const content = readFileSync(join(hooksDir, file), "utf-8");
    const result = extractFromFile(file, content);
    callSites.push(...result.callSites);
    skipped.push(...result.skipped);
  }
  return { callSites, skipped };
}
