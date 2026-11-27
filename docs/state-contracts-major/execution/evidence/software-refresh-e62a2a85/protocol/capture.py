import datetime,hashlib,json,os,re,stat,subprocess,sys,time
from pathlib import Path,PureWindowsPath
OUT=Path(__file__).resolve().parent
REPO=Path(r'C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter')
SOURCE='e62a2a85a6a804bd14a80ad6faec5cb61aff8b20'
GIT=r'C:/Program Files/Git/cmd/git.exe'
PY=r'C:/Python314/python.exe'
ROOTS=['.github/scripts','core/pysrc']
selection=json.loads((OUT/'selection.json').read_text())
p02=json.loads((OUT/'seed-p02.json').read_text());recovery=json.loads((OUT/'seed-recovery.json').read_text())
oldstart=json.loads((OUT/'seed-p02_start.json').read_text())
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
runtime_paths=[v['path'] for v in oldstart['runtime']];assert len(runtime_paths)==len(set(runtime_paths))==1905
def runtime():return [{'path':name,'sha256':sha(Path(name).read_bytes())} for name in runtime_paths]
def host_lookup():
    physical_rows=[];git_rows=[];parent=REPO;relative=''
    for component in ('core','pysrc','_host.py'):
        info=parent.lstat();assert stat.S_ISDIR(info.st_mode) and not parent.is_symlink() and not getattr(info,'st_file_attributes',0)&0x400
        names=sorted(p.name for p in parent.iterdir());assert all(n.isascii() for n in names)
        matched=[n for n in names if n.casefold()==component.casefold()]
        raw=git('ls-tree','-z',SOURCE+(':'+relative if relative else ''));entries=[]
        for row in raw.split(b'\0'):
            if not row:continue
            header,name=row.split(b'\t',1);assert name.isascii();entries.append({'name':name.decode(),'entry':header.decode()})
        found=[v for v in entries if v['name'].casefold()==component.casefold()]
        physical_rows.append({'parent':relative or '.','successful_enumeration':True,'names':names,'matches':matched,'directory_identity':[info.st_dev,info.st_ino]})
        git_rows.append({'parent':relative or '.','successful_enumeration':True,'entries':entries,'matches':found,'stdout_sha256':sha(raw)})
        if component=='_host.py':assert matched==[] and found==[]
        else:
            assert matched==[component] and len(found)==1 and found[0]['name']==component and found[0]['entry'].startswith('040000 tree ')
            parent/=component;relative=(relative+'/'+component).lstrip('/')
    return {'descriptor':{'path':'core/pysrc/_host.py','path_style':'windows'},'physical':physical_rows,'immutable':git_rows}
def snapshot(names):
    known={name:sha((REPO/name).read_bytes()) for name in sorted(names)}
    assert all(sha(git('show',SOURCE+':'+name))==digest for name,digest in known.items())
    return {'identity':identity(),'inputs':known,'Git_namespaces':{s:namespace(s) for s in ROOTS},
        'physical_namespaces':{s:physical(s) for s in ROOTS},'runtime':runtime(),
        'owning_host_lookup':host_lookup(),'fixture_parameters':{n:sha((REPO/n).read_bytes()) for n in ['docs/state-contracts-major/execution/coverage-ledger.json','docs/state-contracts-major/execution/progress.json']}}
def projection(before):
    result={}
    for root in ROOTS:
        tracked={v[0] for v in before['Git_namespaces'][root]};seen=before['physical_namespaces'][root]
        assert not tracked-set(seen)
        extra=sorted(set(seen)-tracked);legacy=[p for p in extra if '__pycache__' in p.split('/')];other=[p for p in extra if p not in legacy]
        causal=[p for p in other if seen[p]['kind']=='directory' or p.casefold().endswith(('.py','.pyc','.pyo','.pyw','.pyd','.so'))]
        assert not causal,(root,causal)
        result[root]={'Git_names_equal_physical_names':tracked==set(seen),'legacy_cache_entries_preserved':legacy,'other_entries_preserved':other,'causal_untracked_shadows':causal,'limits':'All entries and byte hashes retained; Git/Windows physical modes are distinct. Legacy cache content is not deleted or called absent.'}
    return result
