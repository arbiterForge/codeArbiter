/** Generated downloads are projections of the same model the Astro page uses. */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import { loadAtlas } from './execution-maps/atlas';
import { renderAtlasHtml, renderAtlasSvg } from './execution-maps/atlas-render';
import { escape } from './execution-maps/atlas-model';
const site=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const atlas=loadAtlas(resolve(site,'..'));
const destination=resolve(site,'public/workflow-atlas',atlas.reviewedAt);
mkdirSync(destination,{recursive:true});
const css=readFileSync(resolve(site,'src/styles/workflow-atlas.css'),'utf8');
const browserSource=readFileSync(resolve(site,'src/scripts/workflow-atlas.ts'),'utf8');
const browser=ts.transpileModule(browserSource,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext},reportDiagnostics:true});
if(browser.diagnostics?.some(d=>d.category===ts.DiagnosticCategory.Error))throw new Error('Atlas browser compilation failed');
const body=renderAtlasHtml(atlas,'',true);
function document(script:boolean):string {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>codeArbiter workflow atlas</title><style>body{margin:0 auto;padding:1rem;max-width:1100px;background:#111720;color:#edf1f6}*{box-sizing:border-box}${css}</style></head><body data-pagefind-ignore="all"><h1>codeArbiter workflow atlas</h1><p>Offline source explanation at ${escape(atlas.reviewedAt)}. <a href="https://codearbiter.dev/concepts/workflow-routes/">Public documentation</a></p><section id="workflow-atlas">${body}</section>${script?`<script type="module">${browser.outputText.replace(/<\/script/gi,'<\\/script')}</script>`:''}</body></html>`;
}
writeFileSync(resolve(destination,'atlas.html'),document(true));
writeFileSync(resolve(destination,'reading-guide.html'),document(false));
for(const view of atlas.views)writeFileSync(resolve(destination,`${view.id}.svg`),renderAtlasSvg(view));
writeFileSync(resolve(destination,'sources.json'),JSON.stringify({reviewedAt:atlas.reviewedAt,entries:atlas.entries.map(e=>({id:e.id,source:e.source,visibility:e.visibility,invocations:e.invocations})),views:atlas.views.map(v=>({id:v.id,sources:v.sources})),boundary:'Editorial source bindings. Not a released-artifact or installed-host qualification.'},null,2)+'\n');
console.log(`Generated workflow atlas: ${atlas.entries.length} entries, ${atlas.views.length} maps -> ${destination}`);
