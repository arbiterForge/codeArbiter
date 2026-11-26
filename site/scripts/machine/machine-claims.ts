/** machine-claims.ts - check the behavior claims the machine page makes about the hooks.
 *
 * Hook IDs, messages and command names are compared with the generator's own
 * extraction (machine-model.ts). A few statements describe behavior instead:
 * which calls write to gate-events.log, and when the rules are injected again.
 * Each one names the smallest source fact it depends on, so a change to that
 * fact fails the build with the claim to re-review, while unrelated edits to
 * the same file do not.
 */

export type ClaimCheck =
  | { type: "python-function-calls"; file: string; function: string; call: string }
  | { type: "python-function-avoids"; file: string; function: string; call: string }
  | { type: "python-function-contains"; file: string; function: string; text: string }
  | { type: "contains"; file: string; text: string[] };

export interface MachineClaim {
  id: string;
  /** The sentence the page shows; it must stay true while the check passes. */
  statement: string;
  check: ClaimCheck;
}

/** Python source with comments removed and every string literal (docstrings included) emptied,
 *  so a call or text that only appears in prose cannot satisfy a check. */
export function pythonCode(source: string): string {
  let out = "";
  for (let i = 0; i < source.length;) {
    const c = source[i];
    if (c === "#") {
      while (i < source.length && source[i] !== "\n") i++;
    } else if (c === '"' || c === "'") {
      const quote = source.startsWith(c.repeat(3), i) ? c.repeat(3) : c;
      i += quote.length;
      while (i < source.length && !source.startsWith(quote, i) && (quote.length === 3 || source[i] !== "\n")) i += source[i] === "\\" ? 2 : 1;
      i += quote.length;
      out += '""';
    } else {
      out += c;
      i++;
    }
  }
  return out;
}

/** The body of a top-level `def name(...)`: everything after its (possibly multi-line) signature up
 *  to the next code line at column 0. Blank lines and column-0 comments stay inside the body. */
export function pythonFunctionBody(source: string, name: string): string | undefined {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const start = lines.findIndex((line) => line.startsWith(`def ${name}(`));
  if (start < 0) return undefined;
  let depth = 0;
  let header = start;
  for (; header < lines.length; header++) {
    const code = pythonCode(lines[header]);
    for (const ch of code) depth += ch === "(" ? 1 : ch === ")" ? -1 : 0;
    if (depth <= 0 && /:\s*$/.test(code)) break;
  }
  const body: string[] = [];
  for (const line of lines.slice(header + 1)) {
    if (line.trim() !== "" && !/^\s/.test(line) && !line.startsWith("#")) break;
    body.push(line);
  }
  return body.join("\n");
}

const calls = (body: string, call: string) => new RegExp(`(^|[^\\w.])${call.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\(`, "m").test(pythonCode(body));

/** Every claim that no longer holds, as a sentence naming the claim, the file and the fact. */
export function checkClaims(claims: readonly MachineClaim[], read: (path: string) => string): string[] {
  const findings: string[] = [];
  for (const { id, check } of claims) {
    let source: string;
    try {
      source = read(check.file);
    } catch {
      findings.push(`claim ${id} cannot be checked: cannot read ${check.file}`);
      continue;
    }
    if (check.type === "contains") {
      for (const text of check.text) {
        if (!source.includes(text)) findings.push(`claim ${id} no longer holds: ${check.file} does not contain "${text}"`);
      }
      continue;
    }
    const body = pythonFunctionBody(source, check.function);
    if (body === undefined) {
      findings.push(`claim ${id} no longer holds: ${check.function}() is not defined at the top level of ${check.file}`);
    } else if (check.type === "python-function-calls" && !calls(body, check.call)) {
      findings.push(`claim ${id} no longer holds: ${check.function}() in ${check.file} does not call ${check.call}`);
    } else if (check.type === "python-function-avoids" && calls(body, check.call)) {
      findings.push(`claim ${id} no longer holds: ${check.function}() in ${check.file} now calls ${check.call}`);
    } else if (check.type === "python-function-contains" && !pythonCode(body).includes(check.text)) {
      findings.push(`claim ${id} no longer holds: ${check.function}() in ${check.file} no longer contains ${check.text}`);
    }
  }
  return findings;
}
