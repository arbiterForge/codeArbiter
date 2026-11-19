"""Passive finite source/import and Python child-environment witness."""
import atexit,hashlib,json,os,sys
from pathlib import Path
OUT=Path(__file__).resolve().parents[1]
REPO=Path(r'C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter').resolve()
executed={};errors=[];spawns=[]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def profile(frame,event,arg):
    if event!='call' or frame.f_code.co_name!='<module>':return
    try:
        path=Path(frame.f_code.co_filename).resolve();relative=path.relative_to(REPO).as_posix()
    except (ValueError,OSError):return
    try:
        if path.is_file():executed[relative]=digest(path)
    except OSError as error:errors.append(type(error).__name__)
def audit(event,args):
    if event!='subprocess.Popen':return
    try:
        executable,argv,cwd,environment=args
        if not isinstance(argv,(list,tuple)) or not argv or not isinstance(argv[0],str):return
        if Path(argv[0]).resolve()!=Path(sys.executable).resolve():return
        env=os.environ if environment is None else environment
        fixture=None;test=None;frame=sys._getframe(1)
        for _ in range(32):
            if frame is None:break
            value=frame.f_locals.get('self')
            if value is not None and type(value).__module__=='test_workflow_recovery' and type(value).__name__=='RecoveryRuntimeTest':
                fixture=str(value.root);test=value.id();break
            frame=frame.f_back
        forbidden=('APPDATA','LOCALAPPDATA','XDG_CONFIG_HOME','XDG_CACHE_HOME','PYTHONPATH','FARM_API_KEY','CLAUDE_CODE_OAUTH_TOKEN','GITHUB_TOKEN','OPENAI_API_KEY')
        spawns.append({'fixture_root':fixture,'test_id':test,'python':str(Path(argv[0]).resolve()),
            'pycache_prefix':env.get('PYTHONPYCACHEPREFIX'),'no_user_site':env.get('PYTHONNOUSERSITE'),
            'home':env.get('HOME'),'userprofile':env.get('USERPROFILE'),
            'forbidden_present':{key:key in env for key in forbidden},
            'limits':'Actual parent launch boundary environment only; no argv, code, request or credential value recorded.'})
    except BaseException as error:errors.append(type(error).__name__)
def finish():
    sys.setprofile(None);modules={}
    for name,module in list(sys.modules.items()):
        filename=getattr(module,'__file__',None)
        if not isinstance(filename,str):continue
        try:
            path=Path(filename).resolve();relative=path.relative_to(REPO).as_posix()
        except (ValueError,OSError):continue
        if path.is_file():modules[name]={'path':relative,'sha256':digest(path)}
    data={'format':'finite-software-import-and-child-observation/1','pid':os.getpid(),
        'executed_repository_modules':executed,'loaded_repository_modules':modules,'observer_errors':errors,
        'parent_pycache_prefix':sys.pycache_prefix,'parent_no_user_site':sys.flags.no_user_site,
        'python':sys.version,'executable':sys.executable,'sys_path':sys.path,'python_child_launches':spawns,
        'limits':'Passive source execution, final import registry and exact child-launch policy witness; no source/test/target replacement.'}
    (OUT/('actual-imports-'+str(os.getpid())+'.json')).write_text(json.dumps(data,indent=2)+'\n',encoding='utf8',newline='\n')
atexit.register(finish);sys.setprofile(profile);sys.addaudithook(audit)
