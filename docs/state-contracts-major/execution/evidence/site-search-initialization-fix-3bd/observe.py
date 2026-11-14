from pathlib import Path
import hashlib,json,os,subprocess,time
R=Path('C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter')
O=Path(__file__).resolve().parent
GIT='C:/Program Files/Git/cmd/git.exe'
NODE=Path('C:/Users/brenn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
CHROME=Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
NPM=Path('C:/Program Files/nodejs/node_modules/npm/bin/npm-cli.js')
SOURCE='3bd40349f4a403a38ac01979369875faad258548'
NEW='site/test/components/search-interactions.spec.ts'
def sha(b):return hashlib.sha256(b).hexdigest()
def git(*args):return subprocess.check_output([GIT,*args],cwd=R)
assert git('rev-parse','HEAD').decode().strip()==SOURCE
old=json.loads((R/'docs/state-contracts-major/execution/evidence/site-component-current-38bf/component-tested.json').read_text(encoding='utf8'))
paths=list(old['inputs'])
initial={p:sha((O/p).read_bytes()) for p in paths}
new_hash=sha((O/NEW).read_bytes())
subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',"New-Item -ItemType Junction -Path '"+str(O/'site/node_modules')+"' -Target '"+str(R/'site/node_modules')+"' | Out-Null"],check=True,capture_output=True)
def capture():
 out={}
 for p in paths:
  b=(O/p).read_bytes();g=git('show',SOURCE+':'+p);assert sha(b)==initial[p],p
  if p!='site/src/components/Search.astro':assert b==g,p
  out[p]={'executed_Temp':sha(b),'immutable_Git':sha(g),'Gov_physical':sha((R/p).read_bytes())}
 out[NEW]={'Temp_overlay':sha((O/NEW).read_bytes()),'immutable_Git':None}
 assert out[NEW]['Temp_overlay']==new_hash
 return out
runtime_paths=[NODE,CHROME,NPM,*[R/'site/node_modules'/p for p in ['@playwright/test/package.json','playwright/package.json','playwright-core/package.json','typescript/package.json','typescript/lib/typescript.js']]]
def runtime():return {str(p):sha(p.read_bytes()) for p in runtime_paths}
before=capture();tools=runtime();head=git('rev-parse','HEAD').decode().strip();index=sha(git('diff','--cached','--binary'))
env={k:os.environ[k] for k in ['SystemRoot','WINDIR','TEMP','TMP','COMSPEC','PATHEXT'] if k in os.environ}
home=O/'home'
for p in ['AppData/Roaming','AppData/Local','.config','.cache']:(home/p).mkdir(parents=True,exist_ok=True)
env.update(PATH=str(NODE.parent)+';C:/Program Files/Git/cmd;C:/Windows/System32',HOME=str(home),USERPROFILE=str(home),HOMEDRIVE='C:',HOMEPATH=str(home)[2:],APPDATA=str(home/'AppData/Roaming'),LOCALAPPDATA=str(home/'AppData/Local'),XDG_CONFIG_HOME=str(home/'.config'),XDG_CACHE_HOME=str(home/'.cache'),PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD='1')
args=[str(NODE),str(NPM),'--silent','run','test:components','--','test/components/search-interactions.spec.ts','--reporter=json','--output='+str(O/'playwright-output')]
tc=[str(NODE),str(R/'site/node_modules/typescript/bin/tsc'),'--noEmit','--target','ES2022','--module','ESNext','--moduleResolution','Bundler','--lib','ES2022','--types','node','--strict','--esModuleInterop','--skipLibCheck','--forceConsistentCasingInFileNames','--resolveJsonModule','test/components/search-interactions.spec.ts']
start={'source_commit':SOURCE,'HEAD_before':head,'index_before':index,'inputs_before':before,'runtime_before':tools,'argv':args,'cwd':str(O/'site'),'environment':env,'test_scope':'Six focused tests only; actual3bd source plus intentional Search/new-test Temp overlays. Gov originals preserved; no production-page/index claim.','typecheck_argv':tc}
(O/'start.json').write_text(json.dumps(start,indent=2)+'\n',encoding='utf8')
t=time.time();typed=subprocess.run(tc,cwd=O/'site',env=env,capture_output=True,timeout=30)
(O/'typecheck.stdout.log').write_bytes(typed.stdout);(O/'typecheck.stderr.log').write_bytes(typed.stderr)
(O/'typecheck.json').write_text(json.dumps({'argv':tc,'cwd':str(O/'site'),'exit_code':typed.returncode,'seconds':time.time()-t},indent=2)+'\n',encoding='utf8')
assert typed.returncode==0,typed.stdout.decode('utf8',errors='replace')
t=time.time();p=subprocess.run(args,cwd=O/'site',env=env,capture_output=True,timeout=90)
(O/'original-report.json').write_bytes(p.stdout);(O/'stderr.log').write_bytes(p.stderr)
after=capture();tools_after=runtime()
end={'exit_code':p.returncode,'seconds':time.time()-t,'inputs_after':after,'runtime_after':tools_after,'HEAD_after':git('rev-parse','HEAD').decode().strip(),'index_after':sha(git('diff','--cached','--binary')),'stdout_sha256':sha(p.stdout),'stderr_sha256':sha(p.stderr)}
(O/'result.json').write_text(json.dumps(end,indent=2)+'\n',encoding='utf8')
assert before==after and tools==tools_after
print(json.dumps({k:v for k,v in end.items() if not isinstance(v,dict)}))
report=json.loads(p.stdout)
for suite in report['suites']:
 for spec in suite.get('specs',[]):
  print(spec['title'],spec['tests'][0]['status'])
  for outcome in spec['tests'][0]['results']:
   for error in outcome.get('errors',[]):print(error.get('message',''))
