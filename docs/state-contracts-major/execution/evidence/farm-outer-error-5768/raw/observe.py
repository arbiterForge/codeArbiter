from pathlib import Path
import os,json,subprocess,time,hashlib
p=Path(__file__).parent;r=Path(r'C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter');t=p/'candidate/plugins/ca/tools';home=p/'home';home.mkdir(exist_ok=True);node=Path(r'C:/Users/brenn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe');env={}
for canonical in ['SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','TEMP','TMP']:
 for k,v in os.environ.items():
  if k.upper()==canonical:env[canonical]=v;break
env.update(PATH=str(node.parent)+';C:/Program Files/Git/cmd;C:/Windows/System32',HOME=str(home),USERPROFILE=str(home),HOMEDRIVE=home.drive,HOMEPATH=str(home)[len(home.drive):],APPDATA=str(home/'AppData/Roaming'),LOCALAPPDATA=str(home/'AppData/Local'),XDG_CONFIG_HOME=str(home/'.config'),XDG_CACHE_HOME=str(home/'.cache'),GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='NUL',GIT_OPTIONAL_LOCKS='0',NPM_CONFIG_USERCONFIG=str(home/'.npmrc'),NPM_CONFIG_GLOBALCONFIG=str(home/'global-npmrc'))
h=lambda b:hashlib.sha256(b).hexdigest();inputs=lambda:{str(f.relative_to(p/'candidate')).replace('\\','/'):h(f.read_bytes()) for f in (p/'candidate').rglob('*') if f.is_file() and 'node_modules' not in f.parts};records=[]
def run(label,argv):
 before=inputs();start=time.monotonic();v=subprocess.run([str(a) for a in argv],cwd=t,env=env,capture_output=True,timeout=90);(p/(label+'.stdout')).write_bytes(v.stdout);(p/(label+'.stderr')).write_bytes(v.stderr);o={'label':label,'argv':[str(a) for a in argv],'cwd':str(t),'exit_code':v.returncode,'seconds':time.monotonic()-start,'private_home_before_import':str(home),'environment_keys':sorted(env),'runtime_sha256':h(node.read_bytes()),'inputs_before':before,'inputs_after':inputs()};records.append(o);(p/'commands.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:v for k,v in o.items() if not k.startswith('inputs')}),flush=True);return v.returncode
def check(label,pattern):return run(label,[node,r/'plugins/ca/tools/node_modules/vitest/vitest.mjs','run','farm-interruption.test.ts','--testNamePattern',pattern,'--reporter=json','--outputFile='+str(p/(label+'.json'))])
pattern='real outer branch-creation failure|unblocked real post-merge hook control'
assert check('characterization-three',pattern)==0
helper=t/'farm.ts';original=helper.read_bytes();(p/'farm.original.ts').write_bytes(original);needle=b'await writeReport(plan, [...done.values()], blocked, aborted, runId, health);';assert original.count(needle)==1
try:
 helper.write_bytes(original.replace(needle,b'if(false) '+needle));assert check('missing-final-report-negative','real outer branch-creation failure.*source')==1
 o=json.loads((p/'missing-final-report-negative.json').read_text(encoding='utf-8'));failed=[a for s in o['testResults'] for a in s['assertionResults'] if a['status']=='failed'];assert len(failed)==1 and any('expected false to be true' in v for v in failed[0]['failureMessages'])
finally:helper.write_bytes(original)
assert helper.read_bytes()==original
assert check('final-three',pattern)==0
assert run('typecheck',[node,r/'plugins/ca/tools/node_modules/typescript/bin/tsc','--noEmit'])==0
