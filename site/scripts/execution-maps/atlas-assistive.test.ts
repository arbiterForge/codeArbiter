import {execFileSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {beforeAll,describe,expect,it} from 'vitest';
import {ASSISTIVE_SOURCE_BLOBS,loadAtlas,loadAtlasTheme,originalAtlas} from './atlas';
import {geometryRecord,REVIEWED_AT,validateAtlas} from './atlas-model';
import {nodeDetails,renderAtlasHtml,renderAtlasSvg} from './atlas-render';

const root=fileURLToPath(new URL('../../../',import.meta.url));
let atlas:ReturnType<typeof loadAtlas>;
beforeAll(()=>{atlas=loadAtlas(root);});

describe('partial assistive implementation versus retained historical routes',()=>{
  it('binds each current explanation to real tracked owner bytes, not a new release claim',()=>{
    const update=atlas.sourceUpdate!;
    expect(update.revision).toBe('95e8e18c3d6c2f9fecb74bccc40416c7a684cce1');
    expect(update.changes).toHaveLength(37);
    expect(Object.keys(ASSISTIVE_SOURCE_BLOBS)).toEqual(update.changes.map(change=>change.path));
    for(const change of update.changes) {
      const bytes=execFileSync('git',['--no-replace-objects','cat-file','blob',change.blob],{cwd:root});
      const current=readFileSync(new URL(`../../../${change.path}`,import.meta.url),'utf8').replace(/\r\n/g,'\n');
      expect(bytes.toString('utf8')).toBe(current);
      expect(change.summary).not.toMatch(/fully converted|released in|all hosts qualified/);
    }
    expect(update.summary).toContain('remain incomplete');
    expect(update.summary).toContain('No release or installed-host qualification');
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
    expect(atlas.sourceUpdate!.summary).toContain('no duplicate permission ceremony');
    expect(allText).toContain('without replacing the original task review');
    expect(allText).toContain('Read-only task-context');
    expect(allText).toContain('Matching an agreed criterion needs no additional artifact approval');
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
