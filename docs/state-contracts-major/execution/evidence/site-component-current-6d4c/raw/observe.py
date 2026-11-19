from pathlib import Path
import hashlib,json,os,subprocess,time
R=Path('C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter')
O=Path(__file__).resolve().parent
SOURCE='6d4c858fff4df40cc14d71c19c0e4d5a0d6bf434'
GIT='C:/Program Files/Git/cmd/git.exe'
NODE=Path('C:/Users/brenn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
CHROME=Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
paths=['site/src/components/Search.astro','site/src/components/SplashDocsRail.astro',
       'site/test/components/lifecycle.spec.ts','site/playwright.components.config.ts','site/package.json','site/package-lock.json']
def sha(b):return hashlib.sha256(b).hexdigest()
def git(*args):return subprocess.check_output([GIT,*args],cwd=R)
def capture():
 physical={p:sha((R/p).read_bytes()) for p in paths}
 immutable={p:sha(git('show',SOURCE+':'+p)) for p in paths}
 assert physical==immutable
 return {'physical':physical,'immutable_Git':immutable}
def runtime():
 files=[NODE,CHROME,R/'site/node_modules/@playwright/test/package.json',R/'site/node_modules/playwright/package.json',R/'site/node_modules/playwright-core/package.json',R/'site/node_modules/typescript/package.json',R/'site/node_modules/typescript/lib/typescript.js']
 return {str(p):sha(p.read_bytes()) for p in files}
before=capture();tools_before=runtime();head=git('rev-parse','HEAD').decode().strip()
env={k:os.environ[k] for k in ['SystemRoot','WINDIR','TEMP','TMP','COMSPEC','PATHEXT'] if k in os.environ}
home=O/'home';env.update(PATH=str(NODE.parent)+';C:/Program Files/Git/cmd;C:/Windows/System32',HOME=str(home),USERPROFILE=str(home),HOMEDRIVE='C:',HOMEPATH=str(home)[2:],APPDATA=str(home/'AppData/Roaming'),LOCALAPPDATA=str(home/'AppData/Local'),XDG_CONFIG_HOME=str(home/'.config'),XDG_CACHE_HOME=str(home/'.cache'),COMPONENT_SOURCE_REF=SOURCE,PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD='1',DEBUG='pw:browser')
args=[str(NODE),str(R/'site/node_modules/@playwright/test/cli.js'),'test','test/components/lifecycle.spec.ts','--config=playwright.components.config.ts','--reporter=json','--output='+str(O/'playwright-output')]
start={'source_commit':SOURCE,'actual_HEAD_before':head,'inputs_before':before,'runtime_files_before':tools_before,'configured_browser':'installed Chrome channel; file version156.0.8078.80 observed separately','node_version':subprocess.check_output([str(NODE),'--version']).decode().strip(),'argv':args,'cwd':str(R/'site'),'environment':env,'boundary':'existing isolated browser component fixture, no production build/page or actual Pagefind search index'}
(O/'start.json').write_text(json.dumps(start,indent=2)+'\n',encoding='utf-8')
t=time.time();p=subprocess.run(args,cwd=R/'site',env=env,capture_output=True,timeout=90);seconds=time.time()-t
(O/'original-report.json').write_bytes(p.stdout);(O/'browser.stderr.log').write_bytes(p.stderr)
after=capture();tools_after=runtime();end={'actual_HEAD_after':git('rev-parse','HEAD').decode().strip(),'inputs_after':after,'runtime_files_after':tools_after,'exit_code':p.returncode,'seconds':seconds,'stdout_sha256':sha(p.stdout),'stderr_sha256':sha(p.stderr)}
(O/'result.json').write_text(json.dumps(end,indent=2)+'\n',encoding='utf-8')
assert before==after and tools_before==tools_after
print(json.dumps({'exit_code':p.returncode,'seconds':seconds,'source_inputs':len(paths),'input_runtime_bytes_unchanged':True,'actual_HEAD_before':head,'actual_HEAD_after':end['actual_HEAD_after']}))
if p.returncode:
 print(p.stdout.decode('utf-8',errors='replace')[-2000:]);print(p.stderr.decode('utf-8',errors='replace')[-2000:])
