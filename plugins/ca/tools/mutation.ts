/**
 * mutation.ts — codeArbiter's zero-token quality-signal engine.
 *
 * The two cheap, model-free quality heuristics the dispatcher runs after a
 * task's gate goes green: the anti-gaming check (does a tiny impl hard-code the
 * test's asserted literals?) and the mutation guard (does the narrow test catch
 * single-point mutants, or are there survivors?). Extracted from farm.ts
 * (v2.rev.0020 / architecture-003); depends only on the shared exec layer
 * (./exec.ts) and imports the Task contract type-only from farm.ts, so there is
 * no runtime import cycle. This is a move, not a rewrite — behaviour is
 * identical to the prior in-farm.ts definitions.
 */
import { spawn } from "node:child_process";
import { writeFile } from "node:fs/promises";
import path from "node:path";
import {
  run,
  treeKill,
  readWorktreeFile,
  SHELL_BIN,
  SHELL_FLAG,
  SHELL_OPTS,
  GATE_TIMEOUT_MS,
} from "./exec.ts";
import type { Task } from "./farm.ts";

// Mutation guard — a zero-token quality signal. After the gate goes green we
// mutate the worker's in-scope impl and re-run ONLY the task's narrow test
// (gate.commands[0]); a mutant the test fails to catch ("survivor") is code the
// test does not constrain — gaming, dead code, or a weak test. Bounded by test
// strength, so a LOW score is a strong red flag but a high one is only
// necessary-not-sufficient. Low score → warning into Phase 3; only a near-zero
// score on a non-trivial impl hard-escalates. Pluggable: set FARM_MUTATION_CMD
// to a real per-language framework (it runs in the worktree with
// FARM_MUTATION_FILES / FARM_MUTATION_TEST_PATH / FARM_MUTATION_TEST_CMD set,
// and must print a trailing JSON line containing a numeric "score").
export const MUT = {
  enabled: (process.env.FARM_MUTATION ?? "on").toLowerCase() !== "off",
  sample: Number(process.env.FARM_MUTATION_SAMPLE ?? 15),
  budgetMs: Number(process.env.FARM_MUTATION_BUDGET_MS ?? 30_000),
  warnBelow: Number(process.env.FARM_MUTATION_WARN_BELOW ?? 0.5),
  escalateBelow: Number(process.env.FARM_MUTATION_ESCALATE_BELOW ?? 0.1),
  cmd: process.env.FARM_MUTATION_CMD ?? null,
};

