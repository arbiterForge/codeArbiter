"""Owned supervisor for the reviewed, single HW15 characterization.

This does not acquire packages, create qualification claims, or modify the
characterization. Its child records actual controller code reads/processes.
"""
from pathlib import Path
import argparse, hashlib, json, os, runpy, shutil, subprocess, sys, tempfile, threading, time, unittest

T=Path('C:/Users/brenn/AppData/Local/Temp')
D=T/'ca-hw15-retained-rollback-2c0fd13010'
PY=Path('C:/Python314/python.exe')
GIT=Path('C:/Program Files/Git/cmd/git.exe')
M='0b0ae193496335c0d87337e5993f032a9385fffb'
RUN=43960617519
CAP=4*1024*1024
digest=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(path,value):
 with Path(path).open('x',encoding='utf-8',newline='\n') as f:json.dump(value,f,indent=2);f.write('\n')

def child(config,output):
 cfg=json.loads(config.read_bytes());source=Path(cfg['controller_source_repo']).resolve(strict=True)
 code_reads,processes,prefix_observations={},[],[]
 def prefix_snapshot(prefix):
  result={}
  for p in sorted(Path(prefix).rglob('*')):
   info=p.lstat()
   if p.is_symlink() or getattr(info,'st_file_attributes',0)&1024:
    raise RuntimeError('installed prefix contains a link/reparse point')
   if p.is_file():result[p.relative_to(prefix).as_posix()]={'sha256':digest(p),'bytes':info.st_size}
  return result
 original_test_run=unittest.TestCase.run
 def observed_test_run(case,*positional,**keywords):
  if type(case).__name__!='RetainedLifecycle':return original_test_run(case,*positional,**keywords)
  prefixes={str(p):prefix_snapshot(p) for p in [*case.hosts.values(),case.old]}
  original_codex=prefixes[str(case.hosts['codex'])]
  try:return original_test_run(case,*positional,**keywords)
  finally:
   after={p:prefix_snapshot(Path(p)) for p in prefixes}
   fresh=prefix_snapshot(case.hosts['codex'])
   prefix_observations.append({'before':prefixes,'after':after,
                               'codex_prefix_after_case':str(case.hosts['codex']),'codex_members_after_case':fresh})
   if after!=prefixes or fresh!=original_codex:
    raise RuntimeError('installed prefix membership/bytes changed or fresh extraction differs')
 unittest.TestCase.run=observed_test_run
 busy=False
 def audit(event,args):
  nonlocal busy
  if busy:return
  busy=True
  try:
   if event in ('socket.connect','socket.bind'):
    raise RuntimeError('HW15 owned characterization has no network authority')
   if event=='subprocess.Popen':
    executable,argv,cwd,env=args
    if isinstance(argv,str):
     import ctypes
     argc=ctypes.c_int()
     shell=ctypes.WinDLL(str(Path(os.environ['SystemRoot'])/'System32/shell32.dll'),use_last_error=True)
     split=shell.CommandLineToArgvW
     split.argtypes=[ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_int)]
     split.restype=ctypes.POINTER(ctypes.c_wchar_p)
     pointer=split(argv,ctypes.byref(argc))
     if not pointer:raise RuntimeError('Windows command-line observation failed')
     try:
      if not 0<argc.value<=512:raise RuntimeError('observed argument population exceeds bound')
      argv=[pointer[i] for i in range(argc.value)]
     finally:
      free=ctypes.WinDLL(str(Path(os.environ['SystemRoot'])/'System32/kernel32.dll')).LocalFree
      free.argtypes=[ctypes.c_void_p];free.restype=ctypes.c_void_p
      free(ctypes.cast(pointer,ctypes.c_void_p))
    if not isinstance(argv,(list,tuple)) or not argv:raise RuntimeError('unavailable process argument observation')
    exe=Path(executable or argv[0])
    if not exe.is_absolute():
     found=shutil.which(str(exe),path=(env or os.environ).get('PATH',''))
     if not found:raise RuntimeError('unresolved characterization executable')
     exe=Path(found)
    exe=exe.resolve(strict=True)
    if exe not in {PY.resolve(strict=True),GIT.resolve(strict=True)}:
     raise RuntimeError('characterization requested an undeclared executable')
    if exe==GIT.resolve(strict=True) and any(str(a).casefold() in
       {'clone','fetch','push','pull','credential','upload-pack','receive-pack','submodule'} for a in argv[1:]):
     raise RuntimeError('characterization requested nonlocal Git effects')
    if len(processes)>=512:raise RuntimeError('characterization process record bound exceeded')
    processes.append({'executable':str(exe),'sha256':digest(exe),'argv':list(map(str,argv)),
                      'cwd':str(Path(cwd or Path.cwd()).resolve()),'environment_keys':sorted((env or os.environ).keys())})
   elif event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
    path=Path(os.fsdecode(args[0]));flags=args[2]
    if path.suffix.casefold() in {'.py','.pyc','.pyd','.dll'} and not flags & (os.O_WRONLY|os.O_RDWR):
     path=path.resolve(strict=True)
     if path.is_file() and path.stat().st_size<=16*1024*1024:
      code_reads[str(path)]={'sha256':digest(path),'bytes':path.stat().st_size}
      if len(code_reads)>4096:raise RuntimeError('characterization code-read bound exceeded')
  finally:busy=False
 sys.addaudithook(audit)
 sys.argv=[str(D/'characterization.py'),'--config',str(config),'--output',str(output/'actual-result.json')]
 try:
  runpy.run_path(str(D/'characterization.py'),run_name='__main__')
 finally:
  modules=[]
  for name,module in sorted(list(sys.modules.items())):
   filename=getattr(module,'__file__',None)
   if filename:modules.append({'module':name,'file':str(filename)})
  changed=[]
  for path,value in list(code_reads.items()):
   p=Path(path)
   if p.exists() and digest(p)!=value['sha256']:changed.append(path)
  save(output/'controller-footprint.json',{'actual_controller_code_reads':code_reads,
       'actual_controller_modules':modules,'actual_child_launches':processes,
       'installed_prefix_observations':prefix_observations,
       'changed_observed_code_files':changed,'python_sha256':digest(PY),'git_sha256':digest(GIT),
       'limits':['Controller observations do not enumerate child Python imports or whole OS/DLL closure.',
                 'Package bytes are independently authenticated by the unchanged retained-cohort verifier.',
                 'No host UI, provider/model, native execution or final task/program qualification.']})
  if changed:raise RuntimeError('observed controller code changed during execution')

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--config',type=Path,required=True)
 ap.add_argument('--package-authority',type=Path,required=True)
 ap.add_argument('--package-authority-sha256',required=True)
 ap.add_argument('--child-output',type=Path)
 args=ap.parse_args()
 if args.child_output:return child(args.config,args.child_output)
 assert digest(args.package_authority)==args.package_authority_sha256
 authority=json.loads(args.package_authority.read_bytes())
 assert authority['source_commit']==M and str(authority['run_id'])==str(RUN)
 assert authority['source_tree']=='8144b495df88c1b8a5011e3eb19c8d61a8d5e285'
 assert authority['workflow']=='.github/workflows/ci.yml' and authority['run_attempt']==1
 assert authority['ci']=='SUCCESS' and authority['package_verifier']=='PASS' and authority['require_production'] is True
 assert authority['docs']=='FAILURE' and authority['whole_normal_verdict']=='BLOCK'
 assert digest(D/'delivery.json')=='5a25aedb2dfc1f76c42a108d413feff1cc31a2a4ddee7efd1ce8d31821ab60f1'
 for item in json.loads((D/'filemap.json').read_bytes()):
  assert digest(D/item['path'])==item['sha256']
 cfg=json.loads(args.config.read_bytes());assert cfg['trusted_source_commit']==M
 assert str(cfg['trusted_workflow_run'])==str(RUN) and cfg['trusted_workflow']=='.github/workflows/ci.yml'
 assert Path(cfg['git_executable']).resolve(strict=True)==GIT.resolve(strict=True)
 assert Path(cfg['cohort_path']).resolve(strict=True)==Path(authority['cohort']).resolve(strict=True)
 assert digest(cfg['cohort_path'])==authority['cohort_sha256']
 assert Path(cfg['release_package_stage']).resolve(strict=True)==Path(authority['promoted_stage']).resolve(strict=True)
 assert cfg['promotion_receipt_sha256']==authority['promotion_receipt_sha256']
 source=Path(cfg['controller_source_repo']).resolve(strict=True)
 for path,item in json.loads((D/'source-inputs.json').read_bytes())['inputs'].items():
  # This declaration is read through immutable M by the trusted verifier;
  # the 16 actual controller/fixture sources must still match physically.
  if path!='.github/workflows/ci.yml':assert digest(source/path)==item['source_sha256'],path
  original=subprocess.check_output([str(GIT),'show',M+':'+path],cwd=source)
  assert hashlib.sha256(original).hexdigest()==item['source_sha256'],path
 out=Path(tempfile.mkdtemp(prefix='ca-hw15-actual-'))
 with tempfile.TemporaryDirectory(prefix='ca-hw15-supervisor-home-') as home:
  safe={k:os.environ[k] for k in ('SystemRoot','WINDIR') if k in os.environ}
  safe.update(HOME=home,USERPROFILE=home,TEMP=home,TMP=home,PATH=str(GIT.parent),
              PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',PYTHONUTF8='1',
              PYTHONPYCACHEPREFIX=str(Path(home)/'pycache'))
  os.environ.clear();os.environ.update(safe)
  sys.path.insert(0,str(source/'.github/scripts'))
  import _boundedproc as bounded
  cmd=[str(PY),'-I','-S','-B',str(Path(__file__).resolve()),'--config',str(args.config.resolve()),
       '--package-authority',str(args.package_authority.resolve()),'--package-authority-sha256',args.package_authority_sha256,
       '--child-output',str(out)]
  start=time.monotonic();proc=bounded.start(cmd,cwd=out,env=safe,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  count=[0];lock=threading.Lock();overflow=threading.Event()
  def consume(stream,path):
   with path.open('xb') as f:
    while True:
     raw=stream.read(8192)
     if not raw:break
     with lock:
      keep=max(0,CAP-count[0]);accepted=raw[:keep];count[0]+=len(accepted)
      if len(accepted)<len(raw):overflow.set()
     f.write(accepted)
  readers=[threading.Thread(target=consume,args=(stream,out/name),daemon=True)
           for stream,name in ((proc.stdout,'stdout.log'),(proc.stderr,'stderr.log'))]
  for reader in readers:reader.start()
  reason=None
  while proc.poll() is None:
   if overflow.is_set():reason='output-cap';break
   if time.monotonic()-start>=300:reason='deadline';break
   time.sleep(.1)
  containment=bounded.terminate_tree(proc) if reason else 'exited'
  for reader in readers:reader.join(timeout=5)
  result={'status':'PASS' if proc.returncode==0 and not reason and not any(t.is_alive() for t in readers) else 'FAIL',
          'returncode':proc.returncode,'stop_reason':reason,'containment':containment,'seconds':round(time.monotonic()-start,3),
          'captured_pipe_bytes':count[0],'argv':cmd,'environment_keys':sorted(safe),
          'package_authority':{'path':str(args.package_authority),'sha256':args.package_authority_sha256,
                               'ci':'SUCCESS','docs':'FAILURE','whole_normal_verdict':'BLOCK'},
          'controller_inputs':'16 physical sources unchanged; workflow declaration authenticated from immutable M Git blob',
          'driver_sha256':digest(D/'characterization.py'),'config_sha256':digest(args.config),
          'task_program_qualification':False,'scope':'one literal published-package legacy-board downgrade/reinstall characterization'}
  save(out/'supervisor-result.json',result);print(json.dumps({'folder':str(out),**result}))
  return 0 if result['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
