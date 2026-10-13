/** Same graph, viewer and theme for native docs and portable editions. */
import {mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import ts from 'typescript';
import {loadAtlas,loadAtlasTheme} from './execution-maps/atlas';
import {renderAtlasHtml,renderAtlasSvg} from './execution-maps/atlas-render';
const site=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const atlas=loadAtlas(resolve(site,'..')),theme=loadAtlasTheme(resolve(site,'..'));
const destination=resolve(site,'public/workflow-atlas',atlas.commit);
mkdirSync(destination,{recursive:true});
const css=readFileSync(resolve(site,'src/styles/workflow-atlas.css'),'utf8');
const browser=ts.transpileModule(readFileSync(resolve(site,'src/scripts/workflow-atlas.ts'),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext},reportDiagnostics:true});
if(browser.diagnostics?.some(d=>d.category===ts.DiagnosticCategory.Error))throw new Error('Atlas browser compilation failed');
const body=renderAtlasHtml(atlas,theme,'',true);
function document(interactive:boolean):string {
  const content=interactive?body:body.replace(/<script type="application\/json" data-atlas-data>[\s\S]*?<\/script>/,'').replace(/<template\b[^>]*>[\s\S]*?<\/template>/g,'').replace('<details class="reading-wrap" id="atlas-reading">','<details open class="reading-wrap" id="atlas-reading">');
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>codeArbiter · Route Atlas</title><style>:root{${theme.variables}color-scheme:dark}*{box-sizing:border-box}body{margin:0 auto;padding:1rem;max-width:100rem;background:var(--ca-bg);color:var(--ca-ink-soft);font:1rem/1.65 var(--ca-font-sans)}body>header{display:flex;align-items:baseline;justify-content:space-between;gap:1rem;flex-wrap:wrap}h1{color:var(--ca-ink);font-size:var(--ca-text-xl);letter-spacing:-.025em}a{color:var(--ca-ink-soft)}${css}${interactive?'':'.ca-atlas .frame{display:none}.ca-atlas .reading-wrap::details-content{display:block;content-visibility:visible}.ca-atlas .reading-wrap>summary{display:none}'}</style></head><body data-pagefind-ignore="all"><header><h1>codeArbiter · Route Atlas</h1><a href="https://codearbiter.dev/concepts/workflow-routes/">Public documentation</a></header>${content}${interactive?`<script type="module">${browser.outputText.replace(/<\/script/gi,'<\\/script')}</script>`:''}</body></html>`;
}
writeFileSync(resolve(destination,'atlas.html'),document(true));
writeFileSync(resolve(destination,'reading-guide.html'),document(false));
for(const view of atlas.views)writeFileSync(resolve(destination,`${view.id}.svg`),renderAtlasSvg(atlas,view,theme));
writeFileSync(resolve(destination,'sources.json'),JSON.stringify({reviewedAt:atlas.commit,scope:atlas.scope,sources:atlas.sources,commands:atlas.commands.map(c=>({name:c.name,visibility:c.visibility,source:c.source,invocations:c.invocations}))},null,2)+'\n');
console.log(`Generated original route atlas: ${atlas.commands.length} entries, ${atlas.views.length} spatial maps -> ${destination}`);
