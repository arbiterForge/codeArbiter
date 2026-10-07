import { readFileSync, mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { loadAtlas, gitBlob, checkReviewedSource } from './atlas';
import { REVIEWED_AT, validateAtlas } from './atlas-model';
import { renderAtlasHtml } from './atlas-render';
import { featureMap } from './model';
import { workflows } from './workflows';
const root=new URL('../../../',import.meta.url);
describe('atlas against actual repository sources',()=>{
  it('covers the entire owning catalog with host-specific exposure',()=>{
    const a=loadAtlas();const catalog=JSON.parse(readFileSync(new URL('core/surface/command-routes.json',root),'utf8'));
    expect(a.entries.map(e=>e.id).sort()).toEqual(Object.keys(catalog.commands).sort());
    expect(validateAtlas(a)).toEqual([]);
    expect(a.entries.find(e=>e.id==='prune')!.invocations.codex).toBeNull();
    expect(a.entries.find(e=>e.id==='statusline')!.invocations.pi).toBeNull();
    expect(a.entries.find(e=>e.id==='cleanup')!.replacement).toBe('pr --cleanup');
    expect(a.entries.find(e=>e.id==='conflict')!.visibility).toBe('internal');
    expect(a.entries.find(e=>e.id==='btw')!.visibility).toBe('deprecated');
    expect(a.lensCount).toBe(13);
  });
  it('reuses every existing chapter node and edge without repinning its history',()=>{
    const a=loadAtlas();
    for(const original of [featureMap,...workflows.map(w=>w.map)]){
      const view=a.views.find(v=>v.id===original.id)!;
      expect(view.chapters.flatMap(c=>c.nodes.map(n=>n.id))).toEqual(original.chapters.flatMap(c=>c.nodes.map(n=>n.id)));
      expect(view.edges).toEqual([...original.chapters.flatMap(c=>c.edges),...original.alternatives]);
      for(const source of Object.values(view.sources))expect(source.revision).toBe(original.reviewedAt);
    }
  });
  it('keeps the existing page and adds a native component, not an iframe',()=>{
    const page=readFileSync(new URL('site/src/content/docs/concepts/workflow-routes.mdx',root),'utf8');
    expect(page).toContain('<WorkflowDirectory />');expect(page).toContain('<WorkflowAtlas />');expect(page).toContain('## Keep your place in a route');expect(page).not.toContain('<iframe');
    expect(renderAtlasHtml(loadAtlas(),'/nested/base')).toContain('/nested/base/workflow-atlas/');
  });
  it('rejects source drift and supports logical CRLF checkouts',()=>{
    const dir=mkdtempSync(join(tmpdir(),'ca-atlas-source-'));
    try{
      mkdirSync(join(dir,'core'));writeFileSync(join(dir,'core/source.md'),'source\r\n');
      const pin=gitBlob(Buffer.from('source\n'));
      expect(()=>checkReviewedSource(dir,'core/source.md',pin)).not.toThrow();
      writeFileSync(join(dir,'core/source.md'),'changed\n');expect(()=>checkReviewedSource(dir,'core/source.md',pin)).toThrow(/Atlas source changed/);
      expect(()=>checkReviewedSource(dir,'../outside.md',pin)).toThrow(/Invalid atlas source path/);
    }finally{rmSync(dir,{recursive:true,force:true});}
  });
  it('generates script-free and interactive editions with the same source identity',()=>{
    const base=new URL(`site/public/workflow-atlas/${REVIEWED_AT}/`,root);
    const plain=readFileSync(new URL('reading-guide.html',base),'utf8'),interactive=readFileSync(new URL('atlas.html',base),'utf8');
    expect(plain).not.toContain('<script');expect(interactive).toContain('<script type="module">');
    for(const doc of [plain,interactive]){expect(doc).toContain(REVIEWED_AT);expect(doc).toContain('name="robots" content="noindex"');expect(doc).toContain('data-pagefind-ignore="all"');expect(doc).not.toMatch(/\.woff2|<iframe/);}
  });
});
