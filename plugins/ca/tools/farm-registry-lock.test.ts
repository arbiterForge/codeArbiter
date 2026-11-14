import { afterEach, describe, expect, it } from "vitest";
import { spawn, execFileSync, type ChildProcess } from "node:child_process";
import { mkdtemp, mkdir, writeFile, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createInterface } from "node:readline";
import { treeKill } from "./exec.ts";
import { withWorktreeLock, prepareWorktree, removeWorktreeVerified, allowedWorktreeRoot, _resetAllowedWorktreeRoot } from "./farm.ts";

const tools = dirname(fileURLToPath(import.meta.url));
const tsx = import.meta.resolve("tsx");
const LOCK = "codearbiter-farm-worktrees.lock";
const roots: string[] = [];
const children: ChildProcess[] = [];
const childCode = `
import { pathToFileURL } from 'node:url';
import { existsSync } from 'node:fs';
import { writeFile, unlink } from 'node:fs/promises';
import { join } from 'node:path';
const [modulePath,role,marker,lock] = process.argv.slice(1);
process.argv[1]='farm-registry-owned-driver';
const {withWorktreeLock}=await import(pathToFileURL(modulePath).href);
let waiting=false;
const options={timeoutMs:role==='stale'?60:5000,onContention:()=>{if(!waiting){waiting=true;console.log('contended');}}};
try {
  await withWorktreeLock(async()=>{
    if(role==='first') {
      await writeFile(marker,'held'); console.log('held');
      await new Promise(resolve=>process.stdin.once('data',resolve));
      await unlink(marker);
    } else if(role==='second') console.log(existsSync(marker)?'overlap':'entered');
    else if(role==='replace') {await unlink(lock);await writeFile(lock,'foreign-owned-fixture');}
    else if(role==='throw') throw new Error('controlled-primary');
    else console.log('executed');
  },options);
  console.log('settled');
} catch(error) {console.log(role==='throw'&&error.message==='controlled-primary'?'primary-preserved':'refused');}
if(role==='throw') await withWorktreeLock(async()=>console.log('again'),options);
`;

async function fixture() {
  const root = await mkdtemp(join(tmpdir(), "farm-registry-owned-")); roots.push(root);
  const repo = join(root,"repo"), home=join(root,"home"), scratch=join(root,"temp");
  await Promise.all([mkdir(repo),mkdir(home),mkdir(scratch)]);
  const env: NodeJS.ProcessEnv = {};
  for (const [key,value] of Object.entries(process.env))
    if (["PATH","SYSTEMROOT","WINDIR","COMSPEC","PATHEXT","SYSTEMDRIVE"].includes(key.toUpperCase())) env[key]=value;
  Object.assign(env,{HOME:home,USERPROFILE:home,TEMP:scratch,TMP:scratch,GIT_CONFIG_NOSYSTEM:"1",GIT_CONFIG_GLOBAL:process.platform==="win32"?"NUL":"/dev/null"});
  const git=(...args:string[])=>execFileSync("git",args,{cwd:repo,env,encoding:"utf8",stdio:["ignore","pipe","pipe"]}).trim();
  git("init","-q","-b","main");git("config","core.autocrlf","false");
  git("config","user.name","Fixture");git("config","user.email","fixture@example.invalid");
  await writeFile(join(repo,"base.txt"),"base\n");git("add",".");git("-c","core.hooksPath=", "commit","-qm","fixture");
  const linked=join(root,"linked");git("worktree","add","--detach",linked,"HEAD");
  return {root,repo,linked,env,marker:join(root,"held"),lock:join(repo,".git",LOCK)};
}

function launch(kind:"source"|"bundle",role:string,cwd:string,env:NodeJS.ProcessEnv,marker:string,lock:string) {
  const argv=[...(kind==="source"?["--import",tsx]:[]),"--input-type=module","-e",childCode,join(tools,kind==="source"?"farm.ts":"farm.js"),role,marker,lock];
  const child=spawn(process.execPath,argv,{cwd,env,stdio:["pipe","pipe","pipe"]}); children.push(child);
  const lines:string[]=[];let stderr="";
  const readers=new Set<()=>void>();
  createInterface({input:child.stdout!}).on("line",line=>{lines.push(line);for(const notify of readers)notify();});
  child.stderr!.on("data",data=>{stderr+=data.toString();});
  const exit=new Promise<number|null>(resolve=>child.on("exit",resolve));
  return {child,lines,exit,wait:async(names:string[])=>new Promise<string>((resolve,reject)=>{
    const check=()=>{const match=lines.find(line=>names.includes(line));if(match){clearTimeout(timer);readers.delete(check);resolve(match);}};
    const timer=setTimeout(()=>{readers.delete(check);reject(new Error(`owned child did not reach barrier: ${lines.join(",")} ${stderr.slice(-500)}`));},8000);
    readers.add(check);check();
  })};
}

