/** Real shipped-bundle cases. Source mode never creates installed qualification. */
import { expect, it } from "vitest";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  appendFileSync, chmodSync, existsSync, lstatSync, mkdirSync, mkdtempSync,
  readFileSync, realpathSync, rmSync, writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { dockerGate } from "./docker-gate.ts";
import { FALLBACK_BASE_IMAGE } from "./build.ts";

const GROUP = "shipped sandbox bundle [docker]";
const d = dockerGate("installed-bundle", { linux: true });
const sourcePlugin = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const configuredPlugin = process.env.CA_SANDBOX_INSTALLED_PLUGIN;
const plugin = configuredPlugin ?? sourcePlugin;
const bundle = path.join(plugin, "tools", "sandbox.js");
const trace = process.env.CA_SANDBOX_BUNDLE_OBSERVATION;
const fixtureBase = process.env.CA_SANDBOX_BUNDLE_TMP_ROOT ?? tmpdir();
const hash = (raw: Buffer | string) => createHash("sha256").update(raw).digest("hex");

type Command = {
  argv: string[]; exit_code: number | null; timed_out: boolean;
  containment: string; stdout_utf8: string; stderr_utf8: string;
};
type Fixture = {
  id: string; container: string; volume: string; host_dir: string;
  labels: Record<string, string>;
};
type Image = {
  reference: string; id: string; repo_digests: string[];
  os: string; architecture: string;
};

function childEnv(): NodeJS.ProcessEnv {
  const allow = new Set([
    "PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT",
    "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME",
    "XDG_CACHE_HOME", "TEMP", "TMP", "DOCKER_CONFIG", "CI",
  ]);
  return {
    ...Object.fromEntries(Object.entries(process.env).filter(([key]) => allow.has(key.toUpperCase()))),
    MSYS_NO_PATHCONV: "1",
  };
}

function docker(args: string[], acceptable = [0]) {
  const result = spawnSync("docker", args, {
    encoding: "utf8", env: childEnv(), timeout: 45_000, maxBuffer: 1024 * 1024,
  });
  expect(result.error, "owned Docker call could not execute").toBeUndefined();
  expect(result.signal, "owned Docker call did not exit").toBeNull();
  expect(acceptable, result.stderr).toContain(result.status);
  return result;
}

function inspectImage(): Image {
  const raw = JSON.parse(docker(["image", "inspect", FALLBACK_BASE_IMAGE]).stdout);
  expect(raw).toHaveLength(1);
  const value = raw[0];
  expect(value.Os).toBe("linux");
  expect(value.Architecture).toBe("amd64");
  expect(value.RepoDigests.some((item: string) =>
    item.endsWith("@" + FALLBACK_BASE_IMAGE.split("@")[1]))).toBe(true);
  return { reference: FALLBACK_BASE_IMAGE, id: value.Id,
    repo_digests: [...value.RepoDigests].sort(), os: value.Os, architecture: value.Architecture };
}

function actualCli(tail: string[], commands: Command[]) {
  const argv = [process.execPath, bundle, ...tail];
  const before = hash(readFileSync(bundle));
  const result = spawnSync(argv[0], argv.slice(1), {
    encoding: "utf8", env: childEnv(), timeout: 45_000, maxBuffer: 65536,
  });
  const record: Command = {
    argv, exit_code: result.status,
    timed_out: (result.error as NodeJS.ErrnoException | undefined)?.code === "ETIMEDOUT",
    containment: Number.isInteger(result.status) && result.signal === null ? "exited" : "unknown",
    stdout_utf8: result.stdout ?? "", stderr_utf8: result.stderr ?? "",
  };
  // Keep failure boundaries before any assertion; the enclosing case retains
  // the complete command record even when the actual CLI fails.
  commands.push(record);
  expect(record.timed_out).toBe(false);
  expect(record.containment).toBe("exited");
  expect(record.exit_code, record.stderr_utf8).toBe(0);
  expect(hash(readFileSync(bundle))).toBe(before);
  return record;
}

