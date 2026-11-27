from pathlib import Path
import hashlib,json,os,subprocess,time
R=Path('C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter')
O=Path(__file__).resolve().parent
SOURCE='45a6a8e33db6c6143bbddc4bd009b7e7bac79207'
GIT='C:/Program Files/Git/cmd/git.exe'
NODE=Path('C:/Users/brenn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
CHROME=Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
paths=['site/src/components/Search.astro','site/playwright.components.config.ts','site/package.json','site/package-lock.json']
new='site/test/components/search-boundaries.spec.ts'
def sha(b):return hashlib.sha256(b).hexdigest()
def git(*args):return subprocess.check_output([GIT,*args],cwd=R)
for p in paths:
 b=git('show',SOURCE+':'+p)
 assert b==(R/p).read_bytes(),p
 (O/p).parent.mkdir(parents=True,exist_ok=True)
 (O/p).write_bytes(b)
def capture():
 result={}
 for p in paths:
  b=(O/p).read_bytes();expected=git('show',SOURCE+':'+p)
  assert b==expected==(R/p).read_bytes(),p
  result[p]={'physical':sha(b),'immutable_Git':sha(expected)}
 result[new]={'physical':sha((O/new).read_bytes()),'immutable_Git':None,'epoch':'Temp new-test overlay'}
 return result
runtime_paths=[NODE,CHROME,*[R/'site/node_modules'/p for p in ['@playwright/test/package.json','playwright/package.json','playwright-core/package.json','typescript/package.json','typescript/lib/typescript.js']]]
def runtime():return {str(p):sha(p.read_bytes()) for p in runtime_paths}
before=capture();tools=runtime();head=git('rev-parse','HEAD').decode().strip();index=sha(git('diff','--cached','--binary'))
env={k:os.environ[k] for k in ['SystemRoot','WINDIR','TEMP','TMP','COMSPEC','PATHEXT'] if k in os.environ}
home=O/'home'
for d in ['AppData/Roaming','AppData/Local','.config','.cache']:(home/d).mkdir(parents=True,exist_ok=True)
env.update(PATH=str(NODE.parent)+';C:/Program Files/Git/cmd;C:/Windows/System32',HOME=str(home),USERPROFILE=str(home),HOMEDRIVE='C:',HOMEPATH=str(home)[2:],APPDATA=str(home/'AppData/Roaming'),LOCALAPPDATA=str(home/'AppData/Local'),XDG_CONFIG_HOME=str(home/'.config'),XDG_CACHE_HOME=str(home/'.cache'),PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD='1')
args=[str(NODE),str(R/'site/node_modules/@playwright/test/cli.js'),'test','test/components/search-boundaries.spec.ts','--config=playwright.components.config.ts','--reporter=json','--output='+str(O/'playwright-output')]
start={'source_commit':SOURCE,'HEAD_before':head,'index_before':index,'inputs_before':before,'runtime_before':tools,'argv':args,'cwd':str(O/'site'),'environment':env,'runtime_version':subprocess.check_output([str(NODE),'--version']).decode().strip(),'scope':'Actual Search markup/script, controlled fake Pagefind, real installed Chrome; Temp test overlay not committed'}
(O/'start.json').write_text(json.dumps(start,indent=2)+'\n',encoding='utf-8')
t=time.time();p=subprocess.run(args,cwd=O/'site',env=env,capture_output=True,timeout=90)
(O/'original-report.json').write_bytes(p.stdout);(O/'stderr.log').write_bytes(p.stderr)
after=capture();tools_after=runtime()
end={'exit_code':p.returncode,'seconds':time.time()-t,'inputs_after':after,'runtime_after':tools_after,'HEAD_after':git('rev-parse','HEAD').decode().strip(),'index_after':sha(git('diff','--cached','--binary')),'stdout_sha256':sha(p.stdout),'stderr_sha256':sha(p.stderr)}
(O/'result.json').write_text(json.dumps(end,indent=2)+'\n',encoding='utf-8')
assert before==after and tools==tools_after
print(json.dumps({k:v for k,v in end.items() if not isinstance(v,dict)}))
if p.returncode:print(p.stdout.decode('utf8',errors='replace')[-5000:]);print(p.stderr.decode('utf8',errors='replace')[-1500:])