afterEach(async()=>{
  for(const child of children.splice(0)) {
    if(child.stdin?.writable)child.stdin.end("release");
    if(child.exitCode===null)await treeKill(child);
  }
  for(const root of roots.splice(0))await rm(root,{recursive:true,force:true});
});

describe("cross-process Farm worktree administration",()=>{
  it("source: unknown common directory, foreign ownership and failed release refuse conservatively",async()=>{
    const f=await fixture(), original=process.cwd();
    try {
      process.chdir(f.root);let called=false;
      await expect(withWorktreeLock(async()=>{called=true;})).rejects.toThrow(/common directory unavailable/);
      expect(called).toBe(false);
      const fakeGit=async()=>{called=true;return {code:0,out:"",stdout:"",stderr:""};};
      _resetAllowedWorktreeRoot();
      expect(await prepareWorktree("farm/no-admin",join(allowedWorktreeRoot(),"no-admin"),"HEAD",fakeGit)).toMatch(/administration unavailable/);
      const cleanup=await removeWorktreeVerified(fakeGit,join(f.root,"unused"),{attempts:1,delayMs:0});
      expect(cleanup.ok).toBe(false);expect(cleanup.attempts).toBe(0);
      expect(cleanup.detail).toMatch(/administration unavailable/);expect(called).toBe(false);
      process.chdir(f.repo);
      await writeFile(f.lock,"foreign-owned-fixture");
      await expect(withWorktreeLock(async()=>{called=true;},{timeoutMs:0})).rejects.toThrow(/retained lock/);
      expect(called).toBe(false);expect(await readFile(f.lock,"utf8")).toBe("foreign-owned-fixture");
      await rm(f.lock);
      await expect(withWorktreeLock(async()=>{}, {timeoutMs:NaN})).rejects.toThrow(/invalid worktree lock deadline/);
      await expect(withWorktreeLock(async()=>{await rm(f.lock);await writeFile(f.lock,"foreign-owned-fixture");})).rejects.toThrow(/release unverified/);
      expect(await readFile(f.lock,"utf8")).toBe("foreign-owned-fixture");await rm(f.lock);
      await expect(withWorktreeLock(async()=>{
        await rm(f.lock);await writeFile(f.lock,"foreign-owned-fixture");throw new Error("controlled-primary");
      })).rejects.toThrow("controlled-primary");
      expect(await readFile(f.lock,"utf8")).toBe("foreign-owned-fixture");await rm(f.lock);
      await expect(withWorktreeLock(async()=>"released")).resolves.toBe("released");
    } finally { process.chdir(original); _resetAllowedWorktreeRoot(); }
  });
  for(const kind of ["source","bundle"] as const) {
    it(`${kind}: linked checkouts cannot overlap the shared administration boundary`,async()=>{
      const f=await fixture();
      const first=launch(kind,"first",f.repo,f.env,f.marker,f.lock);
      await first.wait(["held"]);
      const second=launch(kind,"second",f.linked,f.env,f.marker,f.lock);
      const observed=await second.wait(["contended","overlap","entered","refused"]);
      expect(observed,"second process must observe real sidecar contention before entering Git administration").toBe("contended");
      expect(await readFile(f.marker,"utf8")).toBe("held");
      expect(second.lines).not.toContain("entered");
      first.child.stdin!.end("release");
      await first.wait(["settled"]);await second.wait(["entered"]);await second.wait(["settled"]);
      expect(await Promise.all([first.exit,second.exit])).toEqual([0,0]);
    },20000);

    it(`${kind}: a foreign lock refuses without running the callback or changing bytes`,async()=>{
      const f=await fixture();await writeFile(f.lock,"foreign-owned-fixture");
      const child=launch(kind,"stale",f.repo,f.env,f.marker,f.lock);
      expect(await child.wait(["refused","executed"])).toBe("refused");
      expect(await readFile(f.lock,"utf8")).toBe("foreign-owned-fixture");
      expect(await child.exit).toBe(0);
    },15000);

    it(`${kind}: replacement ownership is retained and primary errors release the owned lock`,async()=>{
      const f=await fixture();
      const replaced=launch(kind,"replace",f.repo,f.env,f.marker,f.lock);
      expect(await replaced.wait(["refused","settled"])).toBe("refused");
      expect(await readFile(f.lock,"utf8")).toBe("foreign-owned-fixture");
      expect(await replaced.exit).toBe(0);
      await rm(f.lock); // only this fixture's explicit foreign sentinel
      const thrown=launch(kind,"throw",f.repo,f.env,f.marker,f.lock);
      await thrown.wait(["primary-preserved"]);await thrown.wait(["again"]);
      expect(await thrown.exit).toBe(0);
    },15000);
  }
});
