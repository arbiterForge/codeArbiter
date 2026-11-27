/**
 * cp.test.ts — T-12. Covers AC-10.
 *
 * Host-initiated, PULL-ONLY file extraction. `await cpOut(id, containerPath, hostDest)`
 * shells `docker cp <container>:<path> <hostDest>` — the host reaches IN and pulls
 * a file out. The reverse direction (getting host files INTO the box) is the
 * danger: the only way to bulk-inject host files would be a bind mount, and the
 * load-bearing invariant (spec AC-02 / AC-10) is that a sandbox container NEVER
 * gets a host bind. So this module routes any "copy-in" mount request through
 * mounts.ts's buildMountArgs, which THROWS on any bind spec — making a
 * host->container bind structurally impossible.
 *
 * Two layers:
 *   1. PURE unit tests — buildCpOutArgs(...) assembles the right pull-only argv
 *      (`cp <id>:<path> <dest>`, in that direction, never the reverse), and the
 *      reverse-direction guard rejects a host->container bind via the mount
 *      chokepoint. RED gate; runs everywhere.
 *   2. A DOCKER-GATED integration test (guarded by `docker info`): start a real
 *      container, write a file at /work, cpOut it to a host temp dir, assert the
 *      bytes match. Namespaced + cleaned up.
 */
