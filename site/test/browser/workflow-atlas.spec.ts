import { expect, test } from '@playwright/test';
const route='/concepts/workflow-routes/';
test('entry selection, explicit permalinks, history and page lifecycle',async({page})=>{
  const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto(route+'#atlas-fix');
  const atlas=page.locator('ca-workflow-atlas');
  await expect(atlas.locator('#atlas-fix')).toBeVisible();
  await expect(atlas.locator('[data-atlas-select]')).toHaveValue('fix');
  const initial=page.url();await atlas.locator('[data-atlas-select]').selectOption('tribunal');expect(page.url()).toBe(initial);
  await atlas.locator('[data-atlas-permalink]').click();await expect(page).toHaveURL(/#atlas-tribunal$/);
  await page.reload();await expect(atlas.locator('[data-atlas-select]')).toHaveValue('tribunal');
  await page.goBack();await expect(atlas.locator('[data-atlas-select]')).toHaveValue('fix');
  await atlas.locator('a[href="#atlas-view-context-layers"]').first().click();
  await expect(atlas.locator('#atlas-view-context-layers')).toHaveAttribute('open','');
  await page.goto('/guides/feature-lane/');await page.goto(route+'#atlas-tribunal');
  await expect(atlas.locator('[data-atlas-select]')).toHaveValue('tribunal');expect(errors).toEqual([]);
});
test('every catalog entry, host exclusions and every map remain reachable',async({page})=>{
  await page.goto(route);const atlas=page.locator('ca-workflow-atlas');
  const ids=await atlas.locator('[data-atlas-select] option').evaluateAll(options=>options.map(o=>(o as HTMLOptionElement).value).filter(Boolean));
  expect(ids.length).toBe(37);
  for(const id of ids){await atlas.locator('[data-atlas-select]').selectOption(id);await expect(atlas.locator(`#atlas-${id}`)).toBeVisible();}
  await atlas.locator('[data-atlas-select]').selectOption('prune');await atlas.locator('[data-atlas-host-select]').selectOption('codex');
  await expect(atlas.locator('#atlas-prune [data-atlas-host="codex"]')).toContainText('Not exposed');
  await atlas.locator('[data-atlas-show-all]').click();
  const views=await atlas.locator('[data-atlas-view]').evaluateAll(nodes=>nodes.map(n=>n.id));
  for(const id of views){await page.goto(route+'#'+id);await expect(page.locator('#'+id)).toHaveAttribute('open','');}
});
test('narrow reading, keyboard targets, reduced motion and print',async({page})=>{
  await page.setViewportSize({width:390,height:844});await page.emulateMedia({reducedMotion:'reduce'});
  await page.goto(route+'#atlas-view-tribunal');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
  const atlas=page.locator('ca-workflow-atlas');
  await atlas.locator('[data-atlas-select]').focus();await expect(atlas.locator('[data-atlas-select]')).toBeFocused();
  await page.evaluate(()=>window.dispatchEvent(new Event('beforeprint')));await page.emulateMedia({media:'print'});
  await expect(atlas.locator('#atlas-view-debug-fix')).toBeVisible();await expect(atlas.locator('#atlas-status')).toBeVisible();
  await page.emulateMedia({media:'screen',forcedColors:'active'});await page.evaluate(()=>window.dispatchEvent(new Event('afterprint')));
  await expect(atlas.locator('#atlas-view-tribunal')).toBeVisible();
});
test('JavaScript-disabled reading and exact generated downloads',async({browser,request})=>{
  const context=await browser.newContext({javaScriptEnabled:false});const page=await context.newPage();
  try{
    await page.goto('http://127.0.0.1:4322'+route);const atlas=page.locator('ca-workflow-atlas');
    await atlas.locator('#atlas-fix > summary').click();await expect(atlas.locator('#atlas-fix .ca-atlas-entry-body')).toBeVisible();
    await atlas.locator('#atlas-view-tribunal > summary').click();await expect(atlas.locator('#atlas-view-tribunal .ca-atlas-handoffs')).toBeVisible();
    const download=await atlas.locator('footer a').first().getAttribute('href');expect(download).toMatch(/\/workflow-atlas\/[0-9a-f]{40}\/atlas.html$/);
    const response=await request.get(download!);expect(response.ok()).toBeTruthy();expect(await response.text()).toContain('report-written');
    const svg=await request.get(download!.replace('atlas.html','context-layers.svg'));expect(svg.ok()).toBeTruthy();expect(await svg.text()).toContain('<svg');
  }finally{await context.close();}
});
