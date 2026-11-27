/** Prepared only: invoked by the reviewed controller after original artifact admission. */
const fs=require('node:fs');
const crypto=require('node:crypto');
const assert=require('node:assert/strict');
const config=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const {chromium,expect}=require(config.playwright);
const hash=value=>crypto.createHash('sha256').update(value).digest('hex');
const results=[];
let browser,cleanup='not-started',browserVersion=null;
const targets=mode=>{
  const root=document.querySelector('ca-splash-docs');
  const tray=root.querySelector('[data-ca-docs-tray]');
  const values=[...tray.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),summary,[tabindex]:not([tabindex="-1"])')]
    .filter(e=>!e.hasAttribute('hidden')&&e.getAttribute('aria-hidden')!=='true'&&!e.closest('[inert]')&&e.getClientRects().length>0);
  if(mode==='count')return values.length;
  if(mode==='focus-last'){values.at(-1).focus();return true;}
  if(mode==='is-first')return document.activeElement===values[0];
  if(mode==='is-last')return document.activeElement===values.at(-1);
  throw Error('Unknown bounded focus observation');
};
async function seed(page){
  await page.goto('/',{waitUntil:'load'});
  await page.waitForFunction(()=>document.querySelector('ca-splash-docs')?.dataset.initialized==='true');
  await page.evaluate(async()=>{await document.fonts.ready;});
  return page.evaluate(()=>{
    const element=document.querySelector('ca-splash-docs');
    const nodes=[...new Set([document.querySelector('header'),...[...element.parentElement.children].filter(e=>e!==element)].filter(e=>e instanceof HTMLElement))];
    if(nodes.length<2)throw Error('Insufficient real background targets');
    document.body.style.overflow='clip';
    nodes.forEach((node,index)=>{
      node.inert=index===0;
      if(index%2===0)node.removeAttribute('aria-hidden');else node.setAttribute('aria-hidden','false');
    });
    window.__drawerBaseline={overflow:'clip',nodes:nodes.map(node=>({node,inert:node.inert,aria:node.getAttribute('aria-hidden')}))};
    return {backgroundCount:nodes.length};
  });
}
async function assertOpen(page){
  const opener=page.locator('ca-splash-docs .ca-docs-rail__opener');
  await opener.click();
  await expect(opener).toHaveAttribute('aria-expanded','true');
  await expect(page.getByRole('dialog',{name:'Documentation navigation',exact:true})).toBeVisible();
  await expect(page.locator('#ca-docs-drawer')).toHaveAttribute('aria-hidden','false');
  const state=await page.evaluate(()=>{
    const element=document.querySelector('ca-splash-docs'),drawer=element.querySelector('#ca-docs-drawer');
    return {overflow:document.body.style.overflow,drawerInert:drawer.inert,
      focusInsideDrawer:drawer.contains(document.activeElement),
      backgroundsLocked:window.__drawerBaseline.nodes.every(({node})=>node.inert&&node.getAttribute('aria-hidden')==='true')};
  });
  assert.deepEqual(state,{overflow:'hidden',drawerInert:false,focusInsideDrawer:true,backgroundsLocked:true});
  return state;
}
async function assertRestored(page,detached=false){
  const state=await page.evaluate(()=>{
    const element=document.querySelector('ca-splash-docs')||window.__drawerWitness?.element;
    const opener=element.querySelector('.ca-docs-rail__opener'),drawer=element.querySelector('#ca-docs-drawer');
    return {overflow:document.body.style.overflow,drawerInert:drawer.inert,drawerAria:drawer.getAttribute('aria-hidden'),
      layerHidden:element.querySelector('[data-ca-docs-drawer-layer]').hidden,
      expanded:opener.getAttribute('aria-expanded'),role:element.querySelector('[data-ca-docs-tray]').getAttribute('role'),
      exactBackgrounds:window.__drawerBaseline.nodes.every(({node,inert,aria})=>node.inert===inert&&node.getAttribute('aria-hidden')===aria),
      openerFocused:document.activeElement===opener,focusInDetached:!element.isConnected&&element.contains(document.activeElement)};
  });
  assert.equal(state.overflow,'clip');assert.equal(state.drawerInert,true);assert.equal(state.drawerAria,'true');
  assert.equal(state.layerHidden,true);assert.equal(state.expanded,'false');assert.equal(state.role,null);
  assert.equal(state.exactBackgrounds,true);assert.equal(state.openerFocused,!detached);assert.equal(state.focusInDetached,false);
  return state;
}
async function bounded(name,fn){
  let context,timer;const blocked=[];
  const started=Date.now();
  try{
    context=await browser.newContext({baseURL:config.origin,viewport:{width:390,height:844},serviceWorkers:'block'});
    await context.route('**/*',route=>{
      const url=new URL(route.request().url());
      if((url.origin===config.origin&&!url.username&&!url.password)||['blob:','data:'].includes(url.protocol))return route.continue();
      blocked.push({scheme:['http:','https:'].includes(url.protocol)?url.protocol:'other',url_sha256:hash(url.href)});
      return route.abort('blockedbyclient');
    });
    const page=await context.newPage();page.setDefaultTimeout(2000);page.setDefaultNavigationTimeout(10000);
    const observation=await Promise.race([fn(page),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('case deadline')),10000);})]);
    assert.equal(blocked.length,0,'External resource request refused');
    results.push({name,status:'PASSED',seconds:(Date.now()-started)/1000,observation,blocked});
  }catch(error){
    const data=String(error.stack||error);
    results.push({name,status:'FAILED',seconds:(Date.now()-started)/1000,
      error_bytes:Buffer.byteLength(data),error_sha256:hash(data),blocked});
  }finally{
    clearTimeout(timer);if(context)await context.close();
  }
}
(async()=>{
  try{
    browser=await chromium.launch({executablePath:config.chrome,headless:true,timeout:10000});
    browserVersion=browser.version();cleanup='pending';
    await bounded('original built drawer restores seeded state after Escape',async page=>{
      const seeded=await seed(page),opened=await assertOpen(page);
      await page.keyboard.press('Escape');
      const closed=await assertRestored(page);
      return {seeded,opened,closed};
    });
    await bounded('original built backdrop restores seeded state',async page=>{
      const seeded=await seed(page);await assertOpen(page);
      const control=page.locator('ca-splash-docs [data-ca-docs-drawer-close]');
      await expect(control).toHaveCount(1);
      const box=await control.boundingBox();assert(box&&box.width>8&&box.height>8);
      await control.click({position:{x:box.width-4,y:4}});
      return {seeded,closed:await assertRestored(page)};
    });
    await bounded('original built drawer traps forward and reverse boundary focus',async page=>{
      await seed(page);await assertOpen(page);
      // Use the exact owner eligibility predicate on the real built DOM, not fixture elements.
      const count=await page.evaluate(targets,'count');assert(count>=2);
      await page.evaluate(targets,'focus-last');
      await page.keyboard.press('Tab');
      assert.equal(await page.evaluate(targets,'is-first'),true);
      await page.keyboard.press('Shift+Tab');
      assert.equal(await page.evaluate(targets,'is-last'),true);
      await page.keyboard.press('Escape');await assertRestored(page);
      return {eligibleTargets:count,forwardWrapped:true,reverseWrapped:true};
    });
    await bounded('original built detached drawer releases Escape and initialized marker',async page=>{
      await seed(page);
      const capture=await page.evaluate(()=>{
        const element=document.querySelector('ca-splash-docs'),parent=element.parentElement,next=element.nextSibling;
        const records=[],descriptor=Object.getOwnPropertyDescriptor(document,'addEventListener');
        const native=document.addEventListener;
        document.addEventListener=function(type,listener,options){
          if(type==='keydown'&&listener&&options&&options.signal instanceof AbortSignal){
            const record={signal:options.signal,calls:0};records.push(record);
            const wrapped=function(event){record.calls++;return typeof listener==='function'?listener.call(this,event):listener.handleEvent(event);};
            return native.call(this,type,wrapped,options);
          }
          return native.call(this,type,listener,options);
        };
        try{element.remove();parent.insertBefore(element,next);}
        finally{if(descriptor)Object.defineProperty(document,'addEventListener',descriptor);else delete document.addEventListener;}
        window.__drawerWitness={element,parent,next,records};
        return {records:records.length,initialized:element.dataset.initialized,aborted:records.map(r=>r.signal.aborted)};
      });
      assert.deepEqual(capture,{records:1,initialized:'true',aborted:[false]});
      await assertOpen(page);
      const detached=await page.evaluate(()=>{
        const w=window.__drawerWitness;w.element.remove();
        const before=w.records[0].calls;
        document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));
        return {connected:w.element.isConnected,hasMarker:Object.prototype.hasOwnProperty.call(w.element.dataset,'initialized'),
          aborted:w.records[0].signal.aborted,callsBefore:before,callsAfter:w.records[0].calls};
      });
      assert.equal(detached.connected,false);assert.equal(detached.hasMarker,false);assert.equal(detached.aborted,true);
      assert.equal(detached.callsAfter,detached.callsBefore);
      await assertRestored(page,true);
      await page.evaluate(()=>{const w=window.__drawerWitness;if(w.next&&w.next.parentNode!==w.parent)throw Error('Sibling changed');w.parent.insertBefore(w.element,w.next);});
      await assertOpen(page);await page.keyboard.press('Escape');await assertRestored(page);
      return {capture,detached,reconnected:true};
    });
    await bounded('original Pages Pagefind entry bytes and real index support UI navigation',async page=>{
      await page.goto('/concepts/workflow-routes/');
      const response=await page.request.get('/pagefind/pagefind.js');assert.equal(response.status(),200);
      const value=await response.body();assert.equal(value.length,config.pagefind_entry.size);assert.equal(hash(value),config.pagefind_entry.sha256);
      const query='Protect Your First Repository',expected='/getting-started/quickstart/';
      const actual=await page.evaluate(async query=>{
        const provider=await import('/pagefind/pagefind.js');
        const result=await provider.search(query);
        return {exports:Object.keys(provider).sort(),paths:await Promise.all(result.results.map(async entry=>(await entry.data()).url))};
      },query);
      for(const name of ['search','options','init'])assert(actual.exports.includes(name));assert(actual.paths.includes(expected));
      const input=page.getByRole('combobox',{name:'Search the docs',exact:true});
      await page.keyboard.press('ControlOrMeta+k');await expect(input).toBeFocused();await input.fill(query);
      const option=page.getByRole('listbox',{name:'Search results',exact:true}).getByRole('option',{name:new RegExp('^'+query)});
      await expect(option).toHaveAttribute('href',expected);await input.press('ArrowDown');
      await expect(option).toHaveAttribute('aria-selected','true');await input.press('Enter');
      await expect(page).toHaveURL(config.origin+expected);
      await expect(page.getByRole('heading',{level:1,name:query,exact:true})).toBeVisible();
      return {entry_sha256:hash(value),entry_bytes:value.length,exports:actual.exports,realIndexExpectedPath:true,uiNavigated:true};
    });
  }catch(error){
    const text=String(error.stack||error);results.push({name:'browser setup',status:'FAILED',error_bytes:Buffer.byteLength(text),error_sha256:hash(text)});
  }finally{
    if(browser){let timer;try{await Promise.race([browser.close(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('cleanup deadline')),8000);})]);cleanup='closed';}catch{cleanup='unknown';}finally{clearTimeout(timer);}}
    const output={product_source_M:config.product_source_M,product_tree:config.product_tree,docs_run_R:config.docs_run_R,
      producer:'local Windows Chrome original-built Pages observation',browserVersion,viewport:{width:390,height:844},
      cases:results,browser_cleanup:cleanup,limits:['No synthetic HTML/Pagefind provider; original admitted static bytes only.','Seeded DOM state and bounded listener instrumentation are explicit acceptance setup.','No full WCAG/platform-union/native/TUI/provider/publication claim.']};
    fs.writeFileSync(config.output,JSON.stringify(output,null,2)+'\n',{flag:'wx'});
    process.exitCode=results.length===5&&results.every(r=>r.status==='PASSED')&&cleanup==='closed'?0:1;
  }
})();