function scopedObjects(fixture: Fixture) {
  const filters = ["--filter", "label=ca.sandbox=1",
    "--filter", "label=ca.sandbox.id=" + fixture.id,
    "--filter", "label=ca.sandbox.qualification=" + fixture.id];
  return {
    containers: docker(["ps", "-aq", "--no-trunc", ...filters]).stdout.trim().split(/\s+/).filter(Boolean),
    volumes: docker(["volume", "ls", "-q", ...filters]).stdout.trim().split(/\s+/).filter(Boolean),
  };
}

function ownCleanup(fixture: Fixture) {
  const found = scopedObjects(fixture);
  if (fixture.container === "" && found.containers.length === 1) {
    fixture.container = found.containers[0];
  }
  expect(found.containers.every(id => id === fixture.container)).toBe(true);
  expect(found.volumes.every(name => name === fixture.volume)).toBe(true);
  for (const id of found.containers) docker(["rm", "-f", id]);
  for (const name of found.volumes) docker(["volume", "rm", name]);
  const after = scopedObjects(fixture);
  return { container_absent: after.containers.length === 0,
    volume_absent: after.volumes.length === 0, owned_only: true };
}

function runCase(name: string, effect: (fixture: Fixture, commands: Command[]) =>
  { exec_marker: boolean; copy_sha256: string | null; destroy_empty: boolean }) {
  if (configuredPlugin !== undefined) {
    expect(path.isAbsolute(configuredPlugin)).toBe(true);
    expect(realpathSync(configuredPlugin)).toBe(path.resolve(configuredPlugin));
    expect(trace, "installed mode requires the owned observation sink").toBeTruthy();
    expect(process.env.CA_SANDBOX_BUNDLE_TMP_ROOT).toBeTruthy();
  }
  expect(lstatSync(bundle).isFile()).toBe(true);
  expect(lstatSync(bundle).isSymbolicLink()).toBe(false);
  const bundleBefore = hash(readFileSync(bundle));
  mkdirSync(fixtureBase, { recursive: true });
  const hostDir = mkdtempSync(path.join(fixtureBase, "sbx-installed-"));
  expect(path.dirname(realpathSync(hostDir))).toBe(realpathSync(fixtureBase));
  const id = path.basename(hostDir);
  const fixture: Fixture = {
    id, container: "", volume: "ca-sbx-vol-" + id, host_dir: hostDir,
    labels: { "ca.sandbox": "1", "ca.sandbox.id": id, "ca.sandbox.qualification": id },
  };
  const commands: Command[] = [];
  let image: Image | undefined;
  let checks = { exec_marker: false, copy_sha256: null as string | null, destroy_empty: false };
  let cleanup = { container_absent: false, volume_absent: false, owned_only: false };
  let cleanupAllowed = false;
  let failed = false;
  try {
    image = inspectImage(); // No implicit image acquisition or image substitution.
    // Refuse preexisting names before touching them, including an unrelated
    // volume that Docker would otherwise return from volume create.
    expect(docker(["volume", "inspect", fixture.volume], [0, 1]).status).toBe(1);
    expect(docker(["container", "inspect", "ca-sbx-" + id], [0, 1]).status).toBe(1);
    expect(scopedObjects(fixture)).toEqual({ containers: [], volumes: [] });
    cleanupAllowed = true;
    const labels = Object.entries(fixture.labels).flatMap(([key, value]) => ["--label", key + "=" + value]);
    docker(["volume", "create", ...labels, fixture.volume]);
    const volume = JSON.parse(docker(["volume", "inspect", fixture.volume]).stdout);
    expect(volume).toHaveLength(1);
    expect(volume[0].Labels).toEqual(fixture.labels);
    fixture.container = docker([
      "run", "--pull=never", "-d", "--name", "ca-sbx-" + id, ...labels,
      "--user", "1000:1000", "--read-only", "--cap-drop", "ALL",
      "--security-opt", "no-new-privileges", "--network", "none",
      "--pids-limit", "64", "--memory", "128m", "--cpus", "1",
      "--mount", "type=volume,source=" + fixture.volume + ",target=/work/repo",
      "--tmpfs", "/tmp:rw,size=16m,mode=1777", FALLBACK_BASE_IMAGE, "sleep", "infinity",
    ]).stdout.trim();
    expect(fixture.container).toMatch(/^[a-f0-9]{64}$/);
    checks = effect(fixture, commands);
  } catch (error) {
    failed = true;
    throw error;
  } finally {
    try {
      try {
        // Do not touch any object outside the three exact per-fixture labels.
        // A startup failure may have created the volume but no container.
        if (cleanupAllowed) {
          cleanup = ownCleanup(fixture);
          expect(cleanup.container_absent && cleanup.volume_absent && cleanup.owned_only).toBe(true);
        }
        expect(hash(readFileSync(bundle))).toBe(bundleBefore);
      } finally {
        if (trace) {
          const info = lstatSync(trace);
          expect(info.isFile() && !info.isSymbolicLink() && info.nlink === 1).toBe(true);
          appendFileSync(trace, JSON.stringify({
            format: "codearbiter.sandbox-bundle-case/1", name: GROUP + " " + name,
            plugin_root: plugin, bundle_sha256: bundleBefore, node: process.execPath,
            image, fixture, commands, checks, cleanup,
          }) + "\n", { encoding: "utf8" });
        }
        const resolved = realpathSync(hostDir);
        expect(path.dirname(resolved)).toBe(realpathSync(fixtureBase));
        rmSync(resolved, { recursive: true, force: false });
      }
    } catch (cleanupError) {
      // The original effect error is already propagating. A second failure
      // must not hide it or turn the incomplete cleanup receipt into success.
      if (!failed) throw cleanupError;
    }
  }
  expect(failed).toBe(false);
}

