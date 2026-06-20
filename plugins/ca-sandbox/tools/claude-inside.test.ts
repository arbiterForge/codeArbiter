/**
 * claude-inside.test.ts — T-14. Covers AC-12.
 *
 * `--with-claude` runs Claude Code INSIDE a ca-sandbox box, authenticating via an
 * env-injected CLAUDE_CODE_OAUTH_TOKEN (Spike B / CONFIRM-07) with NO host bind of
 * ~/.claude. The image installs a PINNED @anthropic-ai/claude-code with
 * DISABLE_AUTOUPDATER=1; HOME is backed by a docker NAMED VOLUME so the .claude
 * state survives a restart; and the posture is HARD-DEFAULTED to offline or
 * Anthropic-domains-only egress, NEVER co-mounting the token volume with an
 * untrusted-code (source) run.
 *
 * Two layers:
 *   1. PURE unit tests over the builders (Dockerfile + run argv + the co-mount
 *      guard) — no real docker. The RED gate; runs everywhere.
 *   2. DOCKER-GATED integration (guarded by `docker info`, DUMMY token only):
 *        - `claude -p` with a dummy token reaches AUTH and is rejected by the
 *          server with a real `401 Invalid bearer token` (proves the env token is
 *          the auth path, not a config-file demand);
 *        - the .claude state written under the named-volume HOME PERSISTS across a
 *          container restart (a fresh container on the same volume sees it);
 *        - the offline / Anthropic-only default is enforced.
 *      Namespaced (ca-sbx-t14-*) + labeled (ca.sandbox.build=1) + cleaned up.
 *      DUMMY token only — never a real credential.
 */
import { describe, it, expect, afterAll } from "vitest";
import { spawnSync } from "node:child_process";
import {
  CLAUDE_CODE_VERSION,
  CLAUDE_HOME,
  TOKEN_ENV_VAR,
  buildClaudeImageDockerfile,
  buildClaudeRunArgs,
  TokenCoMountRejectedError,
} from "./claude-inside.ts";
import { SANDBOX_USER } from "./run.ts";

// --------------------------------------------------------------------------
// PURE unit layer — image + argv builders, no real docker.
// --------------------------------------------------------------------------
describe("buildClaudeImageDockerfile — pinned install + autoupdater off (AC-12)", () => {
  const df = buildClaudeImageDockerfile();

  it("installs @anthropic-ai/claude-code at a PINNED version (reproducible image)", () => {
    // The version must be pinned (semver), never a floating `@latest`.
    expect(CLAUDE_CODE_VERSION).toMatch(/^\d+\.\d+\.\d+$/);
    expect(df).toContain(`@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}`);
    expect(df).not.toMatch(/@anthropic-ai\/claude-code@latest/);
  });

  it("disables the autoupdater so the pinned version stays put", () => {
    expect(df).toMatch(/DISABLE_AUTOUPDATER=1/);
  });

  it("runs non-root and owns CLAUDE_HOME by the run uid (writable under --read-only)", () => {
    // The box runs as uid 1000; the credential store under the named-volume HOME
    // must be writable for that uid, so the image chowns it and defaults USER to it.
    expect(df).toMatch(/chown -R 1000:1000/);
    expect(df).toMatch(/^USER 1000:1000$/m);
  });
});

describe("buildClaudeRunArgs — env-token auth, no host bind (AC-12)", () => {
  const argv = buildClaudeRunArgs({
    image: "ca-sbx-claude:demo",
    token: "dummy-not-a-real-token",
    homeVolume: "ca-sbx-claude-home-demo",
  });

  it("injects the OAuth token via the environment (the auth path, Spike B)", () => {
    const i = argv.indexOf("-e");
    expect(i).toBeGreaterThanOrEqual(0);
    // Some `-e KEY=VALUE` token carries the OAuth env var with the supplied value.
    const envEntries = collectEnv(argv);
    expect(envEntries[TOKEN_ENV_VAR]).toBe("dummy-not-a-real-token");
  });

  it("backs HOME with a NAMED VOLUME (no host bind of ~/.claude), so state persists", () => {
    // HOME points at the in-container claude home...
    const envEntries = collectEnv(argv);
    expect(envEntries.HOME).toBe(CLAUDE_HOME);
    // ...and a named volume is mounted there (NOT a bind).
    const flat = argv.join(" ");
    expect(flat).toMatch(
      new RegExp(`type=volume,source=ca-sbx-claude-home-demo,target=${CLAUDE_HOME}`),
    );
    // No bind expression anywhere — the token/credential store is never on the host.
    for (const tok of argv) expect(tok).not.toMatch(/type=bind/);
  });

  it("NEVER passes --privileged and NEVER mounts the docker socket", () => {
    expect(argv).not.toContain("--privileged");
    expect(argv.join(" ")).not.toMatch(/docker\.sock/);
  });

  it("runs NON-ROOT and drops ALL capabilities, matching run.ts (token box is no softer)", () => {
    // The load-bearing isolation parity: the token-bearing box must be as
    // locked-down as an ordinary sandbox. Regression guard for the gap where the
    // docstring claimed cap-drop/non-root but the argv omitted them.
    const u = argv.indexOf("--user");
    expect(u).toBeGreaterThanOrEqual(0);
    expect(argv[u + 1]).toBe(SANDBOX_USER);
    const c = argv.indexOf("--cap-drop");
    expect(c).toBeGreaterThanOrEqual(0);
    expect(argv[c + 1]).toBe("ALL");
    expect(argv).toContain("--read-only");
    expect(argv).toContain("no-new-privileges");
  });

  it("defaults egress to offline (the hard default — Spike B caveat)", () => {
    // With no netPolicy supplied the box is offline: --network none.
    const i = argv.indexOf("--network");
    expect(i).toBeGreaterThanOrEqual(0);
    expect(argv[i + 1]).toBe("none");
  });
});

