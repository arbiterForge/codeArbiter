import datetime,hashlib,json,os,stat,subprocess,sys,time
from pathlib import Path,PureWindowsPath
OUT=Path(__file__).resolve().parent
REPO=Path(r'C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter')
SOURCE='4278a1800eeb89b7bf2ef3a6ec90b30bd8f0d84d'
GIT=r'C:/Program Files/Git/cmd/git.exe'
PY=r'C:/Python314/python.exe'
ROOTS=['core/pysrc','plugins/ca/hooks']
sha=lambda b:hashlib.sha256(b).hexdigest()
def save(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n',encoding='utf8',newline='\n')

def git(*args):return subprocess.check_output([GIT,'--no-lazy-fetch',*args],cwd=REPO)

def identity():
    index=Path(git('rev-parse','--path-format=absolute','--git-path','index').decode().strip())
    return {'head':git('rev-parse','HEAD').decode().strip(),'tree':git('rev-parse','HEAD^{tree}').decode().strip(),'index_sha256':sha(index.read_bytes())}

def namespace(root):
    rows=[];raw=git('ls-tree','-z','-l','-r','-t',SOURCE+':'+root)
    assert len(raw)<=2*1024*1024
    for row in raw.split(b'\0'):
        if not row:continue
        header,name=row.split(b'\t',1);mode,kind,oid,size=header.decode().split();name=name.decode('utf8')
        assert name.isascii() and (mode,kind) in [('040000','tree'),('100644','blob'),('100755','blob')]
        rows.append([name,mode,kind])
    assert len(rows)<=4096 and len({x[0].casefold() for x in rows})==len(rows)
    return sorted(rows,key=lambda x:PureWindowsPath(x[0]))

def physical(root):
    result={}
    def visit(base):
        info=base.lstat();assert stat.S_ISDIR(info.st_mode) and not base.is_symlink() and not getattr(info,'st_file_attributes',0)&0x400
        for p in sorted(base.iterdir()):
            info=p.lstat();name=p.relative_to(REPO/root).as_posix()
            assert not p.is_symlink() and not getattr(info,'st_file_attributes',0)&0x400
            kind='directory' if stat.S_ISDIR(info.st_mode) else 'file' if stat.S_ISREG(info.st_mode) else 'unsupported';assert kind!='unsupported'
            result[name]={'kind':kind,'physical_mode':oct(stat.S_IMODE(info.st_mode))}
            if kind=='directory':visit(p)
            else:result[name]['sha256']=sha(p.read_bytes())
    visit(REPO/root);return result

def env_for(out):
    base=out/'profile'
    for rel in ('home','appdata','localappdata','xdg/config','xdg/cache','tmp','pycache'):(base/rel).mkdir(parents=True,exist_ok=False)
    env={k:os.environ[k] for k in ['SystemRoot','WINDIR','COMSPEC','PATHEXT'] if k in os.environ}
    env.update(PATH=str(Path(GIT).parent)+os.pathsep+str(Path(os.environ['SystemRoot'])/'System32'),HOME=str(base/'home'),USERPROFILE=str(base/'home'),APPDATA=str(base/'appdata'),LOCALAPPDATA=str(base/'localappdata'),XDG_CONFIG_HOME=str(base/'xdg/config'),XDG_CACHE_HOME=str(base/'xdg/cache'),TEMP=str(base/'tmp'),TMP=str(base/'tmp'),PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONPYCACHEPREFIX=str(base/'pycache'),PYTHONPATH=str(out/'observer'),GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=str(base/'home/no-global-config'),GIT_TERMINAL_PROMPT='0',GIT_NO_LAZY_FETCH='1',GIT_NO_REPLACE_OBJECTS='1')
    return env
runtime_paths=[v['path'] for v in json.loads((OUT/'runtime-seed.json').read_text())['runtime']]
assert len(runtime_paths)==len(set(runtime_paths))==1905
names=set(json.loads((OUT/'seed-proof.json').read_text())['inputs'])
def snapshot():
 inputs={n:sha((REPO/n).read_bytes()) for n in sorted(names)}
 assert all(sha(git('show',SOURCE+':'+n))==h for n,h in inputs.items())
 return {'identity':identity(),'inputs':inputs,'Git_namespaces':{s:namespace(s) for s in ROOTS},'physical_namespaces':{s:physical(s) for s in ROOTS},'runtime':[{'path':n,'sha256':sha(Path(n).read_bytes())} for n in runtime_paths],'fixture_parameters':{n:sha((REPO/n).read_bytes()) for n in ['docs/state-contracts-major/execution/coverage-ledger.json','docs/state-contracts-major/execution/progress.json']}}
assert identity()['head']==SOURCE
before=snapshot();env=env_for(OUT)
# The observer and driver are separate private paths; no write or import-shadow entry is added to the repository.
env['PYTHONPATH']=str(OUT/'observer')
argv=[PY,'-B','-X','utf8',str(OUT/'run-selected.py'),str(REPO),str(OUT)]
save(OUT/'run-start.json',{'format':'finite-statusline-refresh-start/1','source_commit':SOURCE,'snapshot':before,'environment':env,'argv':argv,'cwd':str(OUT),'started_utc':datetime.datetime.now(datetime.UTC).isoformat(),'driver_sha256':sha((OUT/'run-selected.py').read_bytes()),'observer_sha256':sha((OUT/'observer/sitecustomize.py').read_bytes())})
clock=time.monotonic()
try:
 process=subprocess.run(argv,cwd=OUT,env=env,capture_output=True,timeout=60);duration=time.monotonic()-clock
 (OUT/'original.stdout.log').write_bytes(process.stdout);(OUT/'original.stderr.log').write_bytes(process.stderr)
 save(OUT/'process-exit.json',{'argv':argv,'cwd':str(OUT),'exit_code':process.returncode,'seconds':duration,'stdout_sha256':sha(process.stdout),'stderr_sha256':sha(process.stderr)})
except BaseException as error:
 save(OUT/'process-failure.json',{'error_type':type(error).__name__,'seconds':time.monotonic()-clock});raise
# Persist the complete after closure before interpreting any test or observer result.
after=snapshot();save(OUT/'after-snapshot.json',after)
observations=[json.loads(p.read_text()) for p in OUT.glob('actual-imports-*.json')]
loaded={n:h for o in observations for n,h in o['executed_repository_modules'].items()}
for o in observations:
 for v in o['loaded_repository_modules'].values():loaded[v['path']]=v['sha256']
extra=set(loaded)-set(before['inputs'])
closure_errors=[]
for n,h in loaded.items():
 root=next((r for r in ROOTS if n.startswith(r+'/')),None)
 if root is None:closure_errors.append('outside-captured-import-root:'+n);continue
 rel=n[len(root)+1:]
 if before['physical_namespaces'][root].get(rel,{}).get('sha256')!=h or after['physical_namespaces'][root].get(rel,{}).get('sha256')!=h or sha(git('show',SOURCE+':'+n))!=h:closure_errors.append('source-byte-mismatch:'+n)
named=json.loads((OUT/'named-results.json').read_text())
result={'source_commit':SOURCE,'exit_code':process.returncode,'seconds':duration,'before_after_all_closure_equal':before==after,'positive_inputs':len(before['inputs']),'runtime_records':len(before['runtime']),'actual_imports':loaded,'additional_imports':sorted(extra),'closure_errors':closure_errors,'observer_files':[p.name for p in OUT.glob('actual-imports-*.json')],'observed_outcomes':named,'limits':'Local actual main/private settings with authenticated fixture Host seam, no installed/UI/native/provider/publication claim.'}
save(OUT/'run-result.json',result)
assert process.returncode==0 and before==after and len(observations)==1 and all(not x['observer_errors'] for x in observations) and not closure_errors and not extra
assert observations[0]['parent_no_user_site']==1 and Path(observations[0]['parent_pycache_prefix']).resolve()==Path(env['PYTHONPYCACHEPREFIX']).resolve()
assert named['run']==10 and len(named['outcomes'])==10 and all(x['outcome']=='PASS' for x in named['outcomes'])
save(OUT/'capture-complete.json',{'state':'CAPTURE_SEALED_RELEASE_SOURCE_HOLD','source_commit':SOURCE,'exit_code':process.returncode,'seconds':duration,'PASS':10,'positive_inputs':len(before['inputs']),'runtime_records':1905,'source_tree':before['identity']['tree'],'HEAD_index_source_runtime_namespaces_stable':True})
print(json.dumps({'sealed':str(OUT/'capture-complete.json'),'PASS':10,'seconds':duration,'inputs':len(before['inputs']),'actual_imports':len(loaded)}))
