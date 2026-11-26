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
  | { type: "contains"; file: string; text: string[] };

export interface MachineClaim {
  id: string;
  /** The sentence the page shows; it must stay true while the check passes. */
  statement: string;
  check: ClaimCheck;
}

/** The body of a top-level `def name(...)`, up to the next line that starts at column 0. */
export function pythonFunctionBody(source: string, name: string): string | undefined {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const start = lines.findIndex((line) => line.startsWith(`def ${name}(`));
  if (start < 0) return undefined;
  const body: string[] = [];
  for (const line of lines.slice(start + 1)) {
    if (line !== "" && !/^\s/.test(line)) break;
    body.push(line);
  }
  return body.join("\n");
}

const calls = (body: string, call: string) => new RegExp(`(^|[^\\w.])${call.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\(`, "m").test(body);

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
    }
  }
  return findings;
}
