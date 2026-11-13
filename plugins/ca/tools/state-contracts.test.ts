import { it, expect } from "vitest";
import { mkdtemp, mkdir, writeFile, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { checkDrift, runTask, runGate } from "./farm.ts";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { createRunDirectory, refIdentity, repositoryIdentity, writeEffect, recoverReceipt, type FarmEffect } from "./farm-recovery.ts";
import type { RunTaskDeps, Task } from "./farm.ts";

it("FARM-R03 refuses unknown Git drift instead of inventing a clean observation", async () => {
  const probe = async () => ({ code: 128, out: "unavailable", stdout: "", stderr: "unavailable" });
  await expect(checkDrift("unused", new Set(), probe)).rejects.toThrow(/drift.*unavailable/i);
});

it("FARM-R02 preserves failed containment and admits no reset or second author", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "farm-contained-"));
  let authors = 0;
  let resets = 0;
  let mutations = 0;
  const t: Task = { id: "contained", description: "fixture", filesInScope: ["src/a.ts"],
    test: { path: "test.ts" }, gate: { commands: ["test"] }, maxRetries: 2 };
  const deps: RunTaskDeps = {
    worker: { apply: async () => { authors++; return { ok: true, filesWritten: ["src/a.ts"] }; } },
    prepareWorktree: async () => null, resetWorktree: async () => { resets++; },
    fileHash: async () => null, checkDrift: async () => [],
    runGate: async () => ({ ok: false, failed: "test", tail: "descendant remains", cleanupFailed: true, timedOut:true,commandCode:125,processId:123 }),
    antiGamingCheck: async () => ({ risk: "none" }), mutationCheck: async () => null,
    git: async () => { mutations++; return { code: 0, out: "", stdout: "", stderr: "" }; },
    withMergeLock: async fn => fn(),
  };
  try {
    const result = await runTask(t, "fixture", "https://example.invalid", "", deps);
    expect(result.status).toBe("escalate");
    expect(result.note).toMatch(/containment/i);
    expect(result.gateOutcome).toMatchObject({commandCode:125,interrupt:"timeout",containment:"unknown",processId:123});
    expect(authors).toBe(1);
    expect(resets).toBe(0);
    expect(mutations).toBe(0);
  } finally { await rm(root, { recursive: true, force: true }); }
});

it("FARM-R01 exclusive identities preserve evidence under a same-ID race", async () => {
  const root=await mkdtemp(path.join(tmpdir(),"farm-claim-"));
  try {
    const claims=await Promise.allSettled([createRunDirectory(root,"same-run"),createRunDirectory(root,"same-run")]);
    expect(claims.filter(r=>r.status==="fulfilled")).toHaveLength(1);
    const evidence=path.join(root,"runs","same-run","farm-results.jsonl");
    await writeFile(evidence,"preserved\n");
    await expect(createRunDirectory(root,"same-run")).rejects.toThrow(/already exists/);
    expect(await readFile(evidence,"utf8")).toBe("preserved\n");
  } finally {await rm(root,{recursive:true,force:true});}
});

