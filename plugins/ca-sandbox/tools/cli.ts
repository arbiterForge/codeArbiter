/**
 * cli.ts — ca-sandbox subcommand dispatch surface (T-15).
 *
 * Covers AC-01 (create), AC-09 (exec), AC-10 (cp), AC-11 (destroy/prune). This is
 * the WIRING layer: it turns a `sandbox <subcommand> ...` argv into a typed command
 * and dispatches it to the module that owns the behavior — create.ts / destroy.ts
 * (+ prune) / exec.ts / cp.ts. The behavior, and its docker-gated proof, lives in
 * those modules (T-09/T-11/T-12); cli.ts adds no docker of its own.
 *
 * Design, mirroring farm.ts's `main()` house style:
 *   - parseCli(argv) is PURE: it validates args and returns a discriminated
 *     `Command` (or THROWS `CliError`). No side effects, so dispatch is unit
 *     testable without real docker. Every subcommand parses ONLY the flags it
 *     knows; any UNKNOWN FLAG is a `CliError` (the task's explicit obligation).
 *   - runCli(argv, handlers) parses then dispatches to an injectable `Handlers`
 *     table (the real handlers shell the modules; tests inject fakes). It returns
 *     a PROCESS EXIT CODE and never throws for a usage error — a `CliError` is
 *     caught, printed to stderr, and mapped to exit 2. An `exec`'s in-container
 *     exit code propagates as the CLI's exit code (AC-09 `exitCode:7`), as does a
 *     non-zero `cp`.
 *
 * The `exec` subcommand honors a `--` separator: everything after `--` is the
 * in-container argv VERBATIM (so `exec <id> -- ls --all` runs `ls --all` inside,
 * and `--all` is NOT treated as an unknown CLI flag). The `cp` subcommand parses
 * only the pull direction `<id>:<path> <dest>` (AC-10) — a source lacking the
 * `<id>:` container prefix is rejected, so the CLI can never express a
 * host->container push.
 *
 * Windows/CRLF/MSYS handling is delegated entirely to the modules (each already
 * sets MSYS_NO_PATHCONV=1 when shelling docker — Spike A/B); cli.ts shells nothing
 * by default and so needs none of it for parsing.
 */
import { fileURLToPath } from "node:url";
import path from "node:path";
import { spawnSync } from "node:child_process";

import { createSandbox, type CreateResult } from "./create.ts";
import { destroySandbox, prune, type DestroyResult, type PruneResult } from "./destroy.ts";
import { execInSandbox, type ExecResult } from "./exec.ts";
import { cpOut, type RunResult } from "./cp.ts";
import { resolveContainerId } from "./registry.ts";

// On Windows + Git Bash, container paths / args handed to docker get mangled by
// MSYS path conversion; the modules set this themselves, and the interactive
// `shell` handler (which shells docker directly) sets it too (Spike A/B).
const DOCKER_ENV = { ...process.env, MSYS_NO_PATHCONV: "1" };

/** The three CLI-exposed network policies (run.ts treats the latter two as the
 * pass-through richer policies; cli.ts only accepts these known names). */
export const NET_POLICIES = ["offline", "clone-then-cut", "allowlist"] as const;
export type CliNetPolicy = (typeof NET_POLICIES)[number];

/** Default in-container shell for the interactive `shell` subcommand. */
export const DEFAULT_SHELL = "sh";

/**
 * A usage error: an unknown subcommand, a missing required arg, an unknown flag,
 * or an out-of-range flag value. runCli catches this and exits 2 — it is never a
 * crash. Distinct type so callers/tests can assert it specifically.
 */
export class CliError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CliError";
  }
}

// --------------------------------------------------------------------------
// the parsed command (discriminated union)
// --------------------------------------------------------------------------
export type Command =
  | { kind: "create"; url: string; netPolicy: CliNetPolicy }
  | { kind: "shell"; id: string; shell: string }
  | { kind: "exec"; id: string; argv: string[] }
  | { kind: "cp"; id: string; containerPath: string; hostDest: string }
  | { kind: "destroy"; id: string; keepVolume: boolean }
  | { kind: "prune" };