d(GROUP, () => {
  it("resolves exec through the shipped CLI", () => {
    runCase("resolves exec through the shipped CLI", (fixture, commands) => {
      const result = JSON.parse(actualCli([
        "exec", fixture.id, "--", "sh", "-c", "printf SBX_INSTALLED_EXEC",
      ], commands).stdout_utf8);
      expect(result.id).toBe(fixture.id);
      expect(result.exitCode).toBe(0);
      expect(result.stdout).toBe("SBX_INSTALLED_EXEC");
      return { exec_marker: true, copy_sha256: null, destroy_empty: false };
    });
  }, 180_000);

  it("copies out through the shipped CLI", () => {
    runCase("copies out through the shipped CLI", (fixture, commands) => {
      const seed = path.join(fixture.host_dir, "seed");
      writeFileSync(seed, "SBX_INSTALLED_COPY", { encoding: "utf8", flag: "wx", mode: 0o644 });
      chmodSync(seed, 0o644); // Readable by UID1000 after Docker copies it as root.
      docker(["cp", seed, fixture.container + ":/work/repo/result"]);
      const result = JSON.parse(actualCli([
        "exec", fixture.id, "--", "cat", "/work/repo/result",
      ], commands).stdout_utf8);
      expect(result.id).toBe(fixture.id);
      expect(result.exitCode).toBe(0);
      expect(result.stdout).toBe("SBX_INSTALLED_COPY");
      const target = path.join(fixture.host_dir, "result");
      expect(existsSync(target)).toBe(false);
      actualCli(["cp", fixture.id + ":/work/repo/result", target], commands);
      expect(readFileSync(target, "utf8")).toBe("SBX_INSTALLED_COPY");
      return { exec_marker: false, copy_sha256: hash(readFileSync(target)), destroy_empty: false };
    });
  }, 180_000);

  it("destroys its owned container and volume", () => {
    runCase("destroys its owned container and volume", (fixture, commands) => {
      const result = JSON.parse(actualCli(["destroy", fixture.id], commands).stdout_utf8);
      expect(result.id).toBe(fixture.id);
      expect(result.failureCount).toBe(0);
      expect(result.remainingContainers).toEqual([]);
      expect(result.remainingVolumes).toEqual([]);
      expect(scopedObjects(fixture)).toEqual({ containers: [], volumes: [] });
      return { exec_marker: false, copy_sha256: null, destroy_empty: true };
    });
  }, 180_000);
});
