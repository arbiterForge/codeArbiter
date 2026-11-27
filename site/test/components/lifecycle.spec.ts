/** Actual component scripts in an isolated browser DOM; production-page proof is separate. */
import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import ts from 'typescript';
const source = (name: string) => process.env.COMPONENT_SOURCE_REF
  ? execFileSync('git',['show',`${process.env.COMPONENT_SOURCE_REF}:site/src/components/${name}.astro`],{encoding:'utf8'})
  : readFileSync(`src/components/${name}.astro`, 'utf8');
const script = (text: string) => ts.transpileModule(text.match(/<script>([\s\S]*?)<\/script>/)![1], { compilerOptions:{ target:ts.ScriptTarget.ES2022, module:ts.ModuleKind.ESNext } }).outputText;
for (const failure of ['query','data','expansion','stale']) test(`search recovers ${failure}`, async ({ page }) => {
  const text = source('Search');
  const markup = text.slice(text.indexOf('<ca-site-search'), text.indexOf('<script>')).replace('class={Astro.props.class} data-base={base}', 'data-base=""');
  await page.route('http://component.test/**', async route => {
    if (route.request().url().includes('/pagefind/')) return route.fulfill({ contentType:'text/javascript', body:`
      let attempt=0, failed=false;
      export async function options() {}
      export async function search(query) {
        const n=++attempt;
        if (${JSON.stringify(failure)}==='stale' && query==='old') { await new Promise(r=>setTimeout(r,600)); throw Error('old'); }
        if (${JSON.stringify(failure)}==='query' && n===1) throw Error('query');
        return {results:Array.from({length:${failure === 'expansion' ? 10 : 1}},(_,i)=>({async data(){
          if (${JSON.stringify(failure)}==='data' && n===1) throw Error('data');
          if (${JSON.stringify(failure)}==='expansion' && i===8 && !failed){failed=true;throw Error('expansion');}
          return {url:'/result',meta:{title:query+' '+i},excerpt:''};
        }}))};
      }` });
    return route.fulfill({ contentType:'text/html', body:`<!doctype html>${markup}<script type="module">${script(text)}</script>` });
  });
  await page.goto('http://component.test/');
  const input=page.getByRole('combobox');
  await input.fill(failure==='stale'?'old':'query');
  if (failure==='stale') {
    await page.waitForTimeout(180); await input.fill('new');
    await expect(page.getByRole('option')).toContainText('new'); await page.waitForTimeout(650);
    await expect(page.getByRole('option')).toContainText('new'); await expect(page.getByText('Retry search',{exact:true})).toBeHidden();
  } else if(failure==='expansion') {
    await expect(page.getByRole('option')).toHaveCount(8); await page.getByText('Show all 10 results').click();
    await expect(page.getByText('Retry loading more results')).toBeEnabled(); await expect(page.getByRole('option')).toHaveCount(8);
    await page.getByText('Retry loading more results').click(); await expect(page.getByRole('option')).toHaveCount(10);
  } else {
    await expect(page.getByText('Search is temporarily unavailable.')).toBeVisible(); await expect(input).toHaveValue('query');
    await page.getByText('Retry search',{exact:true}).click(); await expect(page.getByRole('option')).toHaveCount(1);
    await input.press('ArrowDown'); await expect(input).toHaveAttribute('aria-activedescendant','ca-search-opt-0');
  }
});
test('drawer reconnect owns exactly one set of opener, close and keyboard listeners',async({page})=>{
  await page.setContent(`<header>Header</header><main><div id="background" aria-hidden="false">Background</div><ca-splash-docs><div data-ca-docs-tray><button class="ca-docs-rail__opener" aria-expanded="false">Open</button><div data-ca-docs-drawer-layer hidden><button data-ca-docs-drawer-close>Close</button><div id="ca-docs-drawer" aria-hidden="true" tabindex="-1"><a href="#x">Link</a></div></div></div></ca-splash-docs></main>`);
  await page.addScriptTag({type:'module',content:script(source('SplashDocsRail'))});
  await page.waitForFunction(()=>!!customElements.get('ca-splash-docs'));
  for(let i=0;i<3;i++) {
    await page.evaluate(()=>{const el=document.querySelector('ca-splash-docs')!;const parent=el.parentElement!;el.remove();parent.append(el);});
    const open=page.getByRole('button',{name:'Open documentation navigation'});
    // Initial DOM fixture starts with a plain label; closing initializes the accessible label.
    const opener=page.locator('.ca-docs-rail__opener');
    await opener.click(); await expect(opener).toHaveAttribute('aria-expanded','true');
    await expect(page.locator('#background')).toHaveAttribute('aria-hidden','true');
    await page.keyboard.press('Escape'); await expect(opener).toHaveAttribute('aria-expanded','false');
    await expect(page.locator('#background')).toHaveAttribute('aria-hidden','false');
    await expect(opener).toBeFocused();
  }
});
