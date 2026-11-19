"""Read-only execution/module witness, never replaces target import/process code."""
import atexit
import hashlib
import json
from pathlib import Path
import sys

OUT=Path(__file__).resolve().parents[1]
REPO=Path(r'C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter').resolve()
executed={}
errors=[]
def profiler(frame,event,arg):
    if event!='call' or frame.f_code.co_name!='<module>':return
    try:
        p=Path(frame.f_code.co_filename).resolve()
        name=p.relative_to(REPO).as_posix()
    except (ValueError,OSError):return
    try:
        if p.is_file():executed[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError as error:errors.append(type(error).__name__)
def finish():
    sys.setprofile(None)
    modules={}
    for name,module in list(sys.modules.items()):
        filename=getattr(module,'__file__',None)
        if not isinstance(filename,str):continue
        try:
            path=Path(filename).resolve()
            relative=path.relative_to(REPO).as_posix()
        except (ValueError,OSError):continue
        if path.is_file():modules[name]={'path':relative,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    value={'format':'P02-actual-import-observation/1','executed_repository_modules':executed,
        'loaded_repository_modules':modules,'observer_errors':errors,
        'private_pycache_prefix':sys.pycache_prefix,'sys_path':sys.path,
        'python':sys.version,'executable':sys.executable,
        'limits':'Read-only profile records actual repository module execution and final registry paths. Synthetic disposable fixture code is not relabeled as product source.'}
    (OUT/'actual-imports.json').write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')
atexit.register(finish)
sys.setprofile(profiler)
