/**
 * claude-inside-cli.test.ts — #377, the shipped entry point.
 *
 * Before this, `--with-claude` was documented and had NO shipped code path:
 * `runClaudeInside` had zero callers, so esbuild tree-shook it out of
 * `sandbox.js` entirely. The skill told operators to call TypeScript that no
 * install contained.
 *
 * It ships as its own binary rather than a `sandbox` subcommand, because it
 * starts a container holding a LIVE OAuth token and the sandbox-claude-inside
 * skill's five BLOCK gates are what make that safe. A subcommand would let
 * anyone start a token-bearing box with one ungated command.
 *
 * Everything here runs on injected deps. No docker, no real token.
 */
import { describe, it, expect } from "vitest";
import {
  ClaudeCliError,
  USAGE_ERROR_EXIT,
  parseClaudeCli,
  runClaudeInsideCli,
  usage,
} from "./claude-inside-cli.ts";
import { TOKEN_ENV_VAR, TokenCoMountRejectedError } from "./claude-inside.ts";

const OK = { image: "ca-sbx-claude:t", homeVolume: "ca-sbx-home-t" };
const ARGV = ["--image", OK.image, "--home-volume", OK.homeVolume];
const ENV = { [TOKEN_ENV_VAR]: "DUMMY-NOT-A-REAL-TOKEN" } as NodeJS.ProcessEnv;

function collect() {
  const out: string[] = [];
  const err: string[] = [];
  return { out, err, sinks: { stdout: (l: string) => out.push(l), stderr: (l: string) => err.push(l) } };
}

describe("#377 parseClaudeCli — what the entry point refuses", () => {
  it("accepts the minimal invocation and defaults to the guaranteed posture", () => {
    // `offline` is the only GUARANTEED posture for a token-bearing box, so it is
    // what you get without asking. Requiring an opt-IN to safety would be the
    // wrong default.
    expect(parseClaudeCli(ARGV)).toEqual({ ...OK, netPolicy: "offline" });
  });

  it("accepts the experimental allowlist posture explicitly", () => {
    expect(parseClaudeCli([...ARGV, "--net", "anthropic-only"]).netPolicy).toBe("anthropic-only");
  });

  it("refuses any other egress posture, naming why", () => {
    for (const bad of ["bridge", "host", "none", "allowlist", ""]) {
      expect(() => parseClaudeCli([...ARGV, "--net", bad]), bad).toThrow(ClaudeCliError);
    }
    expect(() => parseClaudeCli([...ARGV, "--net", "host"])).toThrow(/wide-open egress/);
  });

  it("REFUSES --token, because argv is world-readable", () => {
    // The load-bearing one. A process argument list is readable by every other
    // process on the host (ps, /proc/<pid>/cmdline, WMI), so a --token flag
    // would publish the credential. The refusal says so rather than just "no".
    expect(() => parseClaudeCli([...ARGV, "--token", "sk-whatever"])).toThrow(/world-readable/);
    expect(() => parseClaudeCli([...ARGV, "--token", "sk-whatever"])).toThrow(
      new RegExp(TOKEN_ENV_VAR),
    );
  });

  it("REFUSES --source-volume before a container can exist", () => {
    // The co-mount guard is structural in buildClaudeRunArgs, but catching it at
    // parse time means the mistake never reaches docker at all.
    expect(() => parseClaudeCli([...ARGV, "--source-volume", "v"])).toThrow(/NEVER co-mounted/);
  });

  it("requires both the image and the home volume", () => {
    expect(() => parseClaudeCli(["--home-volume", OK.homeVolume])).toThrow(/--image is required/);
    expect(() => parseClaudeCli(["--image", OK.image])).toThrow(/--home-volume is required/);
  });

  it("refuses an unknown flag rather than ignoring it", () => {
    expect(() => parseClaudeCli([...ARGV, "--privileged"])).toThrow(/unknown argument/);
  });

  it("refuses a flag with no value", () => {
    expect(() => parseClaudeCli(["--image"])).toThrow(/requires a value/);
  });
});

describe("#377 runClaudeInsideCli — the process contract", () => {
  it("starts the box and prints only the container id", () => {
    const { out, err, sinks } = collect();
    let seen: Record<string, unknown> | undefined;
    const code = runClaudeInsideCli(ARGV, ENV, {
      ...sinks,
      run: (opts) => { seen = opts as unknown as Record<string, unknown>; return "cid-1"; },
    });
    expect(code).toBe(0);
    expect(out).toEqual(["cid-1"]);
    expect(err).toEqual([]);
    expect(seen).toMatchObject({ ...OK, netPolicy: "offline" });
  });

  it("passes the token from the ENVIRONMENT, not from argv", () => {
    let seenToken: unknown;
    runClaudeInsideCli(ARGV, ENV, {
      ...collect().sinks,
      run: (opts) => { seenToken = opts.token; return "cid"; },
    });
    expect(seenToken).toBe("DUMMY-NOT-A-REAL-TOKEN");
  });

  it("exits with the usage code when the token is absent, and says where it comes from", () => {
    const { err, sinks } = collect();
    const code = runClaudeInsideCli(ARGV, {} as NodeJS.ProcessEnv, {
      ...sinks,
      run: () => { throw new Error("must not start a box without a token"); },
    });
    expect(code).toBe(USAGE_ERROR_EXIT);
    expect(err.join("\n")).toContain(TOKEN_ENV_VAR);
  });

  it("never echoes the token, on any path", () => {
    // Including the failure path, where a diagnostic is most likely to carry
    // something it should not.
    const { out, err, sinks } = collect();
    runClaudeInsideCli(ARGV, ENV, {
      ...sinks,
      run: () => { throw new Error("docker run failed: exit 125"); },
    });
    expect([...out, ...err].join("\n")).not.toContain("DUMMY-NOT-A-REAL-TOKEN");
  });

  it("returns 1 and names the co-mount guard when it fires", () => {
    const { err, sinks } = collect();
    const code = runClaudeInsideCli(ARGV, ENV, {
      ...sinks,
      run: () => { throw new TokenCoMountRejectedError("token volume co-mount refused"); },
    });
    expect(code).toBe(1);
    expect(err.join("\n")).toMatch(/co-mount refused/);
  });

  it("returns 1 on an ordinary start failure, distinct from the usage code", () => {
    const { sinks } = collect();
    const code = runClaudeInsideCli(ARGV, ENV, {
      ...sinks,
      run: () => { throw new Error("docker run failed"); },
    });
    expect(code).toBe(1);
    expect(code).not.toBe(USAGE_ERROR_EXIT);
  });

  it("never throws for a usage error; it returns a code", () => {
    const { sinks } = collect();
    expect(() => runClaudeInsideCli(["--nonsense"], ENV, sinks)).not.toThrow();
    expect(runClaudeInsideCli(["--nonsense"], ENV, sinks)).toBe(USAGE_ERROR_EXIT);
  });

  it("the usage text states that this is skill-gated, not a sandbox subcommand", () => {
    // The gating is a documented contract, not just an absent subcommand. If
    // someone finds this binary directly, the text tells them what they are
    // bypassing.
    expect(usage()).toMatch(/sandbox-claude-inside/);
    expect(usage()).toMatch(/BLOCK gates/);
    expect(usage()).toMatch(new RegExp(TOKEN_ENV_VAR));
  });
});
