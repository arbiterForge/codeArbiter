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
export const RUNTIME_COMPATIBILITY_SOURCE_BLOBS:Readonly<Record<string,string>>=Object.freeze({
  'core/surface/includes/artifacts.md':'c10c13162e63699c3748809f3ef2448bc8b07fb9',
  'core/pysrc/_artifactauthoritylib.py':'7624ad9dce3330505bdca5f5e19c3bf7e2534d10',
  'docs/hooks.md':'d4726a5fdbc6175498ab03ac47fe8ee66c2bf36a',
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

// The 2026-10-23 removal of /btw, /commands, /metrics and /preview deletes their
// owners and drops their catalog rows. These files only lose pointers to those
// routes (or record the new catalog counts); every remaining route, gate and
// owner is unchanged. Bind the reviewed bytes so a squash does not need a branch.
export const RETIRED_COMMANDS:Readonly<Record<string,string>>=Object.freeze({
  btw:'2026-10-23', commands:'2026-10-23', metrics:'2026-10-23', preview:'2026-10-23',
});
export const COMMAND_REMOVAL_SOURCE_BLOBS:Readonly<Record<string,string>>=Object.freeze({
  'core/pysrc/_provenancelib.py':'a37a5c9503fdcb40c8828d5e77960b787fbae443',
  'core/surface/COMMANDS.md':'c0c448861c4dfcaa97ed73fc5be42315a932828c',
  'core/surface/arbiter.md':'a762089e480bfc9fab9706a700a7cc3ab04e8e13',
  'core/surface/commands/add-dep.md':'53e90d4995356d2a9b7e8247d6ed508bf27feb56',
  'core/surface/commands/feature.md':'b794da0756ed7fdb103da5533112769f0adcee04',
  'core/surface/commands/fix.md':'8b41d39a90ef2ddce57b23e11b793362d8ed36f8',
  'core/surface/commands/review.md':'987a2df9227a19a54fdd85e8fc31dee62c6924bb',
  'core/surface/commands/spike.md':'390283c8c09ae6f68a25c5787e333baebd0f8836',
  'core/surface/commands/status.md':'e4359c41c5352062c34dbcdd44f3294af06d2995',
  'core/surface/includes/routing-table.md':'036424b8c9ca6c5cfa74bd3b8f5f3db5f7f0ae2c',
  'docs/parity.md':'ecbe44a7d870d53a22dc4fb2fa4c934413dccd45',
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
export function loadAtlas(root=repositoryRoot()):Atlas {
  const atlas=originalAtlas();
  if(atlas.commit!==REVIEWED_AT)throw new Error('Atlas review identities disagree');
  const pinFor=(path:string,pin?:string):string|undefined=>pin??COMMAND_REMOVAL_SOURCE_BLOBS[path]??SMARTS_INTEGRATION_SOURCE_BLOBS[path]??ASSISTIVE_SOURCE_BLOBS[path]??RUNTIME_COMPATIBILITY_SOURCE_BLOBS[path]??CONTEXT_MAINTENANCE_SOURCE_BLOBS[path]??DRAFT_PREVIEW_SOURCE_BLOBS[path]??BROWNFIELD_SOURCE_BLOBS[path]??LEGACY_CODE_MAP_SOURCE_BLOBS[path]??(path==='core/pysrc/_artifactauthoritylib.py'?UNITTEST_COLLECTOR_BLOB:undefined);
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
  for(const [path,blob] of Object.entries(ASSISTIVE_SOURCE_BLOBS))read(path,blob);
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
  atlas.scope+=` Original source links and layout retained; source compatibility revalidated at ${REVALIDATED_AT}.`;
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
