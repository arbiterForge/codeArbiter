import { describe, expect, it } from 'vitest';
import { supplementalViews } from './atlas-content';
import { REVIEWED_AT, validateAtlas, sourceHref, invocation, commandDescription, type Atlas, type HostDescriptor } from './atlas-model';
import { renderAtlasHtml, renderAtlasSvg } from './atlas-render';
const fixture = ():Atlas => ({reviewedAt:REVIEWED_AT,lensCount:13,views:structuredClone(supplementalViews),entries:[{id:'fix',visibility:'core',workflow:'change',description:'Fix a confirmed bug.',views:['debug-fix'],source:{path:'core/surface/commands/fix.md',revision:REVIEWED_AT},invocations:{claude:'/ca:fix',codex:'$ca-fix',pi:'/ca-fix'}}]});
describe('workflow atlas model and exports',()=>{
  it('validates the actual supplemental graphs',()=>expect(validateAtlas(fixture())).toEqual([]));
  it('rejects dangling edges, sources and duplicate identities',()=>{
    const a=fixture();a.views[0].edges[0].to='missing';a.views[1].chapters[0].nodes[0].source='missing';a.views.push(a.views[0]);
    expect(validateAtlas(a).join('\n')).toMatch(/Invalid handoff/);expect(validateAtlas(a).join('\n')).toMatch(/Incomplete node/);expect(validateAtlas(a).join('\n')).toMatch(/duplicate view/);
  });
  it('rejects invalid role, entry target and alias metadata',()=>{
    const a=fixture();a.entries[0].views=['invented'];a.entries[0].visibility='alias';
    expect(validateAtlas(a).join('\n')).toContain('Unknown entry view');expect(validateAtlas(a).join('\n')).toContain('Missing alias replacement');
  });
  it('derives host spelling and exclusions from the descriptor',()=>{
    const host:HostDescriptor={name:'codex',command_form:'$ca-{name}',surface:{rules:[{source_prefix:'commands/',exclude:['commands/prune.md']} ]}};
    expect(invocation(host,'fix')).toBe('$ca-fix');expect(invocation(host,'prune')).toBeNull();
    expect(invocation({...host,surface:{rules:[]}},'fix')).toBeNull();
  });
  it('reads quoted, plain and CRLF descriptions without evaluating source',()=>{
    expect(commandDescription('---\r\ndescription: "A \\"quoted\\" word"\r\n---\r\n')).toBe('A "quoted" word');
    expect(commandDescription("---\ndescription: 'It''s a description'\n---\n")).toBe("It's a description");
    expect(commandDescription('---\ndescription: plain text\n---\n')).toBe('plain text');
    expect(()=>commandDescription('---\ndescription: >\n  folded\n---\n')).toThrow();
  });
  it('only emits pinned authorized source links',()=>{
    expect(sourceHref(fixture().entries[0].source)).toContain(`/blob/${REVIEWED_AT}/core/`);
    expect(()=>sourceHref({revision:REVIEWED_AT,path:'core/../../private.md'})).toThrow();
    expect(()=>sourceHref({revision:'main',path:'core/source.md'})).toThrow();
  });
  it('retains every node and directed handoff in both editions',()=>{
    const a=fixture(),html=renderAtlasHtml(a,'/project'),offline=renderAtlasHtml(a,'',true);
    for(const v of a.views)for(const chapter of v.chapters)for(const node of chapter.nodes){expect(html).toContain(`atlas-node-${v.id}-${node.id}`);expect(offline).toContain(`atlas-node-${v.id}-${node.id}`);}
    expect(html).toContain('/project/workflow-atlas/');expect(html).toContain('loading="lazy"');expect(html).not.toContain('<svg');expect(offline).toContain('<svg');
    expect(html).not.toMatch(/<iframe|localStorage|sessionStorage/);
  });
  it('escapes content and rejects invalid base URLs',()=>{
    const a=fixture();a.views[0].title='<script>alert("x")</script>';a.entries[0].description='<img onerror="alert(1)">';
    const html=renderAtlasHtml(a);expect(html).not.toContain('<script>');expect(html).toContain('&lt;script&gt;');expect(html).not.toContain('<img onerror');
    expect(()=>renderAtlasHtml(a,'//evil.test')).toThrow();expect(()=>renderAtlasHtml(a,'/"onclick=bad')).toThrow();
  });
  it('gives SVGs unique IDs and retains conditional return descriptions',()=>{
    const a=fixture(),svgs=a.views.map(renderAtlasSvg).join('');
    const ids=[...svgs.matchAll(/\bid="([^"]+)"/g)].map(match=>match[1]);expect(new Set(ids).size).toBe(ids.length);
    expect(svgs).toContain('Context input, not authority');expect(svgs).toContain('Conditional continuation');
    for(const v of a.views)expect(renderAtlasSvg(v)).toBe(renderAtlasSvg(v));
  });
});
