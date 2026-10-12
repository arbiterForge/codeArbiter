/** The original spatial atlas. Geometry is presentation, not executable state. */
export type AtlasKind = 'cmd' | 'skill' | 'agent' | 'state' | 'gate' | 'out' | 'warn';
export type AtlasRelation = 'flow' | 'context' | 'conditional' | 'return' | 'stop';
export type Point = [number, number];
export interface TextLayout { size: number; y: number; line: number; lengths: number[] }
export interface AtlasSource { id: string; path: string; url: string; note: string; start?: number | null; end?: number | null; revalidation?: string }
export interface AtlasNode {
  id: string; x: number; y: number; w: number; h: number;
  title: string; body: string; kind: AtlasKind; source_ids: string[]; routes: string[];
  detail?: string; tag?: string;
  layout: { title: TextLayout; body: TextLayout | null; sourceY: number; tagY: number | null };
}
export interface AtlasEdge { a: string; b: string; kind: AtlasRelation; label: string; routes: string[]; points: Point[]; label_at?: Point; source_id?: string }
export interface AtlasPanel { x: number; y: number; w: number; h: number; title: string; caption: string }
export interface AtlasView { id: string; title: string; subtitle: string; width: number; height: number; tab_label: string; nodes: AtlasNode[]; edges: AtlasEdge[]; panels: AtlasPanel[]; notes: {x:number;y:number;text:string;kind:string;size:number}[] }
export interface RouteMeta { visibility: string; workflow: string; canonical?: string; replacement?: string }
export interface AtlasCommand {
  name: string; visibility: string; family: string; owner: string; steps: string[];
  context: string[]; output: string; gates: string; source_ids: string[]; related: string[];
  modes: string[]; hosts: string; canonical: string;
  replacement?: string; description?: string; source?: {path:string;revision:string}; invocations?: Record<string,string|null>;
}
export interface Atlas { repository:string; commit:string; checked_at:string; scope:string; sources:AtlasSource[]; commands:AtlasCommand[]; views:AtlasView[]; caveats:string[]; lensCount?:number }
export interface HostDescriptor { name: string; command_form: string; surface: { rules: Array<{ source_prefix: string; exclude: string[] }> } }
export const REVIEWED_AT = '9496cff6332fe0b97195b7ebe67b73f62f30e5b3';
export const OWNER_ROUTE = '/concepts/workflow-routes/';
export const ID = /^[a-z][a-z0-9-]*$/;
export const kinds: readonly AtlasKind[] = ['cmd','skill','agent','state','gate','out','warn'];
export const relations: Record<AtlasRelation,string> = {flow:'Execution',context:'Context / data',conditional:'Conditional / authority',return:'Return / repeat',stop:'Stop / refusal'};
export function escape(value:unknown):string { return String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!)); }
export function validSourcePath(path:string):boolean { return /^(?:(?:core|site|docs)\/[A-Za-z0-9_./-]+|CHANGELOG\.md)$/.test(path) && !path.split('/').some(p=>!p || p==='.' || p==='..'); }
export function sourceHref(source: {path:string;revision:string}):string {
  if (!/^[0-9a-f]{40}$/.test(source.revision) || !validSourcePath(source.path)) throw new Error('Invalid atlas source');
  return `https://github.com/arbiterForge/codeArbiter/blob/${source.revision}/${source.path}`;
}
export function invocation(host:HostDescriptor,entry:string):string|null {
  const rule=host.surface.rules.find(r=>r.source_prefix==='commands/');
  return !rule || rule.exclude.includes(`commands/${entry}.md`) ? null : host.command_form.replace('{name}',entry);
}
export function commandDescription(source:string):string {
  const front=/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/.exec(source)?.[1];
  const raw=front?.match(/^description:[ \t]*(.+)$/m)?.[1]?.trim();
  if(!raw || raw==='|' || raw==='>') throw new Error('Missing or multiline command description: add explicit parser support');
  if(raw.startsWith('"')) { const value:unknown=JSON.parse(raw); if(typeof value!=='string')throw new Error('Description must be text'); return value; }
  return raw.startsWith("'") && raw.endsWith("'") ? raw.slice(1,-1).replace(/''/g,"'") : raw;
}
/** Break lengths were recovered from the original vectors. No automatic grid or
 * prose shortening is allowed to replace the reviewed spatial composition. */
