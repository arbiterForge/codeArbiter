import datetime
import hashlib
import json
import os
from pathlib import Path,PureWindowsPath
import re
import stat
import subprocess
import sys
import time

OUT=Path(__file__).resolve().parent
REPO=Path(r'C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter')
GIT=r'C:/Program Files/Git/cmd/git.exe'
SOURCE='8d04b33c4e8b6ac56644cbd2517cae2dde228d64'
OLD=Path(r'C:/Users/brenn/AppData/Local/Temp/ca-P02-six-current-w6gyvg7a')
ROOTS=['.github/scripts','core/pysrc']
digest=lambda b:hashlib.sha256(b).hexdigest()
def save(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')
def git(*args):return subprocess.check_output([GIT,'--no-lazy-fetch',*args],cwd=REPO)
def identity():
    index=Path(git('rev-parse','--path-format=absolute','--git-path','index').decode().strip())
    return {'head':git('rev-parse','HEAD').decode().strip(),'index_sha256':digest(index.read_bytes())}
def git_namespace(root):
    raw=git('ls-tree','-z','-l','-r','-t',SOURCE+':'+root)
    assert raw.endswith(b'\0') and len(raw)<=2*1024*1024
    result=[]
    for row in raw.split(b'\0')[:-1]:
        header,name=row.split(b'\t',1);mode,kind,oid,size=header.decode('ascii').split()
        name=name.decode('utf-8');assert name.isascii() and ':' not in name and '\\' not in name and '..' not in name.split('/')
        assert (mode,kind) in [('040000','tree'),('100644','blob'),('100755','blob')]
        result.append([name,mode,kind])
    assert len(result)<=4096 and len({name.lower() for name,_,_ in result})==len(result)
    return sorted(result,key=lambda row:PureWindowsPath(row[0]))
def physical_namespace(root):
    result={}
    def walk(base):
        children=sorted(base.iterdir(),key=lambda p:p.name)
        for p in children:
            info=p.lstat();relative=p.relative_to(REPO/root).as_posix()
            reparse=bool(getattr(info,'st_file_attributes',0)&0x400)
            kind='symlink-or-reparse' if p.is_symlink() or reparse else 'directory' if stat.S_ISDIR(info.st_mode) else 'file' if stat.S_ISREG(info.st_mode) else 'unsupported'
            result[relative]={'kind':kind,'physical_mode':oct(stat.S_IMODE(info.st_mode))}
            assert kind in ('directory','file'),(root,relative,kind)
            if kind=='directory':walk(p)
            else:result[relative]['sha256']=digest(p.read_bytes())
    walk(REPO/root)
    return result
def projection(root,tracked,physical):
    names={name for name,_,_ in tracked};extra=sorted(set(physical)-names)
    # Preserve all legacy __pycache__ names/hashes. A fresh private prefix makes
    # these source caches unselected; never excuse a direct/package shadow.
    legacy=[name for name in extra if '__pycache__' in name.split('/')]
    other=[name for name in extra if name not in legacy]
    causal=[name for name in other if name.lower().endswith(('.py','.pyc','.pyd','.pyw')) or physical[name]['kind']=='directory']
    assert not causal,('untracked potential import shadow',root,causal)
    assert not (names-set(physical)),('tracked member absent physically',root,names-set(physical))
    return {'Git_names_equal_physical_names':set(physical)==names,'untracked_legacy_cache_entries':legacy,
        'untracked_other_entries':other,'causal_untracked_shadows':causal,
        'mode_semantics':'Git modes are retained separately from literal Windows physical permission modes; no equality is inferred.',
        'legacy_cache_semantics':'Complete physical entries retained. PYTHONPYCACHEPREFIX is private before imports; Python FileFinder scans direct suffix candidates, not source-absent __pycache__ modules. Existing source caches are not ignored in inventory or deleted.'}
old_proof=json.loads((OLD/'integration-fixtures.json').read_bytes())
old_start=json.loads((OLD/'run-start.json').read_bytes())
positive_names=set(old_proof['inputs'])
before_id=identity();assert before_id['head']==SOURCE
before_inputs={name:digest((REPO/name).read_bytes()) for name in sorted(positive_names)}
assert all(digest(git('show',SOURCE+':'+name))==value for name,value in before_inputs.items())
git_before={root:git_namespace(root) for root in ROOTS}
physical_before={root:physical_namespace(root) for root in ROOTS}
projections={root:projection(root,git_before[root],physical_before[root]) for root in ROOTS}
runtime_paths=list(old_start['runtime'])
runtime_before={name:digest(Path(name).read_bytes()) for name in runtime_paths}
assert len(runtime_before)==1905
module_resolution={}
for module,old in old_start['module_resolution'].items():
    present=[name for name in old['candidates'] if name.split('/',2)[-1]]
    actual_present=[];absent=[]
    for name in old['candidates']:
        root=next(root for root in ROOTS if name.startswith(root+'/'))
        relative=name[len(root)+1:]
        # All ancestor namespace names were successfully enumerated above.
        seen=[n for n in physical_before[root] if n.lower()==relative.lower()]
        assert len(seen)<=1
        if seen:actual_present.append(name)
        else:absent.append(name)
    module_resolution[module]={'candidates':old['candidates'],'present':actual_present,'absent':absent}
assert sum(len(row['absent']) for row in module_resolution.values())==7
fixture_parameters={name:digest((REPO/name).read_bytes()) for name in ['docs/state-contracts-major/execution/coverage-ledger.json','docs/state-contracts-major/execution/progress.json']}
home=OUT/'profile'
for relative in ['home','appdata','localappdata','xdg/config','xdg/cache','tmp','pycache']:(home/relative).mkdir(parents=True,exist_ok=False)
env={k:os.environ[k] for k in ['SystemRoot','WINDIR','COMSPEC','PATHEXT'] if k in os.environ}
env.update(PATH=str(Path(GIT).parent)+os.pathsep+str(Path(os.environ['SystemRoot'])/'System32'),
    HOME=str(home/'home'),USERPROFILE=str(home/'home'),APPDATA=str(home/'appdata'),LOCALAPPDATA=str(home/'localappdata'),
    XDG_CONFIG_HOME=str(home/'xdg/config'),XDG_CACHE_HOME=str(home/'xdg/cache'),TEMP=str(home/'tmp'),TMP=str(home/'tmp'),
    PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',PYTHONIOENCODING='utf-8',
    PYTHONPYCACHEPREFIX=str(home/'pycache'),PYTHONPATH=str(OUT/'observer'),GIT_CONFIG_NOSYSTEM='1',
    GIT_CONFIG_GLOBAL=str(home/'home/no-global-config'),GIT_TERMINAL_PROMPT='0',GIT_NO_LAZY_FETCH='1',GIT_NO_REPLACE_OBJECTS='1')
argv=old_start['argv']
assert argv[:8]==['C:/Python314/python.exe','-B','-X','utf8','-m','unittest','-v',argv[7]] and len(argv)==21
start={'format':'P02-python-namespace-run-start/1','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'source_commit':SOURCE,'identity':before_id,'inputs':before_inputs,'fixture_parameters':fixture_parameters,
    'Git_namespaces':git_before,'physical_namespaces':physical_before,'namespace_projection':projections,
    'runtime':runtime_before,'module_resolution':module_resolution,'environment':env,'argv':argv,'cwd':str(REPO/'.github/scripts'),
    'observer_sha256':digest((OUT/'observer/sitecustomize.py').read_bytes()),'producer_sha256':digest(Path(__file__).read_bytes())}
save('run-start.json',start)
clock=time.monotonic()
p=subprocess.run(argv,cwd=REPO/'.github/scripts',env=env,capture_output=True,timeout=110)
seconds=time.monotonic()-clock
(OUT/'selected14.stdout.log').write_bytes(p.stdout);(OUT/'selected14.stderr.log').write_bytes(p.stderr)
after_id=identity()
after_inputs={name:digest((REPO/name).read_bytes()) for name in before_inputs}
git_after={root:git_namespace(root) for root in ROOTS}
physical_after={root:physical_namespace(root) for root in ROOTS}
runtime_after={name:digest(Path(name).read_bytes()) for name in runtime_paths}
fixture_after={name:digest((REPO/name).read_bytes()) for name in fixture_parameters}
imports=json.loads((OUT/'actual-imports.json').read_bytes())
loaded={**imports['executed_repository_modules'],**{v['path']:v['sha256'] for v in imports['loaded_repository_modules'].values()}}
for name,value in loaded.items():
    if name in before_inputs:assert before_inputs[name]==value
    else:
        root=next(root for root in ROOTS if name.startswith(root+'/'))
        relative=name[len(root)+1:]
        assert physical_before[root][relative]['sha256']==physical_after[root][relative]['sha256']==value
        before_inputs[name]=value;after_inputs[name]=value
    assert digest(git('show',SOURCE+':'+name))==value
text=p.stderr.decode('utf-8');named=[]
for name in argv[7:]:
    method=name.rsplit('.',1)[1]
    pattern=r'(?m)^'+re.escape(method)+r' \('+re.escape(name)+r'\) \.\.\. ([^\r\n]+)\r?$'
    named.append({'id':name,'outcomes':re.findall(pattern,text)})
stable=before_id==after_id and before_inputs==after_inputs and git_before==git_after and physical_before==physical_after and runtime_before==runtime_after and fixture_parameters==fixture_after
result={'format':'P02-python-namespace-run-result/1','source_commit':SOURCE,'exit_code':p.returncode,'seconds':seconds,
    'argv':argv,'cwd':str(REPO/'.github/scripts'),'named_results':named,'identity_after':after_id,
    'inputs_before':before_inputs,'inputs_after':after_inputs,'Git_namespaces_after':git_after,'physical_namespaces_after':physical_after,
    'runtime_after':runtime_after,'fixture_parameters_after':fixture_after,'all_causal_inputs_namespaces_runtime_parameters_stable':stable,
    'actual_imports_match_before_Git_physical':True,'observer_errors':imports['observer_errors'],
    'limits':'Local fourteen existing disposable Git/workflow fixture assertions only; no hosted, native/installed, provider or publication eligibility claim.'}
save('run-result.json',result)
assert p.returncode==0 and stable and len(named)==14 and all(row['outcomes']==['ok'] for row in named) and not imports['observer_errors']
print(json.dumps({'passed':len(named),'seconds':seconds,'source':SOURCE,'positive_inputs':len(before_inputs),'runtime_files':1905,'Git_physical_names_equal':{root:projections[root]['Git_names_equal_physical_names'] for root in ROOTS},'causal_closure_stable':stable}))