/** The injectable dispatch table. The real ones shell the modules; tests fake them. */
export type Handlers = {
  create: (url: string, opts: { netPolicy: CliNetPolicy }) => Promise<CreateResult>;
  destroy: (id: string, opts: { keepVolume: boolean }) => DestroyResult;
  prune: () => PruneResult;
  exec: (id: string, argv: string[]) => ExecResult;
  cp: (id: string, containerPath: string, hostDest: string) => RunResult;
  shell: (id: string, shell: string) => number;
};

// --------------------------------------------------------------------------
// small flag-parsing helpers (shared by the subcommand parsers)
// --------------------------------------------------------------------------
/** Is this token a flag (starts with `--`)? Bare `--` is the exec separator,
 * handled separately and never reaches here. */
function isFlag(tok: string): boolean {
  return tok.startsWith("--");
}

/**
 * Split a flag token into name/inline-value: `--net=x` -> ["--net","x"];
 * `--net` -> ["--net", undefined]. Only the FIRST `=` splits (values may contain `=`).
 */
function splitFlag(tok: string): [string, string | undefined] {
  const eq = tok.indexOf("=");
  if (eq === -1) return [tok, undefined];
  return [tok.slice(0, eq), tok.slice(eq + 1)];
}

/** Reject the first unexpected token as an unknown flag / extra positional. */
function rejectUnknown(sub: string, tok: string): never {
  if (isFlag(tok)) throw new CliError(`sandbox ${sub}: unknown flag '${tok}'`);
  throw new CliError(`sandbox ${sub}: unexpected argument '${tok}'`);
}

// --------------------------------------------------------------------------
// parseCli — pure: argv -> Command, or throw CliError
// --------------------------------------------------------------------------
/**
 * Parse a ca-sandbox argv (everything after the program name) into a typed
 * `Command`. Pure — no side effects. Each subcommand parses ONLY its known flags;
 * any other flag is a `CliError` (the task's unknown-flag obligation).
 *
 * @throws {CliError} on no subcommand, an unknown subcommand, a missing required
 *   arg, an unknown flag, or an out-of-range flag value.
 */
export function parseCli(argv: string[]): Command {
  const [sub, ...rest] = argv;
  if (!sub) throw new CliError(usage());
  switch (sub) {
    case "create":
      return parseCreate(rest);
    case "shell":
      return parseShell(rest);
    case "exec":
      return parseExec(rest);
    case "cp":
      return parseCp(rest);
    case "destroy":
      return parseDestroy(rest);
    case "prune":
      return parsePrune(rest);
    default:
      throw new CliError(`sandbox: unknown subcommand '${sub}'\n${usage()}`);
  }
}

function parseCreate(args: string[]): Command {
  let url: string | undefined;
  let netPolicy: CliNetPolicy = "offline";

  for (let i = 0; i < args.length; i++) {
    const tok = args[i];
    if (isFlag(tok)) {
      const [name, inline] = splitFlag(tok);
      if (name === "--net") {
        const val = inline ?? args[++i];
        if (val === undefined) throw new CliError("sandbox create: --net requires a value");
        if (!(NET_POLICIES as readonly string[]).includes(val))
          throw new CliError(
            `sandbox create: unknown --net value '${val}' (one of: ${NET_POLICIES.join(", ")})`,
          );
        netPolicy = val as CliNetPolicy;
      } else {
        rejectUnknown("create", tok);
      }
    } else if (url === undefined) {
      url = tok;
    } else {
      rejectUnknown("create", tok);
    }
  }

  if (!url) throw new CliError("sandbox create: requires a repo <url>");
  return { kind: "create", url, netPolicy };
}