import { describe, it, expect, afterAll } from "vitest";
import { dockerGate } from "./docker-gate.ts";
import { spawnSync } from "node:child_process";
import { readFileSync, mkdtempSync, rmSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { buildCpOutArgs, cpOut, assertNoCopyInBind } from "./cp.ts";
import { BindMountRejectedError } from "./mounts.ts";

// --------------------------------------------------------------------------
// PURE unit layer — argv assembly + reverse-bind rejection, no real docker.
// --------------------------------------------------------------------------
describe("buildCpOutArgs — pull-only direction (AC-10)", () => {
  it("assembles `cp <id>:<containerPath> <hostDest>` in the pull direction", async () => {
    const argv = buildCpOutArgs("abc123", "/work/out.txt", "./dest/out.txt");
    expect(argv).toEqual(["cp", "abc123:/work/out.txt", "./dest/out.txt"]);
  });

  it("never produces the reverse direction (host source before container dest)", async () => {
    const argv = buildCpOutArgs("abc123", "/work/out.txt", "./dest/out.txt");
    // The container ref (`<id>:`) is the SOURCE (argv[1]); the host path is the
    // DEST (argv[2]). A reversed `cp <hostDest> <id>:<path>` would be a push.
    expect(argv[1]).toBe("abc123:/work/out.txt");
    expect(argv[2]).toBe("./dest/out.txt");
    expect(argv[2].startsWith("abc123:")).toBe(false);
  });

  it("refuses an empty container id, container path, or host dest", async () => {
    expect(() => buildCpOutArgs("", "/work/x", "./x")).toThrow();
    expect(() => buildCpOutArgs("abc", "", "./x")).toThrow();
    expect(() => buildCpOutArgs("abc", "/work/x", "")).toThrow();
  });
});

describe("assertNoCopyInBind — host->container bind is impossible (AC-10)", () => {
  it("throws (via the mount chokepoint) on a -v host:container bind copy-in", async () => {
    expect(() => assertNoCopyInBind("/home/user/secrets:/work/secrets")).toThrow(
      BindMountRejectedError,
    );
  });

  it("throws on an explicit type=bind copy-in spec", async () => {
    expect(() =>
      assertNoCopyInBind({ type: "bind", source: "/etc", target: "/work/etc" }),
    ).toThrow(/bind/i);
  });

  it("the rejection comes from mounts.ts (cp does not hand-roll its own check)", async () => {
    // BindMountRejectedError is mounts.ts's error type — proving the routing.
    let err: unknown;
    try {
      assertNoCopyInBind("/x:/work/x");
    } catch (e) {
      err = e;
    }
    expect(err).toBeInstanceOf(BindMountRejectedError);
  });
});

// --------------------------------------------------------------------------
// DOCKER-GATED integration layer (AC-10).
// cpOut copies a real file out of a real container to the host.
// --------------------------------------------------------------------------
const d = dockerGate("cp");

const NS = "ca-sbx-t12";
const DENV = { ...process.env, MSYS_NO_PATHCONV: "1" };

d("cpOut [docker] — pulls a file from /work to the host (AC-10)", () => {
  const created = { containers: [] as string[] };
  let tmp: string | undefined;

  afterAll(() => {
    for (const c of created.containers) spawnSync("docker", ["rm", "-f", c], { env: DENV });
    if (tmp) rmSync(tmp, { recursive: true, force: true });
  });

  it("copies /work/<f> out to a host dest with identical bytes", async () => {
    const image = "busybox:latest";
    const pull = spawnSync("docker", ["pull", image], { encoding: "utf8", env: DENV });
    expect(pull.status, pull.stderr).toBe(0);

    const name = `${NS}-${Date.now()}`;
    // A minimal container that writes a known file at /work then idles. No mounts
    // at all — cp reaches into the container's own FS, no host bind anywhere.
    const marker = "ca-sandbox-cp-out-marker-12345";
    const run = spawnSync(
      "docker",
      [
        "run",
        "-d",
        "--name",
        name,
        "--label",
        "ca.sandbox.build=1",
        image,
        "sh",
        "-c",
        `mkdir -p /work && printf '%s' '${marker}' > /work/out.txt && sleep infinity`,
      ],
      { encoding: "utf8", env: DENV },
    );
    expect(run.status, run.stderr).toBe(0);
    const id = run.stdout.trim();
    created.containers.push(id);

    // Give the container a beat to write the file (sh runs the printf at start).
    // Poll docker exec for the file rather than sleeping blindly.
    let ready = false;
    for (let i = 0; i < 50 && !ready; i++) {
      const chk = spawnSync("docker", ["exec", id, "test", "-f", "/work/out.txt"], { env: DENV });
      ready = chk.status === 0;
      if (!ready) spawnSync("docker", ["exec", id, "true"], { env: DENV }); // tiny yield
    }
    expect(ready, "file /work/out.txt should exist in the container").toBe(true);

    tmp = mkdtempSync(path.join(tmpdir(), "ca-sbx-t12-"));
    const dest = path.join(tmp, "pulled.txt");

    const r = await cpOut(id, "/work/out.txt", dest, { dockerRun: async (args) => {
      const res = spawnSync("docker", args, { encoding: "utf8", env: DENV });
      return { code: res.status ?? 1, stdout: res.stdout ?? "", stderr: res.stderr ?? "" };
    } });
    expect(r.code, r.stderr).toBe(0);

    expect(existsSync(dest)).toBe(true);
    expect(readFileSync(dest, "utf8")).toBe(marker);
  }, 120_000);
});

// Bounded real effects using an already-cached reviewed image only. Kept in
// cp.test.ts because the old Claude integration describe eagerly builds during
// collection; filtering that file would not prevent its network/build effects.
// These cases are filesystem/container fixtures, never real Claude auth/CLI.
import { randomUUID, createHash } from "node:crypto";
import {
  mkdirSync, realpathSync, lstatSync, statSync, openSync, readSync, closeSync, writeFileSync,
} from "node:fs";
import { makeDockerRun, type DockerRun, type RunResult } from "./docker.ts";
import { runClaudeInside, CLAUDE_HOME, TOKEN_ENV_VAR } from "./claude-inside.ts";
import { hardeningFlags, SANDBOX_LABEL } from "./run.ts";

const EFFECT_IMAGE = "node:20-slim@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0";
const EFFECT_DIGEST = EFFECT_IMAGE.slice(EFFECT_IMAGE.indexOf("@") + 1);
const EFFECT_LABEL = "ca.sandbox.effect-fixture";
const EFFECT_DUMMY = "DUMMY-OWNED-OFFLINE-FIXTURE-NOT-A-CREDENTIAL";

type EffectInspect = {
  Id: string; Name: string; Image: string;
  Config: { Labels: Record<string, string>; User: string; Env: string[]; WorkingDir: string };
  HostConfig: { NetworkMode: string; ReadonlyRootfs: boolean; Privileged: boolean;
    CapDrop: string[]; SecurityOpt: string[]; PidsLimit: number; Memory: number; NanoCpus: number;
    Binds: string[] | null };
  Mounts: { Type: string; Name?: string; Destination: string }[];
  State: { Running: boolean };
};

/** Actual client calls through the existing runner: no fake result/status. */
async function withOwnedOfflineEffect(body: (f: {
  root: string; nonce: string; volume: string; docker: DockerRun; env: NodeJS.ProcessEnv;
  check: (args: string[]) => Promise<RunResult>;
  inspect: (id: string) => Promise<EffectInspect>;
  start: () => Promise<string>;
}) => Promise<void>): Promise<void> {
  const root = realpathSync(mkdtempSync(path.join(tmpdir(), "ca-sbx-owned-effect-")));
  const rootInfo = lstatSync(root); const ambient = realpathSync(tmpdir());
  if (path.dirname(root) !== ambient) throw new Error("owned fixture root is outside ambient Temp");
  const nonce = randomUUID(); const prefix = `ca-sbx-effect-${nonce}`; const volume = `${prefix}-home`;
  const names = new Set<string>(); let volumeRequested = false;
  const profile = path.join(root, "profile");
  for (const name of ["home", "config", "temp", "cache", "appdata", "localappdata"]) {
    mkdirSync(path.join(profile, name), { recursive: true });
  }
  // A private synthetic host-auth canary. Never read an operator home/store.
  mkdirSync(path.join(profile, "home", ".claude"));
  const authCanary = path.join(profile, "home", ".claude", ".credentials.json");
  // Deliberately non-credential data, checked only by the fixture container.
  const { writeFileSync } = await import("node:fs");
  writeFileSync(authCanary, JSON.stringify({ fixtureOnly: nonce }));
  const env: NodeJS.ProcessEnv = {};
  for (const key of ["PATH", "SystemRoot", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "SystemDrive"]) {
    if (process.env[key] !== undefined) env[key] = process.env[key];
  }
  Object.assign(env, {
    HOME: path.join(profile, "home"), USERPROFILE: path.join(profile, "home"),
    APPDATA: path.join(profile, "appdata"), LOCALAPPDATA: path.join(profile, "localappdata"),
    TEMP: path.join(profile, "temp"), TMP: path.join(profile, "temp"),
    XDG_CACHE_HOME: path.join(profile, "cache"), DOCKER_CONFIG: path.join(profile, "config"),
    DOCKER_HOST: process.platform === "win32"
      ? "npipe:////./pipe/dockerDesktopLinuxEngine" : "unix:///var/run/docker.sock",
    MSYS_NO_PATHCONV: "1",
  });
  let deadline = Date.now() + 30_000;
  const docker: DockerRun = async (args, call = {}) => {
    if (Date.now() >= deadline) throw new Error("owned effect operation deadline reached");
    if (args[0] === "run") {
      const name = args[args.indexOf("--name") + 1];
      if (args.indexOf("--name") < 0 || !name.startsWith(prefix + "-")) throw new Error("unowned fixture run refused");
      names.add(name); // Retain exact requested name even if the client fails after creation.
      if (!args.includes(EFFECT_IMAGE)) throw new Error("unreviewed fixture image refused");
    }
    const actualArgs = args[0] === "run" ? ["run", "--pull=never", ...args.slice(1)] : args;
    return makeDockerRun({ env }, { timeoutMs: Math.min(10_000, deadline - Date.now()), maxBuffer: 256 * 1024 })(actualArgs, call);
  };
  const check = async (args: string[]) => {
    const r = await docker(args);
    if (r.code !== 0) {
      throw new Error(`owned fixture ${args[0]} failed code=${r.code}; stderr_sha256=${createHash("sha256").update(r.stderr).digest("hex")}`);
    }
    return r;
  };
  const inspect = async (id: string) => {
    if (!/^[0-9a-f]{64}$/.test(id)) throw new Error("full owned container identity required");
    const value = JSON.parse((await check(["inspect", id])).stdout)[0] as EffectInspect;
    if (value.Id !== id || !names.has(value.Name.slice(1)) || value.Config.Labels[EFFECT_LABEL] !== nonce) {
      throw new Error("owned container identity/label mismatch");
    }
    return value;
  };
  let primary: unknown;
  try {
    const cached = JSON.parse((await check(["image", "inspect", EFFECT_IMAGE])).stdout)[0] as {
      Id: string; Os: string; RepoDigests: string[];
    };
    expect(cached.Os).toBe("linux");
    expect(cached.RepoDigests.some((name) => name.endsWith("@" + EFFECT_DIGEST))).toBe(true);
    expect(cached.Id).toMatch(/^sha256:[0-9a-f]{64}$/);
    expect((await check(["volume", "ls", "-q", "--filter", `name=^${volume}$`])).stdout.trim()).toBe("");
    volumeRequested = true;
    await check(["volume", "create", "--label", `${EFFECT_LABEL}=${nonce}`, volume]);
    const vol = JSON.parse((await check(["volume", "inspect", volume])).stdout)[0] as {
      Name: string; Labels: Record<string, string>;
    };
    expect(vol.Name).toBe(volume); expect(vol.Labels[EFFECT_LABEL]).toBe(nonce);
    // First mount inherits /home/node uid 1000 from the pinned image. No root
    // chown helper, host bind, auth copy, image build or installation is used.
    await check(["run", "--name", `${prefix}-seed`, "--label", `${EFFECT_LABEL}=${nonce}`,
      "--label", SANDBOX_LABEL, ...hardeningFlags(), "--network", "none",
      "--mount", `type=volume,source=${volume},target=/home/node`, "--workdir", "/home/node",
      EFFECT_IMAGE, "node", "-e", "const fs=require('fs');fs.mkdirSync('/home/node/.claude',{recursive:true});" +
        `fs.writeFileSync('/home/node/.fixture-owner',${JSON.stringify(nonce)});`]);
    const start = async () => {
      const id = await runClaudeInside({ image: EFFECT_IMAGE, token: EFFECT_DUMMY, homeVolume: volume,
        extraLabels: [`${EFFECT_LABEL}=${nonce}`], namePrefix: prefix,
        command: ["node", "-e", "setInterval(()=>{},1000)"] }, docker, { env });
      const value = await inspect(id);
      expect(value.Image).toBe(cached.Id); expect(value.State.Running).toBe(true);
      return id;
    };
    await body({ root, nonce, volume, docker, env, check, inspect, start });
  } catch (error) { primary = error; }
  // Cancellation/deadline-independent cleanup over only exact owned names.
  deadline = Date.now() + 20_000;
  let cleanup: unknown;
  try {
    for (const name of [...names].reverse()) {
      const ids = (await check(["ps", "-a", "-q", "--no-trunc", "--filter", `name=^/${name}$`])).stdout.trim();
      if (ids === "") continue;
      if (!/^[0-9a-f]{64}$/.test(ids)) throw new Error("ambiguous cleanup container observation");
      await inspect(ids); await check(["rm", "-f", ids]);
      expect((await check(["ps", "-a", "-q", "--no-trunc", "--filter", `id=${ids}`])).stdout.trim()).toBe("");
    }
    if (volumeRequested) {
      const found = (await check(["volume", "ls", "-q", "--filter", `name=^${volume}$`])).stdout.trim();
      if (found !== "") {
        expect(found).toBe(volume);
        const value = JSON.parse((await check(["volume", "inspect", volume])).stdout)[0] as {
          Name: string; Labels: Record<string, string>;
        };
        expect(value.Name).toBe(volume); expect(value.Labels[EFFECT_LABEL]).toBe(nonce);
        await check(["volume", "rm", volume]);
        expect((await check(["volume", "ls", "-q", "--filter", `name=^${volume}$`])).stdout.trim()).toBe("");
      }
    }
    const finalRoot = lstatSync(root);
    if (realpathSync(root) !== root || path.dirname(root) !== ambient || finalRoot.isSymbolicLink() ||
        finalRoot.dev !== rootInfo.dev || finalRoot.ino !== rootInfo.ino ||
        !path.basename(root).startsWith("ca-sbx-owned-effect-")) {
      throw new Error("owned fixture root identity changed; directory retained");
    }
    rmSync(root, { recursive: true });
  } catch (error) { cleanup = error; }
  if (primary !== undefined && cleanup !== undefined) throw new AggregateError([primary, cleanup], "effect failed; owned cleanup also unknown");
  if (primary !== undefined) throw primary;
  if (cleanup !== undefined) throw cleanup;
}

/** Copy-only fixture: ordinary writable image layer, never a product guard change. */
async function withOwnedWritableCopyLayer(body: (f: {
  root: string; nonce: string; id: string; docker: DockerRun;
  check: (args: string[]) => Promise<RunResult>;
}) => Promise<void>): Promise<void> {
  const root = realpathSync(mkdtempSync(path.join(tmpdir(), "ca-sbx-copy-layer-")));
  const rootInfo = lstatSync(root); const ambient = realpathSync(tmpdir());
  if (path.dirname(root) !== ambient) throw new Error("copy fixture outside ambient Temp");
  const nonce = randomUUID(); const name = `ca-sbx-copy-layer-${nonce}`;
  for (const dir of ["home", "config", "temp", "cache", "appdata", "localappdata"]) mkdirSync(path.join(root, dir));
  const env: NodeJS.ProcessEnv = {};
  for (const key of ["PATH", "SystemRoot", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "SystemDrive"]) {
    if (process.env[key] !== undefined) env[key] = process.env[key];
  }
  Object.assign(env, { HOME: path.join(root, "home"), USERPROFILE: path.join(root, "home"),
    TEMP: path.join(root, "temp"), TMP: path.join(root, "temp"),
    APPDATA: path.join(root, "appdata"), LOCALAPPDATA: path.join(root, "localappdata"),
    XDG_CACHE_HOME: path.join(root, "cache"), DOCKER_CONFIG: path.join(root, "config"),
    DOCKER_HOST: process.platform === "win32" ? "npipe:////./pipe/dockerDesktopLinuxEngine" : "unix:///var/run/docker.sock",
    MSYS_NO_PATHCONV: "1" });
  let deadline = Date.now() + 30_000;
  const docker: DockerRun = (args, call = {}) => {
    if (Date.now() >= deadline) throw new Error("copy fixture deadline reached");
    const argv = args[0] === "run" ? ["run", "--pull=never", ...args.slice(1)] : args;
    return makeDockerRun({ env }, { timeoutMs: Math.min(10_000, deadline - Date.now()), maxBuffer: 256 * 1024 })(argv, call);
  };
  const check = async (args: string[]) => {
    const result = await docker(args);
    if (result.code !== 0) throw new Error(`owned copy ${args[0]} failed code=${result.code}; stderr_sha256=${createHash("sha256").update(result.stderr).digest("hex")}`);
    return result;
  };
  let requested = false; let primary: unknown;
  try {
    const image = JSON.parse((await check(["image", "inspect", EFFECT_IMAGE])).stdout)[0] as {
      Id: string; Os: string; RepoDigests: string[];
    };
    expect(image.Os).toBe("linux"); expect(image.RepoDigests.some((value) => value.endsWith("@" + EFFECT_DIGEST))).toBe(true);
    expect((await check(["ps", "-a", "-q", "--no-trunc", "--filter", `name=^/${name}$`])).stdout.trim()).toBe("");
    const hardening = hardeningFlags(); const readOnly = hardening.indexOf("--read-only"); const tmpfs = hardening.indexOf("--tmpfs");
    expect(readOnly).toBeGreaterThanOrEqual(0); expect(hardening[tmpfs + 1]).toBe("/tmp");
    // Only this controlled copy fixture omits read-only-root and the tmpfs mount.
    // The two real hardened cases above remain byte-for-byte unchanged.
    const flags = hardening.filter((_, index) => index !== readOnly && index !== tmpfs && index !== tmpfs + 1);
    requested = true;
    const id = (await check(["run", "-d", "--name", name, "--label", `${EFFECT_LABEL}=${nonce}`,
      "--label", SANDBOX_LABEL, ...flags, "--network", "none", "--workdir", "/home/node",
      EFFECT_IMAGE, "node", "-e", "setInterval(()=>{},1000)"])).stdout.trim();
    expect(id).toMatch(/^[0-9a-f]{64}$/);
    const value = JSON.parse((await check(["inspect", id])).stdout)[0] as EffectInspect;
    expect(value.Id).toBe(id); expect(value.Name).toBe("/" + name); expect(value.Image).toBe(image.Id);
    expect(value.Config.Labels[EFFECT_LABEL]).toBe(nonce); expect(value.State.Running).toBe(true);
    expect(value.Config.User).toBe("1000:1000"); expect(value.Mounts).toEqual([]);
    expect(value.HostConfig).toMatchObject({ ReadonlyRootfs: false, NetworkMode: "none", Privileged: false,
      PidsLimit: 512, Memory: 4 * 1024 ** 3, NanoCpus: 2_000_000_000 });
    expect(value.HostConfig.CapDrop).toContain("ALL"); expect(value.HostConfig.SecurityOpt).toContain("no-new-privileges");
    expect(value.HostConfig.Binds ?? []).toEqual([]);
    expect(value.Config.Env.some((entry) => /^(CLAUDE_CODE_OAUTH_TOKEN|GH_TOKEN|GITHUB_TOKEN|ANTHROPIC_API_KEY|OPENAI_API_KEY)=/.test(entry))).toBe(false);
    await body({ root, nonce, id, docker, check });
  } catch (error) { primary = error; }
  deadline = Date.now() + 20_000;
  let cleanup: unknown;
  try {
    if (requested) {
      const id = (await check(["ps", "-a", "-q", "--no-trunc", "--filter", `name=^/${name}$`])).stdout.trim();
      if (id !== "") {
        expect(id).toMatch(/^[0-9a-f]{64}$/);
        const value = JSON.parse((await check(["inspect", id])).stdout)[0] as EffectInspect;
        expect(value.Id).toBe(id); expect(value.Name).toBe("/" + name); expect(value.Config.Labels[EFFECT_LABEL]).toBe(nonce);
        await check(["rm", "-f", id]);
        expect((await check(["ps", "-a", "-q", "--no-trunc", "--filter", `id=${id}`])).stdout.trim()).toBe("");
      }
    }
    const final = lstatSync(root);
    if (realpathSync(root) !== root || path.dirname(root) !== ambient || final.isSymbolicLink() ||
        final.dev !== rootInfo.dev || final.ino !== rootInfo.ino || !path.basename(root).startsWith("ca-sbx-copy-layer-")) {
      throw new Error("copy fixture root identity changed; retained");
    }
    rmSync(root, { recursive: true });
  } catch (error) { cleanup = error; }
  if (primary !== undefined && cleanup !== undefined) throw new AggregateError([primary, cleanup], "copy failed; owned cleanup also unknown");
  if (primary !== undefined) throw primary;
  if (cleanup !== undefined) throw cleanup;
}

/** Full captured strings, private adjacent artifact only; never raw console text. */
function retainOwnedCopyResult(root: string, nonce: string, id: string, result: RunResult): void {
  const stdout = Buffer.from(result.stdout, "utf8"); const stderr = Buffer.from(result.stderr, "utf8");
  if (stdout.length + stderr.length > 256 * 1024 + 4096) throw new Error("copy result exceeds existing runner bound");
  const file = path.join(path.dirname(root), path.basename(root) + "-copy-result.json");
  const raw = Buffer.from(JSON.stringify({ format: "sandbox-private-copy-result/1", nonce, id,
    code: result.code, aborted: result.aborted === true, timedOut: result.timedOut === true,
    overflowed: result.overflowed === true, encoding: "base64-of-utf8-captured-RunResult",
    originalCliByteStreamClaim: false,
    stdoutBytes: stdout.length, stdoutSha256: createHash("sha256").update(stdout).digest("hex"), stdoutBase64: stdout.toString("base64"),
    stderrBytes: stderr.length, stderrSha256: createHash("sha256").update(stderr).digest("hex"), stderrBase64: stderr.toString("base64") }));
  if (raw.length > 512 * 1024) throw new Error("copy diagnostic serialization exceeds bound");
  writeFileSync(file, raw, { flag: "wx", mode: 0o600 });
  console.log(JSON.stringify({ format: "sandbox-private-copy-result-pointer/1", file: path.basename(file),
    sha256: createHash("sha256").update(raw).digest("hex"), bytes: raw.length, privateOnly: true }));
}

d("owned offline effect acceptance [docker]", () => {
  it("prepares a credential-blind owned home and retains its bytes across restart", async () => {
    await withOwnedOfflineEffect(async (f) => {
      const id = await f.start();
      const script = "const fs=require('fs'),p=process.env.HOME;" +
        `fs.writeFileSync(p+'/.claude/effect-state.json',JSON.stringify({nonce:${JSON.stringify(f.nonce)}}));` +
        "console.log(JSON.stringify({uid:process.getuid(),home:p,owner:fs.statSync(p).uid," +
        "hostAuthCopied:fs.existsSync(p+'/.claude/.credentials.json'),seed:fs.readFileSync(p+'/.fixture-owner','utf8')}))";
      const observed = JSON.parse((await f.check(["exec", id, "node", "-e", script])).stdout) as {
        uid: number; home: string; owner: number; hostAuthCopied: boolean; seed: string;
      };
      expect(observed).toEqual({ uid: 1000, home: CLAUDE_HOME, owner: 1000, hostAuthCopied: false, seed: f.nonce });
      const before = await f.inspect(id);
      expect(before.Mounts.filter((m) => m.Type === "volume")).toEqual([
        expect.objectContaining({ Name: f.volume, Destination: CLAUDE_HOME }),
      ]);
      expect(before.Mounts.some((m) => m.Type === "bind" || ["/work/repo", "/var/run/docker.sock"].includes(m.Destination))).toBe(false);
      await f.check(["restart", "--time", "1", id]);
      expect((await f.inspect(id)).State.Running).toBe(true);
      const after = JSON.parse((await f.check(["exec", id, "node", "-e",
        "console.log(require('fs').readFileSync(process.env.HOME+'/.claude/effect-state.json','utf8'))"])).stdout) as { nonce: string };
      console.log(JSON.stringify({ format: "sandbox-owned-effect/1", case: "home", id, volume: f.volume,
        uid: observed.uid, homeOwner: observed.owner, hostAuthCopied: observed.hostAuthCopied,
        sameContainerRestarted: true, persistedNonceMatches: after.nonce === f.nonce }));
      expect(after).toEqual({ nonce: f.nonce });
    });
  }, 60_000);

  it("runs the real Claude builder offline with scoped dummy env and effective hardening", async () => {
    await withOwnedOfflineEffect(async (f) => {
      const id = await f.start(); const value = await f.inspect(id);
      expect(value.HostConfig).toMatchObject({ NetworkMode: "none", ReadonlyRootfs: true, Privileged: false,
        PidsLimit: 512, Memory: 4 * 1024 ** 3, NanoCpus: 2_000_000_000 });
      expect(value.Config.User).toBe("1000:1000"); expect(value.Config.WorkingDir).toBe(CLAUDE_HOME);
      expect(value.HostConfig.CapDrop).toContain("ALL");
      expect(value.HostConfig.SecurityOpt).toContain("no-new-privileges");
      expect(value.HostConfig.Binds ?? []).toEqual([]);
      const observed = JSON.parse((await f.check(["exec", id, "node", "-e",
        "const os=require('os'),fs=require('fs'),s=fs.readFileSync('/proc/self/status','utf8');" +
        "console.log(JSON.stringify({uid:process.getuid(),interfaces:Object.keys(os.networkInterfaces())," +
        `dummyOnly:process.env.${TOKEN_ENV_VAR}===${JSON.stringify(EFFECT_DUMMY)},` +
        "foreignCredentialPresent:['GH_TOKEN','GITHUB_TOKEN','ANTHROPIC_API_KEY','OPENAI_API_KEY','AWS_SECRET_ACCESS_KEY'].some(k=>!!process.env[k])," +
        "capEff:s.match(/^CapEff:\\s*(.+)$/m)?.[1],noNewPrivs:s.match(/^NoNewPrivs:\\s*(.+)$/m)?.[1]}))"])).stdout) as {
        uid: number; interfaces: string[]; dummyOnly: boolean; foreignCredentialPresent: boolean; capEff: string; noNewPrivs: string;
      };
      console.log(JSON.stringify({ format: "sandbox-owned-effect/1", case: "offline", id, ...observed,
        networkMode: value.HostConfig.NetworkMode, readOnly: value.HostConfig.ReadonlyRootfs }));
      expect(observed.uid).toBe(1000); expect(observed.interfaces).toEqual(["lo"]);
      expect(observed.dummyOnly).toBe(true); expect(observed.foreignCredentialPresent).toBe(false);
      expect(observed.capEff).toMatch(/^0+$/); expect(observed.noNewPrivs).toBe("1");
    });
  }, 60_000);

  it("retains real partial docker cp bytes after cancellation without rollback metadata", async () => {
    await withOwnedWritableCopyLayer(async (f) => {
      const id = f.id; const total = 64 * 1024 * 1024;
      const seeded = JSON.parse((await f.check(["exec", id, "node", "-e", "const fs=require('fs'),p='/home/node/effect-payload.bin',fd=fs.openSync(p,'w');" +
        "try{const b=Buffer.alloc(1024*1024,65);for(let i=0;i<64;i++)fs.writeSync(fd,b)}finally{fs.closeSync(fd)};" +
        "const s=fs.lstatSync(p);console.log(JSON.stringify({size:s.size,regular:s.isFile(),uid:process.getuid()}))"])).stdout) as { size: number; regular: boolean; uid: number };
      expect(seeded).toEqual({ size: total, regular: true, uid: 1000 });
      const dest = path.join(f.root, "partial.bin");
      expect(existsSync(dest)).toBe(false);
      const abort = new AbortController();
      let settled = false; let observedPartial = 0;
      const pending = cpOut(id, "/home/node/effect-payload.bin", dest, { dockerRun: f.docker, signal: abort.signal })
        .then((result) => { settled = true; return { result }; },
          (error: unknown) => { settled = true; return { error }; });
      const pollDeadline = Date.now() + 8_000;
      let observationError: unknown;
      try {
        while (!settled && Date.now() < pollDeadline) {
          try {
            const size = statSync(dest).size;
            if (size > 0 && size < total) { observedPartial = size; abort.abort(); break; }
          } catch (error) {
            if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
          }
          await new Promise((resolve) => setTimeout(resolve, 1));
        }
      } catch (error) { observationError = error; }
      finally { if (!settled && !abort.signal.aborted) abort.abort(); }
      const outcome = await pending; // Settle the owned client before fixture cleanup.
      if ("error" in outcome) throw outcome.error;
      const result = outcome.result; // Preserve the genuine original outcome before assertions.
      retainOwnedCopyResult(f.root, f.nonce, id, result);
      if (observationError !== undefined) throw observationError;
      const retained = existsSync(dest) ? statSync(dest).size : 0;
      let prefix = "";
      if (retained > 0) {
        const fd = openSync(dest, "r"); const first = Buffer.alloc(Math.min(32, retained));
        try { readSync(fd, first, 0, first.length, 0); prefix = first.toString("ascii"); }
        finally { closeSync(fd); }
      }
      console.log(JSON.stringify({ format: "sandbox-owned-effect/1", case: "partial-copy", id,
        observedPartial, retained, expectedBytes: total, code: result.code, aborted: result.aborted === true,
        timedOut: result.timedOut === true, overflowed: result.overflowed === true,
        stdoutSha256: createHash("sha256").update(result.stdout).digest("hex"),
        stderrSha256: createHash("sha256").update(result.stderr).digest("hex"), prefixMatches: /^A+$/.test(prefix) }));
      expect(observedPartial, "copy completed/failed before partial bytes were observed; no qualifying partial oracle").toBeGreaterThan(0);
      expect(result.code).not.toBe(0); expect(result.aborted).toBe(true);
      expect(retained).toBeGreaterThan(0); expect(retained).toBeLessThan(total); expect(prefix).toMatch(/^A+$/);
      expect("rollback" in result).toBe(false); expect("recovery" in result).toBe(false);
    });
  }, 60_000);
});
