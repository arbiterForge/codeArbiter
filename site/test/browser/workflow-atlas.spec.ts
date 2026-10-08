import {expect,test,type Page} from '@playwright/test';
import {mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import type {Atlas} from '../../scripts/execution-maps/atlas-model';

const route='/concepts/workflow-routes/';
const model=async(page:Page):Promise<Atlas>=>JSON.parse((await page.locator('ca-workflow-atlas [data-atlas-data]').textContent())!);
const root=(page:Page)=>page.locator('ca-workflow-atlas');

test('original diagram is visible immediately and every spatial map retains its geometry',async({page},testInfo)=>{
  await page.setViewportSize({width:1920,height:1080});await page.goto(route);await page.evaluate(()=>document.fonts.ready);
  const atlas=root(page),a=await model(page),stage=atlas.locator('[data-atlas-stage]');
  await expect(atlas).toHaveAttribute('data-active-view','all-routes');await expect(stage.locator('svg')).toBeVisible();
  await expect(atlas.locator('.ca-atlas-entry,.ca-atlas-view')).toHaveCount(0);
  expect(a.views).toHaveLength(9);expect(a.views.flatMap(v=>v.nodes)).toHaveLength(213);expect(a.views.flatMap(v=>v.edges)).toHaveLength(178);
  for(const v of a.views){
    await atlas.locator(`button[data-atlas-view="${v.id}"]`).click();await expect(atlas).toHaveAttribute('data-active-view',v.id);
    await expect(stage.locator('[data-node]')).toHaveCount(v.nodes.length);await expect(stage.locator('.edge')).toHaveCount(v.edges.length);
    const observed=await stage.evaluate(element=>({nodes:[...element.querySelectorAll<SVGGElement>('[data-node]')].map(n=>{const r=n.querySelector('rect')!;return [n.dataset.node,...['x','y','width','height'].map(k=>Number(r.getAttribute(k)))];}),edges:[...element.querySelectorAll('.edge polyline')].map(e=>e.getAttribute('points'))}));
    expect(observed.nodes).toEqual(v.nodes.map(n=>[n.id,n.x,n.y,n.w,n.h]));expect(observed.edges).toEqual(v.edges.map(e=>e.points.map(p=>p.join(',')).join(' ')));
    const overflow=await stage.evaluate(element=>[...element.querySelectorAll<SVGGElement>('[data-node]')].flatMap(n=>{const r=n.querySelector('rect')!.getBBox();return [...n.querySelectorAll<SVGTextElement>(':scope > text')].filter(t=>{const b=t.getBBox();return b.x<r.x || b.y<r.y || b.x+b.width>r.x+r.width || b.y+b.height>r.y+r.height;}).map(t=>`${n.id}: ${t.textContent}`);}));
    expect(overflow,`Actual rendered text in ${v.id}`).toEqual([]);
  }
  await atlas.locator('[data-atlas-view="feature-sprint"]').click();await atlas.locator('[data-atlas-select]').selectOption('feature');
  const fonts=await atlas.evaluate(element=>({atlas:getComputedStyle(element).fontFamily,body:getComputedStyle(document.body).fontFamily}));expect(fonts.atlas).toBe(fonts.body);
  const boxes=await atlas.evaluate(element=>({stage:element.querySelector('[data-atlas-stage]')!.getBoundingClientRect().toJSON(),inspector:element.querySelector('[data-atlas-inspector]')!.getBoundingClientRect().toJSON()}));
  expect(boxes.inspector.x).toBeGreaterThan(boxes.stage.x+boxes.stage.width-2);
  mkdirSync(resolve('.astro/browser-evidence'),{recursive:true});
  const capture=resolve('.astro/browser-evidence/native-atlas-feature.png');
  await atlas.scrollIntoViewIfNeeded();await page.screenshot({path:capture});
  await testInfo.attach('native-atlas-feature',{path:capture,contentType:'image/png'});
  await atlas.locator('[data-atlas-view="context-layers"]').click();await atlas.locator('[data-action="clear"]').click();
  await page.screenshot({path:resolve('.astro/browser-evidence/native-atlas-context.png')});
});

test('all 37 entries highlight the original nodes and arrows without replacing the map',async({page})=>{
  await page.goto(route);const atlas=root(page),a=await model(page),stage=atlas.locator('[data-atlas-stage]');
  for(const command of a.commands){
    const v=a.views.find(v=>v.nodes.some(n=>n.routes.includes(command.name)))!;
    await atlas.locator(`[data-atlas-view="${v.id}"]`).click();const before=page.url();
    await atlas.locator('[data-atlas-select]').selectOption(command.name);await expect(atlas).toHaveAttribute('data-route',command.name);expect(page.url()).toBe(before);
    await expect(atlas.locator('[data-atlas-inspector] h3')).toHaveText('/'+command.name);
    await expect(stage.locator('[data-node]')).toHaveCount(v.nodes.length);
    const membership=await stage.evaluate(element=>({nodes:[...element.querySelectorAll<SVGGElement>('[data-node]')].filter(n=>!n.classList.contains('dim')).map(n=>n.dataset.node),edges:[...element.querySelectorAll('.edge')].map(n=>!n.classList.contains('dim'))}));
    expect(membership.nodes).toEqual(v.nodes.filter(n=>n.routes.includes(command.name)).map(n=>n.id));
    expect(membership.edges).toEqual(v.edges.map(e=>e.routes.length?e.routes.includes(command.name):v.nodes.find(n=>n.id===e.a)!.routes.includes(command.name)&&v.nodes.find(n=>n.id===e.b)!.routes.includes(command.name)));
  }
  await atlas.locator('[data-atlas-select]').selectOption('prune');await expect(atlas.locator('[data-atlas-inspector] .atlas-hosts')).toContainText('Not exposed on this host');
  await atlas.locator('[data-action="clear"]').click();await expect(stage.locator('.dim')).toHaveCount(0);await expect(atlas.locator('[data-atlas-select]')).toHaveValue('');
});

test('node inspector, pan, zoom and full editable export retain the original interaction',async({page})=>{
  await page.setViewportSize({width:1600,height:1100});await page.goto(route+'#atlas-view-context-layers');
  const atlas=root(page),stage=atlas.locator('[data-atlas-stage]'),a=await model(page),v=a.views.find(v=>v.id==='context-layers')!;
  const node=stage.locator('[data-node]').first();await node.focus();await page.keyboard.press('Enter');await expect(atlas).toHaveAttribute('data-selected-node',v.nodes[0].id);
  await expect(atlas.locator('[data-atlas-inspector] h3')).toHaveText(v.nodes[0].title);
  await atlas.locator('[data-action="read-size"]').click();await expect(atlas).toHaveAttribute('data-zoom','0.85');
  await atlas.locator('[data-action="plus"]').click();expect(Number(await atlas.getAttribute('data-zoom'))).toBeGreaterThan(.85);
  await atlas.locator('[data-action="minus"]').click();expect(Number(await atlas.getAttribute('data-zoom'))).toBeCloseTo(.85,4);
  await stage.focus();await page.keyboard.press('+');expect(Number(await atlas.getAttribute('data-zoom'))).toBeGreaterThan(.85);
  await page.keyboard.press('0');expect(Number(await atlas.getAttribute('data-zoom'))).toBeLessThan(.85);
  await atlas.locator('[data-action="read-size"]').click();await stage.evaluate(el=>{el.scrollLeft=0;el.scrollTop=0;});
  const box=(await stage.boundingBox())!;await page.mouse.move(box.x+10,box.y+50);await page.mouse.down();await page.mouse.move(box.x+5,box.y+5);await page.mouse.up();
  expect(await stage.evaluate(el=>el.scrollTop)).toBeGreaterThan(0);
  const zoom=Number(await atlas.getAttribute('data-zoom'));await page.keyboard.down('Control');await page.mouse.wheel(0,-100);await page.keyboard.up('Control');
  await expect.poll(async()=>Number(await atlas.getAttribute('data-zoom'))).toBeGreaterThan(zoom);
  await atlas.locator('[data-atlas-select]').selectOption('feature');
  const exported=page.waitForEvent('download');await atlas.locator('[data-action="export"]').click();const download=await exported;
  expect(download.suggestedFilename()).toBe('codearbiter-context-layers.svg');
  const stream=await download.createReadStream();const chunks:Buffer[]=[];for await(const chunk of stream!)chunks.push(Buffer.from(chunk));const svg=Buffer.concat(chunks).toString();
  // Inspect presentation classes, not prose such as "selected rules" in the
  // original diagram. The negative control proves the selector detects state.
  const exportedState=await page.evaluate(source=>{
    const doc=new DOMParser().parseFromString(source,'image/svg+xml');
    const presentation=()=>doc.querySelectorAll('.dim,.selected').length;
    const result={parseErrors:doc.querySelectorAll('parsererror').length,root:doc.documentElement.localName,nodes:doc.querySelectorAll('[data-node]').length,presentation:presentation(),detectsState:false};
    const first=doc.querySelector('[data-node]');
    if(first){first.classList.add('dim','selected');result.detectsState=presentation()>0;}
    return result;
  },svg);
  expect(exportedState).toEqual({parseErrors:0,root:'svg',nodes:v.nodes.length,presentation:0,detectsState:true});
  for(const n of v.nodes)expect(svg).toContain(`data-node="${n.id}"`);
  for(const e of v.edges)expect(svg).toContain(`points="${e.points.map(p=>p.join(',')).join(' ')}"`);
  await atlas.locator('[data-action="sources"]').click();await expect(atlas.locator('dialog')).toBeVisible();await page.keyboard.press('Escape');await expect(atlas.locator('dialog')).toBeHidden();
});

test('explicit addresses, repeated fragments, history and real Astro reconnection work',async({page})=>{
  const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));await page.goto(route+'#atlas-fix');
  const atlas=root(page),select=atlas.locator('[data-atlas-select]');await expect(select).toHaveValue('fix');await expect(atlas).toHaveAttribute('data-active-view','change-lanes');
  const initial=page.url();await select.selectOption('tribunal');expect(page.url()).toBe(initial);
  await atlas.locator('[data-atlas-view="tribunal-lifecycle"]').click();await atlas.locator('[data-atlas-permalink]').click();
  await expect(page).toHaveURL(/#atlas-view-tribunal-lifecycle~tribunal$/);await page.reload();await expect(select).toHaveValue('tribunal');await expect(atlas).toHaveAttribute('data-active-view','tribunal-lifecycle');
  await page.goBack();await expect(select).toHaveValue('fix');await page.goForward();await expect(select).toHaveValue('tribunal');
  const length=await page.evaluate(()=>history.length);await atlas.locator('[data-atlas-permalink]').focus();await page.keyboard.press('Enter');expect(await page.evaluate(()=>history.length)).toBe(length);
  await expect(atlas.locator('[data-atlas-stage]')).toBeFocused();
  const node=atlas.locator('[data-atlas-stage] [data-node]').first();await node.focus();await page.keyboard.press('Enter');await atlas.locator('[data-atlas-permalink]').click();
  await expect(page).toHaveURL(/#atlas-node-tribunal-lifecycle-t-entry~tribunal$/);await expect(node).toBeFocused();await page.reload();await expect(atlas).toHaveAttribute('data-selected-node','t-entry');await expect(select).toHaveValue('tribunal');
  await select.selectOption('fix');await atlas.evaluate(el=>el.setAttribute('data-test-original','true'));await page.evaluate(()=>Reflect.set(window,'atlasTestDocument','retained'));
  await atlas.locator('[data-atlas-inspector] a[href="/reference/commands/fix/"]').click();await expect(page).toHaveURL(/\/reference\/commands\/fix\/$/);
  await page.locator(`a[href="${route}#atlas-fix"]`).first().click();await expect(select).toHaveValue('fix');await expect(atlas).not.toHaveAttribute('data-test-original');expect(await page.evaluate(()=>Reflect.get(window,'atlasTestDocument'))).toBe('retained');
  await atlas.locator('[data-action="plus"]').click();expect(Number(await atlas.getAttribute('data-zoom'))).toBeGreaterThan(0);expect(errors).toEqual([]);
});

test('unrelated, malformed, modified and canceled addresses leave the selected route intact',async({page})=>{
  await page.goto(route+'#atlas-fix');const atlas=root(page),select=atlas.locator('[data-atlas-select]');
  for(const hash of ['#unrelated-chapter','#%E0%A4%A','#%22%5D%5Bhidden%5D','#'+'x'.repeat(1025)]){
    await page.evaluate(value=>{history.replaceState(history.state,'',value);window.dispatchEvent(new HashChangeEvent('hashchange'));},hash);await expect(select).toHaveValue('fix');
  }
  await atlas.evaluate(async el=>{
    const link=el.querySelector<HTMLAnchorElement>('[data-atlas-permalink]')!;link.setAttribute('href','#atlas-tribunal');
    const cancel=(event:Event)=>event.preventDefault();document.addEventListener('click',cancel);
    try{
      for(const init of [{ctrlKey:true},{metaKey:true},{shiftKey:true},{altKey:true},{button:1}]){link.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,...init}));await Promise.resolve();}
      link.addEventListener('click',cancel,{once:true});link.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));await Promise.resolve();
      for(const [name,value] of [['target','_blank'],['download','atlas']]){link.setAttribute(name,value);link.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));await Promise.resolve();link.removeAttribute(name);}
    }finally{document.removeEventListener('click',cancel);}
  });
  await expect(select).toHaveValue('fix');
});

