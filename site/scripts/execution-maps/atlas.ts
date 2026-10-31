import {readFileSync,readdirSync,lstatSync,existsSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {execFileSync} from 'node:child_process';
import {commandMetadata} from './atlas-command';
import {REVIEWED_AT,invocation,validateAtlas,validSourcePath,type Atlas,type HostDescriptor,type RouteMeta} from './atlas-model';
import catalog from './atlas-data/catalog.json';
import commands from './atlas-data/commands.json';
import sources from './atlas-data/sources.json';
import overview from './atlas-data/all-routes.json';
import feature from './atlas-data/feature-sprint.json';
import context from './atlas-data/context-layers.json';
import change from './atlas-data/change-lanes.json';
import delivery from './atlas-data/review-delivery.json';
import operations from './atlas-data/knowledge-operations.json';
import brownfield from './atlas-data/brownfield-lifecycle.json';
import debug from './atlas-data/debug-handoff.json';
import tribunal from './atlas-data/tribunal-lifecycle.json';
import assistiveUpdate from './atlas-data/assistive-update.json';

// Original diagram/source links retain REVIEWED_AT. Freshness is separately
// revalidated against this exact source revision, never whichever HEAD is newest.
// PR936 corrected the Claude role count; PR935 added preflight batching. PR943
// changes the Pi target to 1.1.0 in the host fingerprint key, doctor and parity
// text, without changing command forms, exclusions, routes or diagram geometry.
// PR918 updates the artifacts owner and cited native adapter with normalized
// completion closure and bounded context retention. Their routes and authority
// boundaries agree with the maps. PR945 adds the exact native V2 activity/child
// binding, steering refusal and frozen verification context references to those
// owners and docs/hooks.md. Routes and authority boundaries remain compatible;
// historical comparisons remain independently tested.
// PR952 makes the existing brownfield host prerequisites explicit before
// scaffolding and links debug packet preparation before one-shot validation.
// The reviewed containment, handoff, authority and recovery routes still agree
// with the maps; no host qualification or new runtime capability is implied.
export const REVALIDATED_AT = '25980c292b529fca90c39f5f26d69a1c0674de44';
// PR956's exact unittest matching change agrees with S32's cited lines and
// native authority routes. All 71 product reads and the lens roster were
// compared. Pin the retained blob so a squash does not require a branch commit.
export const UNITTEST_COLLECTOR_BLOB = '76a2998f4bd5b6f441f5fd162bbe810b2de2ee93';

// These exact tracked owner blobs retain the packet-preparation review through
// changelog integration and a squash/main clone. All other owners retain the
// historical native V2 binding; later release notes remain unreviewed additions.
export const BROWNFIELD_SOURCE_BLOBS:Readonly<Record<string,string>>=Object.freeze({
  'core/surface/commands/init.md':'c3de948de1617aa323e310eefee7fde2bd8a65fc',
  'core/surface/skills/debug/SKILL.md':'6a791230cdbfa0916c63d2b1dcc6431d1625b1a3',
});

// #967 supplies bounded legacy metadata maintenance and a separate explicitly
// selected per-block resolver. Commit review/staging and the displayed original
// exact-HEAD recovery retain their gates; neither operation grants native ownership.
export const LEGACY_CODE_MAP_SOURCE_BLOBS:Readonly<Record<string,string>>=Object.freeze({
  'core/surface/skills/commit-gate/SKILL.md':'8818ab0ae6230aafcc42b48f72190e0e4ec9adcb',
  'core/surface/skills/finishing-a-development-branch/SKILL.md':'7e495efd47875a05560c34634c46b59b71838ee5',
});

// #959 adds an authority-free initial draft-preview rebind. S07/S10 still
// require genuine combined approval before sprint execution and preserve the
// ordinary approved-source feature path. Bind only these reviewed canonical
// file blobs, which the tracked documents retain through a squash/main clone.
// PR961 (ADR-0042) adds ship-set input identity to the artifacts include; no route
// reads or depends on that identity, so the same pin carries the combined text.
export const DRAFT_PREVIEW_SOURCE_BLOBS:Readonly<Record<string,string>>=Object.freeze({
  'core/surface/SPRINT.md':'c3c47d38028fb3a8141fe1235957e827031acd43',
  'core/surface/includes/artifacts.md':'8a834b919fb81c77213086a1b1661d16b5290bbe',
});

// #968 clarifies observed/unknown host qualification, the fixed manifest layout
// and complete same-interpreter helper calls. These three reviewed document
// blobs preserve the existing routes and gates; earlier review objects remain
// historical evidence rather than being relabelled as this clarification.
export const CONTEXT_MAINTENANCE_SOURCE_BLOBS:Readonly<Record<string,string>>=Object.freeze({
  'core/surface/commands/init.md':'83afa327833ff6f76379389b6d1b80c4978f332b',
  'core/surface/skills/commit-gate/SKILL.md':'bbfc5054fe7ac94309ded7b8cdd6073b3ad65c9d',
  'core/surface/skills/finishing-a-development-branch/SKILL.md':'c9b8bc36934e5b79f0e4ec72c35c69997519378f',
});

// PR979 separates Codex release provenance from native review protocol proof.
// S10/S17 retain admission, observed approval and host-event boundaries; S32
// retains native IDs, producer states, Claude joins and canonical digests.
// Independent source-bound review still requires actual launch/child/first-Stop
// evidence. No route, geometry or installed-host qualification claim changes.
// These tracked owner blobs survive a squash; earlier bindings stay historical.
// Fresh legacy context approval arming is now refused; the assistive update
// already describes the ordinary context writer without that receipt.
export const RUNTIME_COMPATIBILITY_SOURCE_BLOBS:Readonly<Record<string,string>>=Object.freeze({
  'core/surface/includes/artifacts.md':'c10c13162e63699c3748809f3ef2448bc8b07fb9',
  'core/pysrc/_artifactauthoritylib.py':'5c95b3f70eb84e26e494d294c9028eca1fb78871',
  'docs/hooks.md':'d4726a5fdbc6175498ab03ac47fe8ee66c2bf36a',
});
// #982 adds a Git-ignore preflight before verification arming. S32's producer
// identity and completion drift routes retain their earlier geometry; this
// binding is current source evidence, separate from the historical reviews.
export const MARKER_PREFLIGHT_BLOB='3bd569c1cbc9be1d25da7bff51429c0cd60793af';
// #1054 caches packaged schema patterns and default presentation assets after
// validation. Rendered artifact semantics and the reviewed map stay the same.
export const SCHEMA_CACHE_RENDER_BLOB='916287678b836f1bf9a98782dc8e7d0bb58d6986';

// PR1029 adds an operator-confirmed, exact-digest recovery for one stranded
// Tribunal write lock. S29's resume/history/continue path still requires the
// same source binding and preserves historical files; S30 now guards active
// writers and archives the inspected lock before work can continue. Fresh-run,
// cost, dispatch and completion routes keep their existing geometry and gates.
// A failed fingerprint probe has its own fail-closed status. Staging a selected
// untracked input, changing scope, or changing committed HEAD reports source
// drift even if a later probe cannot read evidence; neither state resumes an audit.
export const TRIBUNAL_LOCK_RECOVERY_SOURCE_BLOBS:Readonly<Record<string,string>>=Object.freeze({
  'core/surface/skills/tribunal/SKILL.md':'fa411c6e8d9b335914e0b31a875d6739d38ade40',
  'core/pysrc/_tribunalrunlib.py':'c2db7a2b082e005e0be9dd637a853c6ee096a01f',
});

// PR893 adds one SMARTS hard rule to debug, the only SMARTS owner outside the
// assistive record below: diagnosis stays evidence-led and a remediation strategy
// choice belongs to /fix after root cause. No route, gate or geometry changes.
export const SMARTS_INTEGRATION_SOURCE_BLOBS:Readonly<Record<string,string>>=Object.freeze({
  'core/surface/skills/debug/SKILL.md':'cc99c8c62cdb5888a3372cddcab45f1db123d412',
});

// PR983 is not merely source-compatible with the old permission diagram. Retain
// that geometry as explicitly historical and attach the bounded implementation
// delta. Exact tracked owner blobs survive a squash; no moving-main substitution
// or fabricated host qualification makes the old arrows current.
export const ASSISTIVE_SOURCE_BLOBS:Readonly<Record<string,string>>=Object.freeze(
  Object.fromEntries(assistiveUpdate.changes.map(change=>[change.path,change.blob])),
);

/** Sources reviewed for HTML knowledge records and decomposition (#1023): the
 * context owners gained an HTML procedure and kept Markdown in references.
 * The conversion route now asks the agent to map each Markdown section to
 * saved knowledge before a digest-bound cutover; the context-creation and decompose routes retain
 * their explicit format choice and unchanged Markdown fallback. The Python
 * artifact bridge also now exposes a bounded error field for diagnostics;
 * this does not change the context or approval routes. Security
 * policy readers now select complete HTML records after conversion while the
 * Markdown scope blocks remain operative. Native legacy migration now requires
 * both spec and plan mappings in one request; the diagram routes are unchanged.
 * This changes the cited source text,
 * not the diagram routes or gate ownership. */
export const CONTEXT_KNOWLEDGE_SOURCE_BLOBS:Readonly<Record<string,string>>=Object.freeze({
  'core/pysrc/_readinjectlib.py':'eb9ac0c2ed4516450ec8607327790e3edaab8252',
  'core/surface/commands/add-dep.md':'4f39d82c50862c0f16965c1676c8c0a78813362d',
  'core/surface/commands/review.md':'4ead3a713888eeabaa003c3679e02d459a8647ea',
  'core/surface/includes/reference-map.md':'983ed0c26c2bbe14009847017507e871f772e380',
  'core/surface/skills/debug/SKILL.md':'83c3124f046df51e3db67278545260bff93b19d2',
  'core/surface/skills/security-architecture/SKILL.md':'669e8a1d4660a7166d0d3304304bcf322758c111',
  'core/surface/skills/tribunal/SKILL.md':'a549fae64b1bf6243b59ea78aa608c05beeab348',
  'core/artifacts/internal/operations/protocol.go':'c3238af44ac7dca08fa4002eec28847ab85f6b50',
  'core/artifacts/internal/operations/task_context.go':'9e5e5694241ab3a25bdc3af22e8efdc9afdde5c6',
  'core/artifacts/internal/render/render.go':'2be6970d8ac51fcf6c8a4908441d94421e0bf921',
  'core/pysrc/_artifactlib.py':'5b900d8ee592935d04a2d6f1a2f7ffcc832dd976',
  'core/pysrc/init-codearbiter.py':'ab47257f03a0bdd2cbd249cc00478cdbeeea4f39',
  'core/surface/commands/feature.md':'ebb6047b0ec2f7040c60c6847535bb1f65f6cd10',
  'core/surface/commands/fix.md':'03fbef8fef446eb3c40f8f7ea5207352e587ba0f',
  'core/surface/commands/init.md':'d00ab436b525ad86d0e9f95fb106833c9a297006',
  'core/surface/skills/brainstorming/SKILL.md':'036c3c440f8d09b563e00c472b9394deb6f6e705',
  'core/surface/skills/commit-gate/SKILL.md':'159e0f1d0746c26006e4d12a4f28429fb0c023b6',
  'core/surface/skills/context-check/SKILL.md':'10814dbe261c9ecd98be83716a03fd9699715018',
  'core/surface/skills/context-creation/SKILL.md':'9f28e5f8c9dbb903abee8e2264f60069c5128487',
  'core/surface/skills/decompose/SKILL.md':'891a4ed873bbe2a8cbfd5ccb5315e6ef7ece1e02',
  'core/surface/skills/finishing-a-development-branch/SKILL.md':'5082926a20883837a75994322db5c0b845eae3fd',
  'core/surface/skills/release/SKILL.md':'15216183910a201eb5966b741bbb1a8d023927f8',
  'core/surface/skills/subagent-driven-development/SKILL.md':'7c27d8ebb707088636e39a5ce28ca59043745609',
  'core/surface/skills/tdd/SKILL.md':'1246d507b3bc3f46a8b15757b2a74d57207b93f0',
  'core/surface/skills/writing-plans/SKILL.md':'5b47ef521e29bcb9b49db2662d13806a415cd8de',
  'core/surface/skills/refactor/SKILL.md':'3f96c8640832c34d7fb91d59fd5928b8fa68ecfc',
});
// The local work owner adds selected work operations to the artifact bridge
// and a work document rendering. The bridge now also admits a derived project
// page read; existing review routes retain their geometry. These are the
// current reviewed source bytes for those shared owners.
export const WORK_SYSTEM_SOURCE_BLOBS:Readonly<Record<string,string>>=Object.freeze({
  // Init now sends initialized Markdown acquisition through decompose and
  // refresh through context-check; the historical route layout is unchanged.
  'core/surface/commands/init.md':'ed0f32b734097fa549cd95738ceaa30c56b7b849',
  'core/pysrc/_artifactlib.py':'0cbc621fe6eeab05e7eb2bf96ebbee6c58d21c38',
  'core/artifacts/internal/render/render.go':'8b8c6c203d6897b7b23d105900f8dfcf1b3b0383',
  'core/artifacts/internal/operations/protocol.go':'0fb2db079a80621a3488b72ff2997aad07a9e2d0',
  'core/surface/agents/checkpoint-aggregator.md':'d77511be701e20a5a7c407d7da4c937f4bb89ca4',
  'core/surface/commands/standup.md':'c6ff812ec6525a4d995ec6ad66d982b140fcd5d0',
  'core/surface/commands/status.md':'3dbf7706a86ba959d3fb4721dc23afb7a0b23960',
  'core/surface/commands/task.md':'5bf344c907f9af13689e3ce71c7f036f4b26d61f',
  'core/surface/includes/reference-map.md':'4a024e9c0afbf3a07472e28cd66d41298c73db35',
  'core/surface/includes/routing-table.md':'6064c94e7507d0fa3f10fd32d0a96f23eca0c7c7',
  'core/surface/skills/brainstorming/SKILL.md':'9d53f27511dc063341068498c45766ae042f5b4d',
  'core/surface/skills/commit-gate/SKILL.md':'b009fa35e839f2ae929451a7114ac2a05e26c9db',
  'core/surface/skills/context-check/SKILL.md':'c590950615c6c3a93ee5a57413394b8389d02e4e',
  'core/surface/skills/context-creation/SKILL.md':'dff4947f37e686afb5d43dbe1ce83580aa9ccc5c',
  'core/surface/skills/debug/SKILL.md':'6450b02b225522df7a1e06abf9d5e0db018dd801',
  'core/surface/skills/decompose/SKILL.md':'7abb26dbd435a959e049d41e1e126fefeed5c64d',
  'core/surface/skills/subagent-driven-development/SKILL.md':'0d96d04585e579907b3a86d7b2823a9079f60b59',
});
// The 2026-10-23 removal of /btw, /commands, /metrics and /preview deletes their
// owners and drops their catalog rows. These files only lose pointers to those
// routes (or record the new catalog counts); every remaining route, gate and
// owner is unchanged. Bind the reviewed bytes so a squash does not need a branch.
export const RETIRED_COMMANDS:Readonly<Record<string,string>>=Object.freeze({
  btw:'2026-10-23', commands:'2026-10-23', metrics:'2026-10-23', preview:'2026-10-23',
});
export const COMMAND_REMOVAL_SOURCE_BLOBS:Readonly<Record<string,string>>=Object.freeze({
  'core/surface/COMMANDS.md':'c0c448861c4dfcaa97ed73fc5be42315a932828c',
  'core/surface/arbiter.md':'a762089e480bfc9fab9706a700a7cc3ab04e8e13',
  'core/surface/commands/add-dep.md':'53e90d4995356d2a9b7e8247d6ed508bf27feb56',
  'core/surface/commands/feature.md':'b794da0756ed7fdb103da5533112769f0adcee04',
  'core/surface/commands/fix.md':'8b41d39a90ef2ddce57b23e11b793362d8ed36f8',
  'core/surface/commands/review.md':'987a2df9227a19a54fdd85e8fc31dee62c6924bb',
  'core/surface/commands/spike.md':'390283c8c09ae6f68a25c5787e333baebd0f8836',
  'core/surface/commands/status.md':'e4359c41c5352062c34dbcdd44f3294af06d2995',
  'core/surface/includes/routing-table.md':'036424b8c9ca6c5cfa74bd3b8f5f3db5f7f0ae2c',
  'docs/parity.md':'ea25f8681bcd2c4d5be27ea79fc9f365aee175fc',
});

function rootBoundGitEnv():NodeJS.ProcessEnv {
  const env={...process.env};
  // Match core/pysrc/_gitexec.py: retain configuration such as safe.directory,
  // removing only repository, object and discovery selectors that override cwd.
  const selectors=new Set([
    'GIT_ALTERNATE_OBJECT_DIRECTORIES','GIT_OBJECT_DIRECTORY','GIT_DIR','GIT_WORK_TREE',
    'GIT_IMPLICIT_WORK_TREE','GIT_GRAFT_FILE','GIT_INDEX_FILE','GIT_NO_REPLACE_OBJECTS',
    'GIT_REPLACE_REF_BASE','GIT_PREFIX','GIT_SHALLOW_FILE','GIT_COMMON_DIR',
    'GIT_CEILING_DIRECTORIES','GIT_DISCOVERY_ACROSS_FILESYSTEM',
  ]);
  for(const name of Object.keys(env))if(selectors.has(name.toUpperCase()))delete env[name];
  return env;
}

function repositoryRoot():string {
  let root=process.cwd();
  while(!existsSync(resolve(root,'core/hosts.json')) || !existsSync(resolve(root,'site/package.json'))) {
    const parent=dirname(root);if(parent===root)throw new Error('Run the atlas build inside the codeArbiter checkout');root=parent;
  }
  return root;
}
/** S40 cites immutable release history, not notes added after its review. */
export function retainsReviewedChangelog(current:string,reviewed:string):boolean {
  current=current.replace(/\r\n/g,'\n');reviewed=reviewed.replace(/\r\n/g,'\n');
  const boundary='## [Unreleased]\n\n';
  const start=reviewed.indexOf(boundary);
  if(start<0 || start!==reviewed.lastIndexOf(boundary))return false;
  const split=start+boundary.length;
  const header=reviewed.slice(0,split),history=reviewed.slice(split);
  // Only insertion between the unchanged preamble and complete old history is
  // permitted. The added notes are not consumed, rendered or marked reviewed.
  return history.startsWith('## [') && current.length>=reviewed.length &&
    current.startsWith(header) && current.endsWith(history) &&
    current.indexOf(boundary)===current.lastIndexOf(boundary);
}
function currentSource(root:string,path:string,pin?:string):string {
  if(!validSourcePath(path))throw new Error(`Invalid atlas source path: ${path}`);
  // Reject symlinked parents as well as a symlink leaf.
  let absolute=root;
  for(const part of path.split('/')) {absolute=resolve(absolute,part);if(lstatSync(absolute).isSymbolicLink())throw new Error(`Atlas source is a symlink: ${path}`);}
  if(!lstatSync(absolute).isFile())throw new Error(`Atlas source is not a regular file: ${path}`);
  if(pin!==undefined && !/^[0-9a-f]{40}$/.test(pin))throw new Error(`Atlas source changed: ${path}. Use the exact reviewed blob identity.`);
  return readFileSync(absolute,'utf8').replace(/\r\n/g,'\n');
}
function compareReviewedSource(path:string,pin:string|undefined,current:string,reviewed:Buffer):void {
  // Compare actual reviewed bytes; Git owns object identities, not application crypto.
  if(Buffer.from(current).equals(reviewed))return;
  // Keep explicit pins and every workflow owner byte-strict. Only the root
  // historical changelog may grow above its intact reviewed release history.
  if(path==='CHANGELOG.md' && pin===undefined) {
    if(retainsReviewedChangelog(current,reviewed.toString('utf8')))return;
  }
  throw new Error(`Atlas source changed: ${path}. Review affected routes, then intentionally update the review binding.`);
}
/** Validate a finite source inventory in one offline Git read. Each call takes a
 * fresh filesystem snapshot; no process-wide cache can conceal later drift. */
function checkedSources(root:string,requests:ReadonlyMap<string,string|undefined>):Map<string,string> {
  const inputs=[...requests].map(([path,pin])=>({path,pin,expected:pin??`${REVALIDATED_AT}:${path}`,current:currentSource(root,path,pin)}));
  if(!inputs.length)return new Map();
  let batch:Buffer;
  try {batch=execFileSync('git',['--no-replace-objects','--no-lazy-fetch','cat-file','--batch'],{
    cwd:root,env:rootBoundGitEnv(),input:inputs.map(input=>`${input.expected}\n`).join(''),
    stdio:['pipe','pipe','pipe'],maxBuffer:16*1024*1024,
  });} catch {throw new Error('Atlas needs reviewed Git objects for its source inventory. Do not substitute main.');}
  const checked=new Map<string,string>();
  let offset=0;
  for(const input of inputs) {
    const end=batch.indexOf(10,offset);
    const header=end<offset?null:/^([0-9a-f]{40}) blob (\d+)$/.exec(batch.subarray(offset,end).toString('utf8'));
    if(!header || input.pin!==undefined && header[1]!==input.pin)
      throw new Error(`Atlas needs reviewed Git object ${input.expected} for ${input.path}. Do not substitute main.`);
    const size=Number(header[2]),start=end+1;
    if(!Number.isSafeInteger(size)||size<0||start+size>=batch.length||batch[start+size]!==10)
      throw new Error(`Malformed reviewed Git object for ${input.path}`);
    compareReviewedSource(input.path,input.pin,input.current,batch.subarray(start,start+size));
    checked.set(input.path,input.current);
    offset=start+size+1;
  }
  if(offset!==batch.length)throw new Error('Unexpected trailing reviewed Git object bytes');
  return checked;
}
export function checkReviewedSource(root:string,path:string,pin?:string):void {
  checkedSources(root,new Map([[path,pin]]));
}
/** Exact recovered maps, not the former grid-card projection. */
export function originalAtlas():Atlas {
  const atlas=structuredClone({...catalog,commands,sources,views:[overview,feature,context,change,delivery,operations,brownfield,debug,tribunal]}) as unknown as Atlas;
  const errors=validateAtlas(atlas);if(errors.length)throw new Error(errors.join('\n'));
  return atlas;
}
/** Current selected-work labels over the immutable original atlas snapshot. */
function applySelectedWorkRoute(atlas:Atlas):void {
  const task=atlas.commands.find(command=>command.name==='task');
  if(!task)throw new Error('Task route missing from atlas');
  task.owner='work.py → native engine or legacy taskwrite.py → _taskboardlib';
  task.steps=['Select native work or legacy board owner',
    'Validate add, start or done through the selected writer',
    'Persist native work state or dated board transition'];
  task.context=['Selected work ID or legacy open-tasks.md row and current state',
    'Requested task or harvested work'];
  task.output='Native work item or legacy task-board transition, separate from typed plan acceptance.';
  task.gates='Native updates require stable work ID, replay identity and expected revision/hash; legacy start stamps date and done requires in-progress. Never delete a task to complete it. A debug disposition alone never authorizes a task write; a concrete follow-up needs separate task authority.';
  const setNode=(viewId:string,nodeId:string,title:string|undefined,body:string):void=>{
    const node=atlas.views.find(view=>view.id===viewId)?.nodes.find(item=>item.id===nodeId);
    if(!node || !node.layout.body)throw new Error(`Selected-work atlas node missing: ${nodeId}`);
    if(title!==undefined){node.title=title;node.layout.title.lengths=title.split('\n').map(line=>Array.from(line).length);}
    node.body=body;node.layout.body.lengths=body.split('\n').map(line=>Array.from(line).length);
  };
  setNode('knowledge-operations','k-writer','work.py → selected owner',
    'Native work.py; legacy taskwrite.py\nStart stamps date; done needs in-progress\nNever delete an entry to mark it done');
  setNode('knowledge-operations','k-board','Selected work transition',
    'Native HTML or open-tasks.md state\nNot a typed-plan acceptance receipt\nLater work still selects its own lane');
  setNode('debug-handoff','d-task',undefined,
    'A needed task needs separate authorization, action, provenance and completion evidence.\nThe selected task owner uses work.py; legacy boards delegate to taskwrite.py.\nA design question may lead to an attributed ADR later, never by automatic conversion.');
}
export function loadAtlas(root=repositoryRoot()):Atlas {
  const atlas=originalAtlas();
  if(atlas.commit!==REVIEWED_AT)throw new Error('Atlas review identities disagree');
  const pinFor=(path:string,pin?:string):string|undefined=>pin??WORK_SYSTEM_SOURCE_BLOBS[path]??(path==='core/pysrc/_artifactauthoritylib.py'?MARKER_PREFLIGHT_BLOB:undefined)??(path==='core/artifacts/internal/render/render.go'?SCHEMA_CACHE_RENDER_BLOB:undefined)??TRIBUNAL_LOCK_RECOVERY_SOURCE_BLOBS[path]??CONTEXT_KNOWLEDGE_SOURCE_BLOBS[path]??COMMAND_REMOVAL_SOURCE_BLOBS[path]??SMARTS_INTEGRATION_SOURCE_BLOBS[path]??ASSISTIVE_SOURCE_BLOBS[path]??RUNTIME_COMPATIBILITY_SOURCE_BLOBS[path]??CONTEXT_MAINTENANCE_SOURCE_BLOBS[path]??DRAFT_PREVIEW_SOURCE_BLOBS[path]??BROWNFIELD_SOURCE_BLOBS[path]??LEGACY_CODE_MAP_SOURCE_BLOBS[path]??(path==='core/pysrc/_artifactauthoritylib.py'?UNITTEST_COLLECTOR_BLOB:undefined);
  const requests=new Map<string,string|undefined>([
    ['core/surface/command-routes.json',catalog.catalog_snapshot.verified_current_blob],['core/hosts.json',undefined],
  ]);
  for(const path of [...atlas.sources.filter(source=>!source.path.startsWith('site/')).map(source=>source.path),
    ...Object.keys(ASSISTIVE_SOURCE_BLOBS),...atlas.commands.filter(command=>!RETIRED_COMMANDS[command.name]).map(command=>`core/surface/commands/${command.name}.md`)
  ])if(!requests.has(path))requests.set(path,pinFor(path));
  const checked=checkedSources(root,requests);
  const read=(path:string,pin?:string):string=>{
    if(!checked.has(path))checked.set(path,checkedSources(root,new Map([[path,pinFor(path,pin)]])).get(path)!);
    return checked.get(path)!;
  };
  const registry=JSON.parse(read('core/surface/command-routes.json',catalog.catalog_snapshot.verified_current_blob)) as {commands:Record<string,RouteMeta>};
  const hosts=(JSON.parse(read('core/hosts.json')) as {hosts:HostDescriptor[]}).hosts;
  const retired=Object.keys(RETIRED_COMMANDS);
  if(retired.some(name=>name in registry.commands))throw new Error('A retired atlas route is still registered');
  if(JSON.stringify([...Object.keys(registry.commands),...retired].sort())!==JSON.stringify(atlas.commands.map(c=>c.name).sort()))throw new Error('Atlas catalog coverage changed');
  // A retired route keeps its historical box; its owner text comes from the
  // revalidated revision because the working-tree file no longer exists.
  const historical=(path:string):string=>execFileSync('git',['--no-replace-objects','--no-lazy-fetch','cat-file','blob',`${REVALIDATED_AT}:${path}`],
    {cwd:root,env:rootBoundGitEnv(),encoding:'utf8'});
  // Product owners must still match. Site-design pointers are historical
  // integration evidence, not product claims; this PR intentionally changes them.
  for(const s of atlas.sources)if(!s.path.startsWith('site/'))read(s.path);
  // Retain the historical assistive packet while checking later work-system
  // owner changes against their separately reviewed current blobs.
  for(const [path,blob] of Object.entries(ASSISTIVE_SOURCE_BLOBS))read(path,WORK_SYSTEM_SOURCE_BLOBS[path]??blob);
  for(const command of atlas.commands) {
    if(RETIRED_COMMANDS[command.name]) {
      const owner=commandMetadata(command.name,historical);
      command.description=owner.description;
      command.source={path:owner.path,revision:REVALIDATED_AT};
      command.invocations=Object.fromEntries(hosts.map(host=>[host.name,null]));
      command.removed=RETIRED_COMMANDS[command.name];
      continue;
    }
    const meta=registry.commands[command.name];
    if(meta.visibility!==command.visibility || (meta.canonical??command.name)!==command.canonical)throw new Error(`Atlas catalog classification changed: ${command.name}`);
    const owner=commandMetadata(command.name,read);
    command.replacement=meta.replacement;
    command.description=owner.description;
    command.source={path:owner.path,revision:REVIEWED_AT};
    command.invocations=Object.fromEntries(hosts.map(host=>[host.name,invocation(host,command.name)]));
  }
  const lensDir='core/surface/skills/tribunal/references/lenses';
  const names=readdirSync(resolve(root,lensDir)).filter(n=>n.endsWith('.md')&&n!=='INDEX.md').sort();
  const expected=execFileSync('git',['--no-replace-objects','ls-tree','--name-only',`${REVALIDATED_AT}:${lensDir}`],{cwd:root,env:rootBoundGitEnv(),encoding:'utf8'}).trim().split('\n').filter(n=>n.endsWith('.md')&&n!=='INDEX.md').sort();
  if(JSON.stringify(names)!==JSON.stringify(expected))throw new Error('Atlas lens roster changed; review the Tribunal route');
  atlas.lensCount=names.length;
  applySelectedWorkRoute(atlas);
  atlas.scope+=` Original source links and spatial positions retained; task labels show the selected work owner. Source compatibility revalidated at ${REVALIDATED_AT}.`;
  atlas.scope+=` Unittest collector compatibility bound to reviewed blob ${UNITTEST_COLLECTOR_BLOB}.`;
  atlas.sourceUpdate=structuredClone(assistiveUpdate);
  atlas.scope=`Historical route snapshot at ${REVIEWED_AT}. Current assistive source bindings identify inspected implementation bytes, with ${assistiveUpdate.revision} as the committed source base. Live host qualification and release are separate evidence. `+atlas.scope;
  atlas.caveats=atlas.caveats.map(note=>`Historical snapshot: ${note}`);
  const errors=validateAtlas(atlas);if(errors.length)throw new Error(errors.join('\n'));
  return atlas;
}

import {atlasTheme,type AtlasTheme} from './atlas-theme';
export function loadAtlasTheme(root=repositoryRoot()):AtlasTheme {
  return atlasTheme(readFileSync(resolve(root,'site/src/styles/design-system.css'),'utf8'));
}