describe("buildClaudeRunArgs — hardened posture is enforced, not optional (AC-12)", () => {
  it("accepts an Anthropic-domains-only allowlist as the other permitted default", () => {
    const argv = buildClaudeRunArgs({
      image: "img",
      token: "dummy",
      homeVolume: "home-vol",
      netPolicy: "anthropic-only",
    });
    // anthropic-only must NOT be a wide-open network: it adds the egress caps and
    // a custom bridge (the experimental allowlist machinery), never plain bridge.
    const flat = argv.join(" ");
    expect(flat).toMatch(/--cap-add NET_ADMIN/);
  });

  it("REFUSES an arbitrary wide-open network policy (no escaping the hard default)", () => {
    expect(() =>
      buildClaudeRunArgs({
        image: "img",
        token: "dummy",
        homeVolume: "home-vol",
        // @ts-expect-error — a non-hardened policy is not assignable; the runtime
        // guard rejects it too.
        netPolicy: "open",
      }),
    ).toThrow();
  });

  it("THROWS when the token volume would be co-mounted with an untrusted-code run", () => {
    // The load-bearing Spike B caveat: never co-mount the token/credential volume
    // with a run that also mounts the untrusted source volume at /work/repo.
    expect(() =>
      buildClaudeRunArgs({
        image: "img",
        token: "dummy",
        homeVolume: "home-vol",
        sourceVolume: "ca-sbx-vol-untrusted",
      }),
    ).toThrow(TokenCoMountRejectedError);
  });

  it("requires a non-empty image, token, and home volume", () => {
    expect(() => buildClaudeRunArgs({ image: "", token: "t", homeVolume: "h" })).toThrow();
    expect(() => buildClaudeRunArgs({ image: "i", token: "", homeVolume: "h" })).toThrow();
    expect(() => buildClaudeRunArgs({ image: "i", token: "t", homeVolume: "" })).toThrow();
  });
});

// Collect every `-e KEY=VALUE` from an argv into a record.
function collectEnv(argv: string[]): Record<string, string> {
  const out: Record<string, string> = {};
  argv.forEach((a, i) => {
    if (a === "-e" && typeof argv[i + 1] === "string") {
      const eq = argv[i + 1].indexOf("=");
      if (eq > 0) out[argv[i + 1].slice(0, eq)] = argv[i + 1].slice(eq + 1);
    }
  });
  return out;
}

// --------------------------------------------------------------------------
// DOCKER-GATED integration layer (AC-12) — DUMMY token only.
// --------------------------------------------------------------------------
function dockerAvailable(): boolean {
  const r = spawnSync("docker", ["info", "--format", "{{.OSType}}"], { encoding: "utf8" });
  return r.status === 0 && /linux/i.test(r.stdout);
}
const HAS_DOCKER = dockerAvailable();
const d = HAS_DOCKER ? describe : describe.skip;

const NS = "ca-sbx-t14";
const DENV = { ...process.env, MSYS_NO_PATHCONV: "1" };
// The dummy token never validates server-side — this test must NEVER carry a real
// credential. The 401 it produces is the proof the env token IS the auth path.
const DUMMY_TOKEN = "dummy-not-a-real-token";

function dk(args: string[], input?: string) {
  return spawnSync("docker", args, {
    encoding: "utf8",
    env: DENV,
    input,
    maxBuffer: 64 * 1024 * 1024,
  });
}

