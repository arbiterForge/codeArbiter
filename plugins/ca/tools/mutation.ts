/**
 * mutation.ts — codeArbiter's zero-token quality-signal engine.
 *
 * The two cheap, model-free quality heuristics the dispatcher runs after a
 * task's gate goes green: the anti-gaming check (does a tiny impl hard-code the
 * test's asserted literals?) and the mutation guard (does the narrow test catch
 * single-point mutants, or are there survivors?). Extracted from farm.ts
 * (v2.rev.0020 / architecture-003); depends only on the shared exec layer
 * (./exec.ts) and imports the Task contract type-only from farm.ts, so there is
 * no runtime import cycle. External measurements require successful completed
 * stdout, while failure diagnostics are bounded and distinct from scores.
 */
import { spawn } from "node:child_process";
import { performance } from "node:perf_hooks";
import {
  run,
  treeKill,
  readWorktreeFile,
  scrubbedEnv,
  numEnv,
  SHELL_BIN,
  SHELL_FLAG,
  SHELL_OPTS,
  GATE_TIMEOUT_MS,
  EXIT_TIMEOUT,
  EXIT_TIMEOUT_UNCLEAN,
  type RunResult,
} from "./exec.ts";
import { redactSecrets } from "./redactor.ts";
import { isUnsafeWorktreePathError, writeWorktreeFile } from "./worktree-fs.ts";
import type { Task } from "./farm.ts";

// Mutation guard — a zero-token quality signal. After the gate goes green we
// mutate the worker's in-scope impl and re-run ONLY the task's narrow test
// (gate.commands[0]); a mutant the test fails to catch ("survivor") is code the
// test does not constrain — gaming, dead code, or a weak test. Bounded by test
// strength. Bare nonzero exits cannot establish assertion kills rather than
// compiler/loader failures, so built-in positive ratios are unverified upper
// bounds, never measured scores. Low score → warning into Phase 3; only a near-zero
// score on a non-trivial impl hard-escalates. Pluggable: set FARM_MUTATION_CMD
// to a real per-language framework (it runs in the worktree with
// FARM_MUTATION_FILES / FARM_MUTATION_TEST_PATH / FARM_MUTATION_TEST_CMD set,
// and must print a trailing JSON line containing a numeric "score").
export const MUT = {
  enabled: (process.env.FARM_MUTATION ?? "on").toLowerCase() !== "off",
  // reliability-014: routed through the shared numEnv reader (exec.ts) so a
  // typo'd FARM_MUTATION_* value falls back to the default loudly instead of
  // silently becoming NaN (every comparison against MUT.warnBelow/escalateBelow
  // would then read false, disabling the anti-gaming mutation signal).
  sample: numEnv("FARM_MUTATION_SAMPLE", 15, { min: 1 }),
  budgetMs: numEnv("FARM_MUTATION_BUDGET_MS", 30_000, { min: 0 }),
  warnBelow: numEnv("FARM_MUTATION_WARN_BELOW", 0.5, { min: 0 }),
  escalateBelow: numEnv("FARM_MUTATION_ESCALATE_BELOW", 0.1, { min: 0 }),
  cmd: process.env.FARM_MUTATION_CMD ?? null,
};

// --------------------------------------------------------------------------
// anti-gaming guard — bounded lexical evidence, not a parser or intent proof.
// Test descriptions/inputs can still contain legitimate shared constants. Keep
// the existing size/risk policy, but a substring, comment or different literal
// kind cannot establish that the implementation repeats an observed value.
// --------------------------------------------------------------------------
type LiteralAtom = { kind: "string" | "number"; value: string };
type CommentStyle = "slash" | "hash" | "none";

/** Recognize only declared conventional comment families; never execute source. */
function commentStyle(file: string): CommentStyle {
  if (/\.pyi?$/i.test(file)) return "hash";
  return /\.(?:[cm]?[jt]sx?|c|cc|cpp|cxx|h|hh|hpp|cs|java|go|rs|swift|kt|kts)$/i.test(file)
    ? "slash" : "none";
}

