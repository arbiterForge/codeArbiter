import { readFileSync, readdirSync, lstatSync, existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { featureMap, type ExecutionMap } from './model';
import { workflows } from './workflows';
import { supplementalViews } from './atlas-content';
import { commandMetadata } from './atlas-command';
import { REVIEWED_AT, invocation, validateAtlas, type Atlas, type AtlasView, type AtlasSource, type HostDescriptor, type RouteMeta } from './atlas-model';

// Astro bundles server imports, so import.meta.url is not a repository path.
function repositoryRoot(): string {
  let root=process.cwd();
  while (!existsSync(resolve(root,'core/hosts.json')) || !existsSync(resolve(root,'site/package.json'))) {
    const parent=dirname(root);
    if(parent===root)throw new Error('Run the atlas build inside the codeArbiter checkout');
    root=parent;
  }
  return root;
}
export const entryViews: Record<string,string[]> = {
  feature:['feature','context-layers'], sprint:['sprint','context-layers'],
  fix:['debug-fix','context-layers'], debug:['debug-fix'],
  init:['greenfield','brownfield'], decompose:['greenfield'], 'create-context':['brownfield'],
  'add-dep':['dependency'], adr:['adr'], 'adr-status':['adr'], release:['release'],
  tribunal:['tribunal'], review:['review-delivery','context-layers'], commit:['review-delivery'], pr:['review-delivery'], watch:['review-delivery'], cleanup:['review-delivery'],
};
export function gitBlob(bytes: Uint8Array): string { return createHash('sha1').update(`blob ${bytes.byteLength}\0`).update(bytes).digest('hex'); }
/** Full-file freshness, not a quote-only green light. Never fetch or repin automatically. */
export function checkReviewedSource(root: string, path: string, pin?: string): void {
  if (!/^(core|site|docs)\/[A-Za-z0-9_./-]+$/.test(path) || path.split('/').includes('..')) throw new Error(`Invalid atlas source path: ${path}`);
  const absolute = resolve(root,path);
  if (!lstatSync(absolute).isFile() || lstatSync(absolute).isSymbolicLink()) throw new Error(`Atlas source is not a regular file: ${path}`);
  let expected = pin;
  if (!expected) {
    try { expected = execFileSync('git',['rev-parse','--verify',`${REVIEWED_AT}:${path}`],{cwd:root,encoding:'utf8',stdio:['ignore','pipe','pipe']}).trim(); }
    catch { throw new Error(`Atlas needs reviewed Git object ${REVIEWED_AT}:${path}. Use a checkout containing that revision; do not substitute main.`); }
  }
  // Text input is normalized only for platform checkout line endings. A changed
  // logical source, including whitespace beyond CRLF, requires editorial review.
  const bytes = Buffer.from(readFileSync(absolute,'utf8').replace(/\r\n/g,'\n'));
  if (gitBlob(bytes) !== expected) throw new Error(`Atlas source changed: ${path}. Review affected routes, then intentionally update the review binding.`);
}
function projectMap(map: ExecutionMap): AtlasView {
  const sources: Record<string,AtlasSource> = {};
  for (const [key,value] of Object.entries(map.sources)) sources[key] = {path:value.path, revision:map.reviewedAt, quote:value.quote};
  return {
    id:map.id, title:map.title, boundary:map.boundary, outcome:map.outcome, sources,
    chapters:map.chapters.map(chapter => ({id:chapter.id,title:chapter.title,question:chapter.question,output:chapter.output,nodes:chapter.nodes.map(node => ({id:node.id,kind:node.role,title:node.title,detail:node.detail,output:node.output,source:node.source,href:node.href,checks:node.checks,conditional:node.conditional}))})),
    edges:[...map.chapters.flatMap(chapter=>chapter.edges),...map.alternatives],
  };
}
export function loadAtlas(root = repositoryRoot()): Atlas {
  const catalogPath = 'core/surface/command-routes.json';
  checkReviewedSource(root,catalogPath,'a6b8aa3746347cf07e867f7e0f40bd0194d3ee60');
  checkReviewedSource(root,'core/hosts.json','3b100523fb773d1bac374c52ca331936f0c37bf6');
  const catalog = JSON.parse(readFileSync(resolve(root,catalogPath),'utf8')) as { commands: Record<string,RouteMeta>; visibilityOrder:string[]; workflowOrder:string[] };
  const hosts = (JSON.parse(readFileSync(resolve(root,'core/hosts.json'),'utf8')) as {hosts:HostDescriptor[]}).hosts;
  const originals = [featureMap,...workflows.map(w=>w.map)];
  const checked = new Set<string>([catalogPath,'core/hosts.json']);
  for (const map of originals) for (const source of Object.values(map.sources)) {
    const path = source.currentPath ?? source.path;
    if (!checked.has(path)) { checkReviewedSource(root,path); checked.add(path); }
    if (!readFileSync(resolve(root,path),'utf8').replace(/\r\n/g,'\n').includes((source.currentQuote ?? source.quote).replace(/\r\n/g,'\n'))) throw new Error(`Atlas source anchor changed: ${path}`);
  }
  for (const view of supplementalViews) for (const source of Object.values(view.sources)) if (!checked.has(source.path)) { checkReviewedSource(root,source.path,source.blob); checked.add(source.path); }
  const entries = Object.entries(catalog.commands).map(([id,meta]) => {
    const {path,description} = commandMetadata(id, path => {
      checkReviewedSource(root,path);
      return readFileSync(resolve(root,path),'utf8');
    });
    return {...meta,id,description,views:entryViews[id] ?? [],source:{path,revision:REVIEWED_AT},invocations:Object.fromEntries(hosts.map(host=>[host.name,invocation(host,id)]))};
  }).sort((a,b)=>catalog.visibilityOrder.indexOf(a.visibility)-catalog.visibilityOrder.indexOf(b.visibility)||a.id.localeCompare(b.id,'en'));
  // The directory itself is reviewed, so adding/removing a lens cannot silently
  // change the count in an otherwise stale explanation.
  const lensDir = 'core/surface/skills/tribunal/references/lenses';
  const lensNames = readdirSync(resolve(root,lensDir)).filter(name=>name.endsWith('.md') && name !== 'INDEX.md').sort();
  const expectedLensNames = execFileSync('git',['ls-tree','--name-only',`${REVIEWED_AT}:${lensDir}`],{cwd:root,encoding:'utf8'}).trim().split('\n').filter(name=>name.endsWith('.md') && name !== 'INDEX.md').sort();
  if (JSON.stringify(lensNames)!==JSON.stringify(expectedLensNames)) throw new Error('Atlas lens roster changed; review the Tribunal explanation');
  const catalogSource = {path:catalogPath,revision:REVIEWED_AT};
  const allRoutes: AtlasView = {
    id:'all-routes',title:'All entries and their owning routes',sources:{catalog:catalogSource},
    boundary:'Catalog groups are not execution phases. Only compatibility redirects are arrows here. Select an entry for its exact procedure and the source-traced maps that apply.',
    outcome:'Find an entry without promoting aliases, internal protocols or deprecated names to primary choices.',
    chapters:catalog.workflowOrder.map(workflow=>({id:workflow,title:workflow[0].toUpperCase()+workflow.slice(1),nodes:entries.filter(entry=>entry.workflow===workflow).map(entry=>({id:entry.id,kind:'command' as const,title:`/${entry.id}`,detail:entry.description,output:entry.replacement ? `Compatibility destination: ${entry.replacement}` : `${entry.visibility} entry; consult its exact command procedure.`,source:'catalog',href:`/reference/commands/${entry.id}/`}))})).filter(chapter=>chapter.nodes.length>0),
    edges:entries.filter(entry=>entry.visibility==='alias' && entry.canonical).map(entry=>({from:entry.id,to:entry.canonical!,kind:'reuse' as const,label:entry.replacement!,detail:`Compatibility spelling routes to ${entry.replacement}; its original submode is retained.`,source:'catalog'})),
  };
  const atlas:Atlas = {reviewedAt:REVIEWED_AT,entries,views:[...originals.map(projectMap),...structuredClone(supplementalViews),allRoutes],lensCount:lensNames.length};
  const errors = validateAtlas(atlas); if (errors.length) throw new Error(errors.join('\n'));
  return atlas;
}
