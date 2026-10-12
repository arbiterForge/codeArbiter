import {describe,expect,it} from 'vitest';
import {readFileSync} from 'node:fs';
import {originalAtlas} from './atlas';
import {REVIEWED_AT,validateAtlas,sourceHref,invocation,commandDescription,layoutLines,edgeRelevant,type HostDescriptor} from './atlas-model';
import {renderAtlasHtml,renderAtlasSvg} from './atlas-render';
import {atlasTheme} from './atlas-theme';
const theme=()=>atlasTheme(readFileSync(new URL('../../src/styles/design-system.css',import.meta.url),'utf8'));

describe('original spatial atlas model and exports',()=>{
  it('validates all nine original maps and the complete entry set',()=>{
    const a=originalAtlas();expect(validateAtlas(a)).toEqual([]);
    expect(a.commands).toHaveLength(37);expect(a.views).toHaveLength(9);
    expect(a.views.flatMap(v=>v.nodes)).toHaveLength(213);expect(a.views.flatMap(v=>v.edges)).toHaveLength(178);
  });
  it('rejects dangling handoffs, missing sources and duplicate identities',()=>{
    const a=originalAtlas();a.views[0].edges[0].b='missing';a.views[1].nodes[0].source_ids=['missing'];a.views.push(structuredClone(a.views[0]));
    const errors=validateAtlas(a).join('\n');expect(errors).toContain('Invalid edge');expect(errors).toContain('Unknown node source');expect(errors).toContain('duplicate view');expect(errors).toContain('duplicate node');
  });
  it('rejects unknown roles, route metadata and incomplete alias destinations',()=>{
    const a=originalAtlas();a.views[0].nodes[0].routes=['invented'];a.commands[0].visibility='invented';a.commands[1].visibility='alias';
    const errors=validateAtlas(a).join('\n');expect(errors).toContain('Unknown node route');expect(errors).toContain('Invalid command');expect(errors).toContain('Missing alias destination');
  });
  it('derives host spelling and exclusions from the descriptor',()=>{
    const host:HostDescriptor={name:'codex',command_form:'$ca-{name}',surface:{rules:[{source_prefix:'commands/',exclude:['commands/prune.md']}]}};
    expect(invocation(host,'fix')).toBe('$ca-fix');expect(invocation(host,'prune')).toBeNull();expect(invocation({...host,surface:{rules:[]}},'fix')).toBeNull();
  });
  it('reads quoted, plain and CRLF descriptions without evaluating source',()=>{
    expect(commandDescription('---\r\ndescription: "A \\"quoted\\" word"\r\n---\r\n')).toBe('A "quoted" word');
    expect(commandDescription("---\ndescription: 'It''s a description'\n---\n")).toBe("It's a description");
    expect(commandDescription('---\ndescription: plain text\n---\n')).toBe('plain text');
    expect(()=>commandDescription('---\ndescription: >\n  folded\n---\n')).toThrow();
  });
  it('only admits pinned authorized source paths and rejects forged URLs',()=>{
    expect(sourceHref({revision:REVIEWED_AT,path:'core/surface/commands/fix.md'})).toContain(`/blob/${REVIEWED_AT}/core/`);
    for(const path of ['core/../../private.md','core//file.md','/core/file.md','site/a?b'])expect(()=>sourceHref({revision:REVIEWED_AT,path})).toThrow();
    expect(()=>sourceHref({revision:'main',path:'core/source.md'})).toThrow();
    const a=originalAtlas();a.sources[0].url='javascript:alert(1)';expect(validateAtlas(a).join('\n')).toContain('Invalid source URL');
  });
  it('retains original line breaks and refuses silent reflow after text changes',()=>{
    const a=originalAtlas();for(const n of a.views.flatMap(v=>v.nodes)){
      expect(layoutLines(n.title,n.layout.title).join(' ')).toBe(n.title.trim().replace(/\s+/g,' '));
      if(n.layout.body)expect(layoutLines(n.body,n.layout.body).join(' ')).toBe(n.body.trim().replace(/\s+/g,' '));
    }
    a.views[0].nodes[0].title+=' changed';expect(validateAtlas(a).join('\n')).toContain('Invalid text layout');
    a.views[0].edges[0].points[0][0]=Infinity;expect(validateAtlas(a).join('\n')).toContain('Invalid points');
  });
  it('preserves explicit edge membership instead of inferring reachability',()=>{
    const v=originalAtlas().views[0],edge=v.edges[0];edge.routes=['fix'];
    expect(edgeRelevant(v,edge,'')).toBe(true);expect(edgeRelevant(v,edge,'fix')).toBe(true);expect(edgeRelevant(v,edge,'feature')).toBe(false);
    edge.routes=[];v.nodes.find(n=>n.id===edge.a)!.routes=['feature'];v.nodes.find(n=>n.id===edge.b)!.routes=['feature'];expect(edgeRelevant(v,edge,'feature')).toBe(true);
  });
  it('keeps a live diagram, inert view templates and the same static reading path',()=>{
    const a=originalAtlas(),t=theme(),html=renderAtlasHtml(a,t,'/project'),offline=renderAtlasHtml(a,t,'',true);
    for(const v of a.views){expect(html).toContain(`data-svg-template="${v.id}"`);for(const n of v.nodes){expect(html).toContain(`atlas-read-node-${v.id}-${n.id}`);expect(offline).toContain(`atlas-read-node-${v.id}-${n.id}`);}}
    expect(html).toContain('/project/workflow-atlas/');expect(offline).toContain('href="./all-routes.svg"');expect(html).toContain('data-atlas-stage');expect(html).toContain('<svg');
    expect(html).not.toMatch(/<iframe|localStorage|sessionStorage/);
  });
  it('escapes hostile text, embedded data and invalid site bases',()=>{
    const a=originalAtlas();a.views[0].title='<script>alert("x")</script>';a.commands[0].steps=['<img onerror="alert(1)">'];
    const html=renderAtlasHtml(a,theme());expect(html).not.toContain('<script>alert');expect(html).toContain('&lt;script&gt;');expect(html).not.toContain('<img onerror');expect(html).toContain('\\u003cscript');
    expect(()=>renderAtlasHtml(a,theme(),'//evil.test')).toThrow();expect(()=>renderAtlasHtml(a,theme(),'/"onclick=bad')).toThrow();
  });
  it('renders every original polyline and stable node identity without a replacement grid',()=>{
    const a=originalAtlas(),t=theme(),svgs=a.views.map(v=>renderAtlasSvg(a,v,t));
    const ids=[...svgs.join('').matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]);expect(new Set(ids).size).toBe(ids.length);
    for(const [i,v] of a.views.entries()){
      expect(svgs[i]).toBe(renderAtlasSvg(a,v,t));
      for(const e of v.edges)expect(svgs[i]).toContain(`points="${e.points.map(p=>p.join(',')).join(' ')}"`);
      expect(svgs[i]).not.toContain('<image');
    }
    expect(svgs.join('')).toContain('Context / data');expect(svgs.join('')).toContain('Conditional / authority');
  });
  it('resolves exported colors from the site and excludes font files and unsafe tokens',()=>{
    const css=readFileSync(new URL('../../src/styles/design-system.css',import.meta.url),'utf8'),t=theme();
    expect(t.bg).toBe('#090d12');expect(t.conditional).toBe('#f0b92f');expect(t.variables).not.toMatch(/url\(|\.woff|@font-face/);
    expect(atlasTheme(css.replace('--ca-bg: #090d12;','--ca-bg: #010203;')).bg).toBe('#010203');
    expect(()=>atlasTheme(css.replace('--ca-bg: #090d12;','--ca-bg: var(--ca-bg);'))).toThrow(/cyclic/);
    expect(()=>atlasTheme(css.replace('--ca-bg: #090d12;','--ca-bg: url(https://invalid.example);'))).toThrow(/Unsafe/);
  });
});