d("claude-inside [docker] — env-token auth + named-volume persistence (AC-12)", () => {
  const created = { containers: [] as string[], volumes: [] as string[], images: [] as string[] };
  // Build the pinned claude image ONCE for the whole suite (egress is up at build).
  const img = `${NS}-img:${Date.now()}`;
  const built = (() => {
    const df = buildClaudeImageDockerfile();
    const b = dk(["build", "-t", img, "-f", "-", "."], df);
    return b;
  })();

  afterAll(() => {
    for (const c of created.containers) dk(["rm", "-f", c]);
    for (const v of created.volumes) dk(["volume", "rm", "-f", v]);
    for (const i of created.images) dk(["rmi", "-f", i]);
  });

  it("builds the pinned claude image (DISABLE_AUTOUPDATER baked)", () => {
    expect(built.status, built.stderr).toBe(0);
    created.images.push(img);
    // The pinned version is the one the CLI reports.
    const ver = dk(["run", "--rm", "--label", "ca.sandbox.build=1", img, "claude", "--version"]);
    expect(ver.status, ver.stderr).toBe(0);
    expect(ver.stdout).toContain(CLAUDE_CODE_VERSION);
  }, 300_000);

  it("claude -p with the DUMMY token reaches AUTH (real 401 Invalid bearer token)", () => {
    // Auth needs to talk to the API: bring the box up WITH egress (a real run uses
    // anthropic-only; the dummy 401 only needs to reach the endpoint). DUMMY token.
    const homeVol = `${NS}-home-${Date.now()}`;
    const mkv = dk(["volume", "create", "--label", "ca.sandbox.build=1", homeVol]);
    expect(mkv.status, mkv.stderr).toBe(0);
    created.volumes.push(homeVol);

    const r = dk([
      "run",
      "--rm",
      "--label",
      "ca.sandbox.build=1",
      "--label",
      "ca.sandbox=1",
      "-e",
      `${TOKEN_ENV_VAR}=${DUMMY_TOKEN}`,
      "-e",
      `HOME=${CLAUDE_HOME}`,
      "--mount",
      `type=volume,source=${homeVol},target=${CLAUDE_HOME}`,
      img,
      "claude",
      "-p",
      "say hi",
    ]);
    // Exit non-zero (auth rejected) and the message is the server-side 401 for a
    // SENT bearer token — proof the env token was read, a header built, and sent.
    expect(r.status).not.toBe(0);
    expect(`${r.stdout}\n${r.stderr}`).toMatch(/401|invalid bearer token/i);
  }, 180_000);

  it(".claude state under the named-volume HOME persists across a restart", () => {
    // Run 1 writes a marker into the in-container HOME (the named volume). Run 2 —
    // a FRESH container on the SAME volume — sees it. Same mechanism as the live
    // .claude/.credentials.json store (Spike B): named-volume HOME survives restart.
    const homeVol = `${NS}-persist-${Date.now()}`;
    const mkv = dk(["volume", "create", "--label", "ca.sandbox.build=1", homeVol]);
    expect(mkv.status, mkv.stderr).toBe(0);
    created.volumes.push(homeVol);

    const write = dk([
      "run",
      "--rm",
      "--label",
      "ca.sandbox.build=1",
      "-e",
      `HOME=${CLAUDE_HOME}`,
      "--mount",
      `type=volume,source=${homeVol},target=${CLAUDE_HOME}`,
      img,
      "sh",
      "-c",
      `mkdir -p ${CLAUDE_HOME}/.claude && echo persisted > ${CLAUDE_HOME}/.claude/marker`,
    ]);
    expect(write.status, write.stderr).toBe(0);

    const read = dk([
      "run",
      "--rm",
      "--label",
      "ca.sandbox.build=1",
      "-e",
      `HOME=${CLAUDE_HOME}`,
      "--mount",
      `type=volume,source=${homeVol},target=${CLAUDE_HOME}`,
      img,
      "sh",
      "-c",
      `cat ${CLAUDE_HOME}/.claude/marker`,
    ]);
    expect(read.status, read.stderr).toBe(0);
    expect(read.stdout.trim()).toBe("persisted");
  }, 180_000);

  it("the offline default truly has no egress (curl reaches nothing)", () => {
    // buildClaudeRunArgs defaults to offline. Prove the box under that posture has
    // no network: the install image has node; use it to attempt a fetch that fails.
    const homeVol = `${NS}-offline-${Date.now()}`;
    const mkv = dk(["volume", "create", "--label", "ca.sandbox.build=1", homeVol]);
    expect(mkv.status, mkv.stderr).toBe(0);
    created.volumes.push(homeVol);

    const argv = buildClaudeRunArgs({
      image: img,
      token: DUMMY_TOKEN,
      homeVolume: homeVol,
      // default netPolicy => offline.
      extraLabels: ["ca.sandbox.build=1"],
    });
    // Take the builder's run flags up to (and including) the image, but run a
    // FOREGROUND one-shot egress probe instead of the detached keep-alive so the
    // exit code reflects the probe. Drop the builder's `-d` (detached always exits
    // 0) and add `--rm` so the one-shot cleans itself up.
    const imgIdx = argv.indexOf(img);
    const flags = argv.slice(1, imgIdx).filter((a) => a !== "-d"); // between "run" and image
    const probe = [
      "run",
      "--rm",
      ...flags,
      img,
      "node",
      "-e",
      "fetch('https://api.anthropic.com').then(()=>process.exit(0)).catch(()=>process.exit(42))",
    ];
    const r = dk(probe);
    // offline => fetch cannot connect => our catch exits 42 (or docker/node errors
    // non-zero). Either way it is NOT a clean 0.
    expect(r.status).not.toBe(0);
  }, 180_000);
});
