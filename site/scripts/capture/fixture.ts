/** fixture.ts - the disposable repository and the explicit environment a capture runs in (CON-03).
 *
 * A capture may only run codeArbiter's own deterministic tools. Everything the
 * tool can read or write is therefore inside one temporary directory: the
 * project, a fake home, and a temp area. The environment is built from an
 * allowlist rather than inherited, so this session's host variables, git
 * identity and credentials can never leak into a committed asset.
 */

import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, join, resolve } from "node:path";
import { FIXTURE_PREFIX, type PathAlias } from "./normalize";

export interface FixtureDirs {
  project: string;
  home: string;
  tmp: string;
}

/** Variables a tool needs just to start: where programs are found and, on Windows, the system directory. */
const ENV_ALLOWLIST = new Set([
  "path",
  "pathext",
  "systemroot",
  "systemdrive",
  "windir",
  "comspec",
  "programdata",
  "programfiles",
  "programfiles(x86)",
  "programw6432",
]);

/** The environment for one captured run: the allowlist plus fixed, fixture-local values. */
export function buildCaptureEnv(base: NodeJS.ProcessEnv, dirs: FixtureDirs): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {};
  for (const [key, value] of Object.entries(base)) {
    if (value !== undefined && ENV_ALLOWLIST.has(key.toLowerCase())) env[key] = value;
  }
  return {
    ...env,
    HOME: dirs.home,
    USERPROFILE: dirs.home,
    TMP: dirs.tmp,
    TEMP: dirs.tmp,
    TMPDIR: dirs.tmp,
    CLAUDE_PROJECT_DIR: dirs.project,
    CODEARBITER_HOST: "claude",
    GIT_CONFIG_GLOBAL: join(dirs.home, ".gitconfig").replaceAll("\\", "/"),
    GIT_CONFIG_NOSYSTEM: "1",
    GIT_TERMINAL_PROMPT: "0",
    // A run must not write bytecode into the plugin tree, and must decode the same everywhere.
    PYTHONDONTWRITEBYTECODE: "1",
    PYTHONNOUSERSITE: "1",
    PYTHONUTF8: "1",
    PYTHONIOENCODING: "utf-8",
    NO_COLOR: "1",
  };
}

export interface Fixture extends FixtureDirs {
  root: string;
  /** Every spelling of the fixture directories, for the normalizer. */
  aliases: PathAlias[];
  env: NodeJS.ProcessEnv;
  /** Write an LF text file under the project, creating parent directories. */
  write(relative: string, content: string): void;
  /** Write an LF text file under the fake home. */
  writeHome(relative: string, content: string): void;
  /** Run git inside the project with the fixture environment and return stdout. */
  git(...args: string[]): string;
  /** Initialize the project as a repository with a fixed, example-only identity. */
  initGit(options?: { branch?: string; email?: string; name?: string }): void;
  dispose(): void;
}

/** Remove a fixture root, refusing anything that is not a capture fixture directly under the OS temp directory. */
export function disposeFixtureRoot(root: string): void {
  const resolved = resolve(root);
  const parent = dirname(resolved);
  const safeParents = new Set([resolve(tmpdir()).toLowerCase()]);
  try {
    safeParents.add(realpathSync.native(tmpdir()).toLowerCase());
  } catch {
    // The OS temp directory always exists; the plain form above is enough if it cannot be resolved.
  }
  const parentOk = safeParents.has(parent.toLowerCase());
  if (!basename(resolved).startsWith(FIXTURE_PREFIX) || !parentOk) {
    throw new Error(`Refusing to remove non-temporary capture path (not a capture fixture): ${root}`);
  }
  rmSync(resolved, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
}

export function createFixture(): Fixture {
  const made = mkdtempSync(join(tmpdir(), FIXTURE_PREFIX));
  // Long-name form, so a Windows 8.3 temp directory and its real name are one spelling.
  const root = realpathSync.native(made);
  const dirs: FixtureDirs = { project: join(root, "project"), home: join(root, "home"), tmp: join(root, "tmp") };
  for (const dir of Object.values(dirs)) mkdirSync(dir, { recursive: true });

  const seen = new Set<string>();
  const aliases: PathAlias[] = [];
  const alias = (path: string, token: string) => {
    if (seen.has(path)) return;
    seen.add(path);
    aliases.push({ path, token });
  };
  for (const base of new Set([root, made])) {
    alias(join(base, "project"), "<project>");
    alias(join(base, "home"), "~");
    alias(base, "<fixture>");
  }

  const env = buildCaptureEnv(process.env, dirs);
  const writeText = (base: string, relative: string, content: string) => {
    const target = join(base, ...relative.split("/"));
    mkdirSync(dirname(target), { recursive: true });
    writeFileSync(target, content, "utf8");
  };
  const git = (...args: string[]): string => {
    const result = spawnSync("git", args, { cwd: dirs.project, env, encoding: "utf8", windowsHide: true });
    if (result.error || result.status !== 0) {
      throw new Error(`git ${args.join(" ")} failed (${result.status}): ${result.error?.message ?? result.stderr}`);
    }
    return result.stdout;
  };

  return {
    ...dirs,
    root,
    aliases,
    env,
    write: (relative, content) => writeText(dirs.project, relative, content),
    writeHome: (relative, content) => writeText(dirs.home, relative, content),
    git,
    initGit: ({ branch = "main", email = "you@example.com", name = "Example Author" } = {}) => {
      git("init", "-q", "-b", branch);
      git("config", "user.email", email);
      git("config", "user.name", name);
      git("config", "core.autocrlf", "false");
      git("config", "commit.gpgsign", "false");
    },
    dispose: () => disposeFixtureRoot(root),
  };
}
