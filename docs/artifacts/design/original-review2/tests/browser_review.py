#!/usr/bin/env python3
"""Optional Chromium review of actual reference HTML; not a full accessibility audit."""
import argparse,json,hashlib
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--executable',default='/usr/bin/chromium');ap.add_argument('--report',type=Path,default=root/'browser-report.json');ap.add_argument('--screenshots',type=Path);args=ap.parse_args()
if args.screenshots:args.screenshots.mkdir(parents=True,exist_ok=True)
report={'artifact_sha256':{k:hashlib.sha256((root/f'{k}.html').read_bytes()).hexdigest() for k in ('spec','plan')},'scope':'Chromium reference-HTML layout/safety checks only; not complete accessibility or native-host certification','cells':[]}
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path=args.executable,headless=True,args=['--no-sandbox'])
 report['browser_version']=browser.version
 for kind in ('spec','plan'):
  for width in (1440,390):
   ctx=browser.new_context(viewport={'width':width,'height':1050},java_script_enabled=False)
   page=ctx.new_page();external=[]
   page.on('request',lambda r:external.append(r.url) if r.url.startswith(('http://','https://')) else None)
   uri=(root/f'{kind}.html').as_uri()
   try:page.goto(uri,wait_until='load');mode='file_url'
   except Exception:
    page.close();page=ctx.new_page()
    page.on('request',lambda r:external.append(r.url) if r.url.startswith(('http://','https://')) else None)
    page.set_content((root/f'{kind}.html').read_text(),wait_until='load');mode='in_memory_fallback'
   logo=page.locator('img.brand').evaluate('(e)=>e.complete && e.naturalWidth>0')
   overflow=page.evaluate('document.documentElement.scrollWidth > innerWidth')
   assert logo and not overflow and not external,(kind,width,logo,overflow,external)
   toc=page.locator('.mobile-toc')
   if width==390:
    assert toc.is_visible();toc.locator('summary').click();assert toc.locator('a').first.is_visible();toc.locator('summary').click()
   if args.screenshots:page.screenshot(path=str(args.screenshots/f'{kind}-{width}-top.png'))
   # User text zoom: double existing computed body/content font sizes (not device scale).
   page.evaluate("""() => {const nodes=[...document.querySelectorAll('p,li,td,th,summary,h1,h2,h3,h4,code,pre,.deck')]; const sizes=nodes.map(e=>parseFloat(getComputedStyle(e).fontSize)); nodes.forEach((e,i)=>e.style.fontSize=(sizes[i]*2)+'px');}""")
   assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'),('text_scale_overflow',kind,width)
   # Reload to restore stylesheet, then inspect a contract in the document body.
   if mode=='file_url':page.goto(uri,wait_until='load')
   else:page.set_content((root/f'{kind}.html').read_text(),wait_until='load')
   target='#AC-014' if kind=='spec' else '#T-016'
   page.locator(target).scroll_into_view_if_needed()
   if args.screenshots:page.screenshot(path=str(args.screenshots/f'{kind}-{width}-record.png'))
   # Collapse a native detail, emulate print, and check its body is exposed.
   page.locator(target+' > summary').click();page.emulate_media(media='print')
   visible=page.locator(target+' .record-body').evaluate('(e)=>e.getBoundingClientRect().height>0 && getComputedStyle(e).display!=="none"')
   assert visible,('print_disclosure',kind,width)
   report['cells'].append({'artifact':kind,'viewport_width':width,'load_mode':mode,'javascript_enabled':False,'embedded_logo_loaded':bool(logo),'page_horizontal_overflow':False,'text_200_percent_page_overflow':False,'mobile_contents_available':width==390,'collapsed_detail_visible_in_print':bool(visible),'automatic_external_requests':external,'pass':True})
   ctx.close()
 browser.close()
report['passed']=all(x['pass'] for x in report['cells']);args.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
