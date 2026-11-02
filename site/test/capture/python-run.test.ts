/** python-run.test.ts - how the harness finds Python and which files it records as executed.
 *
 * Interpreter: an explicit PYTHON wins; otherwise a host that ships only
 * `python3` (macOS, most Linux images) must still work, while Windows keeps
 * `python` because `python3` there is usually the Microsoft Store stub.
 *
 * Executed files: the recorded hashes must cover every repository file the tool
 * ran, including a file the tool loads by path without registering it in
 * sys.modules. hostapi.load_host() does exactly that to `_host.py`.
 */
import type { SpawnSyncReturns } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, describe, expect, it, vi } from "vitest";
import { pythonCandidates, RUNNER, spawnPython } from "../../scripts/capture/harness";

const scratch: string[] = [];
afterAll(() => {
  for (const dir of scratch) rmSync(dir, { recursive: true, force: true });
});

function result(partial: Partial<SpawnSyncReturns<string>>): SpawnSyncReturns<string> {
  return { pid: 1, output: [], stdout: "", stderr: "", status: 0, signal: null, ...partial };
}

const missing = (): SpawnSyncReturns<string> => result({ status: null, error: Object.assign(new Error("spawn ENOENT"), { code: "ENOENT" }) });

describe("Python interpreter selection", () => {
  it("prefers an explicit PYTHON and tries nothing else", () => {
    expect(pythonCandidates({ PYTHON: "/opt/py/bin/python3.12" }, "linux")).toEqual(["/opt/py/bin/python3.12"]);
    expect(pythonCandidates({ PYTHON: "py" }, "win32")).toEqual(["py"]);
  });

  it("tries python3 and then python on a POSIX host, and only python on Windows", () => {
    expect(pythonCandidates({}, "linux")).toEqual(["python3", "python"]);
    expect(pythonCandidates({ PYTHON: "" }, "darwin")).toEqual(["python3", "python"]);
    expect(pythonCandidates({}, "win32")).toEqual(["python"]);
  });

  it("falls back to the next interpreter only when the first is not found", () => {
    const spawn = vi.fn((command: string) => (command === "python3" ? missing() : result({ stdout: "ok" })));
    const run = spawnPython(["python3", "python"], ["-c", "pass"], { encoding: "utf8" }, spawn as never);
    expect(run.python).toBe("python");
    expect(run.result.stdout).toBe("ok");
    expect(spawn.mock.calls.map((call) => call[0])).toEqual(["python3", "python"]);
  });

  it("does not retry after any other failure, so a broken interpreter is not hidden", () => {
    const broken = result({ status: null, error: Object.assign(new Error("spawn EACCES"), { code: "EACCES" }) });
    const spawn = vi.fn(() => broken);
    const run = spawnPython(["python3", "python"], [], { encoding: "utf8" }, spawn as never);
    expect(spawn).toHaveBeenCalledTimes(1);
    expect(run.python).toBe("python3");
    expect(run.result.error).toBeDefined();
  });

  it("does not retry a failing run whose exit status is non-zero", () => {
    const spawn = vi.fn(() => result({ status: 3 }));
    expect(spawnPython(["python3", "python"], [], { encoding: "utf8" }, spawn as never).result.status).toBe(3);
    expect(spawn).toHaveBeenCalledTimes(1);
  });

  it("reports the missing interpreter when there is nothing left to try", () => {
    const spawn = vi.fn(() => missing());
    const run = spawnPython(["python"], [], { encoding: "utf8" }, spawn as never);
    expect(spawn).toHaveBeenCalledTimes(1);
    expect(run.python).toBe("python");
    expect(run.result.error).toMatchObject({ code: "ENOENT" });
  });
});

describe("executed-file recording", () => {
  /** A throwaway repository with a plain import, a file loaded by path, and a file never run. */
  function sandbox() {
    const repo = mkdtempSync(join(tmpdir(), "py-runner-test-"));
    scratch.push(repo);
    mkdirSync(join(repo, "tools"), { recursive: true });
    writeFileSync(join(repo, "tools", "lib.py"), "VALUE = 1\n");
    writeFileSync(join(repo, "tools", "by_path.py"), "VALUE = 2\n");
    writeFileSync(join(repo, "tools", "never_run.py"), "VALUE = 3\n");
    writeFileSync(
      join(repo, "tools", "entry.py"),
      [
        "import importlib.util",
        "import os",
        "import lib",
        "here = os.path.dirname(os.path.abspath(__file__))",
        'spec = importlib.util.spec_from_file_location("loaded_by_path", os.path.join(here, "by_path.py"))',
        "module = importlib.util.module_from_spec(spec)",
        "spec.loader.exec_module(module)",
        "print(lib.VALUE, module.VALUE)",
        "",
      ].join("\n"),
    );
    return repo;
  }

  function runRunner(repo: string, entry: string): { files: string[]; stdout: string; status: number | null } {
    const side = join(repo, "side.json");
    const { result: run } = spawnPython(
      pythonCandidates(process.env, process.platform),
      ["-B", "-X", "utf8", RUNNER, side, repo, join(repo, entry)],
      { cwd: repo, encoding: "utf8", windowsHide: true, timeout: 60_000 },
    );
    return { files: JSON.parse(readFileSync(side, "utf8")), stdout: run.stdout, status: run.status };
  }

  it("records a file the tool loads by path without registering it in sys.modules", () => {
    const repo = sandbox();
    const run = runRunner(repo, "tools/entry.py");
    expect(run.status).toBe(0);
    expect(run.stdout.trim()).toBe("1 2");
    expect(run.files).toEqual(["tools/by_path.py", "tools/entry.py", "tools/lib.py"]);
  }, 60_000);

  it("does not record repository files the tool never ran", () => {
    const run = runRunner(sandbox(), "tools/entry.py");
    expect(run.files).not.toContain("tools/never_run.py");
  }, 60_000);
});