it("FARM-R01 reconciles a post-merge crash in real Git without changing a ref or calling an author", async () => {
  const root=await mkdtemp(path.join(tmpdir(),"farm-receipt-"));
  const execute=promisify(execFile);
  const calls:string[][]=[];
  const git=async(args:string[])=>{
    calls.push(args);
    try {const r=await execute("git",args,{cwd:root});return {code:0,stdout:r.stdout};}
    catch {return {code:1,stdout:""};}
  };
  try {
    await git(["init","-b","main"]);await git(["config","user.email","fixture@example.invalid"]);await git(["config","user.name","Fixture"]);
    await writeFile(path.join(root,"base"),"base");await git(["add","base"]);await git(["commit","-m","base"]);
    await git(["branch","farm/integration"]);await git(["checkout","-b","farm/task"]);
    await writeFile(path.join(root,"change"),"change");await git(["add","change"]);await git(["commit","-m","task"]);
    const candidate=(await refIdentity(git,"farm/task"))!;
    await git(["checkout","farm/integration"]);
    const before=(await refIdentity(git,"HEAD"))!;
    const dir=await createRunDirectory(path.join(root,"receipts"),"run-one");
    const effect:FarmEffect={schema:1,runId:"run-one",taskId:"task",repository:await repositoryIdentity(git),branch:"farm/task",integration:"farm/integration",worktree:root,attempt:1,stage:"merge-pending",candidate,integrationBefore:before};
    await writeEffect(dir,effect);
    await git(["merge","--no-ff","farm/task","-m","integrated"]);
    const after=(await refIdentity(git,"HEAD"))!;
    calls.length=0;
    const receipt=await recoverReceipt(dir,"run-one",git);
    expect(receipt.results).toMatchObject([{merge:"observed",status:"unknown",cleanup:"unknown",author:"not-invoked"}]);
    expect(calls.every(c=>["rev-parse","show"].includes(c[0]))).toBe(true);
    expect(await refIdentity(git,"HEAD")).toEqual(after);
    effect.stage="settled";effect.integrationAfter=after;effect.runCleanup={verified:true,failures:[]};effect.result={status:"green"};await writeEffect(dir,effect);
    const receipts=await Promise.all([recoverReceipt(dir,"run-one",git),recoverReceipt(dir,"run-one",git)]);
    expect(receipts.every(r=>(r.results as {status:string}[])[0].status==="green")).toBe(true);
    effect.runCleanup={verified:false,failures:[{target:"retained-integration",detail:"unavailable"}]};await writeEffect(dir,effect);
    expect((await recoverReceipt(dir,"run-one",git)).results).toMatchObject([{status:"unknown",cleanup:"unknown"}]);
    effect.runCleanup={verified:true,failures:[]};await writeEffect(dir,effect);
    await writeFile(path.join(root,"later"),"later");await git(["add","later"]);await git(["commit","-m","later"]);
    expect((await recoverReceipt(dir,"run-one",git)).results).toMatchObject([{status:"unknown",merge:"unknown"}]);
    effect.schema=2 as 1;await writeEffect(dir,effect);
    await expect(recoverReceipt(dir,"run-one",git)).rejects.toThrow(/incompatible/);
  } finally {await rm(root,{recursive:true,force:true});}
},30_000); // Real Git subprocess matrix; bounded separately from in-process unit checks.

it("FARM-R03 bounded read-only retry accepts only a successful current observation", async () => {
  let calls=0;
  const git=async()=>({code:++calls===1?128:0,out:"",stdout:"",stderr:""});
  expect(await checkDrift("unused",new Set(),git)).toEqual([]);
  expect(calls).toBe(4);
  const malformed=async(args:string[])=>({code:0,out:"",stdout:args[0]==="ls-files"?"partial-path":"",stderr:""});
  await expect(checkDrift("unused",new Set(),malformed)).rejects.toThrow(/unavailable/);
});

it("FARM-R02 gate retains executor outcome instead of flattening code 125 into test failure", async () => {
  const gate=await runGate("unused",["fixture"],async()=>({code:125,out:"cleanup unavailable",stdout:"",stderr:"",timedOut:true,cleanupFailed:true,processId:321}));
  expect(gate).toMatchObject({ok:false,commandCode:125,timedOut:true,cleanupFailed:true,processId:321});
});

it("FARM-R02 uncontained sample setup retains scratch resources without authoring or reset",async()=>{
  const priorSamples=process.env.FARM_SAMPLES,priorTemperature=process.env.FARM_TEMPERATURE;
  process.env.FARM_SAMPLES="2";process.env.FARM_TEMPERATURE="0";
  let authors=0,resets=0,mutations=0;
  const task:Task={id:"setup-contained",description:"fixture",filesInScope:["a.ts"],test:{path:"test.ts"},setup:["setup"],gate:{commands:["gate"]},maxRetries:2};
  const deps:RunTaskDeps={worker:{apply:async()=>{authors++;return {ok:true,filesWritten:[]};}},prepareWorktree:async()=>null,
    resetWorktree:async()=>{resets++;},fileHash:async()=>null,checkDrift:async()=>[],
    runGate:async cwd=>cwd.includes("__s")?{ok:false,failed:"setup",tail:"descendants unknown",cleanupFailed:true,timedOut:true,commandCode:125,processId:456}:{ok:true},
    antiGamingCheck:async()=>({risk:"none"}),mutationCheck:async()=>null,withMergeLock:async fn=>fn(),
    git:async()=>{mutations++;return {code:0,out:"",stdout:"",stderr:""};}};
  try {
    const result=await runTask(task,"fixture","https://example.invalid","",deps);
    expect(result).toMatchObject({status:"escalate",containment:"unknown",gateOutcome:{commandCode:125,processId:456,containment:"unknown"}});
    expect(authors).toBe(0);expect(resets).toBe(0);expect(mutations).toBe(0);
    expect(result.cleanup).toHaveLength(2);
  } finally {
    if(priorSamples===undefined)delete process.env.FARM_SAMPLES;else process.env.FARM_SAMPLES=priorSamples;
    if(priorTemperature===undefined)delete process.env.FARM_TEMPERATURE;else process.env.FARM_TEMPERATURE=priorTemperature;
  }
});
