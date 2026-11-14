/** Real default-clone failures and actual scoped Docker compensation. */
import { expect, it } from "vitest";
import { randomUUID } from "node:crypto";
import { dockerGate } from "./docker-gate.ts";
import { createSandbox, CreateFailure, newSandboxId, VOLUME_PREFIX } from "./create.ts";
import { FALLBACK_BASE_IMAGE } from "./build.ts";
import { makeDockerRun, type DockerRun } from "./docker.ts";
import { runContainer } from "./run.ts";
import { idLabel, SANDBOX_LABEL, listContainersResult } from "./registry.ts";

const realDocker = dockerGate("create-partial-compensation", { linux: true });
// This is loopback INSIDE the pinned alpine/git helper, with no listener at
// port1. It reaches the real default clone failure without a provider, DNS,
// reusable credential, TLS bypass or alternate cloner/build implementation.
const CLOSED_CLONE_URL = "https://127.0.0.1:1/owned-fixture.git";

realDocker("SBX-C03 real partial-create compensation", () => {
  for (const mode of ["clone-failure", "abort-after-volume", "volume-in-use"] as const) {
    it(`preserves exact real resource outcomes and another running box (${mode})`, async () => {
      const run = makeDockerRun({}, { timeoutMs: 10_000 });
      const target = newSandboxId(), survivor = newSandboxId(), blocker = newSandboxId();
      const fixtureLabel = `ca.sandbox.fixture=${randomUUID()}`;
      const ids = [target, survivor, blocker];
      const claimed = new Set<string>();
      const targetVolume = `${VOLUME_PREFIX}-${target}`, survivorVolume = `${VOLUME_PREFIX}-${survivor}`;
      const volumes = new Map<string, string>();
      const controller = new AbortController();
      const calls: Array<{ args: string[]; code: number; signalProvided: boolean }> = [];
      let survivorContainer = "", blockerContainer = "", deadlineFired = false;
      let ordinaryDeadline: ReturnType<typeof setTimeout> | undefined;

      async function assertVolumeAbsent(name: string) {
        const result = await run(["volume", "ls", "-q", "--filter", `name=^${name}$`]);
        expect(result.code, result.stderr).toBe(0);
        expect(result.stdout.trim()).toBe("");
      }
      async function inspectRunning(container: string) {
        const result = await run(["inspect", "--format", "{{.State.Running}}", container]);
        expect(result.code, result.stderr).toBe(0);
        return result.stdout.trim();
      }
      async function startOwnedBox(id: string, volume: string) {
        claimed.add(id); // Scope was verified empty before any creation attempt.
        const container = await runContainer(FALLBACK_BASE_IMAGE, volume, "offline", {
          dockerRun: run, extraLabels: [idLabel(id), fixtureLabel], namePrefix: `ca-sbx-partial-${id}`,
        });
        expect(container).toMatch(/^[a-f0-9]{64}$/);
        const ownership = await run(["inspect", "--format", '{{index .Config.Labels "ca.sandbox.id"}}', container]);
        expect(ownership.code, ownership.stderr).toBe(0);
        expect(ownership.stdout.trim()).toBe(id);
        expect(await inspectRunning(container)).toBe("true");
        return container;
      }
      // Observe every Docker result unchanged; this is not a fake runner. The
      // only injected events are cancellation at a known resource boundary and
      // another exclusively fixture-owned box holding that resource in use.
      const observedRun: DockerRun = async (args, call) => {
        const result = await run(args, call);
        calls.push({ args: [...args], code: result.code, signalProvided: call?.signal !== undefined });
        if (args[0] === "volume" && args[1] === "create" && result.code === 0) {
          expect(result.stdout.trim()).toBe(targetVolume);
          claimed.add(target);
          volumes.set(targetVolume, target);
          if (mode === "volume-in-use") blockerContainer = await startOwnedBox(blocker, targetVolume);
          if (mode === "abort-after-volume") controller.abort();
        }
        return result;
      };

      try {
        for (const id of ids) {
          const prior = await listContainersResult([SANDBOX_LABEL, idLabel(id)], run);
          expect(prior.code, prior.stderr).toBe(0);
          expect(prior.items).toEqual([]);
        }
        await assertVolumeAbsent(targetVolume);
        await assertVolumeAbsent(survivorVolume);
        const created = await run(["volume", "create", "--label", SANDBOX_LABEL, "--label", idLabel(survivor), "--label", fixtureLabel, survivorVolume]);
        expect(created.code, created.stderr).toBe(0);
        expect(created.stdout.trim()).toBe(survivorVolume);
        claimed.add(survivor);
        volumes.set(survivorVolume, survivor);
        survivorContainer = await startOwnedBox(survivor, survivorVolume);
        ordinaryDeadline = setTimeout(() => { deadlineFired = true; controller.abort(); }, 30_000);
        let failure: CreateFailure | undefined;
        try {
          // No cloneRepo/buildImage overrides: run the production default path.
          await createSandbox(CLOSED_CLONE_URL, { id: target, dockerRun: observedRun, signal: controller.signal, extraLabels: [fixtureLabel] });
        } catch (error) {
          expect(error).toBeInstanceOf(CreateFailure);
          failure = error as CreateFailure;
        }
        expect(failure).toBeDefined();
        expect(failure!.message).toMatch(/clone .*failed/i);
        expect(deadlineFired, "the closed-port clone must fail on its own, not at the fixture watchdog").toBe(false);
        expect(failure!.id).toBe(target);
        expect(failure!.volumeName).toBe(targetVolume);
        expect(failure!.cleanup.volume).toBe(targetVolume);
        const removal = calls.filter(c => c.args[0] === "volume" && c.args[1] === "rm" && c.args.at(-1) === targetVolume);
        expect(removal).toHaveLength(1);
        expect(removal[0].signalProvided).toBe(false);
        const targetContainers = await listContainersResult([SANDBOX_LABEL, idLabel(target)], run);
        expect(targetContainers.code, targetContainers.stderr).toBe(0);
        expect(targetContainers.items).toEqual([]);
        const observedVolume = await run(["volume", "ls", "-q", "--filter", `name=^${targetVolume}$`]);
        expect(observedVolume.code, observedVolume.stderr).toBe(0);
        if (mode === "volume-in-use") {
          expect(removal[0].code).not.toBe(0);
          expect(failure!.cleanup.verified).toBe(false);
          expect(failure!.cleanup.failures.join(" ")).toMatch(/volume removal unverified|absence not verified/);
          expect(failure!.message).toMatch(/cleanup unknown/);
          expect(observedVolume.stdout.trim()).toBe(targetVolume);
          expect(await inspectRunning(blockerContainer)).toBe("true");
        } else {
          expect(removal[0].code).toBe(0);
          expect(failure!.cleanup.verified).toBe(true);
          expect(observedVolume.stdout.trim()).toBe("");
        }
        expect(controller.signal.aborted).toBe(mode === "abort-after-volume");
        expect(await inspectRunning(survivorContainer)).toBe("true");
        const survivorStillPresent = await run(["volume", "ls", "-q", "--filter", `name=^${survivorVolume}$`]);
        expect(survivorStillPresent.code, survivorStillPresent.stderr).toBe(0);
        expect(survivorStillPresent.stdout.trim()).toBe(survivorVolume);
      } finally {
        if (ordinaryDeadline) clearTimeout(ordinaryDeadline);
        controller.abort();
        // Exact generated IDs only, plus the fixture marker where supported.
        // Production clone helpers have the generated id but no extra marker.
        // No global prune,
        // no partial failure stdout as targets, and containers before volumes.
        const cleanupFailures: string[] = [];
        for (const id of ids) {
          if (!claimed.has(id)) continue;
          const scope = id === target ? [SANDBOX_LABEL, idLabel(id)] : [SANDBOX_LABEL, idLabel(id), fixtureLabel];
          const listed = await listContainersResult(scope, run);
          if (listed.code !== 0) { cleanupFailures.push(`unavailable owned container scope ${id}`); continue; }
          for (const container of listed.items) {
            if (!/^[a-f0-9]{64}$/.test(container)) { cleanupFailures.push(`invalid owned container identity ${id}`); continue; }
            const result = await run(["rm", "-f", container]);
            if (result.code !== 0) cleanupFailures.push(`owned container removal unverified ${container}`);
          }
          const after = await listContainersResult(scope, run);
          if (after.code !== 0 || after.items.length) cleanupFailures.push(`owned container absence unverified ${id}`);
        }
        for (const [volume, id] of volumes) {
          const listed = await run(["volume", "ls", "-q", "--filter", `name=^${volume}$`]);
          if (listed.code !== 0) { cleanupFailures.push(`unavailable owned volume ${volume}`); continue; }
          if (!listed.stdout.trim()) continue;
          const label = await run(["volume", "inspect", "--format", '{{index .Labels "ca.sandbox.id"}}', volume]);
          if (listed.stdout.trim() !== volume || label.code !== 0 || label.stdout.trim() !== id) { cleanupFailures.push(`owned volume identity unverified ${volume}`); continue; }
          const removed = await run(["volume", "rm", "-f", volume]);
          if (removed.code !== 0) cleanupFailures.push(`owned volume removal unverified ${volume}`);
          const after = await run(["volume", "ls", "-q", "--filter", `name=^${volume}$`]);
          if (after.code !== 0 || after.stdout.trim()) cleanupFailures.push(`owned volume absence unverified ${volume}`);
        }
        expect(cleanupFailures, "retain these exact fixture resource references for inspection").toEqual([]);
      }
    }, 180_000);
  }
});
