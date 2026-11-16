import { it, expect } from "vitest";
import { randomBytes } from "node:crypto";
import { writeFile } from "node:fs/promises";
import path from "node:path";
import { dockerGate } from "./docker-gate.ts";
import { defaultDockerRun, makeDockerRun } from "./docker.ts";
import { defaultBuildDeps, defaultEnsureNixpacks, CACHE_LABEL, type BuildContext, type BuildDeps } from "./build.ts";
import { createSandbox, CLONE_IMAGE } from "./create.ts";
import { destroySandbox, teardownIncomplete } from "./destroy.ts";

/** Two actual cache misses rendezvous; no inspect/build result is fabricated. */
function coldPair() {
  let waiters: Array<{ resolve: () => void; reject: (error: Error) => void }> = [];
  let timer: ReturnType<typeof setTimeout> | undefined;
  let failure: Error | undefined;
  const cancel = (error: Error) => {
    failure = error;
    if (timer) clearTimeout(timer);
    for (const waiter of waiters) waiter.reject(error);
    waiters = [];
  };
  return {
    cancel,
    meet: () => new Promise<void>((resolve, reject) => {
      if (failure) { reject(failure); return; }
      waiters.push({ resolve, reject });
      if (waiters.length === 2) {
        if (timer) clearTimeout(timer);
        for (const waiter of waiters) waiter.resolve();
        waiters = [];
      } else {
        timer = setTimeout(() => cancel(new Error("cache fixture could not observe two cold requests")), 10_000);
      }
    }),
  };
}

