/** An editorial projection. Neither a workflow engine nor a record of completed work. */
export type AtlasKind = 'command' | 'skill' | 'agent' | 'context' | 'state' | 'gate' | 'output';
export type AtlasRelation = 'sequence' | 'dispatch' | 'return' | 'repeat' | 'reuse' | 'context' | 'conditional';
export interface AtlasSource { path: string; revision: string; quote?: string; blob?: string }
export interface AtlasNode { id: string; kind: AtlasKind; title: string; detail: string; output: string; source: string; href?: string; checks?: string[]; conditional?: boolean }
export interface AtlasEdge { from: string; to: string; kind: AtlasRelation; label: string; detail: string; source: string }
export interface AtlasChapter { id: string; title: string; nodes: AtlasNode[]; question?: string; output?: string }
export interface AtlasView { id: string; title: string; boundary: string; outcome: string; sources: Record<string, AtlasSource>; chapters: AtlasChapter[]; edges: AtlasEdge[] }
export interface RouteMeta { visibility: string; workflow: string; canonical?: string; replacement?: string }
export interface AtlasEntry extends RouteMeta { id: string; description: string; views: string[]; source: AtlasSource; invocations: Record<string, string | null> }
export interface Atlas { reviewedAt: string; entries: AtlasEntry[]; views: AtlasView[]; lensCount: number }
export interface HostDescriptor { name: string; command_form: string; surface: { rules: Array<{ source_prefix: string; exclude: string[] }> } }
export const REVIEWED_AT = '9496cff6332fe0b97195b7ebe67b73f62f30e5b3';
export const OWNER_ROUTE = '/concepts/workflow-routes/';
export const ID = /^[a-z][a-z0-9-]*$/;
export const kinds: readonly AtlasKind[] = ['command','skill','agent','context','state','gate','output'];
export const relations: Record<AtlasRelation, string> = { sequence:'Next action', dispatch:'Bounded dispatch', return:'Return to caller', repeat:'Repeat with current evidence', reuse:'Reuse a procedure', context:'Context input, not authority', conditional:'Conditional continuation' };
export function escape(value: unknown): string { return String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!)); }
export function sourceHref(source: AtlasSource): string {
  if (!/^[0-9a-f]{40}$/.test(source.revision) || !/^(core|site|docs)\/[A-Za-z0-9_./-]+$/.test(source.path) || source.path.split('/').includes('..')) throw new Error('Invalid atlas source');
  return `https://github.com/arbiterForge/codeArbiter/blob/${source.revision}/${source.path}`;
}
export function invocation(host: HostDescriptor, entry: string): string | null {
  const rule = host.surface.rules.find(r => r.source_prefix === 'commands/');
  return !rule || rule.exclude.includes(`commands/${entry}.md`) ? null : host.command_form.replace('{name}', entry);
}
/** Descriptions come from the owning command, not a parallel inventory. */
export function commandDescription(source: string): string {
  const front = /^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/.exec(source)?.[1];
  const raw = front?.match(/^description:[ \t]*(.+)$/m)?.[1]?.trim();
  if (!raw || raw === '|' || raw === '>') throw new Error('Missing or multiline command description: add explicit parser support');
  if (raw.startsWith('"')) return JSON.parse(raw);
  return raw.startsWith("'") && raw.endsWith("'") ? raw.slice(1,-1).replace(/''/g,"'") : raw;
}
export function validateAtlas(atlas: Atlas): string[] {
  const errors: string[] = [];
  const entries = new Set<string>(), views = new Set<string>();
  if (!/^[0-9a-f]{40}$/.test(atlas.reviewedAt)) errors.push('Invalid review revision');
  for (const view of atlas.views) {
    if (!ID.test(view.id) || views.has(view.id)) errors.push(`Invalid/duplicate view ${view.id}`);
    views.add(view.id);
    const ids = new Set<string>(), chapters = new Set<string>();
    for (const chapter of view.chapters) {
      if (!ID.test(chapter.id) || chapters.has(chapter.id)) errors.push(`Invalid/duplicate chapter ${view.id}:${chapter.id}`);
      chapters.add(chapter.id);
      for (const node of chapter.nodes) {
        if (!ID.test(node.id) || ids.has(node.id)) errors.push(`Invalid/duplicate node ${view.id}:${node.id}`);
        ids.add(node.id);
        if (!kinds.includes(node.kind) || !node.detail.trim() || !node.output.trim() || !view.sources[node.source]) errors.push(`Incomplete node ${view.id}:${node.id}`);
        if (node.href && !/^\/(reference|guides|concepts)\/[a-z0-9/#-]+$/.test(node.href)) errors.push(`Invalid node link ${node.id}`);
      }
    }
    for (const edge of view.edges) if (!ids.has(edge.from) || !ids.has(edge.to) || !relations[edge.kind] || !view.sources[edge.source] || !edge.detail.trim()) errors.push(`Invalid handoff ${view.id}:${edge.from}:${edge.to}`);
    if (!view.boundary.trim() || !view.outcome.trim()) errors.push(`Missing boundary ${view.id}`);
    for (const source of Object.values(view.sources)) { try { sourceHref(source); } catch { errors.push(`Invalid source ${view.id}`); } }
  }
  for (const entry of atlas.entries) {
    if (!ID.test(entry.id) || entries.has(entry.id)) errors.push(`Invalid/duplicate entry ${entry.id}`);
    entries.add(entry.id);
    if (!['core','advanced','alias','internal','deprecated'].includes(entry.visibility)) errors.push(`Invalid visibility ${entry.id}`);
    for (const view of entry.views) if (!views.has(view)) errors.push(`Unknown entry view ${entry.id}:${view}`);
    if (entry.visibility === 'alias' && !entry.replacement) errors.push(`Missing alias replacement ${entry.id}`);
    try { sourceHref(entry.source); } catch { errors.push(`Invalid entry source ${entry.id}`); }
  }
  return errors;
}
