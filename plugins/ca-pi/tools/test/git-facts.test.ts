import { describe, expect, test } from "vitest";

import { collectGitFacts, parseOriginRepository } from "../src/git-facts.ts";
import type { GitFactsOptions } from "../src/git-facts.ts";

type Behavior =
  | { readonly stdout: string; readonly code: number }
  | { readonly hang: true }
  | { readonly error: string };

interface SpawnCall {
  readonly command: string;
  readonly args: readonly string[];
  readonly options: Record<string, unknown>;
}

/** Minimal scripted stand-in for a spawned git child process. */
class FakeChild {
  killed = false;
  private readonly dataListeners: Array<(chunk: Buffer) => void> = [];
  private readonly closeListeners: Array<(code: number | null) => void> = [];
  private readonly errorListeners: Array<(error: Error) => void> = [];
  readonly stdout = {
    on: (event: string, listener: (chunk: Buffer) => void): void => {
      if (event === "data") this.dataListeners.push(listener);
    },
  };

  constructor(private readonly behavior: Behavior) {
    queueMicrotask(() => this.run());
  }

  on(event: string, listener: never): void {
    if (event === "close") this.closeListeners.push(listener);
    if (event === "error") this.errorListeners.push(listener);
  }

  kill(): boolean {
    this.killed = true;
    for (const listener of this.closeListeners) listener(null);
    return true;
  }

  private run(): void {
    if ("hang" in this.behavior) return;
    if ("error" in this.behavior) {
      for (const listener of this.errorListeners) listener(new Error(this.behavior.error));
      return;
    }
    if (this.behavior.stdout) {
      for (const listener of this.dataListeners) listener(Buffer.from(this.behavior.stdout, "utf8"));
    }
    if (this.killed) return;
    for (const listener of this.closeListeners) listener(this.behavior.code);
  }
}

function fakeSpawn(script: Record<string, Behavior>): {
  readonly calls: SpawnCall[];
  readonly children: FakeChild[];
  readonly spawn: GitFactsOptions["spawn"];
} {
  const calls: SpawnCall[] = [];
  const children: FakeChild[] = [];
  const spawn = ((command: string, args: readonly string[], options: Record<string, unknown>) => {
    calls.push({ command, args, options });
    const child = new FakeChild(script[args.join(" ")] ?? { stdout: "", code: 1 });
    children.push(child);
    return child;
  }) as unknown as GitFactsOptions["spawn"];
  return { calls, children, spawn };
}

describe("git facts — origin parsing (spec pi-footer-parity-gaps O-3)", () => {
  test("parses ssh and https remotes down to owner/name and strips the .git suffix", () => {
    expect(parseOriginRepository("git@github.com:arbiterForge/codeArbiter.git")).toBe("arbiterForge/codeArbiter");
    expect(parseOriginRepository("https://github.com/arbiterForge/codeArbiter.git")).toBe("arbiterForge/codeArbiter");
    expect(parseOriginRepository("https://github.com/arbiterForge/codeArbiter")).toBe("arbiterForge/codeArbiter");
    expect(parseOriginRepository("ssh://git@host.example/team/deep/project.git")).toBe("deep/project");
  });

  test("handles ports, preserved case, and unicode segments without guessing", () => {
    expect(parseOriginRepository("https://github.com:443/owner/name.git")).toBe("owner/name");
    expect(parseOriginRepository("https://git.example.com:8443/owner/name")).toBe("owner/name");
    expect(parseOriginRepository("https://github.com:443/only-name")).toBeUndefined();
    expect(parseOriginRepository("HTTPS://GITHUB.COM/Owner/Name.git")).toBe("Owner/Name");
    expect(parseOriginRepository("https://github.com/café/repo-日本")).toBe("café/repo-日本");
  });

  test("refuses garbage instead of guessing", () => {
    expect(parseOriginRepository("")).toBeUndefined();
    expect(parseOriginRepository("not a url")).toBeUndefined();
    expect(parseOriginRepository("https://github.com/only-one-segment")).toBeUndefined();
    expect(parseOriginRepository(42)).toBeUndefined();
    expect(parseOriginRepository(undefined)).toBeUndefined();
  });
});