const d = dockerGate("cache-provenance", { linux: true });
d("SBX-C01 real two-create cache provenance", () => {
  for (const builder of ["dockerfile-fallback", "nixpacks"] as const) {
    it(`${builder}: distinct staging names reuse the exact labeled image and preserve another box`, async () => {
      const installed=await defaultEnsureNixpacks();
      if(builder==="nixpacks" && !installed.available) {
        throw new Error("SBX-C01 required Nixpacks qualification unavailable: install a reviewed pinned builder in the hosted qualification environment; no driver auto-install");
      }
      if (builder === "nixpacks") expect(installed.version).toBe("1.41.0");
      const suffix=randomBytes(16).toString("hex");
      const roles = ["a1", "a2", "b", "c1", "c2", "c3"] as const;
      type Role = typeof roles[number];
      const ids = Object.fromEntries(roles.map(role => [role, `cache-${role}-${suffix}`])) as Record<Role, string>;
      const touched = new Set<string>();
      const coldTags = new Map<string, string>();
      const imageIds = new Set<string>();
      const staging = new Map<Role, string>();
      const builds: Array<{ role: Role; tag: string; key: string; start: number; end?: number; code?: number }> = [];
      const completed: Partial<Record<Role, Awaited<ReturnType<typeof createSandbox>>>> = {};
      let bodyFailed = false;
      const pair = coldPair();
      const body = new AbortController();
      const bodyTimer = setTimeout(() => body.abort(new Error("cache fixture body deadline")), 240_000);
      const versions = { a1: "1.0.0", a2: "1.0.0", b: "1.0.1", c1: "1.0.2", c2: "1.0.2", c3: "1.0.2" };
      const observations: unknown[] = [];
      const observe = async (value: unknown) => {
        observations.push(value);
        const directory = process.env.CA_SANDBOX_CACHE_OBSERVATION_DIR;
        if (directory) {
          const encoded = JSON.stringify({ builder, suffix, ids, observations });
          if (Buffer.byteLength(encoded) > 64 * 1024) throw new Error("cache fixture observation bound");
          await writeFile(path.join(directory, `cache-${builder}-${suffix}.json`), encoded + "\n", { mode: 0o600 });
        }
      };
      const depsFor = (role: Role): BuildDeps => {
        const deps = defaultBuildDeps();
        const actualInspect = deps.imageInspect, actualBuild = deps.runBuild, actualStack = deps.detectStack!;
        deps.ensureNixpacks = builder === "dockerfile-fallback" ? async () => ({ available: false }) : async () => {
          const actual = await defaultEnsureNixpacks();
          if (!actual.available || actual.version !== "1.41.0") throw new Error("reviewed Nixpacks identity unavailable or changed");
          return actual;
        };
        deps.detectStack = async directory => {
          staging.set(role, directory);
          return actualStack(directory);
        };
        deps.imageInspect = async tag => {
          const actual = await actualInspect(tag); // Unknown observation still throws.
          await observe({ event: "inspect", role, tag, code: actual });
          if (role === "a1" || role === "b" || role === "c1" || role === "c2") {
            expect(actual, "unique cold fixture tag must not preexist").not.toBe(0);
          }
          if (role === "c1" || role === "c2") await pair.meet();
          return actual;
        };
        deps.runBuild = async (tag: string, context: BuildContext) => {
          expect(context.builder).toBe(builder);
          expect(context.cacheKey).toMatch(/^[a-f0-9]{64}$/);
          coldTags.set(tag, context.cacheKey!);
          const call = { role, tag, key: context.cacheKey!, start: performance.now() } as typeof builds[number];
          builds.push(call);
          await observe({ event: "build-start", role, tag, key: call.key });
          call.start = performance.now();
          try {
            const result = await actualBuild(tag, context);
            call.end = performance.now();
            call.code = result.code;
            if (result.imageId) imageIds.add(result.imageId);
            await observe({ event: "build-end", role, tag, code: result.code, imageId: result.imageId });
            return result;
          } finally { call.end ??= performance.now(); }
        };
        return deps;
      };
      // Seed a real repository on each named volume. No external provider or
      // account is contacted; default create staging/build/run still execute.
      const cloneRepo = (role: Role) => async (_url: string, volume: string, _id: string, signal?: AbortSignal) => {
        const manifest = { name: `cache-${suffix}`, version: versions[role], private: true, engines: { node: "20.x" }, scripts: {} };
        const lock = { name: manifest.name, version: manifest.version, lockfileVersion: 3, requires: true,
          packages: { "": { name: manifest.name, version: manifest.version, engines: manifest.engines } } };
        // Fixed first-party, dependency-free data. This does NOT exercise remote clone/auth.
        const commands = ["cd /work/repo", "git init -q", "git config user.email fixture@example.invalid", "git config user.name Fixture",
          `printf '%s' '${JSON.stringify(manifest)}' > package.json`,
          `printf '%s' '${JSON.stringify(lock)}' > package-lock.json`,
          `printf '%s' 'process.stdout.write("SBX_CACHE_OK\\n")' > probe.js`,
          "git add package.json package-lock.json probe.js",
          "GIT_AUTHOR_DATE=2000-01-01T00:00:00Z GIT_COMMITTER_DATE=2000-01-01T00:00:00Z git commit -qm fixture",
          "chown -R 1000:1000 /work/repo"];
        const result = await defaultDockerRun(["run", "--rm", "--network", "none", "--entrypoint", "sh",
          "--label", `ca.sandbox.cache-fixture=${suffix}`, "--mount", `type=volume,source=${volume},target=/work/repo`,
          CLONE_IMAGE, "-c", commands.join(" && ")], { signal });
        return { code: result.code, stderr: result.stderr };
      };
      const create = async (role: Role) => {
        touched.add(ids[role]);
        await observe({ event: "create-start", role, id: ids[role] });
        const result = await createSandbox("https://example.invalid/fixture", { id: ids[role],
          cloneRepo: cloneRepo(role), buildDeps: depsFor(role), signal: body.signal,
          extraLabels: [`ca.sandbox.cache-fixture=${suffix}`] });
        completed[role] = result;
        if (!result.imageId) throw new Error("actual create returned no verified immutable image");
        imageIds.add(result.imageId);
        const inspected = await defaultDockerRun(["image", "inspect", result.imageId], { signal: body.signal });
        expect(inspected.code).toBe(0);
        const image = JSON.parse(inspected.stdout)[0];
        expect(image.Id).toBe(result.imageId);
        expect(image.Id).toMatch(/^sha256:[a-f0-9]{64}$/);
        expect(image.Config.Labels[CACHE_LABEL]).toBe(result.image.split(":v2-")[1]);
        const container = await defaultDockerRun(["inspect", result.containerId], { signal: body.signal });
        expect(container.code).toBe(0);
        const actual = JSON.parse(container.stdout)[0];
        expect(actual.Image).toBe(result.imageId);
        expect(actual.State.Running).toBe(true);
        expect(actual.HostConfig.NetworkMode).toBe("none");
        expect(actual.HostConfig.ReadonlyRootfs).toBe(true);
        expect(actual.Config.User).toBe("1000:1000");
        const marker = await defaultDockerRun(["exec", result.containerId, "node", "probe.js"], { signal: body.signal });
        expect(marker.code).toBe(0);
        expect(marker.stdout).toBe("SBX_CACHE_OK\n");
        await observe({ event: "create-end", role, imageId: result.imageId, tag: result.image, container: result.containerId });
        return result;
      };
      const remove = async (role: Role) => {
        const removed = await destroySandbox(ids[role]);
        expect(teardownIncomplete(removed)).toBe(false);
        touched.delete(ids[role]);
      };
      try {
        const first = await create("a1");
        expect(builds).toHaveLength(1);
        const second = await create("a2");
        expect(second.image).toBe(first.image);
        expect(second.imageId).toBe(first.imageId);
        expect(staging.get("a1")).not.toBe(staging.get("a2"));
        expect(builds).toHaveLength(1);
        const inspected=await defaultDockerRun(["image","inspect",first.image]);
        expect(inspected.code).toBe(0);
        const image=JSON.parse(inspected.stdout)[0];
        expect(image.Id).toMatch(/^sha256:[a-f0-9]{64}$/);
        expect(image.Config.Labels[CACHE_LABEL]).toBe(first.image.split(":v2-")[1]);
        await remove("a1");
        const survivor=await defaultDockerRun(["inspect","--format","{{.State.Running}}",second.containerId]);
        expect(survivor.code).toBe(0);expect(survivor.stdout.trim()).toBe("true");
        const changed = await create("b");
        expect(changed.image).not.toBe(first.image);
        expect(changed.imageId).not.toBe(first.imageId);
        expect(builds).toHaveLength(2);
        await remove("a2");
        await remove("b");
        const cold = await Promise.allSettled([create("c1"), create("c2")]);
        for (const result of cold) expect(result.status).toBe("fulfilled");
        const one = completed.c1!, two = completed.c2!;
        expect(one.image).toBe(two.image);
        expect(one.image).not.toBe(changed.image);
        const concurrent = builds.filter(call => call.role === "c1" || call.role === "c2");
        expect(concurrent.length).toBeGreaterThanOrEqual(1);
        expect(concurrent.length).toBeLessThanOrEqual(2); // No exactly-one-build requirement.
        if (concurrent.length === 2) {
          expect(Math.max(...concurrent.map(call => call.start))).toBeLessThan(Math.min(...concurrent.map(call => call.end!)));
        }
        expect(concurrent.every(call => call.code === 0)).toBe(true);
        const finalIdentity = await defaultDockerRun(["image", "inspect", one.image], { signal: body.signal });
        expect(finalIdentity.code).toBe(0);
        const published = JSON.parse(finalIdentity.stdout)[0];
        expect([one.imageId, two.imageId]).toContain(published.Id);
        expect(published.Config.Labels[CACHE_LABEL]).toBe(one.image.split(":v2-")[1]);
        const beforeHit = builds.length;
        const converged = await create("c3");
        expect(converged.imageId).toBe(published.Id);
        expect(builds).toHaveLength(beforeHit);
      } catch (error) {
        bodyFailed = true;
        body.abort(error);
        pair.cancel(new Error("cache fixture stopped"));
        throw error;
      } finally {
        clearTimeout(bodyTimer);
        pair.cancel(new Error("cache fixture cleanup"));
        // Cleanup authority is independent of body cancellation and limited to
        // this nonce's exact intended IDs / cold-before-build image identities.
        const cleanupController = new AbortController();
        const cleanupTimer = setTimeout(() => cleanupController.abort(), 45_000);
        const cleanupRun = makeDockerRun({}, { timeoutMs: 8_000 });
        const cleanupErrors: string[] = [];
        try {
          for (const id of touched) {
            const result = await destroySandbox(id, { dockerRun: (args, call) => cleanupRun(args, { ...call, signal: cleanupController.signal }) });
            if (teardownIncomplete(result)) cleanupErrors.push(id);
          }
          for (const [tag, key] of coldTags) {
            const inspected = await cleanupRun(["image", "inspect", tag], { signal: cleanupController.signal });
            if (inspected.code !== 0) {
              if (!/no such image/i.test(inspected.stdout + inspected.stderr)) cleanupErrors.push(tag);
              continue;
            }
            const image = JSON.parse(inspected.stdout)[0];
            if (image.Config?.Labels?.[CACHE_LABEL] !== key) { cleanupErrors.push(tag); continue; }
            imageIds.add(image.Id);
            const removed = await cleanupRun(["image", "rm", tag], { signal: cleanupController.signal });
            if (removed.code !== 0) cleanupErrors.push(tag);
          }
          for (const id of imageIds) {
            // A concurrent immutable ID may now be untagged; never image-prune.
            await cleanupRun(["image", "rm", id], { signal: cleanupController.signal });
            const absent = await cleanupRun(["image", "inspect", id], { signal: cleanupController.signal });
            if (absent.code === 0 || !/no such image/i.test(absent.stdout + absent.stderr)) cleanupErrors.push(id);
          }
          await observe({ event: "cleanup", unresolved: cleanupErrors });
          if (!bodyFailed) expect(cleanupErrors).toEqual([]);
          else if (cleanupErrors.length) console.error("cache fixture cleanup unresolved", cleanupErrors.join(","));
        } catch (error) {
          if (!bodyFailed) throw error;
          console.error("cache fixture cleanup observation failed; retain intended IDs and tags");
        } finally {
          clearTimeout(cleanupTimer);
        }
      }
    },300_000);
  }
});
