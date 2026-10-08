import {readFileSync,readdirSync,lstatSync,existsSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {createHash} from 'node:crypto';
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

// Original diagram/source links retain REVIEWED_AT. Freshness is separately
// revalidated against this exact main revision, never whichever HEAD is newest.
// PR936 changes only the Claude role count (19 -> 20) in the atlas's product
// inputs. No route, host authority or geometry changes follow from that correction.
export const REVALIDATED_AT = '81055792c71ba7aaeeaf5280e81ce2929bb25cc1';

function repositoryRoot():string {
  let root=process.cwd();
  while(!existsSync(resolve(root,'core/hosts.json')) || !existsSync(resolve(root,'site/package.json'))) {
    const parent=dirname(root);if(parent===root)throw new Error('Run the atlas build inside the codeArbiter checkout');root=parent;
  }
  return root;
}
export function gitBlob(bytes:Uint8Array):string {return createHash('sha1').update(`blob ${bytes.byteLength}\0`).update(bytes).digest('hex');}
export function checkReviewedSource(root:string,path:string,pin?:string):void {
  if(!validSourcePath(path))throw new Error(`Invalid atlas source path: ${path}`);
  // Reject symlinked parents as well as a symlink leaf.
  let absolute=root;
  for(const part of path.split('/')) {absolute=resolve(absolute,part);if(lstatSync(absolute).isSymbolicLink())throw new Error(`Atlas source is a symlink: ${path}`);}
  if(!lstatSync(absolute).isFile())throw new Error(`Atlas source is not a regular file: ${path}`);
  let expected=pin;
  if(!expected) {
    try {expected=execFileSync('git',['rev-parse','--verify',`${REVALIDATED_AT}:${path}`],{cwd:root,encoding:'utf8',stdio:['ignore','pipe','pipe']}).trim();}
    catch{throw new Error(`Atlas needs reviewed Git object ${REVALIDATED_AT}:${path}. Do not substitute main.`);}
  }
  if(gitBlob(Buffer.from(readFileSync(absolute,'utf8').replace(/\r\n/g,'\n')))!==expected)throw new Error(`Atlas source changed: ${path}. Review affected routes, then intentionally update the review binding.`);
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
  const checked=new Set<string>();
  const read=(path:string,pin?:string):string=>{if(!checked.has(path)){checkReviewedSource(root,path,pin);checked.add(path);}return readFileSync(resolve(root,path),'utf8');};
  const registry=JSON.parse(read('core/surface/command-routes.json',catalog.catalog_snapshot.blob_sha)) as {commands:Record<string,RouteMeta>};
  const hosts=(JSON.parse(read('core/hosts.json','3b100523fb773d1bac374c52ca331936f0c37bf6')) as {hosts:HostDescriptor[]}).hosts;
  if(JSON.stringify(Object.keys(registry.commands).sort())!==JSON.stringify(atlas.commands.map(c=>c.name).sort()))throw new Error('Atlas catalog coverage changed');
  // Product owners must still match. Site-design pointers are historical
  // integration evidence, not product claims; this PR intentionally changes them.
  for(const s of atlas.sources)if(!s.path.startsWith('site/'))read(s.path);
  for(const command of atlas.commands) {
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
  const expected=execFileSync('git',['ls-tree','--name-only',`${REVALIDATED_AT}:${lensDir}`],{cwd:root,encoding:'utf8'}).trim().split('\n').filter(n=>n.endsWith('.md')&&n!=='INDEX.md').sort();
  if(JSON.stringify(names)!==JSON.stringify(expected))throw new Error('Atlas lens roster changed; review the Tribunal route');
  atlas.lensCount=names.length;
  atlas.scope+=` Original source links and layout retained; source compatibility revalidated at ${REVALIDATED_AT}.`;
  return atlas;
}

import {atlasTheme,type AtlasTheme} from './atlas-theme';
export function loadAtlasTheme(root=repositoryRoot()):AtlasTheme {
  return atlasTheme(readFileSync(resolve(root,'site/src/styles/design-system.css'),'utf8'));
}
