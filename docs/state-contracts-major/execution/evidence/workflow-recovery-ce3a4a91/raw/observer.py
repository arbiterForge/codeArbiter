import pathlib,json,subprocess,os,sys,hashlib,time,datetime,stat
R=pathlib.Path('C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter');D=pathlib.Path(__file__).parent;G='C:/Program Files/Git/cmd/git.exe';SOURCE='ce3a4a91a3164e1b778e81d206ec76517633c518';H=lambda b:hashlib.sha256(b).hexdigest()
def head():return subprocess.check_output([G,'rev-parse','HEAD'],cwd=R,text=True).strip()
def physical():
 root=R/'core/pysrc';info=root.lstat();assert stat.S_ISDIR(info.st_mode) and not root.is_symlink() and not getattr(info,'st_file_attributes',0)&0x400
 with os.scandir(root) as it:
  names=sorted(x.name for x in it)
 assert not any(n.casefold()=='_host.py' for n in names)
 return {'path':str(root),'successful_directory_enumeration':True,'names':names,'_host_py_absent_case_insensitive':True,'hostapi_py_present':'hostapi.py' in names,'directory_identity':[info.st_dev,info.st_ino]}
def immutable():
 argv=[G,'--no-lazy-fetch','ls-tree','-z','-l',SOURCE+':core/pysrc'];p=subprocess.run(argv,cwd=R,capture_output=True,check=True);rows=[]
 for x in p.stdout.split(b'\0')[:-1]:
  header,name=x.split(b'\t',1);rows.append({'header':header.decode('ascii'),'name':name.decode('utf8')})
 assert rows and not any(x['name'].casefold()=='_host.py' for x in rows)
 return {'argv':argv,'exit_code':0,'stdout_sha256':H(p.stdout),'entries':rows,'_host_py_absent':True}
old=json.loads((R/'docs/state-contracts-major/execution/evidence/workflow-recovery-b7a75fca/canonical-runtime.json').read_text(encoding='utf8'));source_before=head();assert source_before==SOURCE
before={p:H((R/p).read_bytes()) for p in old['inputs']};assert len(before)==100
committed={p:H(subprocess.check_output([G,'show',SOURCE+':'+p],cwd=R)) for p in before};assert before==committed
physical_before=physical();git_before=immutable();home=D/'disposable-home';home.mkdir();env={k:os.environ[k] for k in ('SystemRoot','WINDIR','TEMP','TMP') if k in os.environ};env.update(HOME=str(home),USERPROFILE=str(home),PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8',PATH='C:/Program Files/Git/cmd');argv=['C:/Python314/python.exe','-B','-m','unittest','-v','test_workflow_recovery'];started=datetime.datetime.now(datetime.timezone.utc).isoformat();start=time.monotonic();p=subprocess.run(argv,cwd=R/'.github/scripts',env=env,capture_output=True,timeout=180);seconds=time.monotonic()-start
physical_after=physical();git_after=immutable();after={p:H((R/p).read_bytes()) for p in before};source_after=head();(D/'original-full.stdout.log').write_bytes(p.stdout);(D/'original-full.stderr.log').write_bytes(p.stderr)
result={'actual_start_git_source':source_before,'actual_end_git_source':source_after,'tested_source':SOURCE,'argv':argv,'cwd':str(R/'.github/scripts'),'started_at':started,'seconds':seconds,'exit_code':p.returncode,'runtime':{'executable':sys.executable,'version':sys.version,'platform':sys.platform},'environment_keys':sorted(env),'home_before_imports':str(home),'inputs_before':before,'inputs_after':after,'committed_inputs':committed,'physical_inventory_before':physical_before,'physical_inventory_after':physical_after,'immutable_inventory_before':git_before,'immutable_inventory_after':git_after,'stdout_sha256':H(p.stdout),'stderr_sha256':H(p.stderr),'observer_sha256':H(pathlib.Path(__file__).read_bytes())}
(D/'original-full-result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8');assert before==after==committed and physical_before==physical_after and git_before==git_after
print(json.dumps({'dir':str(D),'exit_code':p.returncode,'seconds':seconds,'source_before':source_before,'source_after':source_after,'inputs':len(before),'physical_and_git_absence_before_after':True}));print(p.stderr.decode('utf8')[-350:])