// --------------------------------------------------------------------------
// anti-gaming guard — zero-token heuristic. A cheap model can satisfy a narrow
// test by hard-coding the asserted value. We extract the literals the test
// asserts and flag an impl file that (a) is tiny and (b) reproduces a
// non-trivial test literal verbatim. Egregious cases escalate; borderline
// cases attach a warning that rides into the report for the human reviewer.
// --------------------------------------------------------------------------
export function extractLiterals(testSrc: string): string[] {
  const lits = new Set<string>();
  // quoted strings
  for (const m of testSrc.matchAll(/(['"`])((?:\\.|(?!\1).){2,})\1/g)) lits.add(m[2]);
  // multi-digit / non-0-1 numbers
  for (const m of testSrc.matchAll(/\b(\d{2,}|[2-9])\b/g)) lits.add(m[1]);
  return [...lits];
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
  const literals = extractLiterals(testSrc).filter((l) => l.length > 1 || /\d{2,}/.test(l));
  if (literals.length === 0) return { risk: "none" };

  const hits: string[] = [];
  let anyTiny = false;
  for (const f of task.filesInScope) {
    if (f === task.test.path) continue;
    const src = await readWorktreeFile(cwd, f);
    if (src === null) continue;
    const tiny = codeLineCount(src) <= 5;
    for (const lit of literals) {
      if (src.includes(lit)) {
        hits.push(`${f} contains test literal ${JSON.stringify(lit)}`);
        if (tiny) anyTiny = true;
      }
    }
  }
  if (hits.length === 0) return { risk: "none" };
  if (anyTiny) return { risk: "high", note: `gaming: ${hits[0]} (impl is trivial)` };
  return { risk: "warn", note: `gaming-risk: ${hits[0]}` };
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
// string/generic content); invalid mutants that break compilation just fail the
// test and count as "killed" — the lenient direction (no false escalation).
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

export type MutationResult = { score: number; evaluated: number; survivors: string[] };

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
    if (typeof parsed.score === "number")
      return { score: parsed.score, evaluated: parsed.total ?? parsed.evaluated ?? 99, survivors: parsed.survived ?? [] };
  } catch {
    /* unparseable — skip leniently */
  }
  return null;
}

export async function mutationCheck(wt: string, task: Task): Promise<MutationResult | null> {
  if (!MUT.enabled) return null;
  const testCmd = task.gate.commands[0];
  if (!testCmd) return null;
  const impl = task.filesInScope.filter((f) => f !== task.test.path);

  // Pluggable hook — hand off to a real per-language framework if configured.
  if (MUT.cmd) {
    const r = await new Promise<{ code: number; out: string }>((resolve) => {
      const c = spawn(SHELL_BIN, [SHELL_FLAG, MUT.cmd!], {
        cwd: wt,
        env: { ...process.env, FARM_MUTATION_FILES: impl.join(","), FARM_MUTATION_TEST_PATH: task.test.path, FARM_MUTATION_TEST_CMD: testCmd },
        ...SHELL_OPTS,
      });
      let out = "";
      let settled = false;
      const finish = (res: { code: number; out: string }) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve(res);
      };
      // T-06: bound the pluggable FARM_MUTATION_CMD by the same wall-clock
      // timeout. A hung mutation framework would otherwise wedge the worker; on
      // timeout the child tree is killed and the result is treated as
      // unparseable (score skipped leniently — no false escalation).
      const timer = setTimeout(() => {
        treeKill(c);
        finish({ code: 124, out: out + "\n[FARM] FARM_MUTATION_CMD exceeded the wall-clock timeout — killed" });
      }, GATE_TIMEOUT_MS);
      c.stdout.on("data", (d) => (out += d));
      c.stderr.on("data", (d) => (out += d));
      c.on("error", (e) => finish({ code: 1, out: String(e) }));
      c.on("close", (code) => finish({ code: code ?? 1, out }));
    });
    // dx-002 (T-08b): shape-guarded parse of the hook's trailing score line.
    return parseMutationHookOutput(r.out);
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

  const start = Date.now();
  let killed = 0;
  let evaluated = 0;
  const survivors: string[] = [];
  try {
    for (const c of candidates) {
      if (Date.now() - start > MUT.budgetMs) break;
      await writeFile(path.resolve(wt, c.file), c.mutated);
      // T-06: bound the mutant re-run by the wall-clock timeout. A hung test
      // here (a mutant that turns the test into an infinite loop, say) would
      // otherwise wedge the worker; the killed result counts as a "killed"
      // mutant (code!=0), the lenient direction.
      const r = await run(SHELL_BIN, [SHELL_FLAG, testCmd], wt, SHELL_OPTS, GATE_TIMEOUT_MS);
      // T-08 (dx-003): skip the restore on a Map miss rather than writing the
      // literal string "undefined" into the worktree file. The invariant
      // (every candidate's file is a key in `originals`) holds for the built-in
      // generator today; this guard preserves the file if that ever changes.
      const orig = originals.get(c.file);
      if (orig !== undefined) await writeFile(path.resolve(wt, c.file), orig); // restore
      evaluated++;
      if (r.code !== 0) killed++;
      else survivors.push(c.tag);
    }
  } finally {
    // defensive: guarantee every impl file is back to the worker's output
    for (const [f, src] of originals) await writeFile(path.resolve(wt, f), src).catch(() => {});
  }
  if (evaluated < 3) return null; // too few mutants to judge fairly
  return { score: killed / evaluated, evaluated, survivors };
}
