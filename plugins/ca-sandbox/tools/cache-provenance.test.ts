import { it, expect } from "vitest";
import { randomBytes } from "node:crypto";
import { dockerGate } from "./docker-gate.ts";
import { defaultDockerRun } from "./docker.ts";
import { defaultBuildDeps, defaultEnsureNixpacks, CACHE_LABEL } from "./build.ts";
import { createSandbox, CLONE_IMAGE } from "./create.ts";
import { destroySandbox, teardownIncomplete } from "./destroy.ts";

const d = dockerGate("cache-provenance");
d("SBX-C01 real two-create cache provenance", () => {
  for (const builder of ["dockerfile-fallback", "nixpacks"] as const) {
    it(`${builder}: distinct staging names reuse the exact labeled image and preserve another box`, async () => {
      const installed=await defaultEnsureNixpacks();
      if(builder==="nixpacks" && !installed.available) {
        throw new Error("SBX-C01 required Nixpacks qualification unavailable: install a reviewed pinned builder in the hosted qualification environment; no driver auto-install");
      }
      const suffix=randomBytes(8).toString("hex");
      const ids=[`cache-a-${suffix}`,`cache-b-${suffix}`];
      const images=new Set<string>();
      const deps=defaultBuildDeps();
      const actualBuild=deps.runBuild;
      let builds=0;
      deps.ensureNixpacks=async()=>builder==="nixpacks"?installed:{available:false};
      deps.runBuild=async(tag,context)=>{builds++;return actualBuild(tag,context);};
      // Seed a real repository on each named volume. No external provider or
      // account is contacted; default create staging/build/run still execute.
      const cloneRepo=async(_url:string,volume:string)=> {
        const result=await defaultDockerRun(["run","--rm","--entrypoint","sh","--mount",`type=volume,source=${volume},target=/work/repo`,CLONE_IMAGE,"-c",
          `cd /work/repo && git init -q && git config user.email fixture@example.invalid && git config user.name Fixture && printf '%s' '{"name":"cache-${suffix}","version":"1.0.0","scripts":{}}' > package.json && git add package.json && git commit -qm fixture && chown -R 1000:1000 /work/repo`]);
        return {code:result.code,stderr:result.stderr};
      };
      try {
        const first=await createSandbox("https://example.invalid/fixture",{id:ids[0],cloneRepo,buildDeps:deps});
        images.add(first.image);
        expect(builds).toBe(1);
        const second=await createSandbox("https://example.invalid/fixture",{id:ids[1],cloneRepo,buildDeps:deps});
        images.add(second.image);
        expect(second.image).toBe(first.image);
        expect(builds).toBe(1);
        const inspected=await defaultDockerRun(["image","inspect",first.image]);
        expect(inspected.code).toBe(0);
        const image=JSON.parse(inspected.stdout)[0];
        expect(image.Id).toMatch(/^sha256:[a-f0-9]{64}$/);
        expect(image.Config.Labels[CACHE_LABEL]).toBe(first.image.split(":v2-")[1]);
        const removed=await destroySandbox(ids[0]);
        expect(teardownIncomplete(removed)).toBe(false);
        const survivor=await defaultDockerRun(["inspect","--format","{{.State.Running}}",second.containerId]);
        expect(survivor.code).toBe(0);expect(survivor.stdout.trim()).toBe("true");
      } finally {
        for(const id of ids) {
          const cleanup=await destroySandbox(id);
          expect(teardownIncomplete(cleanup)).toBe(false);
        }
        for(const image of images) await defaultDockerRun(["image","rm",image]);
      }
    },300_000);
  }
});
