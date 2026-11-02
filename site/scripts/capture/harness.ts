/** harness.ts - run one deterministic codeArbiter tool and record the evidence (AC-05, DEC-04).
 *
 * A capture is the output of a repository script run against a temporary
 * fixture: no model call, no network, no write outside the fixture (CON-03).
 * Each record keeps the argv, the normalized output and the sha256 of every
 * repository source the interpreter executed, so `npm run gen` can tell when a
 * captured tool changed after its output was recorded (verify.ts).
 */

import { spawnSync, type SpawnSyncOptionsWithStringEncoding, type SpawnSyncReturns } from "node:child_process";
import { readFileSync } from "node:fs";
import { isAbsolute, join, relative, resolve } from "node:path";
import { createFixture, type Fixture } from "./fixture";
import { FIXTURE_PREFIX, hashFileLf, normalizeArgv, normalizeText } from "./normalize";

export const REPO_ROOT = resolve(import.meta.dirname, "..", "..", "..");
export const RUNNER = join(import.meta.dirname, "py-runner.py");
const RUN_TIMEOUT_MS = 60_000;

/** Which text a capture shows: one of the tool's streams, or a file the tool left in the fixture. */
export type ShownText =
  | { stream: "stdout" | "stderr" }
  | { file: string; head?: number; tail?: number };

export interface CaptureTarget {
  id: string;
  title: string;
  /** Repository-relative path of the Python entry script. */
  tool: string;
  /** Arguments after the script; `{project}` and `{home}` become the fixture's paths. */
  args: string[];
  stdin?: string;
  /** Build the fixture the tool runs against. */
  setup(fixture: Fixture): void;
  show: ShownText;
  expectExitCode: number;
}

export interface CapturedSource {
  path: string;
  sha256: string;
}

export interface CaptureRecord {
  schema: 1;
  id: string;
  title: string;
  tool: string;
  argv: string[];
  exitCode: number;
  shown: string;
  output: string;
  hashing: "sha256 over file bytes with CRLF collapsed to LF";
  sources: CapturedSource[];
}

export interface PythonRun {
  status: number;
  stdout: string;
  stderr: string;
  /** Repository-relative POSIX paths of the entry script and every repository module it loaded, sorted. */
  modules: string[];
}

/**
 * The interpreters to try, in order. An explicit PYTHON is used alone. Otherwise
 * a POSIX host tries `python3` and then `python`, because many hosts ship only
 * one of them; Windows tries only `python`, since `python3` there is usually the
 * Microsoft Store stub rather than an interpreter.
 */
export function pythonCandidates(env: NodeJS.ProcessEnv, platform: NodeJS.Platform): string[] {
  if (env.PYTHON) return [env.PYTHON];
  return platform === "win32" ? ["python"] : ["python3", "python"];
}

/**
 * Spawn the first interpreter that exists. Only "not found" moves on to the next
 * candidate; any other failure, and any non-zero exit, is returned as it is so a
 * broken interpreter is never hidden by a second try.
 */
export function spawnPython(
  candidates: readonly string[],
  args: string[],
  options: SpawnSyncOptionsWithStringEncoding,
  spawn: typeof spawnSync = spawnSync,
): { python: string; result: SpawnSyncReturns<string> } {
  let python = candidates[0];
  let result = spawn(python, args, options);
  for (const next of candidates.slice(1)) {
    const notFound = result.error && (result.error as NodeJS.ErrnoException).code === "ENOENT";
    if (!notFound) break;
    python = next;
    result = spawn(python, args, options);
  }
  return { python, result };
}

/** Run a repository script through the module-recording runner inside `fixture`. */
export function runPythonEntry(
  fixture: Fixture,
  tool: string,
  args: string[],
  options: { stdin?: string; env?: NodeJS.ProcessEnv } = {},
): PythonRun {
  const entry = resolve(REPO_ROOT, tool);
  const inside = relative(REPO_ROOT, entry);
  if (inside.startsWith("..") || isAbsolute(inside)) {
    throw new Error(`Capture tool must be inside the repository: ${tool}`);
  }
  const sideFile = join(fixture.tmp, "loaded-modules.json");
  const { python, result } = spawnPython(
    pythonCandidates(process.env, process.platform),
    ["-B", "-X", "utf8", RUNNER, sideFile, REPO_ROOT, entry, ...args],
    {
      cwd: fixture.project,
      env: { ...fixture.env, ...options.env },
      input: options.stdin,
      encoding: "utf8",
      windowsHide: true,
      timeout: RUN_TIMEOUT_MS,
    },
  );
  if (result.error) throw new Error(`Could not run ${python} for ${tool}: ${result.error.message}`);
  if (result.status === null) throw new Error(`${tool} did not finish: ${result.signal ?? "no exit status"}`);
  let modules: string[];
  try {
    modules = JSON.parse(readFileSync(sideFile, "utf8")) as string[];
  } catch {
    throw new Error(`${tool} left no loaded-module list (exit ${result.status}):\n${result.stderr}`);
  }
  return { status: result.status, stdout: result.stdout, stderr: result.stderr, modules };
}

function selectLines(text: string, show: { head?: number; tail?: number }): string {
  const lines = text.replace(/\r\n/g, "\n").replace(/\n+$/, "").split("\n");
  if (show.head !== undefined) return lines.slice(0, show.head).join("\n");
  if (show.tail !== undefined) return lines.slice(-show.tail).join("\n");
  return lines.join("\n");
}

function describeShown(show: ShownText): string {
  if ("stream" in show) return show.stream;
  const part = show.head !== undefined ? ` (first ${show.head} lines)` : show.tail !== undefined ? ` (last ${show.tail} lines)` : "";
  return `file ${show.file}${part}`;
}

function substitute(args: readonly string[], fixture: Fixture): string[] {
  return args.map((arg) => arg.replaceAll("{project}", fixture.project).replaceAll("{home}", fixture.home));
}

/** Run a target in a fresh fixture and return its record. The fixture is always removed. */
export function runCapture(target: CaptureTarget): CaptureRecord {
  const fixture = createFixture();
  try {
    target.setup(fixture);
    const args = substitute(target.args, fixture);
    const run = runPythonEntry(fixture, target.tool, args, { stdin: target.stdin });
    if (run.status !== target.expectExitCode) {
      throw new Error(
        `Capture "${target.id}": ${target.tool} returned exit code ${run.status}, expected ${target.expectExitCode}.\n` +
          `stdout: ${run.stdout}\nstderr: ${run.stderr}`,
      );
    }
    let raw: string;
    if ("stream" in target.show) {
      raw = run[target.show.stream];
    } else {
      raw = selectLines(readFileSync(join(fixture.project, ...target.show.file.split("/")), "utf8"), target.show);
    }
    const options = { aliases: fixture.aliases };
    const output = normalizeText(raw, options);
    if (!output) throw new Error(`Capture "${target.id}" produced no output to show (${describeShown(target.show)}).`);
    if (output.includes(FIXTURE_PREFIX)) {
      throw new Error(`Capture "${target.id}" still contains a temporary path after normalization:\n${output}`);
    }
    return {
      schema: 1,
      id: target.id,
      title: target.title,
      tool: target.tool,
      argv: normalizeArgv(["python", target.tool, ...args], options),
      exitCode: run.status,
      shown: describeShown(target.show),
      output,
      hashing: "sha256 over file bytes with CRLF collapsed to LF",
      sources: run.modules.map((path) => ({ path, sha256: hashFileLf(join(REPO_ROOT, ...path.split("/"))) })),
    };
  } finally {
    fixture.dispose();
  }
}
