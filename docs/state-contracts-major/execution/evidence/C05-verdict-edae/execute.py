"""Wait for Root's explicit committed source, then perform only the C05 cohort."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

OUT=Path(__file__).resolve().parent
REPO=Path(r'C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter')
GIT=r'C:/Program Files/Git/cmd/git.exe'
parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);args=parser.parse_args()
selection=json.loads((OUT/'selection.json').read_text(encoding='utf-8'))
assert len(selection['names'])==11, 'Await exact frozen preflight selector; no execution until scope complete'
digest=lambda b:hashlib.sha256(b).hexdigest()
def git(*argv):return subprocess.check_output([GIT,'--no-lazy-fetch',*argv],cwd=REPO)
def identity():
    path=Path(git('rev-parse','--path-format=absolute','--git-path','index').decode().strip())
    return {'HEAD':git('rev-parse','HEAD').decode().strip(),'index_sha256':digest(path.read_bytes())}
def save(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')
inputs=['.github/scripts/run_concurrent_suites.py','.github/scripts/test_run_concurrent_suites.py']
before=identity();assert before['HEAD']==args.source
physical={path:digest((REPO/path).read_bytes()) for path in inputs}
assert all(digest(git('show',args.source+':'+path))==value for path,value in physical.items())
old_runtime=json.loads(Path(r'C:/Users/brenn/AppData/Local/Temp/ca-P02-six-current-w6gyvg7a/run-start.json').read_bytes())['runtime']
runtime={path:digest(Path(path).read_bytes()) for path in old_runtime}
pth={str(path):digest(path.read_bytes()) for path in (Path(sys.base_prefix)/'Lib/site-packages').glob('*.pth')}
assert not pth,'Unexpected system site activation requires inspection before child effects'
home=OUT/'profile'
for name in ['home','appdata','localappdata','tmp','pycache','xdg/config','xdg/cache']:(home/name).mkdir(parents=True,exist_ok=False)
env={key:os.environ[key] for key in ['SystemRoot','WINDIR','COMSPEC','PATHEXT'] if key in os.environ}
env.update(HOME=str(home/'home'),USERPROFILE=str(home/'home'),APPDATA=str(home/'appdata'),LOCALAPPDATA=str(home/'localappdata'),
    TEMP=str(home/'tmp'),TMP=str(home/'tmp'),XDG_CONFIG_HOME=str(home/'xdg/config'),XDG_CACHE_HOME=str(home/'xdg/cache'),
    PATH=str(Path(os.environ['SystemRoot'])/'System32'),PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',
    PYTHONIOENCODING='utf-8',PYTHONPYCACHEPREFIX=str(home/'pycache'))
argv=[sys.executable,'-I','-S','-B','-X','utf8','-X','pycache_prefix='+str(home/'pycache'),str(OUT/'observe-tests.py')]
start={'format':'C05-current-run-start/1','source_commit':args.source,'identity':before,'inputs':physical,'runtime':runtime,'system_site_pth':pth,
    'argv':argv,'cwd':str(OUT),'environment':env,'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'observer_sha256':digest((OUT/'observe-tests.py').read_bytes()),'producer_sha256':digest(Path(__file__).read_bytes())}
save('run-start.json',start)
clock=time.monotonic();child=subprocess.run(argv,cwd=OUT,env=env,capture_output=True,timeout=100);seconds=time.monotonic()-clock
(OUT/'original.stdout.log').write_bytes(child.stdout);(OUT/'original.stderr.log').write_bytes(child.stderr)
after=identity();after_inputs={path:digest((REPO/path).read_bytes()) for path in inputs}
runtime_after={path:digest(Path(path).read_bytes()) for path in old_runtime}
observation=json.loads((OUT/'observations.json').read_bytes())
result={'format':'C05-current-run-result/1','source_commit':args.source,'exit_code':child.returncode,'seconds':seconds,
    'identity_after':after,'inputs_after':after_inputs,'runtime_after':runtime_after,
    'source_runtime_HEAD_index_stable':before==after and physical==after_inputs and runtime==runtime_after,
    'named_methods':observation['actual_tests_run'],'errors':observation['errors'],'failures':observation['failures'],'skipped':observation['skipped'],
    'private_profile_before_source_imports':True,'source_lookups':'Test and runner loaded by exact file path in isolated/no-site parent; children use owned fixture paths and standard library, with no inherited PYTHONPATH/host profile.'}
save('run-result.json',result)
assert child.returncode==0 and result['source_runtime_HEAD_index_stable'] and result['named_methods']==11 and not any(result[name] for name in ['errors','failures','skipped'])
assert len(observation['interpreter_wrapper'])==1 and observation['runtime']['isolated'] and observation['runtime']['no_site']
print(json.dumps({name:result[name] for name in ['source_commit','exit_code','seconds','named_methods','source_runtime_HEAD_index_stable']}))
