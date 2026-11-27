import { mkdtemp, mkdir, writeFile, rm, symlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { it, expect } from "vitest";
import { execInSandbox } from "./exec.ts";
import type { DockerRun, RunResult } from "./docker.ts";
import { ordinaryNetworkCapability, buildRunArgs } from "./run.ts";
import { destroySandbox, formatTeardownDiagnostic, teardownIncomplete } from "./destroy.ts";
import { runClaudeInside } from "./claude-inside.ts";
import { createSandbox, CreateFailure, readManifests } from "./create.ts";
import { findSandbox, listSandboxes } from "./registry.ts";
import { buildOrReuseImage, buildCapabilities, defaultEnsureNixpacks, type BuildDeps } from "./build.ts";

it("SBX-C01 equal inputs in different checkout basenames select a verified stable key", async () => {
  const deps: BuildDeps = { imageInspect: async () => 0,
    imageIdentity: async tag => ({ id: `sha256:${"a".repeat(64)}`, cacheKey: tag.split(":v2-")[1] }),
    targetPlatform: async () => "linux/amd64", runBuild: async () => { throw new Error("unexpected build"); },
    ensureNixpacks: async () => ({ available: true, version: "1.40.0" }), nixpacksVersion: async () => "1.40.0" };
  const a = await buildOrReuseImage("/tmp/checkout-one", "manifest-key", deps);
  const b = await buildOrReuseImage("/tmp/checkout-two", "manifest-key", deps);
  expect(a.tag).toBe(b.tag);
  expect(a.reused && b.reused).toBe(true);
});

it("SBX-C01 existence alone is a cache miss and toolchain identity changes the tag", async () => {
  let builds = 0;
  const deps: BuildDeps = { imageInspect: async () => 0, targetPlatform: async () => "linux/amd64",
    runBuild: async () => { builds++; return { code: 0, out: "" }; },
    ensureNixpacks: async () => ({ available: true, version: "1.40.0" }), nixpacksVersion: async () => "1.40.0" };
  const a = await buildOrReuseImage("/tmp/repo", "manifest-key", deps);
  const b = await buildOrReuseImage("/tmp/repo", "manifest-key", { ...deps,
    ensureNixpacks: async () => ({ available: true, version: "1.41.0" }) });
  expect(builds).toBe(2);
  expect(a.tag).not.toBe(b.tag);
});

it("SBX-C02 treats overflow as lost observation and verifies target containment", async () => {
  const calls: string[][] = [];
  const dockerRun: DockerRun = async args => {
    calls.push(args);
    if (args[0] === "exec") return { code: 1, stdout: "overflow", stderr: "", overflowed: true };
    if (args[0] === "inspect") return { code: 0, stdout: "false\n", stderr: "" };
    return { code: 0, stdout: "", stderr: "" };
  };
  const r = await execInSandbox("owned-target", ["work"], { dockerRun });
  expect(calls.some(c => c[0] === "stop" && c.at(-1) === "owned-target")).toBe(true);
  expect(calls.some(c => c[0] === "inspect" && c.at(-1) === "owned-target")).toBe(true);
  expect(r).toMatchObject({ overflowed: true, containment: "verified-stopped" });
});

async function verifyTeardownReobservation(reason: "overflow" | "abort"): Promise<void> {
  const id = "selected";
  const container = "selected-container";
  const volume = "selected-volume";
  const filters = ["--filter", "label=ca.sandbox=1", "--filter", "label=ca.sandbox.id=selected"];
  const ps = ["ps", "-a", "-q", "--no-trunc", ...filters];
  const volumes = ["volume", "ls", "-q", ...filters];
  const scope = "label=ca.sandbox=1 label=ca.sandbox.id=selected";
  const controller = new AbortController();
  const aborting = reason === "abort";
  const failure = aborting ? {aborted: true} : {overflowed: true};
  const exitCode = aborting ? 130 : 1;
  const output = "output-".repeat(20);
  const result = (code: number, stdout = "", stderr = ""): RunResult => ({code, stdout, stderr});
  const commands: [string[], RunResult][] = [
    [["exec", container, "fixture-command"], {...result(exitCode, output, "command failed"), ...failure}],
    [["stop", "--time", "0", container], result(41, "", "stop denied")],
    [["inspect", "--format", "{{.State.Running}}", container], result(42, "false\n", "inspect failed")],
    [ps, result(0, container + "\n")],
    [volumes, result(0, volume + "\n")],
    [["rm", "-f", container], result(43, "", "remove denied")],
    [["volume", "rm", "-f", volume], result(44, "", "volume in use")],
    [ps, result(45, "unrelated-container\n", "container observation failed")],
    [volumes, result(46, "unrelated-volume\n", "volume observation failed")],
    [ps, result(0, container + "\n")],
    [volumes, result(47, "unrelated-volume\n", "target observation still failed")],
    [ps, result(0, container + "\n")],
    [volumes, result(0, volume + "\n")],
  ];
  let next = 0;
  const dockerRun: DockerRun = async (args, options) => {
    const index = next++;
    const expected = commands[index];
    if (!expected) throw new Error("unexpected Docker command: " + args.join(" "));
    expect(args).toEqual(expected[0]);
    expect(options?.signal).toBe(index === 0 ? controller.signal : undefined);
    if (index === 0 && aborting) controller.abort();
    return expected[1];
  };

  const failed = await execInSandbox(container, ["fixture-command"], {
    dockerRun, signal: controller.signal, maxBytes: 96,
  });
  expect(failed).toMatchObject({
    id: container, exitCode, ...failure, truncated: true, containment: "unknown",
  });
  expect(failed.stdout).toBe(output.slice(0, 96));
  expect(failed.stderr).toContain("command failed");
  expect(failed).not.toHaveProperty("timedOut");
  expect(failed).not.toHaveProperty(aborting ? "overflowed" : "aborted");

  const cleanup = await destroySandbox(id, {dockerRun});
  expect(teardownIncomplete(cleanup)).toBe(true);
  expect(cleanup).toMatchObject({
    id, removedContainers: [], removedVolumes: [], remainingContainers: [], remainingVolumes: [], failureCount: 4,
    failures: [
      {op: "remove-container", ref: container, code: 43},
      {op: "remove-volume", ref: volume, code: 44},
      {op: "list-containers", ref: scope, code: 45},
      {op: "list-volumes", ref: scope, code: 46},
    ],
  });
  await expect(findSandbox(id, dockerRun)).rejects.toThrow(/volume observation unavailable \(exit 47\)/);
  await expect(findSandbox(id, dockerRun)).resolves.toEqual({id, containers: [container], volumes: [volume]});
  expect(next).toBe(commands.length);

  const diagnostic = formatTeardownDiagnostic("destroy", cleanup);
  expect(diagnostic).toContain("teardown INCOMPLETE");
  expect(diagnostic).not.toContain("0 container(s) and 0 volume(s) still present");
  expect(diagnostic).toContain("Resource observation was incomplete.");
}

it("SEQ-20 overflow preserves failure and re-observes only the surviving target", async () => {
  await verifyTeardownReobservation("overflow");
});

it("SEQ-20 abort preserves failure and re-observes only the surviving target", async () => {
  await verifyTeardownReobservation("abort");
});

it("SBX-C03 reports failed resource observations as unavailable, not empty", async () => {
  const dockerRun: DockerRun = async () => ({ code: 1, stdout: "", stderr: "denied" });
  await expect(listSandboxes(dockerRun)).rejects.toThrow(/unavailable/i);
});

it("SBX-C03 cancellation cannot cancel compensation and unknown cleanup retains exact references", async () => {
  const controller = new AbortController();
  const calls: {args:string[]; signal?:AbortSignal}[] = [];
  const dockerRun: DockerRun = async (args, call) => {
    calls.push({args, signal:call?.signal});
    if (args[0] === "volume" && args[1] === "create") return {code:0,stdout:"owned-volume",stderr:""};
    if (args[0] === "ps") return {code:1,stdout:"",stderr:"daemon unavailable"};
    return {code:1,stdout:"",stderr:"denied"};
  };
  let failure: unknown;
  try { await createSandbox("https://example.invalid/repo", { id:"owned", dockerRun, signal:controller.signal,
    cloneRepo:async()=>{controller.abort(); throw new Error("cancelled clone");} }); }
  catch (error) { failure=error; }
  expect(failure).toBeInstanceOf(CreateFailure);
  expect(failure).toMatchObject({id:"owned",volumeName:"ca-sbx-vol-owned",cleanup:{verified:false}});
  expect(calls.filter(c=>c.args[0]==="ps" || c.args.includes("rm")).every(c=>!c.signal)).toBe(true);
});

it("SBX-D01 builder capability permits Node/Python fallback and refuses unsupported stacks", () => {
  expect(buildCapabilities({node:true,python:false},false)).toMatchObject({supported:true,builder:"dockerfile-fallback"});
  expect(buildCapabilities({node:false,python:true},false)).toMatchObject({supported:true,builder:"dockerfile-fallback"});
  expect(buildCapabilities({node:false,python:false},false)).toMatchObject({supported:false});
  expect(buildCapabilities({node:false,python:false},true)).toMatchObject({supported:true,builder:"nixpacks"});
});
it("SBX-D03 requested ordinary allowlist is unavailable and the real argv stays offline", () => {
  expect(ordinaryNetworkCapability("allowlist")).toEqual({requested:"allowlist",effective:"offline",available:false});
  expect(ordinaryNetworkCapability("offline")).toEqual({requested:"offline",effective:"offline",available:true});
  const args=buildRunArgs("image","volume","allowlist");
  expect(args.slice(args.indexOf("--network"),args.indexOf("--network")+2)).toEqual(["--network","none"]);
  expect(args).not.toContain("--privileged");expect(args).not.toContain("NET_ADMIN");
});

it("SBX-C03 cancelled firewall setup keeps exact cleanup live and never invents destruction", async () => {
  const controller=new AbortController();
  const calls:{args:string[];signal?:AbortSignal}[]=[];
  const dockerRun:DockerRun=async(args,call)=>{
    calls.push({args,signal:call?.signal});
    if(args[0]==="run") return {code:0,stdout:"token-container\n",stderr:""};
    if(args[0]==="exec") {controller.abort();return {code:130,stdout:"",stderr:"cancelled",aborted:true};}
    return {code:1,stdout:"",stderr:"daemon unavailable"};
  };
  const failed=runClaudeInside({image:"fixture",homeVolume:"fixture-home",token:"DUMMY-TOKEN",netPolicy:"anthropic-only"},dockerRun,{signal:controller.signal});
  await expect(failed).rejects.toThrow(/cleanup unknown.*token-container/s);
  await expect(failed).rejects.toMatchObject({containerId:"token-container",commandCode:130,cleanup:{containment:"unknown",removeCode:1,observationCode:1}});
  expect(calls.filter(c=>["rm","ps"].includes(c.args[0])).every(c=>!c.signal)).toBe(true);
});
it("SBX-C01 malformed builder observation blocks reuse and invalid provenance forces rebuild", async () => {
  let builds=0;
  const deps:BuildDeps={imageInspect:async()=>0,imageIdentity:async()=>({id:"sha256:short",cacheKey:"forged"}),
    targetPlatform:async()=>"linux/amd64",ensureNixpacks:async()=>({available:true,version:"1.40.0"}),nixpacksVersion:async()=>"1.40.0",
    runBuild:async()=>{builds++;return {code:0,out:""};}};
  const initial=await buildOrReuseImage("/tmp/a","manifest",deps);
  const arm=await buildOrReuseImage("/tmp/a","manifest",{...deps,targetPlatform:async()=>"linux/arm64"});
  expect(initial.tag).not.toBe(arm.tag);expect(builds).toBe(2);
  await expect(buildOrReuseImage("/tmp/a","manifest",{...deps,ensureNixpacks:async()=>({available:true,version:"unavailable"})})).rejects.toThrow(/malformed/);
  expect(builds).toBe(2);
});

it("SBX-C01 real probe output cannot launder malformed version prose into a cache identity", async () => {
  const installed=await defaultEnsureNixpacks(async()=>({code:0,stdout:"garbage 1.40.0 unexpected",stderr:"",out:""}));
  let effects=0;
  const deps:BuildDeps={imageInspect:async()=>{effects++;return 0;},targetPlatform:async()=>"linux/amd64",
    imageIdentity:async()=>null,runBuild:async()=>{effects++;return {code:0,out:""};},
    ensureNixpacks:async()=>installed,nixpacksVersion:async()=>"ignored"};
  await expect(buildOrReuseImage("unused","manifest",deps)).rejects.toThrow(/malformed/);
  expect(effects).toBe(0);
});
it("SBX-C01 create uses the observed immutable image despite a mutable cache tag", async () => {
  const imageId=`sha256:${"a".repeat(64)}`;
  let runArgs:string[]=[];
  const result=await createSandbox("https://example.invalid/repo",{id:"image-pin",cloneRepo:async()=>0,
    buildImage:async()=>({tag:"ca-sbx:v2-fixture",imageId,reused:true,built:false,builder:"nixpacks",notes:[]}),
    dockerRun:async(args)=>{if(args[0]==="run")runArgs=args;return {code:0,stdout:args[0]==="run"?"owned-container":"",stderr:""};}});
  expect(runArgs).toContain(imageId);expect(runArgs).not.toContain("ca-sbx:v2-fixture");
  expect(result).toMatchObject({imageId,network:{requested:"offline",effective:"offline",available:true}});
});

it("SBX-C03 partial failure stdout cannot authorize destruction of an unobserved target", async () => {
  const calls:string[][]=[];
  const result=await destroySandbox("owned",{dockerRun:async args=>{
    calls.push(args);
    if(args[0]==="ps")return {code:1,stdout:"foreign-container\n",stderr:"partial observation unavailable"};
    return {code:0,stdout:"",stderr:""};
  }});
  expect(result.failureCount).toBeGreaterThan(0);
  expect(calls.some(c=>c[0]==="rm")).toBe(false);
  expect(result.removedContainers).toEqual([]);
});

it("SBX-C01 manifest observation distinguishes absent inputs, valid bytes and unreadable declared inputs",async()=>{
  const root=await mkdtemp(path.join(tmpdir(),"sandbox-manifest-observation-"));
  try {
    expect(await readManifests(root,path)).toEqual([]);
    await writeFile(path.join(root,"package.json"),"{\"name\":\"fixture\"}");
    const valid=await readManifests(root,path);
    expect(valid.map(input=>({path:input.path,bytes:Buffer.from(input.bytes).toString("utf8")}))).toEqual([{path:"package.json",bytes:"{\"name\":\"fixture\"}"}]);
    // The old implementation reads this directory, catches EISDIR/EPERM and
    // silently hashes the same input set as the absent .dockerignore case.
    await mkdir(path.join(root,".dockerignore"));
    await expect(readManifests(root,path)).rejects.toThrow(/manifest.*unavailable.*\.dockerignore/i);
  } finally {await rm(root,{recursive:true,force:true});}
});
it("SBX-C01 dangling declared configuration is unavailable rather than a missing input",async()=>{
  const root=await mkdtemp(path.join(tmpdir(),"sandbox-manifest-link-"));
  try {
    // Junction creation does not need symlink privilege on Windows. Either
    // platform's dangling link remains a present, unsafe declared input.
    await symlink(path.join(root,"missing-target"),path.join(root,"nixpacks.toml"),"junction");
    await expect(readManifests(root,path)).rejects.toThrow(/manifest.*unavailable.*nixpacks\.toml/i);
  } finally {await rm(root,{recursive:true,force:true});}
});