/** Extract complete, kind-tagged literal spellings outside conventional comments.
 * This deliberately does not evaluate escapes, constant expressions, Python
 * prefixes or template interpolation. Unknown language forms are not parsed.
 * Keeping raw spellings is conservative: different encodings are not equality
 * proof. The exported value-only helper remains for existing callers.
 */
function literalAtoms(src: string, comments: CommentStyle): LiteralAtom[] {
  const atoms: LiteralAtom[] = [];
  const ident = /[\p{ID_Continue}$]/u;
  const identifierAt = (offset: number) => ident.test(String.fromCodePoint(src.codePointAt(offset) ?? 0));
  const widthAt = (offset: number) => (src.codePointAt(offset) ?? 0) > 0xffff ? 2 : 1;
  const number = /(?:0[xX][\da-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+|(?:\d[\d_]*(?:\.[\d_]*)?|\.\d[\d_]*)(?:[eE][+-]?[\d_]+)?)[nN]?/y;
  let i = 0;
  while (i < src.length) {
    const ch = src[i];
    if ((comments === "slash" && src.startsWith("//", i)) ||
        (comments === "hash" && ch === "#") || (i === 0 && src.startsWith("#!"))) {
      while (i < src.length && src[i] !== "\n" && src[i] !== "\r") i++;
      continue;
    }
    if (comments === "slash" && src.startsWith("/*", i)) {
      const end = src.indexOf("*/", i + 2);
      i = end < 0 ? src.length : end + 2;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === "`") {
      const delimiter = comments === "hash" && src.startsWith(ch.repeat(3), i) ? ch.repeat(3) : ch;
      const begin = i += delimiter.length;
      let dynamic = false, closed = false;
      while (i < src.length) {
        if (src[i] === "\\") { i += Math.min(2, src.length - i); continue; }
        if (src.startsWith(delimiter, i)) { closed = true; break; }
        if (ch === "`" && src.startsWith("${", i)) dynamic = true;
        if (delimiter.length === 1 && ch !== "`" && /[\r\n]/.test(src[i])) break;
        i++;
      }
      const value = src.slice(begin, i);
      if (closed) {
        if (!dynamic && value.length >= 2) atoms.push({ kind: "string", value });
        i += delimiter.length;
      }
      continue;
    }
    // Ignore slash-delimited regex contents in unambiguous expression-start
    // positions. This is not JavaScript ASI/grammar or arbitrary regex parsing.
    if (comments === "slash" && ch === "/" &&
        /(?:^|[=(:,;!?\[{}&|]|\breturn|\bthrow|=>)\s*$/.test(src.slice(Math.max(0, i - 16), i))) {
      let end = i + 1, bracket = false;
      for (; end < src.length && !/[\r\n]/.test(src[end]); end++) {
        if (src[end] === "\\") { end++; continue; }
        if (src[end] === "[") bracket = true;
        if (src[end] === "]") bracket = false;
        if (src[end] === "/" && !bracket) break;
      }
      if (src[end] === "/") {
        i = end + 1;
        while (i < src.length && identifierAt(i)) i += widthAt(i);
        continue;
      }
    }
    if (/\d/.test(ch) || (ch === "." && /\d/.test(src[i + 1] ?? ""))) {
      number.lastIndex = i;
      const match = number.exec(src);
      if (match) {
        i = number.lastIndex;
        if (i < src.length && identifierAt(i)) {
          while (i < src.length && identifierAt(i)) i += widthAt(i);
        } else if (match[0] !== "0" && match[0] !== "1") {
          atoms.push({ kind: "number", value: match[0] });
        }
        continue;
      }
    }
    if (identifierAt(i)) {
      while (i < src.length && identifierAt(i)) i += widthAt(i);
    } else i++;
  }
  return atoms;
}

/** Existing value-only API; the guard itself additionally retains literal kind. */
export function extractLiterals(testSrc: string): string[] {
  return [...new Set(literalAtoms(testSrc, "slash").map((atom) => atom.value))];
}

export function codeLineCount(src: string): number {
  return src
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith("//") && !l.startsWith("#") && !l.startsWith("*") && !l.startsWith("/*")).length;
}

export async function antiGamingCheck(
  cwd: string,
  task: Task,
): Promise<{ risk: "none" | "warn" | "high"; note?: string }> {
  const testSrc = await readWorktreeFile(cwd, task.test.path);
  if (testSrc === null) return { risk: "none" };
  const literals = literalAtoms(testSrc, commentStyle(task.test.path))
    .filter((atom) => atom.value.length > 1);
  if (literals.length === 0) return { risk: "none" };

  let firstHit: string | undefined;
  let firstTinyHit: string | undefined;
  for (const f of task.filesInScope) {
    if (f === task.test.path) continue;
    const src = await readWorktreeFile(cwd, f);
    if (src === null) continue;
    const observed = new Set(literalAtoms(src, commentStyle(f))
      .map((atom) => JSON.stringify([atom.kind, atom.value])));
    const tiny = codeLineCount(src) <= 5;
    for (const atom of literals) {
      if (!observed.has(JSON.stringify([atom.kind, atom.value]))) continue;
      const hit = `${f} contains test literal ${JSON.stringify(atom.value)}`;
      firstHit ??= hit;
      if (tiny) firstTinyHit ??= hit;
    }
  }
  if (firstTinyHit) return { risk: "high", note: `gaming: ${firstTinyHit} (impl is trivial)` };
  if (firstHit) return { risk: "warn", note: `gaming-risk: ${firstHit}` };
  return { risk: "none" };
}

// --------------------------------------------------------------------------
// mutation guard
// --------------------------------------------------------------------------
function shuffle<T>(a: T[]): T[] {
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

// Single-point text mutants. Space-padded operators bias toward real code (not
// string/generic content). A completed nonzero rerun is an unclassified gate
// rejection, NOT a proved assertion kill. Do not guess compiler/loader/test
// semantics from exit numbers or diagnostic words. A per-language framework
// can supply measurements through the existing external hook.
function generateMutants(file: string, src: string): Array<{ file: string; mutated: string; tag: string }> {
  const lines = src.split("\n");
  const rules: Array<[RegExp, string, string]> = [
    [/ >= /, " > ", ">=>"], [/ <= /, " < ", "<=<"],
    [/ === /, " !== ", "===>!=="], [/ !== /, " === ", "!==>==="],
    [/ == /, " != ", "==>!="], [/ != /, " == ", "!=>=="],
    [/ > /, " >= ", ">>="], [/ < /, " <= ", "<<="],
    [/ \+ /, " - ", "+>-"], [/ - /, " + ", "->+"], [/ \* /, " \/ ", "*>/"],
    [/ && /, " || ", "&&>||"], [/ \|\| /, " && ", "||>&&"],
    [/\btrue\b/, "false", "true>false"], [/\bfalse\b/, "true", "false>true"],
  ];
  const out: Array<{ file: string; mutated: string; tag: string }> = [];
  for (let i = 0; i < lines.length; i++) {
    const ln = lines[i];
    const t = ln.trim();
    if (!t || t.startsWith("//") || t.startsWith("#") || t.startsWith("*") || t.startsWith("/*")) continue;
    for (const [re, rep, name] of rules) {
      if (re.test(ln)) {
        const mline = ln.replace(re, rep);
        if (mline !== ln) {
          const m = [...lines]; m[i] = mline;
          out.push({ file, mutated: m.join("\n"), tag: `${file}:${i + 1} ${name}` });
        }
      }
    }
    const rm = ln.match(/\breturn\s+(.+?);/);
    if (rm && rm[1].trim() !== "null" && rm[1].trim() !== "") {
      const m = [...lines];
      m[i] = ln.replace(/\breturn\s+.+?;/, "return null;");
      out.push({ file, mutated: m.join("\n"), tag: `${file}:${i + 1} return>null` });
    }
  }
  return out;
}

// #525: `evaluated` and `survivors` are OPTIONAL because a pluggable
// FARM_MUTATION_CMD is only contractually required to print a numeric `score`
// (includes/farm.md). They used to be declared required, so parseMutationHookOutput
// had to invent values (`?? 99`, `?? []`) to satisfy the type — and once
// invented, no consumer could tell a fabricated count from a measured one. That
// is the root cause of #525 and of three successive wrong fixes to it: the type
// could not express "the producer did not say", so every reader had to guess.
// Optional makes the absence representable and lets the compiler force each
// consumer to decide what to do about it. The built-in path always populates
// both when reporting completed observations.
export type MutationResult = { score: number; evaluated?: number; survivors?: string[] };

// observability-002 (#187): the pluggable-hook branch of mutationCheck used to
// collapse EVERY failure mode (non-zero exit, timeout, crash, unparseable
// output) to the same `null` the caller sees for "mutation checking is not
// configured", so a broken FARM_MUTATION_CMD integration produced a report
// indistinguishable from one that never ran mutation checking. `null` still
// means "not configured / nothing to evaluate" (unchanged — existing callers
// that only check truthiness keep working); MutationHookFailure is a NEW,
// narrow, explicit member the caller uses to distinguish "configured but
// failed" and surface a diagnostic (mirrors the primary API path's stderr body
// dump on a callApi failure).
export type MutationHookFailure = {
  failed: true;
  // The built-in runner shares this failure envelope, not the external-hook
  // measurement channel. Preserve its origin in diagnostics.
  source?: "builtin";
  detail: string;
  cleanupFailed?: true;
  // Diagnostic-only external stdout report, or a built-in gate-rejection upper
  // bound over completed reruns. Nonzero is not proof of a valid/assertion-killed
  // mutant. Never copy this into mutationScore. A low upper bound still retains
  // adverse evidence; an interrupted run cannot erase completed observations.
  unverified?: MutationResult;
};
export type MutationCheckResult = MutationResult | MutationHookFailure | null;

// dx-002 (T-08b): parse a pluggable FARM_MUTATION_CMD's stdout for its trailing
// JSON score line. Extracted as a pure, exported function so the shape guard is
// unit-testable without spawning a process. The last `{...\"score\"...}` match is
// JSON.parsed; a value that is null, not an object, or an array (e.g. "score"
// emitted inside a string, or a bare numeric literal) is rejected to null before
// `parsed.score` is read, rather than silently mis-interpreted. A non-numeric
// score, no match, or unparseable JSON all map to null (skip leniently).
export function parseMutationHookOutput(out: string): MutationResult | null {
  const j = [...out.matchAll(/\{[^\n]*"score"[^\n]*\}/g)].pop();
  if (!j) return null;
  try {
    const parsed = JSON.parse(j[0]) as { score?: number; total?: number; evaluated?: number; survived?: string[] };
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) return null;
    if (typeof parsed.score === "number" && Number.isFinite(parsed.score) && parsed.score >= 0 && parsed.score <= 1) {
      // #525: report only what the hook actually reported. Both fields are
      // optional in the contract, so an absent or unusable one stays ABSENT
      // rather than becoming a default that later reads as a measurement.
      //
      // `survived` accepts only a real array of strings: a hook emitting
      // `"survived": 9` (a count — the natural reading of the field name) or
      // `"survived": "a,b"` produced a `survivors` that was not a string[] at
      // all, so a consumer reading `.length` got `undefined` or a character
      // count. `total`/`evaluated` accept only a non-negative integer; "abc"
      // and -5 previously reached arithmetic and rendered `NaN` and negatives.
      // Zero IS reported — "I evaluated nothing" is information, and it is
      // what keeps such a run below the escalation floor.
      // Stringify rather than FILTER. An earlier cut dropped non-string
      // entries, which silently shortened the list — a hook emitting numeric
      // mutant ids (`"survived": [1,2,3]`, an entirely natural shape) reported
      // "0/10 survived" while escalating the task FOR its survivors. Shortening
      // is the one option that yields a confident wrong number, which is the
      // defect this whole issue is about. The COUNT is trustworthy even when an
      // id is not a string, and nothing renders the ids, so preserve length.
      //
      // `String(x)` THROWS on an object with a non-callable toString/valueOf,
      // which `JSON.parse` can produce (`[{"toString":1}]`). Unguarded, that
      // threw into the catch below and discarded an otherwise valid result,
      // losing the escalation entirely — lenient in the wrong direction.
      const label = (s: unknown): string => {
        try {
          return typeof s === "string" ? s : String(s);
        } catch {
          return "[unprintable id]";
        }
      };
      const survivors = Array.isArray(parsed.survived) ? parsed.survived.map(label) : undefined;
      // A NUMERIC STRING is accepted. Requiring a JSON number looked stricter
      // and was a hole: before #525 this value was compared raw against the
      // escalation floor, so JS coercion made `"total":"10"` escalate. Rejecting
      // it here sends it to "unreported", which no longer clears the floor — so
      // a shell hook that quotes its numbers (`echo "{\"total\":\"$n\"}"`, the
      // most natural way to emit JSON from bash) could never escalate at ANY
      // count. That silently disables the anti-gaming gate for a whole class of
      // hooks, which is worse than the false escalations the strictness avoided.
      // Booleans, arrays and objects are still refused: coercing those to a
      // mutant count would be inventing one.
      const declared = parsed.total ?? parsed.evaluated;
      const n =
        typeof declared === "number" ? declared : typeof declared === "string" ? Number(declared) : Number.NaN;
      const evaluated = Number.isFinite(n) && n >= 0 ? n : undefined;
      return { score: parsed.score, evaluated, survivors };
    }
  } catch {
    /* unparseable — skip leniently */
  }
  return null;
}

/** Interpret completed hook stdout without turning failure diagnostics into proof.
 * Count/survivor absence remains absence. Ordinary configured failures retain
 * their existing warning policy; unverified process cleanup is distinct so the
 * dispatcher can refuse further work against a possibly live writer.
 */
export function interpretMutationHookResult(
  result: Pick<RunResult, "code" | "out" | "stdout" | "timedOut" | "cleanupFailed">,
): MutationResult | MutationHookFailure {
  const parsed = parseMutationHookOutput(result.stdout);
  if (result.code === 0 && !result.timedOut && !result.cleanupFailed && parsed !== null) return parsed;
  // Redact before bounding: trimming a credential's prefix first can make its
  // remaining suffix unrecognizable to the shared detector.
  const tail = redactSecrets(result.out).slice(-500).trim();
  return { failed: true, detail: `exit ${result.code}${tail ? `: ${tail}` : " (no output)"}`,
    ...(result.cleanupFailed ? { cleanupFailed: true as const } : {}),
    ...(parsed !== null ? { unverified: parsed } : {}) };
}

export async function mutationCheck(wt: string, task: Task): Promise<MutationCheckResult> {
  if (!MUT.enabled) return null;
  const testCmd = task.gate.commands[0];
  if (!testCmd) return null;
  const impl = task.filesInScope.filter((f) => f !== task.test.path);

  // Pluggable hook — hand off to a real per-language framework if configured.
  if (MUT.cmd) {
    const r = await new Promise<Pick<RunResult, "code" | "out" | "stdout" | "timedOut" | "cleanupFailed">>((resolve) => {
      // Least-privilege parity with run(): the operator-authored mutation hook
      // is a child like any other and must not inherit the dispatcher's
      // secrets. Route its env through scrubbedEnv(), passing only the
      // FARM_MUTATION_* contract vars on top of the scrubbed base.
      const c = spawn(SHELL_BIN, [SHELL_FLAG, MUT.cmd!], {
        cwd: wt,
        env: scrubbedEnv({ FARM_MUTATION_FILES: impl.join(","), FARM_MUTATION_TEST_PATH: task.test.path, FARM_MUTATION_TEST_CMD: testCmd }),
        ...SHELL_OPTS,
        // #395: process-group isolation, matching run(). The operator-authored
        // mutation hook is a grandchild behind `bash -c` / `cmd.exe /c`, so the
        // timeout kill must be able to address the group, not just the shell.
        detached: process.platform !== "win32",
      });
      let out = "";
      let stdout = "";
      let settled = false;
      let killing = false;
      const finish = (res: Pick<RunResult, "code" | "out" | "timedOut" | "cleanupFailed">) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve({ ...res, stdout });
      };
      // T-06: bound the pluggable FARM_MUTATION_CMD by the same wall-clock
      // timeout. A hung mutation framework would otherwise wedge the worker; on
      // timeout the child tree is killed. Any printed score is rejected because
      // the hook did not finish, rather than crediting partial output as proof.
      // #395: the kill is now AWAITED and verified, and an unverified cleanup is
      // reported as cleanupFailed as well as a redacted detail. The dispatcher
      // must not continue authoring or integrate while a writer might survive.
      const timer = setTimeout(() => {
        killing = true;
        void treeKill(c).then((k) => {
          const note = k.ok
            ? "\n[FARM] FARM_MUTATION_CMD exceeded the wall-clock timeout — killed"
            : `\n[FARM] FARM_MUTATION_CMD exceeded the wall-clock timeout — killed, but CLEANUP UNVERIFIED: ${k.detail ?? "no detail"}`;
          finish({ code: k.ok ? EXIT_TIMEOUT : EXIT_TIMEOUT_UNCLEAN, out: out + note,
            timedOut: true, ...(k.ok ? {} : { cleanupFailed: true as const }) });
        }, (error: unknown) => {
          finish({ code: EXIT_TIMEOUT_UNCLEAN, timedOut: true, cleanupFailed: true,
            out: `${out}\n[FARM] CLEANUP UNVERIFIED: ${String(error)}` });
        });
      }, GATE_TIMEOUT_MS);
      c.stdout.on("data", (d) => { stdout += d; out += d; });
      c.stderr.on("data", (d) => (out += d));
      c.on("error", (e) => {
        if (killing) return;
        finish({ code: 1, out: String(e) });
      });
      c.on("close", (code) => {
        if (killing) return;
        finish({ code: code ?? 1, out });
      });
    });
    return interpretMutationHookResult(r);
  }

  // Built-in text mutation.
  const originals = new Map<string, string>();
  let candidates: Array<{ file: string; mutated: string; tag: string }> = [];
  for (const f of impl) {
    const src = await readWorktreeFile(wt, f);
    if (src === null) continue;
    if (codeLineCount(src) <= 2) continue; // trivial file — nothing to constrain
    originals.set(f, src);
    candidates.push(...generateMutants(f, src));
  }
  if (candidates.length === 0) return null;
  candidates = shuffle(candidates).slice(0, MUT.sample);

  // A monotonic elapsed budget caps EACH launch, including the first. A gate
  // timeout of zero disables the shared runner limit, not this mutation budget.
  // Verified process teardown and defensive restoration can outlast the timer;
  // they must finish (or refuse safely) before any candidate can advance.
  const start = performance.now();
  const remainingMs = () => MUT.budgetMs - (performance.now() - start);
  let rejected = 0;
  let evaluated = 0;
  const survivors: string[] = [];
  let firstRejection: string | undefined;
  // At most every completed rejection could be a valid assertion kill. Treating
  // them all that way gives an upper bound R/(S+R); excluding invalid rejections
  // cannot increase that rate. This preserves a genuinely adverse upper bound
  // without crediting compiler/loader failures as measured kills. Timed-out
  // trials are not included. The existing explicit-count floor stays intact.
  const unverified = () => evaluated >= 3
    ? { score: rejected / evaluated, evaluated, survivors } : undefined;
  try {
    for (const c of candidates) {
      if (remainingMs() <= 0) break;
      await writeWorktreeFile(wt, c.file, c.mutated);
      // Include the write in the remaining budget. If it consumes the budget,
      // finally still restores the worker's bytes without launching a test.
      const remaining = remainingMs();
      if (remaining <= 0) break;
      const timeout = Math.max(1, Math.ceil(Math.min(remaining,
        GATE_TIMEOUT_MS > 0 ? GATE_TIMEOUT_MS : remaining)));
      const r = await run(SHELL_BIN, [SHELL_FLAG, testCmd], wt, SHELL_OPTS, timeout);
      if (r.timedOut || r.cleanupFailed) {
        // A killed PROCESS is not a killed MUTANT. Stop this screening run,
        // restore through finally, and leave no published score from an
        // incomplete trial. Retain already completed adverse observations so
        // an interruption cannot erase the existing low-score/count floor.
        const tail = redactSecrets(r.out).slice(-400).trim();
        return { failed: true, source: "builtin",
          detail: `built-in mutation ${r.cleanupFailed ? "cleanup unverified" : "trial timed out"}` +
            ` after ${evaluated} completed rerun(s)${tail ? `: ${tail}` : ""}`,
          ...(r.cleanupFailed ? { cleanupFailed: true as const } : {}),
          ...(evaluated >= 3 ? { unverified: unverified() } : {}) };
      }
      // T-08 (dx-003): skip the restore on a Map miss rather than writing the
      // literal string "undefined" into the worktree file. The invariant
      // (every candidate's file is a key in `originals`) holds for the built-in
      // generator today; this guard preserves the file if that ever changes.
      const orig = originals.get(c.file);
      if (orig !== undefined) await writeWorktreeFile(wt, c.file, orig); // restore
      evaluated++;
      if (r.code !== 0) {
        rejected++;
        // Preserve a bounded witness, not a language verdict. Redact before
        // truncation, including credentials that extend beyond the limit.
        firstRejection ??= redactSecrets(`${c.tag}: exit ${r.code}${r.out ? `: ${r.out}` : ""}`).slice(0, 300);
      } else survivors.push(c.tag);
    }
  } finally {
    // defensive: guarantee every impl file is back to the worker's output
    for (const [f, src] of originals) {
      try {
        await writeWorktreeFile(wt, f, src);
      } catch (error) {
        if (isUnsafeWorktreePathError(error)) throw error;
      }
    }
  }
  if (rejected > 0) {
    // The command finished, but its exit status alone cannot validate a mutant
    // or identify the failing phase. No positive measured score is fabricated.
    // Report even a short failed screening while leaving thin evidence below
    // the existing count floor. Do not buy another model round just for this.
    return { failed: true, source: "builtin",
      detail: `built-in mutation: ${rejected} unclassified nonzero rerun(s), ` +
        `${survivors.length} passed, ${evaluated} completed; gate-rejection upper bound ` +
        `${(rejected / evaluated).toFixed(3)} is not a measured score; ${firstRejection}`,
      ...(evaluated >= 3 ? { unverified: unverified() } : {}) };
  }
  if (evaluated < 3) return null; // too few completed reruns to judge fairly
  // Every observed rerun passed: no rejection was credited as a kill. This is
  // the existing weak-test signal, not language-aware mutant validity proof.
  return { score: 0, evaluated, survivors };
}
