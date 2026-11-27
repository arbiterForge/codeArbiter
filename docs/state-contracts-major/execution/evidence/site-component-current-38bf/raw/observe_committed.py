from pathlib import Path
import hashlib,json,os,subprocess,sys,tempfile,time
R=Path('C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter')
GIT='C:/Program Files/Git/cmd/git.exe'
NODE=Path('C:/Users/brenn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
CHROME=Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
NPM=Path('C:/Program Files/nodejs/node_modules/npm/bin/npm-cli.js')
SOURCE=sys.argv[1]
def sha(b):return hashlib.sha256(b).hexdigest()
def git(*args):return subprocess.check_output([GIT,*args],cwd=R)
assert git('rev-parse','HEAD').decode().strip()==SOURCE
O=Path(tempfile.mkdtemp(prefix='ca-component10-committed-'+SOURCE[:8]+'-'))
paths=['site/src/components/Search.astro','site/src/components/SplashDocsRail.astro','site/test/components/lifecycle.spec.ts','site/test/components/search-boundaries.spec.ts','site/playwright.components.config.ts','site/package.json','site/package-lock.json']
for p in paths:
 b=git('show',SOURCE+':'+p);target=O/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b)
assert json.loads((O/'site/package.json').read_text(encoding='utf8'))['scripts']['test:components']=='playwright test --config=playwright.components.config.ts'
subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',"New-Item -ItemType Junction -Path '"+str(O/'site/node_modules')+"' -Target '"+str(R/'site/node_modules')+"' | Out-Null"],check=True,capture_output=True)
def capture():
 out={}
 for p in paths:
  b=(O/p).read_bytes();g=git('show',SOURCE+':'+p);assert b==g,p
  out[p]={'executed_Temp':sha(b),'immutable_Git':sha(g),'Gov_physical':sha((R/p).read_bytes())}
 return out
runtime_paths=[NODE,CHROME,NPM,*[R/'site/node_modules'/p for p in ['@playwright/test/package.json','playwright/package.json','playwright-core/package.json','typescript/package.json','typescript/lib/typescript.js']]]
def runtime():return {str(p):sha(p.read_bytes()) for p in runtime_paths}
before=capture();tools=runtime();head=git('rev-parse','HEAD').decode().strip();index=sha(git('diff','--cached','--binary'))
env={k:os.environ[k] for k in ['SystemRoot','WINDIR','TEMP','TMP','COMSPEC','PATHEXT'] if k in os.environ}
home=O/'home'
for p in ['AppData/Roaming','AppData/Local','.config','.cache']:(home/p).mkdir(parents=True,exist_ok=True)
env.update(PATH=str(NODE.parent)+';C:/Program Files/Git/cmd;C:/Windows/System32',HOME=str(home),USERPROFILE=str(home),HOMEDRIVE='C:',HOMEPATH=str(home)[2:],APPDATA=str(home/'AppData/Roaming'),LOCALAPPDATA=str(home/'AppData/Local'),XDG_CONFIG_HOME=str(home/'.config'),XDG_CACHE_HOME=str(home/'.cache'),PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD='1')
args=[str(NODE),str(NPM),'--silent','run','test:components','--','--reporter=json','--output='+str(O/'playwright-output')]
start={'source_commit':SOURCE,'actual_HEAD_before':head,'actual_index_before':index,'inputs_before':before,'runtime_before':tools,'argv':args,'cwd':str(O/'site'),'environment':env,'scope':'Exact committed7-input component source copied byte-for-byte to Temp; admitted node_modules junction. Actual installed Chrome, controlled Pagefind/markup, not production-page/index.','node_version':subprocess.check_output([str(NODE),'--version']).decode().strip(),'npm_version':subprocess.check_output([str(NODE),str(NPM),'--version']).decode().strip()}
(O/'start.json').write_text(json.dumps(start,indent=2)+'\n',encoding='utf8')
(O/'observe_committed.py').write_bytes(Path(__file__).read_bytes())
t=time.time();p=subprocess.run(args,cwd=O/'site',env=env,capture_output=True,timeout=90)
(O/'original-report.json').write_bytes(p.stdout);(O/'stderr.log').write_bytes(p.stderr)
after=capture();tools_after=runtime()
end={'exit_code':p.returncode,'seconds':time.time()-t,'inputs_after':after,'runtime_after':tools_after,'actual_HEAD_after':git('rev-parse','HEAD').decode().strip(),'actual_index_after':sha(git('diff','--cached','--binary')),'stdout_sha256':sha(p.stdout),'stderr_sha256':sha(p.stderr)}
(O/'result.json').write_text(json.dumps(end,indent=2)+'\n',encoding='utf8')
assert before==after and tools==tools_after
print(json.dumps({'folder':str(O),**{k:v for k,v in end.items() if not isinstance(v,dict)}}))
if p.returncode:print(p.stdout.decode('utf8',errors='replace')[-4000:]);print(p.stderr.decode('utf8',errors='replace')[-1500:])