test('narrow layout, enlarged text, forced colors and repeated print restore the canvas',async({page},testInfo)=>{
  await page.setViewportSize({width:390,height:844});await page.emulateMedia({reducedMotion:'reduce'});await page.goto(route+'#atlas-view-tribunal-lifecycle');
  const atlas=root(page);await atlas.locator('[data-action="read-size"]').click();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
  await atlas.locator('[data-action="details"]').click();await expect(atlas.locator('[data-atlas-inspector]')).toBeInViewport();await expect(atlas.locator('[data-atlas-inspector]')).toBeFocused();
  await page.evaluate(()=>document.fonts.ready);mkdirSync(resolve('.astro/browser-evidence'),{recursive:true});
  const capture=resolve('.astro/browser-evidence/native-atlas-mobile.png');
  await page.screenshot({path:capture});await testInfo.attach('native-atlas-mobile',{path:capture,contentType:'image/png'});
  const original=await atlas.getAttribute('data-active-view'),zoom=await atlas.getAttribute('data-zoom');
  await page.evaluate(()=>{window.dispatchEvent(new Event('beforeprint'));window.dispatchEvent(new Event('beforeprint'));});await page.emulateMedia({media:'print'});
  await expect(atlas.locator('[data-reading-entry="status"]')).toBeVisible();await expect(atlas.locator('#atlas-text-debug-handoff')).toBeVisible();await expect(atlas.locator('[data-atlas-status]')).toBeHidden();await expect(atlas.locator('.frame')).toBeHidden();
  await page.emulateMedia({media:'screen',forcedColors:'active'});await page.evaluate(()=>window.dispatchEvent(new Event('afterprint')));
  await expect(atlas).toHaveAttribute('data-active-view',original!);await expect(atlas).toHaveAttribute('data-zoom',zoom!);await expect(atlas.locator('.reading-wrap')).not.toHaveAttribute('open');
  await expect(atlas.locator('[data-atlas-stage] svg')).toBeVisible();
  await page.addStyleTag({content:'html{font-size:200%!important}'});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
  await atlas.locator('[data-action="reading"]').click();await expect(atlas.locator('[data-reading-entry="feature"]')).toBeVisible();
});