def lookups(before):
    found={}
    for module,entry in oldstart['module_resolution'].items():
        present=[];absent=[]
        for path in entry['candidates']:
            root=next(s for s in ROOTS if path.startswith(s+'/'));relative=path[len(root)+1:];matches=[n for n in before['physical_namespaces'][root] if n.casefold()==relative.casefold()]
            assert len(matches)<=1
            (present if matches else absent).append(path)
        found[module]={'candidates':entry['candidates'],'present':present,'absent':absent}
    assert sum(len(v['absent']) for v in found.values())==7
    return found

def env_for(out):
    base=out/'profile'
    for rel in ('home','appdata','localappdata','xdg/config','xdg/cache','tmp','pycache'):(base/rel).mkdir(parents=True,exist_ok=False)
    env={k:os.environ[k] for k in ['SystemRoot','WINDIR','COMSPEC','PATHEXT'] if k in os.environ}
    env.update(PATH=str(Path(GIT).parent)+os.pathsep+str(Path(os.environ['SystemRoot'])/'System32'),HOME=str(base/'home'),USERPROFILE=str(base/'home'),APPDATA=str(base/'appdata'),LOCALAPPDATA=str(base/'localappdata'),XDG_CONFIG_HOME=str(base/'xdg/config'),XDG_CACHE_HOME=str(base/'xdg/cache'),TEMP=str(base/'tmp'),TMP=str(base/'tmp'),PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONPYCACHEPREFIX=str(base/'pycache'),PYTHONPATH=str(out/'observer'),GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=str(base/'home/no-global-config'),GIT_TERMINAL_PROMPT='0',GIT_NO_LAZY_FETCH='1',GIT_NO_REPLACE_OBJECTS='1')
    return env
assert identity()['head']==SOURCE and selection['source']==SOURCE
initial=identity();results={}
for cohort,proof in [('p02',p02),('recovery',recovery)]:
    out=OUT/cohort;selectors=selection[cohort];names=set(proof['inputs'])
    if cohort=='recovery':names.update('plugins/'+host+'/hooks/_workflowrecoverylib.py' for host in ('ca','ca-codex','ca-pi'))
    before=snapshot(names);assert before['identity']==initial;proj=projection(before);lookup=lookups(before);env=env_for(out)
    argv=[PY,'-B','-X','utf8','-m','unittest','-v',*selectors]
    save(out/'run-start.json',{'format':'finite-software-refresh-start/1','source_commit':SOURCE,'started_utc':datetime.datetime.now(datetime.UTC).isoformat(),'snapshot':before,'namespace_projection':proj,'module_resolution':lookup,'environment':env,'argv':argv,'cwd':str(REPO/'.github/scripts'),'producer_sha256':sha(Path(__file__).read_bytes()),'observer_sha256':sha((out/'observer/sitecustomize.py').read_bytes())})
    started=time.monotonic();process=subprocess.run(argv,cwd=REPO/'.github/scripts',env=env,capture_output=True,timeout=150);seconds=time.monotonic()-started
    (out/'original.stdout.log').write_bytes(process.stdout);(out/'original.stderr.log').write_bytes(process.stderr)
    after=snapshot(names);imports=[json.loads(p.read_text()) for p in sorted(out.glob('actual-imports-*.json'))];assert imports,'actual import observer absent'
    named=[];text=process.stderr.decode('utf8')
    for name in selectors:
        pattern=r'(?m)^'+re.escape(name.rsplit('.',1)[1])+r' \('+re.escape(name)+r'\) \.\.\. ([^\r\n]+)\r?$';named.append({'id':name,'outcomes':re.findall(pattern,text)})
    loaded={}
    for observation in imports:
        assert not observation['observer_errors']
        for name,digest in {**observation['executed_repository_modules'],**{v['path']:v['sha256'] for v in observation['loaded_repository_modules'].values()}}.items():
            assert sha(git('show',SOURCE+':'+name))==digest
            root=next(s for s in ROOTS if name.startswith(s+'/'));relative=name[len(root)+1:]
            assert before['physical_namespaces'][root][relative]['sha256']==after['physical_namespaces'][root][relative]['sha256']==digest
            loaded[name]=digest
    parent=[v for v in imports if any(n.endswith('test_state_contracts_integration.py' if cohort=='p02' else 'test_workflow_recovery.py') for n in v['executed_repository_modules'])]
    assert len(parent)==1 and Path(parent[0]['parent_pycache_prefix']).resolve()==Path(env['PYTHONPYCACHEPREFIX']).resolve() and parent[0]['parent_no_user_site']==1
    child_observations=[]
    if cohort=='recovery':
        for line in process.stdout.decode('utf8').splitlines():
            if line.startswith('Recovery child isolation observation: '):child_observations.append(json.loads(line.split(': ',1)[1]))
        assert len(child_observations)==1
        child=child_observations[0];module=Path(child['module_path']);assert module.resolve()==(REPO/'core/pysrc/_workflowrecoverylib.py').resolve();assert child['no_user_site']==1 and not any(child['forbidden_present'].values())
        spawns=[v for observation in imports for v in observation['python_child_launches'] if v['fixture_root'] is not None];assert spawns
        for spawn in spawns:
            assert spawn['pycache_prefix'] is not None and spawn['no_user_site']=='1'
            prefix=Path(spawn['pycache_prefix']).resolve();fixture=Path(spawn['fixture_root']).resolve();assert prefix!=fixture and prefix.is_relative_to(fixture)
        assert any(Path(v['pycache_prefix']).resolve()==Path(child['pycache_prefix']).resolve() for v in spawns)
        child['source_module_paths']=[{'path':'core/pysrc/_workflowrecoverylib.py','sha256':before['inputs']['core/pysrc/_workflowrecoverylib.py'],'actual_loaded_path':child['module_path']}]
    result={'format':'finite-software-refresh-result/1','source_commit':SOURCE,'exit_code':process.returncode,'seconds':seconds,'argv':argv,'cwd':str(REPO/'.github/scripts'),'selected_named_population':len(selectors),'named_results':named,'after_snapshot':after,'before_after_all_closure_equal':before==after,'namespace_projection':proj,'module_resolution':lookup,'actual_repository_imports':loaded,'actual_import_observations':[str(p.relative_to(OUT)).replace('\\','/') for p in sorted(out.glob('actual-imports-*.json'))],'actual_fixture_child_observations':child_observations,'limits':'Local existing software fixtures only; no provider/model/native/installed/hosted/publication claim.'}
    save(out/'run-result.json',result)
    assert process.returncode==0 and before==after and all(v['outcomes']==['ok'] for v in named)
    results[cohort]={'PASS':len(selectors),'seconds':seconds,'positive_inputs':len(before['inputs']),'runtime_records':len(before['runtime']),'actual_imports':len(loaded),'fixture_child_observations':len(child_observations)}
    print(json.dumps({'completed':cohort,**results[cohort]}),flush=True)
