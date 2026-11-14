from pathlib import Path
import hashlib,json,os,subprocess,time
R=Path('C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter')
O=Path(__file__).resolve().parent
GIT='C:/Program Files/Git/cmd/git.exe'
NODE=Path('C:/Users/brenn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
def sha(b):return hashlib.sha256(b).hexdigest()
def git(*args):return subprocess.check_output([GIT,*args],cwd=R)
paths=[p for p in git('ls-files','site').decode().splitlines() if p.endswith(('.ts','.json')) and ('/scripts/' in p or '/test/' in p or p in ['site/tsconfig.json','site/playwright.config.ts','site/package.json','site/package-lock.json'])]
head=git('rev-parse','HEAD').decode().strip()
def capture():
 out={}
 for p in paths:
  b=(R/p).read_bytes();g=git('show',head+':'+p)
  assert b.replace(b'\r\n',b'\n')==g.replace(b'\r\n',b'\n'),p
  out[p]={'physical':sha(b),'immutable_Git':sha(g),'literal_equal':b==g,'EOL_normalized_equal':True}
 return out
before=capture()
home=O/'home'
for p in ['AppData/Roaming','AppData/Local','.config','.cache']:(home/p).mkdir(parents=True,exist_ok=True)
env={k:os.environ[k] for k in ['SystemRoot','WINDIR','TEMP','TMP','COMSPEC','PATHEXT'] if k in os.environ}
env.update(PATH=str(NODE.parent)+';C:/Program Files/Git/cmd;C:/Windows/System32',HOME=str(home),USERPROFILE=str(home),APPDATA=str(home/'AppData/Roaming'),LOCALAPPDATA=str(home/'AppData/Local'),XDG_CONFIG_HOME=str(home/'.config'),XDG_CACHE_HOME=str(home/'.cache'))
args=[str(NODE),str(R/'site/node_modules/typescript/bin/tsc'),'--noEmit']
t=time.time();p=subprocess.run(args,cwd=R/'site',env=env,capture_output=True,timeout=60)
(O/'typecheck.stdout.log').write_bytes(p.stdout);(O/'typecheck.stderr.log').write_bytes(p.stderr)
after=capture();assert before==after
write={'argv':args,'declared_package_command':'typecheck: tsc --noEmit','cwd':str(R/'site'),'actual_source':head,'exit_code':p.returncode,'seconds':time.time()-t,'input_scope':'All tracked site script/test TypeScript/JSON selected below, config/manifests; physical/Git hashes include EOL-only checkout differences explicitly. Candidate changes only script text, workflow, Python contract; no TS semantic delta.','inputs_before':before,'inputs_after':after,'stdout_sha256':sha(p.stdout),'stderr_sha256':sha(p.stderr)}
(O/'typecheck.json').write_text(json.dumps(write,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:v for k,v in write.items() if k not in ['inputs_before','inputs_after']}))
if p.returncode:print(p.stdout.decode('utf8',errors='replace'));print(p.stderr.decode('utf8',errors='replace'))
