/**
 * Unit tests for mutation.ts — the two zero-token quality heuristics the
 * dispatcher runs after a task's gate goes green.
 *
 * `extractLiterals`, `codeLineCount` and `parseMutationHookOutput`'s shape guard
 * are already pinned in farm.unit.test.ts; this file does not restate them. What
 * had no direct coverage at all is the two things those helpers feed:
 * `antiGamingCheck` (the "did a tiny impl hard-code the test's literal?" pass)
 * and `mutationCheck` (both its pluggable-hook and built-in branches).
 *
 * Both are reachable without any injection scaffolding, because `MUT` is an
 * exported mutable object — its knobs are set directly here and restored after
 * each test. No module surgery, no version bump.
 *
 * These heuristics fail QUIETLY by design: a wrong answer is a missing warning
 * on a report, not a crash. That is exactly the shape #511 AC-3 asks to be
 * covered first, and it is why every case below asserts the returned risk/score
 * exactly rather than that a call succeeded.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { mkdtemp, mkdir, rm, writeFile, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { MUT, antiGamingCheck, mutationCheck } from "./mutation.ts";
import type { Task } from "./farm.ts";

const SHELL_TRUE = process.platform === "win32" ? "cmd /c exit 0" : "true";
const SHELL_FALSE = process.platform === "win32" ? "cmd /c exit 1" : "false";

function task(over: Partial<Task> = {}): Task {
  return {
    id: "t1",
    description: "task under test",
    deps: [],
    filesInScope: ["src/impl.ts"],
    test: { path: "src/impl.test.ts" },
    gate: { commands: [SHELL_TRUE] },
    maxRetries: 0,
    ...over,
  };
}

let wt: string;

// PINNED DEFAULTS, not `{ ...MUT }`. MUT is built at import from the ambient
// environment via numEnv, so snapshotting it captures whatever the developer
// happens to export. Measured: with `FARM_MUTATION=off` in the shell this file
// produced 10 failures, `FARM_MUTATION_CMD=...` 6, `FARM_MUTATION_BUDGET_MS=0`
// 3 — a red suite on unrelated work for anyone with a farm .env sourced.
const saved: typeof MUT = {
  enabled: true,
  sample: 15,
  budgetMs: 30_000,
  warnBelow: 0.5,
  escalateBelow: 0.1,
  cmd: null,
};

beforeEach(async () => {
  wt = await mkdtemp(path.join(tmpdir(), "farm-mut-"));
  await mkdir(path.join(wt, "src"), { recursive: true });
  Object.assign(MUT, saved);
});

afterEach(async () => {
  Object.assign(MUT, saved);
  await rm(wt, { recursive: true, force: true });
});

async function write(rel: string, body: string): Promise<void> {
  await writeFile(path.join(wt, rel), body, "utf8");
}

describe("antiGamingCheck", () => {
  it("returns none when the test file cannot be read", async () => {
    // The task names a test that does not exist in the worktree. There is
    // nothing to extract literals FROM, so the heuristic must decline rather
    // than treat "no literals" as "no gaming" further down.
    expect(await antiGamingCheck(wt, task())).toEqual({ risk: "none" });
  });

  it("returns none when the test asserts no literal worth matching", async () => {
    // Single-character numbers and 0/1 are filtered out: they collide with
    // ordinary code (`length > 1`, `x + 1`) and would flag every impl.
    //
    // The impl deliberately CONTAINS both `1` and `0`. With the empty-literals
    // guard deleted the loop runs, finds those characters in a one-line impl,
    // and escalates — so this now fails for its stated reason instead of
    // reaching "none" down the hits-empty path regardless.
    await write("src/impl.test.ts", "expect(x).toBe(1);\nexpect(y).toBe(0);\n");
    await write("src/impl.ts", "export const x = 1 + 0;\n");
    expect(await antiGamingCheck(wt, task())).toEqual({ risk: "none" });
  });

  it("skips the test file itself when it appears in filesInScope", async () => {
    // The test necessarily contains its own literals. Counting it as a hit
    // would flag every task whose test is in scope — which is the normal case
    // for a task allowed to edit its own test.
    await write("src/impl.test.ts", 'expect(answer()).toBe("the-magic-value");\n');
    expect(
      await antiGamingCheck(wt, task({ filesInScope: ["src/impl.test.ts"] })),
    ).toEqual({ risk: "none" });
  });

  it("skips an in-scope file that does not exist yet", async () => {
    // A worker may not have created every in-scope file. A missing impl is not
    // evidence of gaming.
    await write("src/impl.test.ts", 'expect(answer()).toBe("the-magic-value");\n');
    expect(
      await antiGamingCheck(wt, task({ filesInScope: ["src/never-written.ts"] })),
    ).toEqual({ risk: "none" });
  });

  it("returns none when a real impl does not reproduce the literal", async () => {
    await write("src/impl.test.ts", 'expect(answer()).toBe("the-magic-value");\n');
    await write("src/impl.ts", "export function answer() {\n  return compute();\n}\n");
    expect(await antiGamingCheck(wt, task())).toEqual({ risk: "none" });
  });

  it("escalates to high when a TINY impl reproduces the literal verbatim", async () => {
    // The gaming case the heuristic exists for: five code lines or fewer, and
    // the asserted value hard-coded. Both the risk AND the note matter — the
    // note is what reaches the human reviewer's report.
    await write("src/impl.test.ts", 'expect(answer()).toBe("the-magic-value");\n');
    await write("src/impl.ts", 'export const answer = () => "the-magic-value";\n');

    const result = await antiGamingCheck(wt, task());
    expect(result.risk).toBe("high");
    expect(result.note).toBe('gaming: src/impl.ts contains test literal "the-magic-value" (impl is trivial)');
  });

  it("puts the trivial/substantial boundary at exactly five code lines", async () => {
    // Both sides of `codeLineCount(src) <= 5`, one line apart. Without the pair
    // the threshold can move in either direction unnoticed — and it decides
    // whether a task HARD-ESCALATES or merely carries a warning.
    await write("src/impl.test.ts", 'expect(answer()).toBe("the-magic-value");\n');
    const body = (lines: number): string =>
      [
        "export function answer() {",
        ...Array.from({ length: lines - 3 }, (_, i) => `  const v${i} = ${i + 2};`),
        '  return "the-magic-value";',
        "}",
      ].join("\n");

    await write("src/impl.ts", body(5));
    const atBoundary = await antiGamingCheck(wt, task());
    expect(atBoundary.risk).toBe("high");
    expect(atBoundary.note).toBe('gaming: src/impl.ts contains test literal "the-magic-value" (impl is trivial)');

    await write("src/impl.ts", body(6));
    const overBoundary = await antiGamingCheck(wt, task());
    expect(overBoundary.risk).toBe("warn");
    expect(overBoundary.note).toBe('gaming-risk: src/impl.ts contains test literal "the-magic-value"');
  });

  it("names the FIRST hit in the warn note, not the last", async () => {
    // `hits[0]` on the warn branch. With a single hit, first and last coincide
    // and the index is unpinned — measured, `hits[hits.length - 1]` survives the
    // whole tools suite. Two hitting files make the order observable.
    await write("src/impl.test.ts", 'expect(answer()).toBe("the-magic-value");\n');
    const substantial = (name: string): string =>
      [
        `export function ${name}() {`,
        "  const a = 1;",
        "  const b = 2;",
        "  const c = 3;",
        "  const d = 4;",
        '  return "the-magic-value";',
        "}",
      ].join("\n");
    await write("src/first.ts", substantial("first"));
    await write("src/second.ts", substantial("second"));

    const result = await antiGamingCheck(wt, task({ filesInScope: ["src/first.ts", "src/second.ts"] }));
    expect(result.risk).toBe("warn");
    expect(result.note).toBe('gaming-risk: src/first.ts contains test literal "the-magic-value"');
  });

  it("ignores a single-character literal that ordinary code would trip over", async () => {
    // `extractLiterals` yields a bare 2-9 as a literal; the `length > 1` filter
    // is what stops `toBe(7)` flagging every impl that contains a 7. Relaxing it
    // to `>= 1` turns this into a false HIGH on a one-line impl.
    await write("src/impl.test.ts", "expect(answer()).toBe(7);\n");
    await write("src/impl.ts", "export const answer = () => compute(7);\n");
    expect(await antiGamingCheck(wt, task())).toEqual({ risk: "none" });
  });

  it("counts only CODE lines, so a tiny impl padded with comments still escalates", async () => {
    // The boundary that makes the heuristic hard to game: comment and blank
    // lines do not buy an impl its way out of "trivial".
    await write("src/impl.test.ts", 'expect(answer()).toBe("the-magic-value");\n');
    await write(
      "src/impl.ts",
      [
        "// a comment",
        "",
        "# another",
        "* and another",
        "/* and one more",
        'export const answer = () => "the-magic-value";',
      ].join("\n"),
    );

    expect((await antiGamingCheck(wt, task())).risk).toBe("high");
  });

  it("escalates if ANY in-scope file is tiny, not merely the first hit", async () => {
    // `anyTiny` is a running flag across files. A substantial file hitting first
    // must not mask a trivial one hitting second.
    await write("src/impl.test.ts", 'expect(answer()).toBe("the-magic-value");\n');
    await write(
      "src/impl.ts",
      ["export function a() {", "  const x = 1;", "  const y = 2;", "  const z = 3;", "  const w = 4;", '  return "the-magic-value";', "}"].join("\n"),
    );
    await write("src/tiny.ts", 'export const b = "the-magic-value";\n');

    const result = await antiGamingCheck(wt, task({ filesInScope: ["src/impl.ts", "src/tiny.ts"] }));
    expect(result.risk).toBe("high");
    // The note names the FIRST hit, not the tiny one — the reviewer gets the
    // file that matched first plus the fact that something trivial was involved.
    expect(result.note).toContain("src/impl.ts");
    expect(result.note).toContain("(impl is trivial)");
  });
});

describe("mutationCheck — configuration gates", () => {
  it("returns null when mutation checking is disabled", async () => {
    // Same requirement as the gate-command case below, and it was missed here
    // first time: without a mutable impl the built-in path returns null anyway,
    // so DELETING the `MUT.enabled` guard entirely left this green.
    await write(
      "src/impl.ts",
      ["export function f(n) {", "  if (n >= 2) {", "    return true;", "  }", "  return n > 1;", "}"].join("\n"),
    );
    MUT.enabled = false;
    expect(await mutationCheck(wt, task())).toBeNull();
  });

  it("returns null when the task declares no gate command", async () => {
    // `gate.commands[0]` is the narrow test the mutants are re-run against.
    // Without it there is nothing to measure a mutant AGAINST, so a score would
    // be meaningless rather than merely unavailable.
    //
    // The impl MUST exist and be mutable here, or this passes for the wrong
    // reason: with no mutable file the built-in path returns null anyway, and
    // deleting the guard entirely would be invisible.
    await write(
      "src/impl.ts",
      ["export function f(n) {", "  if (n >= 2) {", "    return true;", "  }", "  return n > 1;", "}"].join("\n"),
    );
    expect(await mutationCheck(wt, task({ gate: { commands: [] } }))).toBeNull();
  });
});

describe("mutationCheck — pluggable FARM_MUTATION_CMD hook", () => {
  // The JSON payloads below are SINGLE-QUOTED inside the echo, and must stay
  // that way. The hook runs under `bash -c` off Windows, where an unquoted
  // `{"a":1,"b":2}` is BRACE-EXPANDED into `{a:1 b:2}`-ish garbage and the score
  // line never parses — green on Windows, red on Linux, which is where CI runs
  // this job. cmd.exe does not brace-expand and prints the quotes literally, but
  // `parseMutationHookOutput` matches the JSON substring, so the surrounding
  // quotes are harmless there.

  it("returns the hook's parsed score when it prints a trailing JSON line", async () => {
    MUT.cmd = `echo '{"score":0.75,"total":8,"survived":["a.ts:1"]}'`;
    expect(await mutationCheck(wt, task())).toEqual({
      score: 0.75,
      evaluated: 8,
      survivors: ["a.ts:1"],
    });
  });

  it("falls back to `evaluated` when `total` is absent, and reports NOTHING when both are", async () => {
    // #525 CHANGED THE SECOND HALF OF THIS TEST, deliberately. It previously
    // asserted a 99 fallback here, and its own comment explained the intent:
    // "99 is deliberately implausible so it reads as 'unknown denominator' on a
    // report." That intent was right and the representation could not carry it
    // — `evaluated: number` cannot say "unknown", so 99 printed as an ordinary
    // count (the escalate note read "99/99 survived" for a hook that reported
    // evaluating nothing) and cleared the `evaluated >= 5` rejection floor.
    //
    // The field now stays ABSENT, so no reader can mistake it for a
    // measurement, and the `evaluated >= 5` escalation floor requires a count
    // the hook actually reported rather than substituting one. A run that never
    // said how many mutants it evaluated warns instead of escalating — a
    // deliberate change, recorded in the CHANGELOG.
    MUT.cmd = `echo '{"score":0.5,"evaluated":4}'`;
    expect(await mutationCheck(wt, task())).toEqual({ score: 0.5, evaluated: 4, survivors: undefined });

    MUT.cmd = `echo '{"score":0.5}'`;
    expect(await mutationCheck(wt, task())).toEqual({ score: 0.5, evaluated: undefined, survivors: undefined });
  });

  it("reports a CONFIGURED-BUT-FAILED hook distinctly from an unconfigured one", async () => {
    // observability-002 (#187): both used to collapse to null, so a broken
    // integration was indistinguishable from mutation checking never running.
    // The exit code and the output tail are what make it actionable.
    MUT.cmd = `echo not-a-score-line && ${SHELL_FALSE}`;

    const result = await mutationCheck(wt, task());
    expect(result).not.toBeNull();
    expect(result).toHaveProperty("failed", true);
    const detail = (result as { detail: string }).detail;
    expect(detail).toMatch(/^exit 1: /);
    expect(detail).toContain("not-a-score-line");
  });

  it("says `(no output)` rather than dangling when a failing hook prints nothing", async () => {
    MUT.cmd = SHELL_FALSE;
    const result = await mutationCheck(wt, task());
    expect((result as { detail: string }).detail).toBe("exit 1 (no output)");
  });

  it("REDACTS a secret the hook prints before it reaches the task result", async () => {
    // The failure tail is retained on a report, so it crosses the same boundary
    // runGate's tail does. A hook that echoes its environment must not leak.
    MUT.cmd = `echo api_key=sk-ant-not-a-real-key-1234 && ${SHELL_FALSE}`;

    const result = await mutationCheck(wt, task());
    const detail = (result as { detail: string }).detail;
    expect(detail).not.toContain("sk-ant-not-a-real-key-1234");
    expect(detail).toContain("[REDACTED");
  });

  it("does not leak the dispatcher's API key into the hook's environment", async () => {
    // Least-privilege parity with run(): the operator-authored hook is a child
    // like any other and must not inherit the dispatcher's secrets.
    //
    // The planted value is deliberately NOT secret-shaped. An earlier version
    // used `sk-ant-...`, which `redactSecrets` strips from the failure tail on
    // its way out — so the assertion passed whether or not the env was scrubbed,
    // and removing `scrubbedEnv()` entirely left it green. A plain token can
    // only be absent because the scrub removed it.
    const previous = process.env.FARM_API_KEY;
    process.env.FARM_API_KEY = "PLAINDISPATCHERVALUE12345";
    try {
      // The separate marker line proves the hook actually ran, so the value's
      // absence means "scrubbed" rather than "never executed". It cannot ride on
      // the `v=[...]` line itself: on Windows an undefined `%FARM_API_KEY%` stays
      // literal, and the NAME trips the redactor's `api[_-]?key` rule, so that
      // line arrives redacted whole. The planted value is not secret-shaped, so
      // an unscrubbed env leaves it in the clear and visible.
      MUT.cmd =
        process.platform === "win32"
          ? `echo hook-did-run && echo v=[%FARM_API_KEY%] && ${SHELL_FALSE}`
          : `echo hook-did-run && echo "v=[$FARM_API_KEY]" && ${SHELL_FALSE}`;
      const detail = (await mutationCheck(wt, task()) as { detail: string }).detail;
      expect(detail).toContain("hook-did-run");
      expect(detail).not.toContain("PLAINDISPATCHERVALUE12345");
    } finally {
      if (previous === undefined) delete process.env.FARM_API_KEY;
      else process.env.FARM_API_KEY = previous;
    }
  });

  it("passes the FARM_MUTATION_* contract vars through to the hook", async () => {
    await write("src/a.ts", "export const a = 1;\n");
    await write("src/b.ts", "export const b = 2;\n");
    // All THREE vars the contract names. An earlier version echoed two while
    // the title promised the set, so dropping FARM_MUTATION_TEST_CMD from the
    // spawn was invisible.
    MUT.cmd =
      process.platform === "win32"
        ? `echo files=[%FARM_MUTATION_FILES%] test=[%FARM_MUTATION_TEST_PATH%] cmd=[%FARM_MUTATION_TEST_CMD%] && ${SHELL_FALSE}`
        : `echo "files=[$FARM_MUTATION_FILES] test=[$FARM_MUTATION_TEST_PATH] cmd=[$FARM_MUTATION_TEST_CMD]" && ${SHELL_FALSE}`;

    const detail = (await mutationCheck(wt, task({ filesInScope: ["src/a.ts", "src/b.ts", "src/impl.test.ts"] })) as { detail: string }).detail;
    // The test path is excluded from the mutation file list — mutating the test
    // would measure nothing about the implementation. TWO impl files, so the
    // comma separator is observable; with one the join is invisible.
    expect(detail).toContain("files=[src/a.ts,src/b.ts]");
    expect(detail).toContain("test=[src/impl.test.ts]");
    expect(detail).toContain(`cmd=[${SHELL_TRUE}]`);
  });

  it("runs the hook IN the worktree and keeps the TAIL of a long output", async () => {
    // Two properties one fixture can pin, because both need output the existing
    // cases are too small to expose:
    //
    //  - `cwd: wt`. The hook reads a file that exists only in the worktree, so a
    //    hook launched from anywhere else produces no marker.
    //  - `.slice(-500)`. The marker sits AFTER 600 characters of filler, so the
    //    last 500 characters contain it and the FIRST 500 do not. Every other
    //    hook fixture here is under 500 characters, where the two slices agree.
    await write("filler.txt", `${"A".repeat(600)}\nTAIL-MARKER-XYZ`);
    MUT.cmd = process.platform === "win32" ? `type filler.txt && ${SHELL_FALSE}` : `cat filler.txt && ${SHELL_FALSE}`;

    const detail = (await mutationCheck(wt, task()) as { detail: string }).detail;
    // Present ONLY if the tail was taken: the marker sits past character 600, so
    // `slice(0, 500)` cannot reach it, and a hook launched outside the worktree
    // never produces it.
    expect(detail).toContain("TAIL-MARKER-XYZ");
    // ...and the tail is BOUNDED. Without any slice the whole 616-character
    // output would ride into the task result and onto the report.
    expect(detail.length).toBeLessThan(520);
  });
});

describe("mutationCheck — built-in text mutation", () => {
  const IMPL = [
    "export function classify(n) {",
    "  if (n >= 10) {",
    "    return true;",
    "  }",
    "  if (n === 0) {",
    "    return false;",
    "  }",
    "  return n > 5;",
    "}",
  ].join("\n");

  /**
   * A gate whose exit code DEPENDS ON THE FILE ON DISK.
   *
   * This is the difference between testing the engine and testing nothing. A
   * `true`/`false` gate returns the same code no matter what was written, so
   * mutate -> run -> classify is entirely unobserved: measured, replacing the
   * mutant write with a write of the ORIGINAL survives the whole 402-test tools
   * suite. Every assertion about scores and survivors below is only meaningful
   * because this gate can tell the two apart.
   *
   * Written as a file rather than `node -e "..."` deliberately — an inline
   * script has to survive both `cmd.exe` and `bash -c` quoting, which is how the
   * hook fixtures in this file got brace-expanded on Linux.
   */
  async function writeContentSensitiveGate(needle: string): Promise<string> {
    await write(
      "check.cjs",
      [
        'const fs = require("fs");',
        'const src = fs.readFileSync("src/impl.ts", "utf8");',
        `process.exit(src.includes(${JSON.stringify(needle)}) ? 0 : 1);`,
      ].join("\n"),
    );
    return "node check.cjs";
  }

  it("puts the trivial-file cutoff at exactly two code lines", async () => {
    // Both sides of `codeLineCount(src) <= 2`. At two lines the file is skipped
    // as "nothing to constrain" and the run has nothing to evaluate; at three it
    // is mutated like any other. One line either way and the cutoff moves
    // unnoticed, silently dropping files from the signal.
    //
    // Each line carries THREE mutable operators on purpose. With one apiece the
    // two-line file yields only two mutants, which falls under the `evaluated
    // < 3` floor and returns null anyway — so the test would pass under either
    // threshold, for the wrong reason. Three per line clears that floor and
    // makes the cutoff the only thing deciding the outcome.
    const line = (i: number) => `const v${i} = a${i} >= 1 && b${i} > 2;`;

    await write("src/impl.ts", [line(0), line(1)].join("\n"));
    expect(await mutationCheck(wt, task({ gate: { commands: [SHELL_FALSE] } }))).toBeNull();

    await write("src/impl.ts", [line(0), line(1), line(2)].join("\n"));
    MUT.sample = 3;
    const result = await mutationCheck(wt, task({ gate: { commands: [SHELL_FALSE] } }));
    expect(result).not.toBeNull();
    expect((result as { evaluated: number }).evaluated).toBe(3);
  });

  it("returns null when the in-scope file does not exist", async () => {
    expect(await mutationCheck(wt, task({ filesInScope: ["src/absent.ts"] }))).toBeNull();
  });

  it("scores 1 and reports no survivors when the gate catches every mutant", async () => {
    await write("src/impl.ts", IMPL);
    MUT.sample = 6;

    const result = await mutationCheck(wt, task({ gate: { commands: [SHELL_FALSE] } }));
    expect(result).not.toBeNull();
    const { score, evaluated, survivors } = result as { score: number; evaluated: number; survivors: string[] };
    expect(score).toBe(1);
    expect(evaluated).toBe(6);
    expect(survivors).toEqual([]);
  });

  it("scores 0 and names every survivor when the gate catches none", async () => {
    // A gate that passes regardless is the "test does not constrain the impl"
    // case — a near-zero score is what hard-escalates, so the tags must be
    // specific enough for a human to act on.
    await write("src/impl.ts", IMPL);
    MUT.sample = 4;

    const result = await mutationCheck(wt, task({ gate: { commands: [SHELL_TRUE] } }));
    const { score, evaluated, survivors } = result as { score: number; evaluated: number; survivors: string[] };
    expect(score).toBe(0);
    expect(evaluated).toBe(4);
    expect(survivors).toHaveLength(4);
    for (const tag of survivors) expect(tag).toMatch(/^src\/impl\.ts:\d+ /);
  });

  it("actually MUTATES the file, re-runs the gate, and classifies by the result", async () => {
    // The engine's whole contract, and the only test here that can observe it.
    // The gate passes iff `>= 10` is still present, so the mutant that rewrites
    // that operator MUST be killed while mutants on other lines survive.
    //
    // Measured against this test: writing the original instead of the mutant,
    // dropping the mutant write entirely, and having generateMutants emit
    // unmutated source ALL survive a `true`/`false` gate. None survive this one.
    await write("src/impl.ts", IMPL);
    const gate = await writeContentSensitiveGate(">= 10");
    MUT.sample = 20; // above the candidate count, so nothing is sampled away

    const result = await mutationCheck(wt, task({ gate: { commands: [gate] } }));
    expect(result).not.toBeNull();
    const { score, evaluated, survivors } = result as { score: number; evaluated: number; survivors: string[] };

    // Some mutants died and some lived — a 0 or a 1 here would mean the gate
    // ignored the file, which is exactly the failure this test exists to catch.
    expect(score).toBeGreaterThan(0);
    expect(score).toBeLessThan(1);
    expect(survivors.length).toBeGreaterThan(0);
    expect(survivors.length).toBeLessThan(evaluated);

    // The `>=` mutant on line 2 rewrites the needle, so the gate fails and it is
    // KILLED — it must not appear among the survivors.
    expect(survivors).not.toContain("src/impl.ts:2 >=>");
    // ...while line 8's `>` mutant leaves the needle intact and survives. The
    // EXACT tag is asserted, not a shape: it pins the file, the 1-indexed line,
    // and the rule name together. A tag carrying the wrong line or a generic
    // name still matches `/^src\/impl\.ts:\d+ /`, and a reviewer chasing a
    // survivor to the wrong line learns nothing.
    expect(survivors).toContain("src/impl.ts:8 >>=");
  });

  it("restores the original file through BOTH the in-loop and the final path", async () => {
    // A mutant left on disk is corrupted worker output that the gate already
    // passed. Two mechanisms guarantee it is gone: the per-iteration restore and
    // the `finally` sweep. Either alone passes a simple end-state check, so the
    // end state is asserted here AND the mid-run state is asserted by the gate
    // itself, which records what it saw on every invocation.
    await write("src/impl.ts", IMPL);
    await write("orig.txt", IMPL);
    // The probe compares against the ORIGINAL rather than looking for one
    // needle. A needle only changes for the mutant that rewrites that specific
    // line, and with a random shuffle over more candidates than the sample, that
    // mutant is often not drawn — measured, a needle-based probe here failed
    // about one run in three. Comparing whole contents makes every iteration
    // report "mutated" deterministically.
    await write(
      "check.cjs",
      [
        'const fs = require("fs");',
        'const cur = fs.readFileSync("src/impl.ts", "utf8");',
        'const orig = fs.readFileSync("orig.txt", "utf8");',
        'fs.appendFileSync("seen.log", cur === orig ? "clean\\n" : "mutated\\n");',
        "process.exit(0);",
      ].join("\n"),
    );
    MUT.sample = 6;

    await mutationCheck(wt, task({ gate: { commands: ["node check.cjs"] } }));

    expect(await readFile(path.join(wt, "src/impl.ts"), "utf8")).toBe(IMPL);
    // The gate ran against a MUTATED file at least once — proof the restore is
    // undoing real work rather than a no-op over an untouched file.
    expect(await readFile(path.join(wt, "seen.log"), "utf8")).toContain("mutated");
  });

  it("returns null rather than a score when too few mutants were evaluated", async () => {
    // Below three, the denominator is too small to judge fairly and a score
    // would read as signal it has not earned.
    await write("src/impl.ts", IMPL);
    MUT.sample = 2;
    expect(await mutationCheck(wt, task({ gate: { commands: [SHELL_TRUE] } }))).toBeNull();
  });

  it("stops mid-run at the wall-clock budget and scores only what it evaluated", async () => {
    // Two properties in one run, because both need a budget that expires PART
    // WAY through rather than before the first iteration:
    //
    //  - the denominator is `evaluated`, not `candidates.length`. With every
    //    mutant evaluated the two are equal and the difference is invisible;
    //    measured, swapping them survives the whole tools suite.
    //  - the break is real. A 400ms gate against a 1500ms budget stops after
    //    three or four iterations — the assertion is a RANGE with wide margins
    //    on both sides, not a tuned count, so process-spawn jitter cannot flake
    //    it. (A 200ms gate was too tight: spawn overhead alone is ~200ms here,
    //    so only two iterations fit and the fairness floor returned null.)
    await write("src/impl.ts", IMPL);
    await write("slow-fail.cjs", "setTimeout(() => process.exit(1), 400);");
    MUT.sample = 8;
    MUT.budgetMs = 1500;

    const result = await mutationCheck(wt, task({ gate: { commands: ["node slow-fail.cjs"] } }));
    expect(result).not.toBeNull();
    const { score, evaluated } = result as { score: number; evaluated: number };

    // Stopped short of the sample, but past the fairness floor.
    expect(evaluated).toBeGreaterThanOrEqual(3);
    expect(evaluated).toBeLessThan(8);
    // Every evaluated mutant was killed, so the score is 1 — and ONLY if the
    // denominator is what was evaluated. Over candidates.length it would be
    // evaluated/8, well under 1.
    expect(score).toBe(1);
  });

  // EQUIVALENT MUTANTS — deleting either of these guards changes no observable
  // behaviour, so no test can kill them and none is written to pretend
  // otherwise:
  //
  //  - `if (literals.length === 0) return { risk: "none" };`  With it deleted
  //    the scope loop runs over an EMPTY literal list, produces no hits, and
  //    returns "none" by the next guard down. Pure short-circuit.
  //  - `if (candidates.length === 0) return null;`  With it deleted,
  //    `shuffle([]).slice(0, n)` is `[]`, the loop body never runs, `evaluated`
  //    stays 0, and the `evaluated < 3` floor returns null anyway.
  //
  // Both were reported as surviving by review. They survive because they are
  // optimisations, not behaviour.

  // DELIBERATELY NOT PINNED, each measured as surviving and each for a reason:
  //
  //  - `Date.now() - start > MUT.budgetMs` relaxed to `>=`. The two differ ONLY
  //    when elapsed equals the budget exactly, which for a zero budget means
  //    racing the millisecond tick between `start` and the first check. Windows
  //    has ~15ms timer granularity so elapsed is almost always 0 there; Linux
  //    has 1ms resolution and it is a coin flip. A test that counted gate
  //    invocations at budget 0 was added here on review feedback, passed CI once
  //    by luck, and failed on a clean Linux run with ENOENT because ZERO gates
  //    ran. It has been removed: it was a flake, not a guard, which is what the
  //    original note said before it was over-corrected.
  //  - `shuffle()` replaced by identity or by reverse. Nothing here asserts
  //    sampling ORDER, and pinning it would mean either freezing Math.random or
  //    asserting a statistical property — the first tests the stub, the second
  //    is a flake. The shuffle exists so repeated runs sample differently; that
  //    is a property of many runs, not of one.
  //  - the in-loop restore and the `finally` sweep, INDIVIDUALLY. They are
  //    mutually redundant: the next iteration rewrites the file wholesale from
  //    `originals`, and the `finally` sweep covers the exit. Removing EITHER
  //    leaves the observable end state correct — removing BOTH does not, and
  //    that combination IS killed. Same layered-guard shape as worktree-fs.ts,
  //    and the same conclusion: the property is pinned, the individual layers
  //    cannot be.

  it("stops at the wall-clock budget and reports nothing when it expires first", async () => {
    // Budget 0 means the very first iteration breaks, so nothing is evaluated
    // and the result is null rather than a score over zero mutants.
    await write("src/impl.ts", IMPL);
    MUT.sample = 6;
    MUT.budgetMs = 0;

    expect(await mutationCheck(wt, task({ gate: { commands: [SHELL_TRUE] } }))).toBeNull();
    expect(await readFile(path.join(wt, "src/impl.ts"), "utf8")).toBe(IMPL);
  });
});
