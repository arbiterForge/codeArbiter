/**
 * git-facts.ts — codeArbiter's refresh-time git enrichment for the Pi footer.
 *
 * Collects the repository display name (origin owner/name, else toplevel
 * basename) and the working-tree dirty flag for the footer's git segment
 * (spec: pi-footer-parity-gaps AC-3/AC-4). Invoked only from the footer
 * refresh path of an affirmatively trusted project — never from render —
 * with explicit argv, `shell: false`, a bounded timeout, and a capped
 * output read. Every failure degrades to `undefined`; a fact is omitted,
 * never guessed.
 */
import { spawn as nodeSpawn } from "node:child_process";

export interface GitFacts {
  readonly repository?: string;
  readonly dirty?: boolean;
}

export interface GitFactsOptions {
  readonly spawn?: typeof nodeSpawn;
  readonly timeoutMs?: number;
  readonly maxOutputBytes?: number;
}

const DEFAULT_TIMEOUT_MS = 2_000;
const DEFAULT_MAX_OUTPUT_BYTES = 65_536;
const MAX_REPOSITORY_POINTS = 200;
const CONTROL_AND_ESCAPE_RE = /(?:\x1b\[[0-?]*[ -/]*[@-~]?|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)?|\x1b[@-_]|[\u0000-\u001f\u007f-\u009f])/gu;

interface GitRunResult {
  readonly code: number | null;
  readonly stdout: string;
  readonly capped: boolean;
}

function cleanSegment(value: string): string {
  return value.replace(CONTROL_AND_ESCAPE_RE, "").trim();
}

export function parseOriginRepository(url: unknown): string | undefined {
  if (typeof url !== "string") return undefined;
  const clean = cleanSegment(url).replace(/\/+$/u, "");
  if (!clean || /\s/u.test(clean)) return undefined;
  let path: string | undefined;
  const schemeIndex = clean.indexOf("://");
  if (schemeIndex >= 0) {
    const segments = clean.slice(schemeIndex + 3).split("/");
    if (segments.length < 3) return undefined;
    path = segments.slice(-2).join("/");
  } else {
    const scp = /^[^/:]+:(.+)$/u.exec(clean);
    if (scp === null) return undefined;
    const segments = scp[1]!.split("/");
    if (segments.length < 2) return undefined;
    path = segments.slice(-2).join("/");
  }
  const repository = path.replace(/\.git$/u, "");
  const [owner, name] = repository.split("/");
  if (!owner || !name) return undefined;
  return Array.from(repository).slice(0, MAX_REPOSITORY_POINTS).join("");
}

function toplevelBasename(output: string): string | undefined {
  const line = cleanSegment(output.split(/\r?\n/u, 1)[0] ?? "");
  if (!line) return undefined;
  const segments = line.split(/[\\/]/u).filter((segment) => segment.length > 0);
  const basename = segments.at(-1);
  return basename ? Array.from(basename).slice(0, MAX_REPOSITORY_POINTS).join("") : undefined;
}

function runGit(
  cwd: string,
  args: readonly string[],
  spawnImpl: typeof nodeSpawn,
  timeoutMs: number,
  maxOutputBytes: number,
): Promise<GitRunResult | undefined> {
  return new Promise((resolvePromise) => {
    let child: ReturnType<typeof nodeSpawn>;
    try {
      child = spawnImpl("git", [...args], {
        cwd,
        shell: false,
        windowsHide: true,
        stdio: ["ignore", "pipe", "ignore"],
      });
    } catch {
      resolvePromise(undefined);
      return;
    }
    let settled = false;
    let bytes = 0;
    const chunks: Buffer[] = [];
    const finish = (result: GitRunResult | undefined): void => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolvePromise(result);
    };
    const timer = setTimeout(() => {
      finish(undefined);
      try { child.kill(); } catch { /* Termination remains best-effort. */ }
    }, timeoutMs);
    try {
      child.stdout?.on("data", (chunk: Buffer) => {
        if (settled) return;
        bytes += chunk.length;
        chunks.push(chunk);
        if (bytes > maxOutputBytes) {
          finish({ code: 0, stdout: Buffer.concat(chunks).toString("utf8"), capped: true });
          try { child.kill(); } catch { /* Termination remains best-effort. */ }
        }
      });
      child.on("error", () => finish(undefined));
      child.on("close", (code: number | null) => {
        finish({ code, stdout: Buffer.concat(chunks).toString("utf8"), capped: false });
      });
    } catch {
      finish(undefined);
      try { child.kill(); } catch { /* Termination remains best-effort. */ }
    }
  });
}

export async function collectGitFacts(
  cwd: string,
  options: GitFactsOptions = {},
): Promise<GitFacts | undefined> {
  try {
    const spawnImpl = options.spawn ?? nodeSpawn;
    const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    const maxOutputBytes = options.maxOutputBytes ?? DEFAULT_MAX_OUTPUT_BYTES;
    const status = await runGit(cwd, ["status", "--porcelain"], spawnImpl, timeoutMs, maxOutputBytes);
    if (status === undefined || (!status.capped && status.code !== 0)) return undefined;
    const dirty = status.stdout.trim().length > 0;

    let repository: string | undefined;
    const remote = await runGit(cwd, ["remote", "get-url", "origin"], spawnImpl, timeoutMs, maxOutputBytes);
    if (remote !== undefined && remote.code === 0) {
      repository = parseOriginRepository(remote.stdout.split(/\r?\n/u, 1)[0]);
    }
    if (repository === undefined) {
      const toplevel = await runGit(cwd, ["rev-parse", "--show-toplevel"], spawnImpl, timeoutMs, maxOutputBytes);
      if (toplevel !== undefined && toplevel.code === 0) repository = toplevelBasename(toplevel.stdout);
    }
    return { ...(repository === undefined ? {} : { repository }), dirty };
  } catch {
    return undefined;
  }
}
