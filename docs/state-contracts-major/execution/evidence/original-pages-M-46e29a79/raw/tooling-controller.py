"""Prepared only. Separate acquire/observe phases; no action occurs on import."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import MappingProxyType
from urllib.parse import unquote, urlsplit, quote
import zipfile

REPO=Path('C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter')
GIT='C:/Program Files/Git/cmd/git.exe'
GH=Path('C:/Users/brenn/AppData/Local/Microsoft/WinGet/Links/gh.exe')
NODE=Path('C:/Users/brenn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
CHROME=Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
SOURCE='46e29a796e89e0eaa3250cf171e4c9bea97ac437'
TREE='d69fb1c0eb4b16672137e1185eb085339f13727d'
RUN=43582198099
BRANCH='major/state-contracts'
COMPANION=Path('C:/Users/brenn/AppData/Local/Temp/ca-pages-admission-bf2f/candidate/.github/scripts/pages_readiness.py')
COMPANION_SHA='71e696171575831324103ef699981f9eca7cb05caa2d1417d00ea1885fc1c871'
ROOT=Path(__file__).resolve().parent

def need(value, category):
    if not value:raise ValueError(category)

def sha(value):return hashlib.sha256(value).hexdigest()

def encoded(value):return (json.dumps(value,indent=2)+'\n').encode('utf8')

def git(*args):
    return subprocess.check_output([GIT,'--no-lazy-fetch',*args],cwd=REPO,timeout=20)

def no_link(path):
    path=Path(path).absolute()
    for part in [*reversed(path.parents),path]:
        if part.exists():
            stat=part.lstat()
            need(not part.is_symlink() and not part.is_junction()
                 and not getattr(stat,'st_file_attributes',0)&0x400,'reparse path refused')
    return path

def write_new(root,name,data):
    need('/' not in name and '\\' not in name and ':' not in name,'unsafe output leaf')
    with (no_link(root)/name).open('xb') as stream:stream.write(data)

def read_new(root,name,digest):
    need('/' not in name and '\\' not in name and ':' not in name,'unsafe capture leaf')
    value=no_link(Path(root)/name).read_bytes()
    need(sha(value)==digest,'capture bytes changed')
    return value

def tooling():
    sources={}
    for path in ['.github/scripts/major_readiness.py','.github/scripts/_boundedproc.py',
                 '.github/scripts/_contextverificationlib.py','core/pysrc/_artifactmanifestlib.py']:
        value=(REPO/path).read_bytes()
        need(value==git('show',SOURCE+':'+path),'owning helper drift')
        sources[str(REPO/path)]=sha(value)
    need(git('rev-parse',SOURCE+'^{tree}').decode().strip()==TREE,'wrong immutable product tree')
    need(sha(COMPANION.read_bytes())==COMPANION_SHA,'unreviewed Pages companion')
    for path in [COMPANION,ROOT/'controller.py',ROOT/'browser.cjs']:
        sources[str(path)]=sha(path.read_bytes())
    return {'base_commit':SOURCE,'local_actual_HEAD':git('rev-parse','HEAD').decode().strip(),
            'controller_source_commit':None,'controller_epoch':'Temp reviewed content-addressed tooling, not productM',
            'content_sha256':sha(json.dumps(sources,sort_keys=True,separators=(',',':')).encode()),'sources':sources}

def runtime_files():
    paths=[NODE,CHROME,GH,Path(sys.executable),REPO/'site/package-lock.json',
           *[REPO/'site/node_modules'/p for p in ['@playwright/test/package.json',
             'playwright/package.json','playwright-core/package.json']]]
    need((REPO/'site/package-lock.json').read_bytes()==git('show',SOURCE+':site/package-lock.json'),
         'installed dependency lock source differs from M')
    return {str(p):sha(p.read_bytes()) for p in paths}

def load_owners():
    identity=tooling()
    sys.path.insert(0,str(REPO/'.github/scripts'))
    import major_readiness as owner
    spec=importlib.util.spec_from_file_location('pages_readiness_selected',COMPANION)
    pages=importlib.util.module_from_spec(spec);spec.loader.exec_module(pages)
    return owner,pages,identity

def api_environment():
    # Only this acquisition process/its gh child keeps the existing approved GitHub flow.
    keys=['SystemRoot','WINDIR','TEMP','TMP','COMSPEC','PATHEXT','HOME','USERPROFILE',
          'APPDATA','LOCALAPPDATA','HOMEDRIVE','HOMEPATH','GH_CONFIG_DIR','GH_TOKEN','GITHUB_TOKEN',
          'HTTPS_PROXY','HTTP_PROXY','NO_PROXY','ALL_PROXY']
    need(os.environ.get('GH_HOST','github.com')=='github.com','foreign GitHub host refused')
    values={k:os.environ[k] for k in keys if k in os.environ}
    values.update(PATH=str(GH.parent)+';C:/Program Files/Git/cmd;C:/Windows/System32',
                  GH_HOST='github.com',GH_PROMPT_DISABLED='1')
    os.environ.clear();os.environ.update(values)

def json_member(owner,archive,leaf):
    members=owner.members(archive)
    found=[m for m in members if m['path']==leaf]
    need(len(found)==1,'missing original browser receipt')
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        info=zipped.getinfo(leaf);need(info.file_size<=4*1024*1024,'browser receipt exceeds bound')
        return json.loads(zipped.read(info))

def cross_join(owner,pages_files,browser_zip):
    receipt=json_member(owner,browser_zip,'search-bundle-integrity.json')
    value=pages_files.get('pagefind/pagefind.js')
    need(type(value) is bytes,'Pages Pagefind entry missing')
    need(isinstance(receipt,dict) and receipt.get('commit')==SOURCE and receipt.get('tree')==TREE
         and receipt.get('path')=='/pagefind/pagefind.js' and receipt.get('servedBytesMatchBuild') is True
         and type(receipt.get('bytes')) is int and receipt['bytes']==len(value)
         and receipt.get('sha256')==sha(value),'original browser/Pages source or bytes differ')
    return receipt

def acquire(output):
    api_environment()
    owner,pages,identity=load_owners()
    root=no_link(Path(output).absolute()) if output else Path(tempfile.mkdtemp(prefix='ca-original-pages-M-')).resolve()
    if output:root.mkdir(exist_ok=False)
    run=owner.api(f'actions/runs/{RUN}')
    need(run.get('head_sha')==SOURCE and run.get('id')==RUN and run.get('event')=='push'
         and run.get('head_branch')==BRANCH and run.get('conclusion')=='success'
         and run.get('path')=='.github/workflows/docs.yml','normal successful docsM/R required')
    def population(kind):
        suffix='?filter=latest&per_page=100' if kind=='jobs' else '?per_page=100'
        result=json.loads(owner.command(['gh','api','--paginate','--slurp',
            f'repos/{owner.REPOSITORY}/actions/runs/{RUN}/{kind}'+suffix]))
        need(isinstance(result,list) and len(result)<=6,'API page population exceeds bound')
        values=[v for batch in result for v in batch[kind]]
        need(len(values)<=512,'API population exceeds bound')
        return values
    jobs=population('jobs');artifacts=population('artifacts')
    candidates=[j for j in jobs if j.get('name')==pages.JOB_NAME]
    need(len(candidates)==1,'ambiguous original docs build job')
    job=owner.api(f"actions/jobs/{candidates[0]['id']}")
    required=['Build','Link audit','Record runner Chrome version','Browser component acceptance',
              'Browser publication gate','Retain browser review evidence','Upload Pages artifact']
    positions=[]
    for name in required:
        step=[s for s in job['steps'] if s.get('name')==name]
        need(len(step)==1 and step[0].get('conclusion')=='success'
             and step[0].get('status')=='completed','owning docs stage missing or unsuccessful')
        positions.append(step[0]['number'])
    need(positions==sorted(set(positions)),'owning docs stage order differs')
    def selected(name):
        values=[a for a in artifacts if a.get('name')==name]
        need(len(values)==1,'ambiguous original artifact name')
        return owner.api(f"actions/artifacts/{values[0]['id']}")
    meta=selected('github-pages');browser_meta=selected('site-browser-evidence')
    req={'source_commit':SOURCE,'ci_run_id':RUN}
    archive=owner.artifact_bytes(meta,req)
    browser=owner.artifact_bytes(browser_meta,req)
    log=owner.api(f"actions/jobs/{job['id']}/logs",binary=True)
    admitted=pages.admit_pages_build(source=SOURCE,run_id=RUN,branch=BRANCH,job_id=job['id'],
        artifact_id=meta['id'],run=run,job=job,artifact=meta,archive=archive,job_log=log)
    # Use the unchanged live direct owner for the distinct cf430 browser-evidence upload.
    owner.validate_upload(job,browser_meta,'Retain browser review evidence')
    receipt=cross_join(owner,admitted['files'],browser)
    after=tooling();need(after['sources']==identity['sources'],'acquisition tooling changed')
    saved={'run.json':encoded(run),'job.json':encoded(job),'pages-meta.json':encoded(meta),
           'browser-meta.json':encoded(browser_meta),'original-job.log':log,
           'pages.zip':archive,'browser.zip':browser}
    for name,value in saved.items():write_new(root,name,value)
    record={'state':'ADMITTED_ORIGINAL_STATIC_PAGES','product_source_M':SOURCE,'product_tree':TREE,
        'docs_run_R':RUN,'branch':BRANCH,'tooling_Q':identity,'tooling_after':after,'pages':admitted['provenance'],
        'browser_receipt':receipt,'browser_artifact_id':browser_meta['id'],
        'browser_upload_authenticated_by_unchanged_owner':True,
        'browser_upload_owner_sha256':identity['sources'][str(REPO/'.github/scripts/major_readiness.py')],
        'files':{n:sha(v) for n,v in saved.items()},'gh_runtime_sha256':sha(GH.read_bytes()),
        'captured_at':datetime.now(timezone.utc).isoformat(),
        'privacy':'Original full job log stays private/hash-only; do not automatically publish it or credentials.'}
    write_new(root,'acquisition.json',encoded(record))
    print(json.dumps({'state':record['state'],'root':str(root),'acquisition_sha256':sha(encoded(record)),
                      'source':SOURCE,'docs_run':RUN,'job':job['id'],'pages_artifact':meta['id'],
                      'browser_artifact':browser_meta['id']}))
    return 0

def observe(capture_root,capture_sha):
    root=no_link(Path(capture_root).absolute())
    raw=no_link(root/'acquisition.json').read_bytes();need(sha(raw)==capture_sha,'unselected acquisition record')
    capture=json.loads(raw);owner,pages,identity=load_owners()
    need(capture['product_source_M']==SOURCE and capture['product_tree']==TREE
         and capture['docs_run_R']==RUN and capture['branch']==BRANCH
         and capture['browser_upload_authenticated_by_unchanged_owner'] is True,
         'capture origin differs')
    for path,digest in capture['tooling_Q']['sources'].items():
        need(sha(Path(path).read_bytes())==digest,'capture tooling changed')
    saved={n:read_new(root,n,d) for n,d in capture['files'].items()}
    run=json.loads(saved['run.json']);job=json.loads(saved['job.json']);meta=json.loads(saved['pages-meta.json'])
    admitted=pages.admit_pages_build(source=SOURCE,run_id=RUN,branch=BRANCH,job_id=job['id'],
        artifact_id=meta['id'],run=run,job=job,artifact=meta,archive=saved['pages.zip'],job_log=saved['original-job.log'])
    owner.validate_artifact(json.loads(saved['browser-meta.json']),{'source_commit':SOURCE,'ci_run_id':RUN},sha(saved['browser.zip']))
    receipt=cross_join(owner,admitted['files'],saved['browser.zip'])
    served=MappingProxyType(admitted['files'])  # Original admitted bytes; no filesystem extraction.
    initial={name:sha(value) for name,value in served.items()}
    runtime_before=runtime_files()
    out=Path(tempfile.mkdtemp(prefix='observation-',dir=root)).resolve()
    requests=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_HEAD(self):self.respond(False)
        def do_GET(self):self.respond(True)
        def respond(self,body):
            parsed=urlsplit(self.path)
            try:
                decoded=unquote(parsed.path,errors='strict')
                need(not parsed.scheme and not parsed.netloc and decoded.startswith('/')
                     and '\\' not in decoded and '\x00' not in decoded
                     and '..' not in decoded.split('/'),'unsafe request')
                name=decoded[1:]
                if not name or name.endswith('/'):name+='index.html'
                if name not in served and name+'/index.html' in served:
                    self.send_response(301);self.send_header('Location',quote(decoded.rstrip('/')+'/'));self.end_headers();return
                value=served.get(name)
                if value is None:self.send_error(404);return
                need(len(requests)<4096,'request population exceeds bound')
                requests.append({'member':name,'sha256':sha(value),'bytes':len(value)})
                suffix=Path(name).suffix.lower()
                types={'.html':'text/html; charset=utf-8','.js':'text/javascript','.mjs':'text/javascript',
                    '.css':'text/css','.wasm':'application/wasm','.json':'application/json',
                    '.svg':'image/svg+xml','.png':'image/png','.woff2':'font/woff2','.woff':'font/woff'}
                self.send_response(200);self.send_header('Content-Type',types.get(suffix,'application/octet-stream'))
                self.send_header('Content-Length',str(len(value)));self.end_headers()
                if body:self.wfile.write(value)
            except (ValueError,UnicodeError):self.send_error(400)
    home=out/'home'
    for p in ['AppData/Roaming','AppData/Local','.config','.cache','tmp']:(home/p).mkdir(parents=True,exist_ok=True)
    env={k:os.environ[k] for k in ['SystemRoot','WINDIR','COMSPEC','PATHEXT'] if k in os.environ}
    env.update(PATH=str(NODE.parent)+';C:/Windows/System32',HOME=str(home),USERPROFILE=str(home),
        APPDATA=str(home/'AppData/Roaming'),LOCALAPPDATA=str(home/'AppData/Local'),
        XDG_CONFIG_HOME=str(home/'.config'),XDG_CACHE_HOME=str(home/'.cache'),
        TEMP=str(home/'tmp'),TMP=str(home/'tmp'),PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD='1')
    package=json.loads(git('show',SOURCE+':site/package.json'))
    installed=json.loads((REPO/'site/node_modules/@playwright/test/package.json').read_text(encoding='utf8'))
    need(installed['version']==package['devDependencies']['@playwright/test'],'Playwright version differs from M')
    from _boundedproc import run
    argv=[str(NODE),str(ROOT/'browser.cjs'),str(out/'browser-input.json')]
    started=time.monotonic()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    try:
        origin=f'http://127.0.0.1:{server.server_port}'
        config={'origin':origin,'product_source_M':SOURCE,'product_tree':TREE,'docs_run_R':RUN,
                'pagefind_entry':next(m for m in admitted['provenance']['members'] if m['path']=='pagefind/pagefind.js'),
                'playwright':str(REPO/'site/node_modules/@playwright/test'),'chrome':str(CHROME),
                'output':str(out/'browser-result.json')}
        write_new(out,'browser-input.json',encoded(config))
        thread.start()
        result=run(argv,timeout=120,cwd=str(ROOT),env=env)
    finally:
        if thread.ident is not None:
            server.shutdown();thread.join(3)
        server.server_close()
    need(initial=={name:sha(value) for name,value in served.items()},'served original bytes changed')
    runtime_after=runtime_files();after=tooling()
    need(runtime_before==runtime_after and identity['sources']==after['sources'],'observation tooling changed')
    browser_path=out/'browser-result.json'
    observation=json.loads(browser_path.read_text(encoding='utf8')) if browser_path.is_file() else None
    passed=(result.returncode==0 and not result.timed_out and result.containment=='exited'
            and not thread.is_alive() and server.fileno()==-1 and isinstance(observation,dict)
            and observation.get('product_source_M')==SOURCE and observation.get('product_tree')==TREE
            and observation.get('docs_run_R')==RUN and observation.get('browser_cleanup')=='closed'
            and len(observation.get('cases',[]))==5
            and all(c.get('status')=='PASSED' for c in observation['cases']))
    record={'source':SOURCE,'tree':TREE,'docs_run':RUN,'acquisition_sha256':capture_sha,
        'state':'PASSED' if passed else 'FAILED_OR_UNKNOWN',
        'tooling_Q':identity,'tooling_after':after,'runtime_files_before':runtime_before,
        'runtime_files_after':runtime_after,'argv':argv,'cwd':str(ROOT),'seconds':time.monotonic()-started,
        'returncode':result.returncode,'timed_out':result.timed_out,'containment':result.containment,
        'server_cleanup_confirmed':not thread.is_alive() and server.fileno()==-1,
        'stdout_bytes':len(result.stdout.encode()),'stdout_sha256':sha(result.stdout.encode()),
        'stderr_bytes':len(result.stderr.encode()),'stderr_sha256':sha(result.stderr.encode()),
        'stdio_scope':'UTF8 replacement text projection from owning boundedproc, not an original-byte claim.',
        'browser_result_sha256':sha(browser_path.read_bytes()) if browser_path.is_file() else None,
        'served_member_manifest_before_after':initial,'responses':requests,
        'local_node_sha256':sha(NODE.read_bytes()),'local_chrome_sha256':sha(CHROME.read_bytes()),
        'original_CI_browser':receipt['browser'],'result_scope':'Local Windows Chrome original-built Pages acceptance, not hosted/production deployment or native qualification.'}
    write_new(out,'controller-result.json',encoded(record))
    print(json.dumps({'output':str(out),'state':record['state'],'returncode':result.returncode,'timed_out':result.timed_out,
                      'containment':result.containment,'server_closed':record['server_cleanup_confirmed']}))
    return 0 if passed else 1

def main():
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='phase',required=True)
    a=sub.add_parser('acquire');a.add_argument('--output')
    a=sub.add_parser('observe');a.add_argument('--capture-root',required=True);a.add_argument('--capture-sha256',required=True)
    args=parser.parse_args()
    if args.phase=='acquire':return acquire(args.output)
    return observe(args.capture_root,args.capture_sha256)

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as error:
        # Unknown child/provider/error text never becomes automatic model-facing output.
        text=str(error).encode('utf8',errors='replace')
        print(json.dumps({'state':'FAILED_OR_UNAVAILABLE','error_bytes':len(text),'error_sha256':sha(text)}))
        raise SystemExit(1)