describe("git facts — bounded collection (spec pi-footer-parity-gaps O-3/O-4)", () => {
  test("O-3: a clean repo with an origin yields owner/name and dirty false", async () => {
    const { calls, spawn } = fakeSpawn({
      "status --porcelain": { stdout: "", code: 0 },
      "remote get-url origin": { stdout: "https://github.com/arbiterForge/codeArbiter.git\n", code: 0 },
    });

    const facts = await collectGitFacts("C:/work/proj", { spawn });

    expect(facts).toEqual({ repository: "arbiterForge/codeArbiter", dirty: false });
    expect(calls.map((call) => call.args)).toEqual([
      ["status", "--porcelain"],
      ["remote", "get-url", "origin"],
    ]);
  });

  test("O-4: every spawn uses explicit git argv, shell false, hidden window, and the caller cwd", async () => {
    const { calls, spawn } = fakeSpawn({
      "status --porcelain": { stdout: " M x\n", code: 0 },
      "remote get-url origin": { stdout: "git@github.com:a/b.git", code: 0 },
    });

    await collectGitFacts("C:/work/proj", { spawn });

    expect(calls.length).toBeGreaterThan(0);
    for (const call of calls) {
      expect(call.command).toBe("git");
      expect(call.options["shell"]).toBe(false);
      expect(call.options["windowsHide"]).toBe(true);
      expect(call.options["cwd"]).toBe("C:/work/proj");
    }
  });

  test("O-3: porcelain output makes the tree dirty", async () => {
    const { spawn } = fakeSpawn({
      "status --porcelain": { stdout: " M plugins/ca-pi/tools/src/footer.ts\n", code: 0 },
      "remote get-url origin": { stdout: "git@github.com:a/b.git", code: 0 },
    });

    expect(await collectGitFacts("C:/work/proj", { spawn })).toEqual({ repository: "a/b", dirty: true });
  });

  test("O-3: a failing status means no facts at all", async () => {
    const { spawn } = fakeSpawn({
      "status --porcelain": { stdout: "fatal: not a git repository", code: 128 },
    });

    expect(await collectGitFacts("C:/work/proj", { spawn })).toBeUndefined();
  });

  test("O-3: a spawn error degrades to undefined instead of throwing", async () => {
    const { spawn } = fakeSpawn({
      "status --porcelain": { error: "ENOENT" },
    });

    expect(await collectGitFacts("C:/work/proj", { spawn })).toBeUndefined();
  });

  test("O-3: a missing origin falls back to the toplevel basename on either separator", async () => {
    const posix = fakeSpawn({
      "status --porcelain": { stdout: "", code: 0 },
      "remote get-url origin": { stdout: "", code: 2 },
      "rev-parse --show-toplevel": { stdout: "/home/brenn/projects/codeArbiter\n", code: 0 },
    });
    expect(await collectGitFacts("/home/brenn/projects/codeArbiter", { spawn: posix.spawn }))
      .toEqual({ repository: "codeArbiter", dirty: false });

    const windows = fakeSpawn({
      "status --porcelain": { stdout: "", code: 0 },
      "remote get-url origin": { stdout: "", code: 2 },
      "rev-parse --show-toplevel": { stdout: "C:\\Users\\brenn\\projects\\codeArbiter\n", code: 0 },
    });
    expect(await collectGitFacts("C:/Users/brenn/projects/codeArbiter", { spawn: windows.spawn }))
      .toEqual({ repository: "codeArbiter", dirty: false });
  });

  test("O-3: dirty survives when no repository name is derivable", async () => {
    const { spawn } = fakeSpawn({
      "status --porcelain": { stdout: " M x\n", code: 0 },
      "remote get-url origin": { stdout: "garbage", code: 0 },
      "rev-parse --show-toplevel": { stdout: "", code: 128 },
    });

    expect(await collectGitFacts("C:/work/proj", { spawn })).toEqual({ dirty: true });
  });

  test("O-4: a hung git is killed at the timeout and yields undefined", async () => {
    const { children, spawn } = fakeSpawn({
      "status --porcelain": { hang: true },
    });

    const facts = await collectGitFacts("C:/work/proj", { spawn, timeoutMs: 20 });

    expect(facts).toBeUndefined();
    expect(children[0]!.killed).toBe(true);
  });

  test("O-4: output beyond the cap stops collection without losing the dirty verdict", async () => {
    const { children, spawn } = fakeSpawn({
      "status --porcelain": { stdout: ` M ${"x".repeat(4_096)}\n`, code: 0 },
      "remote get-url origin": { stdout: "git@github.com:a/b.git", code: 0 },
    });

    const facts = await collectGitFacts("C:/work/proj", { spawn, maxOutputBytes: 64 });

    expect(facts).toEqual({ repository: "a/b", dirty: true });
    expect(children[0]!.killed).toBe(true);
  });
});