function parseShell(args: string[]): Command {
  let id: string | undefined;
  let shell = DEFAULT_SHELL;

  for (let i = 0; i < args.length; i++) {
    const tok = args[i];
    if (isFlag(tok)) {
      const [name, inline] = splitFlag(tok);
      if (name === "--shell") {
        const val = inline ?? args[++i];
        if (val === undefined) throw new CliError("sandbox shell: --shell requires a value");
        shell = val;
      } else {
        rejectUnknown("shell", tok);
      }
    } else if (id === undefined) {
      id = tok;
    } else {
      rejectUnknown("shell", tok);
    }
  }

  if (!id) throw new CliError("sandbox shell: requires a sandbox <id>");
  return { kind: "shell", id, shell };
}

function parseExec(args: string[]): Command {
  // Everything after the first bare `--` is the in-container argv, VERBATIM.
  const sep = args.indexOf("--");
  const head = sep === -1 ? args : args.slice(0, sep);
  const tail = sep === -1 ? [] : args.slice(sep + 1);

  let id: string | undefined;
  for (const tok of head) {
    if (isFlag(tok)) {
      // exec has no own flags before `--`; any flag here is unknown.
      rejectUnknown("exec", tok);
    } else if (id === undefined) {
      id = tok;
    } else {
      rejectUnknown("exec", tok);
    }
  }

  if (!id) throw new CliError("sandbox exec: requires a sandbox <id>");
  if (tail.length === 0)
    throw new CliError("sandbox exec: requires a command after '--' (e.g. exec <id> -- sh -c ...)");
  return { kind: "exec", id, argv: tail };
}

function parseCp(args: string[]): Command {
  let source: string | undefined;
  let hostDest: string | undefined;

  for (const tok of args) {
    if (isFlag(tok)) {
      rejectUnknown("cp", tok);
    } else if (source === undefined) {
      source = tok;
    } else if (hostDest === undefined) {
      hostDest = tok;
    } else {
      rejectUnknown("cp", tok);
    }
  }

  if (!source || !hostDest)
    throw new CliError("sandbox cp: requires `<id>:<containerPath> <hostDest>` (pull-only)");

  // Pull-only: the SOURCE must carry the `<id>:` container prefix. A source
  // without it would be a host path — i.e. a host->container push — which this
  // CLI deliberately cannot express (AC-10).
  const colon = source.indexOf(":");
  if (colon <= 0)
    throw new CliError(
      `sandbox cp: source must be '<id>:<containerPath>' (got '${source}'); ` +
        "host->container copy-in is not supported",
    );
  const id = source.slice(0, colon);
  const containerPath = source.slice(colon + 1);
  if (!containerPath)
    throw new CliError(`sandbox cp: source '${source}' is missing the container path after ':'`);

  return { kind: "cp", id, containerPath, hostDest };
}

function parseDestroy(args: string[]): Command {
  let id: string | undefined;
  let keepVolume = false;

  for (const tok of args) {
    if (isFlag(tok)) {
      const [name] = splitFlag(tok);
      if (name === "--keep-volume") keepVolume = true;
      else rejectUnknown("destroy", tok);
    } else if (id === undefined) {
      id = tok;
    } else {
      rejectUnknown("destroy", tok);
    }
  }

  if (!id) throw new CliError("sandbox destroy: requires a sandbox <id>");
  return { kind: "destroy", id, keepVolume };
}

function parsePrune(args: string[]): Command {
  for (const tok of args) rejectUnknown("prune", tok);
  return { kind: "prune" };
}

// --------------------------------------------------------------------------
// default handlers — the real ones shell the modules
// --------------------------------------------------------------------------
/**
 * The interactive `shell` handler: `docker exec -it <id> <shell>` wired straight
 * to the parent stdio so the user gets a live terminal in the box. Returns the
 * shell's exit code. This is the ONE subcommand whose behavior the modules don't
 * own (it is purely an interactive convenience over a running container), so it
 * lives here; it is injectable, so tests never spawn a real tty.
 */
function defaultShell(id: string, shell: string): number {
  // `id` is the user-facing sandbox id; resolve it to the real container id
  // (the container is `ca-sbx-<id>-<suffix>`, not the bare id) before exec.
  const containerId = resolveContainerId(id);
  const r = spawnSync("docker", ["exec", "-it", containerId, shell], {
    stdio: "inherit",
    env: DOCKER_ENV,
  });
  return r.status ?? 1;
}