export function layoutLines(text:string,layout:TextLayout):string[] {
  const remaining=Array.from(text.trim().replace(/\s+/g,' '));
  const lines=layout.lengths.map(length=>{
    if(!Number.isInteger(length) || length<1)throw new Error('Invalid text break');
    const line=remaining.splice(0,length).join('');
    if(Array.from(line).length!==length)throw new Error('Text layout exceeds source');
    if(remaining[0]===' ')remaining.shift();
    return line;
  });
  if(remaining.length || lines.join(' ')!==text.trim().replace(/\s+/g,' '))throw new Error('Text layout no longer matches its source');
  return lines;
}
export function edgeRelevant(view:AtlasView,edge:AtlasEdge,route:string):boolean {
  return !route || (edge.routes.length ? edge.routes.includes(route) : !!view.nodes.find(n=>n.id===edge.a)?.routes.includes(route) && !!view.nodes.find(n=>n.id===edge.b)?.routes.includes(route));
}
export function validateAtlas(atlas:Atlas):string[] {
  const errors:string[]=[],views=new Set<string>(),nodesGlobal=new Set<string>(),commands=new Set(atlas.commands.map(c=>c.name)),sources=new Set<string>();
  if(atlas.repository!=='https://github.com/arbiterForge/codeArbiter' || !/^[0-9a-f]{40}$/.test(atlas.commit))errors.push('Invalid atlas identity');
  if(commands.size!==atlas.commands.length)errors.push('Duplicate commands');
  for(const s of atlas.sources) {
    if(!/^S[0-9]+$/.test(s.id))errors.push(`Invalid source identity ${s.id}`);
    if(sources.has(s.id))errors.push(`Duplicate source ${s.id}`);sources.add(s.id);
    let prefix:string;try{prefix=sourceHref({path:s.path,revision:atlas.commit});}catch{errors.push(`Invalid source path ${s.id}`);continue;}
    if(s.url!==prefix && !new RegExp('^'+prefix.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'#L[1-9][0-9]*(?:-L[1-9][0-9]*)?$').test(s.url))errors.push(`Invalid source URL ${s.id}`);
  }
  for(const c of atlas.commands) {
    if(!ID.test(c.name) || !['core','advanced','alias','internal','deprecated'].includes(c.visibility))errors.push(`Invalid command ${c.name}`);
    if(c.visibility==='alias' && (!c.canonical || c.canonical===c.name))errors.push(`Missing alias destination ${c.name}`);
    if(!c.steps.length || !c.output.trim() || !c.gates.trim())errors.push(`Incomplete command ${c.name}`);
    if(!commands.has(c.canonical))errors.push(`Unknown canonical entry ${c.name}`);
    for(const r of c.related)if(!commands.has(r))errors.push(`Unknown related command ${r}`);
    for(const s of c.source_ids)if(!sources.has(s))errors.push(`Unknown command source ${s}`);
  }
  for(const v of atlas.views) {
    if(!ID.test(v.id) || views.has(v.id))errors.push(`Invalid/duplicate view ${v.id}`);views.add(v.id);
    if(!Number.isFinite(v.width) || !Number.isFinite(v.height) || v.width<=0 || v.height<=0)errors.push(`Invalid canvas ${v.id}`);
    for(const p of v.panels)if(![p.x,p.y,p.w,p.h].every(Number.isFinite)||p.w<=0||p.h<=0)errors.push(`Invalid panel ${v.id}`);
    for(const note of v.notes)if(![note.x,note.y,note.size].every(Number.isFinite)||note.size<=0)errors.push(`Invalid note ${v.id}`);
    const nodes=new Set(v.nodes.map(n=>n.id));
    for(const n of v.nodes) {
      if(!ID.test(n.id) || nodesGlobal.has(n.id))errors.push(`Invalid/duplicate node ${n.id}`);nodesGlobal.add(n.id);
      if(!kinds.includes(n.kind) || !n.title.trim() || !n.source_ids.length)errors.push(`Incomplete node ${n.id}`);
      if(![n.x,n.y,n.w,n.h].every(Number.isFinite) || n.x<0 || n.y<0 || n.w<=0 || n.h<=0 || n.x+n.w>v.width || n.y+n.h>v.height)errors.push(`Invalid box ${n.id}`);
      for(const r of n.routes)if(!commands.has(r))errors.push(`Unknown node route ${r}`);
      for(const s of n.source_ids)if(!sources.has(s))errors.push(`Unknown node source ${s}`);
      try {for(const t of [n.layout.title,n.layout.body])if(t && (![t.size,t.y,t.line].every(Number.isFinite)||t.size<=0||t.line<0))throw new Error('Invalid text geometry');if(!Number.isFinite(n.layout.sourceY)||(n.layout.tagY!==null&&!Number.isFinite(n.layout.tagY)))throw new Error('Invalid label geometry');layoutLines(n.title,n.layout.title);if(n.layout.body)layoutLines(n.body,n.layout.body);else if(n.body)throw new Error('Missing body layout');}catch{errors.push(`Invalid text layout ${n.id}`);}
    }
    for(const e of v.edges) {
      if(!nodes.has(e.a) || !nodes.has(e.b) || !relations[e.kind] || e.points.length<2)errors.push(`Invalid edge ${v.id}:${e.a}:${e.b}`);
      if(e.points.some(p=>p.length!==2) || !e.points.flat().every(Number.isFinite))errors.push(`Invalid points ${v.id}`);
      if(e.label_at && (e.label_at.length!==2 || !e.label_at.every(Number.isFinite)))errors.push(`Invalid edge label ${v.id}`);
      for(const r of e.routes)if(!commands.has(r))errors.push(`Unknown edge route ${r}`);
      if(e.source_id && !sources.has(e.source_id))errors.push(`Unknown edge source ${e.source_id}`);
    }
  }
  for(const c of atlas.commands)if(!atlas.views.some(v=>v.nodes.some(n=>n.routes.includes(c.name))))errors.push(`Undrawn entry ${c.name}`);
  return errors;
}
/** Stable comparison with the original atlas, independent of theme/export markup. */
export function geometryRecord(v:AtlasView):unknown {
  return {size:[v.width,v.height],nodes:v.nodes.map(n=>[n.id,n.x,n.y,n.w,n.h,n.title,n.body,n.kind,n.routes,n.source_ids]),edges:v.edges.map(e=>[e.a,e.b,e.kind,e.label,e.points,e.label_at??null,e.routes]),panels:v.panels,notes:v.notes};
}
