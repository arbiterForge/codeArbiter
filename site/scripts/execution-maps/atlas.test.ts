import {readFileSync,mkdtempSync,mkdirSync,writeFileSync,rmSync,symlinkSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {afterAll,beforeAll,describe,expect,it} from 'vitest';
import {loadAtlas,loadAtlasTheme,originalAtlas,checkReviewedSource,REVALIDATED_AT} from './atlas';
import {commandMetadata} from './atlas-command';
import {REVIEWED_AT,validateAtlas,geometryRecord} from './atlas-model';
import {renderAtlasHtml,renderAtlasSvg} from './atlas-render';
import provenance from './atlas-data/provenance.json';
const root=new URL('../../../',import.meta.url);

describe('atlas source and original-composition regression contract',()=>{
  it('covers the exact catalog, original detail and real host exposure',()=>{
    const a=loadAtlas(),catalog=JSON.parse(readFileSync(new URL('core/surface/command-routes.json',root),'utf8'));
    expect(a.commands.map(c=>c.name).sort()).toEqual(Object.keys(catalog.commands).sort());expect(validateAtlas(a)).toEqual([]);
    expect(a.commands.find(c=>c.name==='prune')!.invocations!.codex).toBeNull();expect(a.commands.find(c=>c.name==='statusline')!.invocations!.pi).toBeNull();
    expect(a.commands.find(c=>c.name==='cleanup')!.replacement).toBe('pr --cleanup');expect(a.commands.find(c=>c.name==='conflict')!.visibility).toBe('internal');expect(a.commands.find(c=>c.name==='btw')!.visibility).toBe('deprecated');expect(a.lensCount).toBe(13);
    for(const c of originalAtlas().commands){const current=a.commands.find(x=>x.name===c.name)!;for(const key of ['steps','context','output','gates','source_ids'] as const)expect(current[key]).toEqual(c[key]);}
  });
  it('matches every original box, routed edge, label, route membership and panel',()=>{
    const a=originalAtlas();
    expect(a.views.map(v=>v.id)).toEqual(['all-routes','feature-sprint','context-layers','change-lanes','review-delivery','knowledge-operations','brownfield-lifecycle','debug-handoff','tribunal-lifecycle']);
    const pins=provenance.geometrySha256 as Record<string,string>;
    for(const v of a.views)expect(createHash('sha256').update(JSON.stringify(geometryRecord(v))).digest('hex')).toBe(pins[v.id]);
    const changed=structuredClone(a.views[0]);changed.nodes[0].x++;
    expect(createHash('sha256').update(JSON.stringify(geometryRecord(changed))).digest('hex')).not.toBe(pins[changed.id]);
  });
  it('preserves prior chapter addresses while placing the restored canvas first',()=>{
    const page=readFileSync(new URL('site/src/content/docs/concepts/workflow-routes.mdx',root),'utf8');
    expect(page).toContain('<WorkflowDirectory />');expect(page).toContain('<WorkflowAtlas />');expect(page).toContain('## Keep your place in a route');expect(page).toContain('tableOfContents: false');expect(page).not.toContain('<iframe');
    expect(page.indexOf('<WorkflowAtlas />')).toBeLessThan(page.indexOf('<WorkflowDirectory />'));
    expect(renderAtlasHtml(loadAtlas(),loadAtlasTheme(),'/nested/base')).toContain('/nested/base/workflow-atlas/');
  });
  it('rejects source drift and preserves logical CRLF checkout support',()=>{
    const dir=mkdtempSync(join(tmpdir(),'ca-atlas-source-'));
    try{
      execFileSync('git',['init','--quiet',dir]);
      mkdirSync(join(dir,'core'));writeFileSync(join(dir,'core/source.md'),'source\r\n');
      const pin=execFileSync('git',['hash-object','-w','--stdin'],{cwd:dir,input:'source\n',encoding:'utf8'}).trim();
      expect(()=>checkReviewedSource(dir,'core/source.md',pin)).not.toThrow();
      for(const invalid of [pin.slice(0,12),`${pin}^{blob}`])expect(()=>checkReviewedSource(dir,'core/source.md',invalid)).toThrow(/Atlas source changed/);
      writeFileSync(join(dir,'core/source.md'),'changed\n');expect(()=>checkReviewedSource(dir,'core/source.md',pin)).toThrow(/Atlas source changed/);
      expect(()=>checkReviewedSource(dir,'../outside.md',pin)).toThrow(/Invalid atlas source path/);
      expect(()=>checkReviewedSource(dir,'core/source.md')).toThrow(/needs reviewed Git object/);
    }finally{rmSync(dir,{recursive:true,force:true});}
  });
  it('does not follow a symlinked parent into another tree',()=>{
    const dir=mkdtempSync(join(tmpdir(),'ca-atlas-link-'));
    try{
      mkdirSync(join(dir,'core'));mkdirSync(join(dir,'actual'));writeFileSync(join(dir,'actual/source.md'),'source\n');symlinkSync(join(dir,'actual'),join(dir,'core/alias'),'junction');
      expect(()=>checkReviewedSource(dir,'core/alias/source.md','0'.repeat(40))).toThrow(/symlink/);
    }finally{rmSync(dir,{recursive:true,force:true});}
  });
  it('requires an explicit reviewed blob even when current text has that identity',()=>{
    const dir=mkdtempSync(join(tmpdir(),'ca-atlas-missing-blob-'));
    try{
      execFileSync('git',['init','--quiet',dir]);
      mkdirSync(join(dir,'core'));writeFileSync(join(dir,'core/source.md'),'source\n');
      const pin=execFileSync('git',['hash-object','--stdin'],{cwd:dir,input:'source\n',encoding:'utf8'}).trim();
      expect(()=>checkReviewedSource(dir,'core/source.md',pin)).toThrow(/needs reviewed Git object/);
    }finally{rmSync(dir,{recursive:true,force:true});}
  });
  it('isolates reviewed blobs from inherited Git repository variables',()=>{
    const dir=mkdtempSync(join(tmpdir(),'ca-atlas-git-env-'));
    const selected=join(dir,'selected'),other=join(dir,'other');
    const fixtureEnv=Object.fromEntries(Object.entries(process.env).filter(([name])=>!name.toUpperCase().startsWith('GIT_')));
    try{
      for(const repo of [selected,other])execFileSync('git',['init','--quiet',repo],{env:fixtureEnv});
      mkdirSync(join(selected,'core'));writeFileSync(join(selected,'core/source.md'),'selected source\n');
      const pin=execFileSync('git',['hash-object','-w','--stdin'],{cwd:selected,env:fixtureEnv,input:'selected source\n',encoding:'utf8'}).trim();
      const foreignPin=execFileSync('git',['hash-object','-w','--stdin'],{cwd:other,env:fixtureEnv,input:'foreign source\n',encoding:'utf8'}).trim();
      const script=`
        import { strict as assert } from 'node:assert';
        import { checkReviewedSource } from ${JSON.stringify(new URL('./atlas.ts',import.meta.url).href)};
        checkReviewedSource(${JSON.stringify(selected)},'core/source.md',${JSON.stringify(pin)});
        assert.throws(()=>checkReviewedSource(${JSON.stringify(selected)},'core/source.md',${JSON.stringify(foreignPin)}),/needs reviewed Git object/);
        console.log('selected repository verified');
      `;
      const output=execFileSync(process.execPath,['--import','tsx','--input-type=module','--eval',script],{
        cwd:new URL('site/',root),encoding:'utf8',
        env:{...fixtureEnv,GIT_DIR:join(other,'.git'),GIT_WORK_TREE:other,
          GIT_COMMON_DIR:join(other,'.git'),GIT_INDEX_FILE:join(other,'.git','index'),
          GIT_OBJECT_DIRECTORY:join(other,'.git','objects'),
          GIT_ALTERNATE_OBJECT_DIRECTORIES:join(other,'.git','objects')},
      });
      expect(output.trim()).toBe('selected repository verified');
    }finally{rmSync(dir,{recursive:true,force:true});}
  });
  describe('Git replacement refs',()=>{
    let dir:string,pin:string;
    beforeAll(()=>{
      dir=mkdtempSync(join(tmpdir(),'ca-atlas-replace-'));
      const fixtureEnv=Object.fromEntries(Object.entries(process.env).filter(([name])=>!name.toUpperCase().startsWith('GIT_')));
      const git=(args:string[],input?:string):string=>execFileSync('git',args,{cwd:dir,env:fixtureEnv,input,encoding:'utf8'}).trim();
      const atlas=originalAtlas(),lensDir='core/surface/skills/tribunal/references/lenses';
      const inputs=new Set(['core/hosts.json',lensDir,...atlas.sources.filter(source=>!source.path.startsWith('site/')).map(source=>source.path)]);
      for(const command of atlas.commands)commandMetadata(command.name,path=>{
        inputs.add(path);return readFileSync(new URL(path,root),'utf8');
      });
      git(['clone','--quiet','--shared','--no-checkout',fileURLToPath(root),dir]);
      git(['restore',`--source=${REVALIDATED_AT}`,'--worktree','--',...inputs]);
      pin=git(['hash-object','-w','--stdin'],'reviewed source\n');
      const replacement=git(['hash-object','-w','--stdin'],'changed source\n');
      git(['replace',pin,replacement]);
      writeFileSync(join(dir,'core/source.md'),'changed source\n');
      const reviewedTree=git(['rev-parse',`${REVALIDATED_AT}:${lensDir}`]);
      const emptyTree=git(['mktree'],'');
      git(['replace',reviewedTree,emptyTree]);
    });
    afterAll(()=>{if(dir)rmSync(dir,{recursive:true,force:true});});
    it('ignores replacement refs for reviewed blobs and lens rosters',()=>{
      expect.soft(()=>checkReviewedSource(dir,'core/source.md',pin)).toThrow(/Atlas source changed/);
      expect(loadAtlas(dir).lensCount).toBe(13);
    });
  });
  it('exports the same spatial SVGs and source identity, without font payloads',()=>{
    const a=loadAtlas(),t=loadAtlasTheme(),base=new URL(`site/public/workflow-atlas/${REVIEWED_AT}/`,root);
    const plain=readFileSync(new URL('reading-guide.html',base),'utf8'),interactive=readFileSync(new URL('atlas.html',base),'utf8');
    expect(plain).not.toContain('<script');expect(interactive).toContain('<script type="module">');
    for(const doc of [plain,interactive]){expect(doc).toContain(REVIEWED_AT);expect(doc).toContain('name="robots" content="noindex"');expect(doc).toContain('data-pagefind-ignore="all"');expect(doc).not.toMatch(/\.woff2|<iframe/);}
    for(const v of a.views)expect(readFileSync(new URL(v.id+'.svg',base),'utf8')).toBe(renderAtlasSvg(a,v,t));
    expect(interactive).toContain('href="./all-routes.svg"');expect(interactive).toContain('data-node-inspector="t-done"');expect(interactive).toContain('run-completed');
  });
});