/**
 * The production handler table — each entry shells the owning module. The
 * exec/cp/shell handlers take the user-facing SANDBOX id and resolve it to the
 * actual container id via the label registry first (the container is named
 * `ca-sbx-<id>-<suffix>`, so the bare id is not a valid `docker exec` target).
 * `create`/`destroy`/`prune` already resolve by label inside their modules.
 */
export const defaultHandlers: Handlers = {
  create: (url, opts) => createSandbox(url, { netPolicy: opts.netPolicy }),
  destroy: (id, opts) => destroySandbox(id, { keepVolume: opts.keepVolume }),
  prune: () => prune(),
  // Preserve the sandbox id the caller passed in the returned contract, even
  // though the exec runs against the resolved container id.
  exec: (id, argv) => ({ ...execInSandbox(resolveContainerId(id), argv), id }),
  cp: (id, containerPath, hostDest) => cpOut(resolveContainerId(id), containerPath, hostDest),
  shell: defaultShell,
};

// --------------------------------------------------------------------------
// runCli — parse + dispatch; returns an exit code, never throws on usage error
// --------------------------------------------------------------------------
/**
 * Parse `argv` and dispatch the resulting command to `handlers`. Returns a
 * process exit code:
 *   - usage error (`CliError`): the message goes to stderr, exit code 2.
 *   - `exec`: the in-container exit code propagates as the CLI's code (AC-09).
 *   - `cp`: docker's exit code propagates.
 *   - `create`/`destroy`/`prune`/`shell`: 0 on success (shell returns its code).
 *
 * Side-effecting work prints a one-line JSON/summary to stdout so the surface is
 * scriptable; the structured result objects come straight from the modules.
 */
export async function runCli(argv: string[], handlers: Handlers = defaultHandlers): Promise<number> {
  let cmd: Command;
  try {
    cmd = parseCli(argv);
  } catch (e) {
    if (e instanceof CliError) {
      process.stderr.write(`${e.message}\n`);
      return 2;
    }
    throw e;
  }

  switch (cmd.kind) {
    case "create": {
      const r = await handlers.create(cmd.url, { netPolicy: cmd.netPolicy });
      process.stdout.write(`${JSON.stringify(r)}\n`);
      return 0;
    }
    case "shell":
      return handlers.shell(cmd.id, cmd.shell);
    case "exec": {
      const r = handlers.exec(cmd.id, cmd.argv);
      process.stdout.write(`${JSON.stringify(r)}\n`);
      // Propagate the in-container exit code as the CLI's own (AC-09).
      return r.exitCode;
    }
    case "cp": {
      const r = handlers.cp(cmd.id, cmd.containerPath, cmd.hostDest);
      if (r.code !== 0 && r.stderr) process.stderr.write(`${r.stderr}\n`);
      return r.code;
    }
    case "destroy": {
      const r = handlers.destroy(cmd.id, { keepVolume: cmd.keepVolume });
      process.stdout.write(`${JSON.stringify(r)}\n`);
      return 0;
    }
    case "prune": {
      const r = handlers.prune();
      process.stdout.write(`${JSON.stringify(r)}\n`);
      return 0;
    }
  }
}

function usage(): string {
  return [
    "usage: sandbox <subcommand> ...",
    "  create <url> [--net offline|clone-then-cut|allowlist]",
    "  shell <id> [--shell sh|bash]",
    "  exec <id> -- <cmd> [args...]",
    "  cp <id>:<containerPath> <hostDest>",
    "  destroy <id> [--keep-volume]",
    "  prune",
  ].join("\n");
}

// Only execute when this file is the direct entry point (not when imported by
// unit tests). tsx/esbuild resolve import.meta.url correctly in both modes.
const _thisFile = fileURLToPath(import.meta.url);
const _entryFile = path.resolve(process.argv[1] ?? "");
if (_thisFile === _entryFile) {
  runCli(process.argv.slice(2))
    .then((code) => process.exit(code))
    .catch((e) => {
      console.error(e);
      process.exit(1);
    });
}
