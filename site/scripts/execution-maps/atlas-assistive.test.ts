import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {beforeAll,describe,expect,it} from 'vitest';
import {ASSISTIVE_SOURCE_BLOBS,COMMAND_REMOVAL_SOURCE_BLOBS,CONTEXT_KNOWLEDGE_SOURCE_BLOBS,MARKER_PREFLIGHT_BLOB,SCHEMA_CACHE_RENDER_BLOB,loadAtlas,loadAtlasTheme,originalAtlas} from './atlas';
import {geometryRecord,REVIEWED_AT,validateAtlas} from './atlas-model';
import {nodeDetails,renderAtlasHtml,renderAtlasSvg} from './atlas-render';

const root=fileURLToPath(new URL('../../../',import.meta.url));
let atlas:ReturnType<typeof loadAtlas>;
beforeAll(()=>{atlas=loadAtlas(root);});

describe('assistive candidate versus retained historical routes',()=>{
  it('binds each current explanation to real tracked owner bytes, not a new release claim',()=>{
    const historical=readFileSync(new URL('./atlas-data/assistive-update.json',import.meta.url),'utf8').replace(/\r\n/g,'\n');
    expect(createHash('sha256').update(historical).digest('hex'))
      .toBe('13a52e112644d5698cd09afb74d7919ebb6f1d04e98a41d8f58304a4f744fb50');
    const update=atlas.sourceUpdate!;
    expect(update.revision).toBe('3549ed56f5d5849116aef8d5e946423d8ee677fc');
    expect(update.changes).toHaveLength(67);
    expect(Object.keys(ASSISTIVE_SOURCE_BLOBS)).toEqual(update.changes.map(change=>change.path));
    const objects=execFileSync('git',['--no-replace-objects','cat-file','--batch'],{
      cwd:root,input:update.changes.map(change=>`${change.blob}\n`).join(''),maxBuffer:4*1024*1024,
    });
    let offset=0;
    for(const change of update.changes) {
      const later=(change.path==='core/pysrc/_artifactauthoritylib.py'?MARKER_PREFLIGHT_BLOB:undefined)
        ??(change.path==='core/artifacts/internal/render/render.go'?SCHEMA_CACHE_RENDER_BLOB:undefined)
        ??CONTEXT_KNOWLEDGE_SOURCE_BLOBS[change.path]??COMMAND_REMOVAL_SOURCE_BLOBS[change.path];
      const current=readFileSync(new URL(`../../../${change.path}`,import.meta.url),'utf8').replace(/\r\n/g,'\n');
      const end=objects.indexOf(10,offset);
      expect(end).toBeGreaterThanOrEqual(offset);
      const headerText=objects.subarray(offset,end).toString('utf8');
      const header=/^([0-9a-f]{40}) blob (\d+)$/.exec(headerText);
      // Historical PR branch objects can disappear from a fresh clone after
      // that branch is removed. Current source still needs a reachable exact
      // binding; the historical OID remains recorded in the retained snapshot.
      if(headerText===`${change.blob} missing`) {
        offset=end+1;
        if(later) {
          expect(execFileSync('git',['--no-replace-objects','cat-file','blob',later],{cwd:root,encoding:'utf8'})).toBe(current);
        } else {
          expect(execFileSync('git',['rev-parse',`HEAD:${change.path}`],{cwd:root,encoding:'utf8'}).trim()).toBe(change.blob);
          expect(execFileSync('git',['show',`HEAD:${change.path}`],{cwd:root,encoding:'utf8'})).toBe(current);
        }
        expect(change.summary).not.toMatch(/fully converted|released in|all hosts qualified/);
        continue;
      }
      if(!header)throw new Error(`Invalid source object: ${change.path}`);
      expect(header[1]).toBe(change.blob);
      const size=Number(header[2]);
      expect(Number.isSafeInteger(size)).toBe(true);
      const bytes=objects.subarray(end+1,end+1+size);
      expect(bytes.length).toBe(size);
      expect(objects[end+1+size]).toBe(10);
      offset=end+2+size;
      // A later exact binding (the 2026-10-23 command removal, then the #1023
      // knowledge records) supersedes the PR983 bytes for its own files; the
      // PR983 blob itself stays recorded.
      expect(later?execFileSync('git',['--no-replace-objects','cat-file','blob',later],{cwd:root,encoding:'utf8'}):bytes.toString('utf8')).toBe(current);
      expect(change.summary).not.toMatch(/fully converted|released in|all hosts qualified/);
    }
    expect(offset).toBe(objects.length);
    expect(update.summary).toContain('Exact blob bindings identify inspected source bytes');
    expect(update.summary).toContain('linked revision is the committed source base');
    expect(update.summary).toContain('live host qualification and release remain separate claims');
  });

  it('retains original geometry and immutable source links while exposing the current difference',()=>{
    const original=originalAtlas();
    expect(original.sourceUpdate).toBeUndefined();
    expect(atlas.commit).toBe(REVIEWED_AT);
    expect(atlas.sources).toEqual(original.sources);
    expect(atlas.views.map(geometryRecord)).toEqual(original.views.map(geometryRecord));
    expect(atlas.scope).toMatch(/^Historical route snapshot/);
    expect(atlas.caveats.every(note=>note.startsWith('Historical snapshot: '))).toBe(true);
    expect(validateAtlas(atlas)).toEqual([]);
    const allText=atlas.sourceUpdate!.changes.map(change=>change.summary).join('\n');
    expect(allText).toContain('author a structurally valid draft');
    expect(atlas.sourceUpdate!.summary).toContain('real user stops and host permissions remain effective');
    expect(allText).toContain('without replacing the original task review');
    expect(allText).toContain('Read-only task-context');
    expect(allText).toContain('Features use current criterion-focused checks');
    expect(allText).toContain('passing characterization baselines');
    expect(allText).toContain('Two delivery attempts end with an advisory unknown observation');
    expect(allText).toContain('full dependency ancestry');
    expect(allText).toContain('independently BLOCKED task and its reason');
    expect(allText).toContain('unanswered legacy reconciliation');
    expect(allText).toContain('paired approval');
    expect(allText).toContain('Confirmed or captured decisions');
    expect(allText).toContain('content-addressed observed reply');
    expect(allText).toContain('strict scan bound');
    expect(allText).toContain('available on demand without burdening ordinary task context');
    expect(allText).toContain('ordinary task start');
    expect(allText.toLowerCase()).toContain('in-flight');
    expect(allText).toContain('Task-check observations now retain');
    expect(allText).toContain('scoped_changed');
    expect(allText).toContain('preserving recorded user stops');
    expect(allText).toContain('unassessed rather than blocking');
  });

  it('shows the distinction before the canvas, in affected node details, and in standalone exports',()=>{
    const theme=loadAtlasTheme(root),html=renderAtlasHtml(atlas,theme);
    expect(html.indexOf('data-atlas-source-update')).toBeLessThan(html.indexOf('class="frame"'));
    const feature=atlas.views.find(view=>view.id==='feature-sprint')!;
    const capability=feature.nodes.find(node=>node.id==='f-capability')!;
    expect(nodeDetails(atlas,capability)).toContain('Native Pi writer admission does not establish a complete live Pi workflow');
    for(const view of atlas.views)expect(renderAtlasSvg(atlas,view,theme)).toContain('HISTORICAL ROUTES  /  CODEARBITER');
    const exported=new URL(`../../../site/public/workflow-atlas/${REVIEWED_AT}/sources.json`,import.meta.url);
    expect(JSON.parse(readFileSync(exported,'utf8')).sourceUpdate).toEqual(atlas.sourceUpdate);
  });

  it('exposes current context callers and native writers at the historical permission and recovery nodes',()=>{
    const boundaries:Record<string,string[]>={
      'b-profile':['core/surface/skills/context-creation/SKILL.md','core/surface/agents/scout.md'],
      'b-refresh':['core/surface/skills/context-check/SKILL.md','core/pysrc/init-codearbiter.py'],
      'b-preview':['core/pysrc/_contextwriterlib.py','core/artifacts/internal/operations/context_assistive.go'],
      'b-approve':['core/surface/skills/context-creation/SKILL.md','core/artifacts/internal/operations/context_assistive.go'],
      'b-apply':['core/artifacts/internal/operations/context_assistive.go','core/artifacts/internal/contextdocument/operations.go'],
      'b-preserve':['core/artifacts/internal/contextdocument/document_selection.go','core/artifacts/internal/contextdocument/operations.go'],
      'b-finalize':['core/surface/skills/context-creation/SKILL.md','core/artifacts/internal/contextdocument/finalization.go'],
      'b-refreshed':['core/surface/skills/context-check/SKILL.md','core/artifacts/internal/contextdocument/document_selection.go'],
      'b-recover':['core/artifacts/internal/operations/context_assistive.go','core/artifacts/internal/contextdocument/operations.go'],
    };
    const brownfield=atlas.views.find(view=>view.id==='brownfield-lifecycle')!;
    for(const [id,owners] of Object.entries(boundaries)) {
      const node=brownfield.nodes.find(node=>node.id===id)!;
      const changes=atlas.sourceUpdate!.changes.filter(change=>change.nodes.includes(id));
      expect(changes.map(change=>change.path),id).toEqual(expect.arrayContaining(owners));
      const details=nodeDetails(atlas,node);
      expect(details,id).toContain('data-atlas-source-update');
      expect(details.indexOf('data-atlas-source-update'),id).toBeLessThan(details.indexOf('<h4>Related entries'));
      for(const path of owners)expect(details,id).toContain(
        `https://github.com/arbiterForge/codeArbiter/blob/${atlas.sourceUpdate!.revision}/${path}`,
      );
    }
    const original=originalAtlas().views.find(view=>view.id==='brownfield-lifecycle')!;
    expect(brownfield).toEqual(original);
  });

  it('binds greenfield finalization and advisory context to their current owners',()=>{
    const updates=atlas.sourceUpdate!.changes;
    const green=updates.find(change=>change.path==='core/surface/skills/decompose/SKILL.md')!;
    expect(green.nodes).toEqual(expect.arrayContaining(['o-green','c-green','c-store']));
    expect(green.summary).toContain('Five document/v2-provenance pairs');
    expect(green.summary).toContain('all thirteen outputs');
    const selector=updates.find(change=>change.path==='core/pysrc/_contextselectlib.py')!;
    expect(selector.nodes).toEqual(expect.arrayContaining(['c-select','c-compose','c-deliver','c-reselect']));
    expect(selector.summary).toContain('task-critical reference and constraint checks');
    expect(selector.summary).toContain('without another retry or an invented receipt');
    expect(updates.find(change=>change.path==='core/surface/commands/audit.md')!.summary)
      .toContain('timestamp and an ancestor commit');
  });

  it('rejects invalid source references or affected nodes and escapes explanatory text',()=>{
    const invalid=structuredClone(atlas);
    invalid.sourceUpdate!.changes[0].path='../outside.md';
    expect(validateAtlas(invalid)).toContain('Invalid atlas update source');
    const unknown=structuredClone(atlas);
    unknown.sourceUpdate!.changes[0].nodes=['missing-node'];
    expect(validateAtlas(unknown)).toContain('Unknown updated node missing-node');
    const escaped=structuredClone(atlas);
    escaped.sourceUpdate!.summary='<script>not executable</script>';
    const html=renderAtlasHtml(escaped,loadAtlasTheme(root));
    expect(html).toContain('&lt;script&gt;not executable&lt;/script&gt;');
    expect(html).not.toContain('<script>not executable</script>');
  });
});
