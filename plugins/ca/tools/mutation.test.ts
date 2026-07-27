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
const saved = { ...MUT };

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
    await write("src/impl.test.ts", "expect(x).toBe(1);\nexpect(y).toBe(0);\n");
    await write("src/impl.ts", "export const x = 1;\n");
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
  it("returns the hook's parsed score when it prints a trailing JSON line", async () => {
    MUT.cmd = `echo {"score":0.75,"total":8,"survived":["a.ts:1"]}`;
    expect(await mutationCheck(wt, task())).toEqual({
      score: 0.75,
      evaluated: 8,
      survivors: ["a.ts:1"],
    });
  });

  it("falls back to `evaluated` then to 99 when `total` is absent", async () => {
    // The `total ?? evaluated ?? 99` chain. A hook that reports neither still
    // yields a usable result rather than NaN — 99 is deliberately implausible so
    // it reads as "unknown denominator" on a report.
    MUT.cmd = `echo {"score":0.5,"evaluated":4}`;
    expect(await mutationCheck(wt, task())).toEqual({ score: 0.5, evaluated: 4, survivors: [] });

    MUT.cmd = `echo {"score":0.5}`;
    expect(await mutationCheck(wt, task())).toEqual({ score: 0.5, evaluated: 99, survivors: [] });
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
    MUT.cmd =
      process.platform === "win32"
        ? `echo files=[%FARM_MUTATION_FILES%] test=[%FARM_MUTATION_TEST_PATH%] && ${SHELL_FALSE}`
        : `echo "files=[$FARM_MUTATION_FILES] test=[$FARM_MUTATION_TEST_PATH]" && ${SHELL_FALSE}`;

    const detail = (await mutationCheck(wt, task({ filesInScope: ["src/impl.ts", "src/impl.test.ts"] })) as { detail: string }).detail;
    // The test path is excluded from the mutation file list — mutating the test
    // would measure nothing about the implementation.
    expect(detail).toContain("files=[src/impl.ts]");
    expect(detail).toContain("test=[src/impl.test.ts]");
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

  it("RESTORES the original file after mutating it, whatever the outcome", async () => {
    // The single most consequential property here: a mutant left on disk is
    // corrupted worker output that the gate already passed. Asserted on the
    // survivor path, where every mutant is written and rolled back.
    await write("src/impl.ts", IMPL);
    MUT.sample = 5;

    await mutationCheck(wt, task({ gate: { commands: [SHELL_TRUE] } }));
    expect(await readFile(path.join(wt, "src/impl.ts"), "utf8")).toBe(IMPL);
  });

  it("returns null rather than a score when too few mutants were evaluated", async () => {
    // Below three, the denominator is too small to judge fairly and a score
    // would read as signal it has not earned.
    await write("src/impl.ts", IMPL);
    MUT.sample = 2;
    expect(await mutationCheck(wt, task({ gate: { commands: [SHELL_TRUE] } }))).toBeNull();
  });

  // DELIBERATELY NOT PINNED, both measured as surviving:
  //
  //  - `Date.now() - start > MUT.budgetMs` relaxed to `>=`. The two differ only
  //    when the elapsed time is exactly 0ms, so distinguishing them means racing
  //    the clock; a test that did would be a flake, not a guard.
  //  - the in-loop `writeWorktreeFile(wt, c.file, orig)` restore removed. The
  //    `finally` block restores every original from the same map, so the file is
  //    correct at the end either way. The in-loop call is a narrower guarantee
  //    (correct BETWEEN iterations) that nothing outside the loop can observe.
  //
  // Recorded rather than papered over with an assertion that pins neither.

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