parity_env=env.copy();parity_env.pop('PYTHONPATH',None);parity_argv=[PY,'-B','-X','utf8','tools/sync-core.py','--check'];before_parity=identity();clock=time.monotonic();p=subprocess.run(parity_argv,cwd=REPO,env=parity_env,capture_output=True,timeout=90);(OUT/'parity.stdout.log').write_bytes(p.stdout);(OUT/'parity.stderr.log').write_bytes(p.stderr);after_parity=identity();assert p.returncode==0 and before_parity==after_parity==initial
copies={name:sha((REPO/name).read_bytes()) for name in ['core/pysrc/_workflowrecoverylib.py',*['plugins/'+h+'/hooks/_workflowrecoverylib.py' for h in ('ca','ca-codex','ca-pi')]]};assert len(set(copies.values()))==1
save(OUT/'parity.json',{'argv':parity_argv,'cwd':str(REPO),'exit_code':p.returncode,'seconds':time.monotonic()-clock,'source_commit':SOURCE,'before_after_identity_equal':True,'exact_helper_copies':copies,'stdout_sha256':sha(p.stdout),'stderr_sha256':sha(p.stderr)})
assert identity()==initial
save(OUT/'capture-complete.json',{'source_commit':SOURCE,'source_tree':initial['tree'],'HEAD_index_stable':True,'cohorts':results,'parity':'PASS','raw_immutable':True,'limits':'Only capture completed. No prospective proof or ledger mutation/admission yet.'})
print(json.dumps({'CAPTURE_COMPLETE_RELEASE_ROOT_HOLD':True,'source':SOURCE,'cohorts':results,'parity':'PASS'}),flush=True)