test('no-script reading, base-safe downloads and the offline viewer use the same nine maps',async({browser,request,baseURL,page})=>{
  const context=await browser.newContext({javaScriptEnabled:false});
  try{
    const plain=await context.newPage();await plain.goto(new URL(route,baseURL).href);const atlas=root(plain);await atlas.locator('.reading-wrap > summary').click();await expect(atlas.locator('[data-reading-entry="fix"]')).toBeVisible();await expect(atlas.locator('#atlas-text-tribunal-lifecycle')).toBeVisible();
    const download=(await atlas.locator('.atlas-downloads a').first().getAttribute('href'))!;expect(download).toMatch(/\/workflow-atlas\/[0-9a-f]{40}\/atlas.html$/);
    const response=await request.get(download);expect(response.ok()).toBeTruthy();expect(await response.text()).toContain('report-written');
    const svg=await request.get(download.replace('atlas.html','context-layers.svg'));expect(svg.ok()).toBeTruthy();expect(await svg.text()).toContain('data-node="c-green"');
    await page.goto(download+'#atlas-view-feature-sprint~feature');await expect(root(page)).toHaveAttribute('data-active-view','feature-sprint');await expect(root(page)).toHaveAttribute('data-route','feature');
    await root(page).locator('[data-atlas-view="context-layers"]').click();await root(page).locator('[data-atlas-permalink]').click();await page.goBack();await expect(root(page)).toHaveAttribute('data-active-view','feature-sprint');
    await page.reload();await expect(root(page)).toHaveAttribute('data-route','feature');await expect(root(page).locator('button[data-atlas-view]')).toHaveCount(9);
    const guide=await request.get(download.replace('atlas.html','reading-guide.html'));expect(guide.ok()).toBeTruthy();expect(await guide.text()).not.toContain('<script');
  }finally{await context.close();}
});
