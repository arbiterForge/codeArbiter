/** Farm effect receipts. Recovery observes exact Git identities; it never authors. */
import { mkdir, open, rename, readFile, readdir, lstat, realpath } from "node:fs/promises";
import { randomBytes } from "node:crypto";
import path from "node:path";

type Git = (args: string[], cwd?: string) => Promise<{code:number; stdout:string}>;
export type RefIdentity = { commit:string; tree:string };
export type FarmEffect = {
  schema:1; runId:string; taskId:string; repository:string; branch:string;
  integration:string; worktree:string; attempt:number;
  stage:"prepared"|"commit-pending"|"committed"|"merge-pending"|"merged"|"settled";
  candidate?:RefIdentity; base?:RefIdentity; integrationBefore?:RefIdentity; integrationAfter?:RefIdentity;
  expectedTree?:string; finalIntegration?:RefIdentity; runCleanup?:{verified:boolean;failures:{target:string;detail:string}[]}; result?:Record<string, unknown>;
};
const hash = /^(?:[a-f0-9]{40}|[a-f0-9]{64})$/;
const safe = /^(?!\.{1,2}$)[A-Za-z0-9._-]{1,64}$/;
export async function refIdentity(git:Git, ref:string, cwd?:string):Promise<RefIdentity|null> {
  const r = await git(["rev-parse", "--verify", `${ref}^{commit}`], cwd);
  const t = await git(["rev-parse", "--verify", `${ref}^{tree}`], cwd);
  const commit=r.stdout.trim(), tree=t.stdout.trim();
  return r.code===0 && t.code===0 && hash.test(commit) && hash.test(tree) ? {commit,tree} : null;
}
export async function repositoryIdentity(git:Git):Promise<string> {
  const result=await git(["rev-parse", "--path-format=absolute", "--git-common-dir"]);
  if(result.code!==0 || !result.stdout.trim()) throw new Error("farm repository identity unavailable");
  return realpath(path.resolve(result.stdout.trim()));
}
/** Only the parent is recursive. The run directory itself is an exclusive claim. */
export async function createRunDirectory(root:string, runId:string):Promise<string> {
  if(!safe.test(runId) || /^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)/i.test(runId)) throw new Error("invalid run identity");
  await mkdir(path.join(root,"runs"),{recursive:true});
  const dir=path.join(root,"runs",runId);
  try { await mkdir(dir); }
  catch { throw new Error(`farm run identity already exists or cannot be claimed: ${runId}; use --recover-receipt ${runId} to inspect effects, or an explicit new attempt identity`); }
  await mkdir(path.join(dir,"effects"));
  return dir;
}
async function durableWrite(file:string, value:unknown):Promise<void> {
  const temp=`${file}.${randomBytes(8).toString("hex")}.tmp`;
  const handle=await open(temp,"wx",0o600);
  try { await handle.writeFile(JSON.stringify(value,null,2)+"\n"); await handle.sync(); }
  finally { await handle.close(); }
  await rename(temp,file);
}
export async function writeEffect(dir:string, effect:FarmEffect):Promise<void> {
  if(!safe.test(effect.taskId)) throw new Error("invalid effect task identity");
  const history=path.join(dir,"effects","history");
  await mkdir(history,{recursive:true});
  await durableWrite(path.join(history,`${effect.taskId}-${effect.attempt}-${effect.stage}-${randomBytes(8).toString("hex")}.json`),effect);
  await durableWrite(path.join(dir,"effects",`${effect.taskId}.json`),effect);
}
function validIdentity(v:unknown):v is RefIdentity {
  return !!v && typeof v==="object" && hash.test((v as RefIdentity).commit) && hash.test((v as RefIdentity).tree);
}
function same(a:RefIdentity|null,b:RefIdentity|undefined):boolean {return !!a && !!b && a.commit===b.commit && a.tree===b.tree;}
/** Repairs only a separate receipt. Original streams/reports and refs are preserved. */
export async function recoverReceipt(dir:string, runId:string, git:Git):Promise<Record<string,unknown>> {
  const run=await lstat(dir);
  const effects=path.join(dir,"effects");
  if(!run.isDirectory() || run.isSymbolicLink() || (await lstat(effects)).isSymbolicLink()) throw new Error("unverified recovery directory");
  const repository=await repositoryIdentity(git);
  const results:Record<string,unknown>[]=[];
  const files=(await readdir(effects)).filter(f=>f.endsWith(".json")).sort();
  for(const file of files) {
    if(!safe.test(file.slice(0,-5)) || (await lstat(path.join(effects,file))).isSymbolicLink()) throw new Error("invalid recovery record path");
    const bytes=await readFile(path.join(effects,file),"utf8");
    if(bytes.length>128*1024) throw new Error("oversized recovery record");
    const record=JSON.parse(bytes) as FarmEffect;
    if(record.schema!==1 || record.runId!==runId || record.repository!==repository || `${record.taskId}.json`!==file ||
      typeof record.branch!=="string" || !record.branch.startsWith("farm/") || typeof record.integration!=="string" ||
      !["prepared","commit-pending","committed","merge-pending","merged","settled"].includes(record.stage) ||
      (record.candidate!==undefined && !validIdentity(record.candidate)) ||
      (record.integrationAfter!==undefined && !validIdentity(record.integrationAfter)) ||
      (record.finalIntegration!==undefined && !validIdentity(record.finalIntegration))) throw new Error("incompatible or unverified recovery record");
    const candidate=await refIdentity(git,`refs/heads/${record.branch}`);
    const integration=await refIdentity(git,`refs/heads/${record.integration}`);
    const candidateMatches=same(candidate,record.candidate);
    let integrated=candidateMatches && same(integration,record.integrationAfter);
    let finalMatches=same(integration,record.finalIntegration ?? record.integrationAfter);
    if(candidateMatches && integration && validIdentity(record.integrationAfter) && finalMatches && record.finalIntegration) {
      const ancestor=await git(["merge-base","--is-ancestor",record.integrationAfter.commit,integration.commit]);
      integrated=ancestor.code===0;
    }
    // Crash after merge but before the after-record: only the exact two-parent
    // merge of the recorded precondition and candidate can settle this effect.
    if(!integrated && record.stage==="merge-pending" && candidateMatches && integration && validIdentity(record.integrationBefore)) {
      const parents=await git(["show","-s","--format=%P",integration.commit]);
      const observed=parents.stdout.trim().split(/\s+/);
      integrated=parents.code===0 && observed.length===2 && observed[0]===record.integrationBefore.commit && observed[1]===candidate!.commit;
    }
    const cleanupVerified=record.stage==="settled" && record.runCleanup?.verified===true && !record.result?.cleanup && record.result?.containment!=="unknown";
    results.push({taskId:record.taskId,stage:record.stage,author:"not-invoked",candidate, integration,
      candidateMatches,runCleanup:record.runCleanup ?? {verified:false,failures:[]},merge:integrated?"observed":"unknown",cleanup:cleanupVerified?"recorded-verified":"unknown",
      status:integrated && finalMatches && cleanupVerified && record.result?.status==="green"?"green":"unknown",
      nextAction:integrated?"inspect remaining cleanup and receipt obligations":"inspect retained refs; new author attempt requires an explicit new identity"});
  }
  const receipt={schema:1,run_id:runId,recovery:"receipt-only",repository,results,empty:files.length===0};
  // Concurrent recoverers have independent names and cannot replace one another.
  await durableWrite(path.join(dir,`farm-recovered-${randomBytes(8).toString("hex")}.json`),receipt);
  return receipt;
}
