"""Execute the exact eleven scoped methods by explicit source path in isolated Python.

Read-only profiling retains original child return values and the inert fixture
wrapper before the original test's own tearDown removes its private directory.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import threading
import unittest

OUT=Path(__file__).resolve().parent
REPO=Path(r'C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter')
TEST=REPO/'.github/scripts/test_run_concurrent_suites.py'
RUNNER=REPO/'.github/scripts/run_concurrent_suites.py'
selection=json.loads((OUT/'selection.json').read_text(encoding='utf-8'))
events=[];wrappers=[];errors=[]
digest=lambda b:hashlib.sha256(b).hexdigest()
def profiler(frame,event,arg):
    if event!='return':return
    try:
        path=Path(frame.f_code.co_filename)
        name=frame.f_code.co_name
        if path==RUNNER and name=='run' and isinstance(arg,tuple):
            events.append({'owner':'run','interpreter':frame.f_locals['interpreter'],
                'script':frame.f_locals['script'],'reported_code':arg[0],'original_output':arg[1],
                'observed_Popen_returncode':frame.f_locals['process'].returncode})
        elif path==TEST and name=='run_main' and isinstance(arg,tuple):
            events.append({'owner':'main-return','argv':frame.f_locals['argv'],
                'reported_code':arg[0],'original_grouped_output':arg[1]})
        elif path==TEST and name=='test_the_named_interpreter_actually_runs_the_suite':
            root=frame.f_locals['self'].root
            fixtures={}
            for filename in ('wrapper.cmd','wrapper.sh','probe.py'):
                file=root/filename
                if file.is_file():
                    raw=file.read_bytes();fixtures[filename]={'sha256':digest(raw),'bytes':len(raw),'original_utf8':raw.decode('utf-8')}
            wrappers.append({'method':name,'fixtures':fixtures})
    except Exception as error:errors.append(type(error).__name__)

sys.setprofile(profiler)
threading.setprofile(profiler)
spec=importlib.util.spec_from_file_location('test_run_concurrent_suites',TEST)
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
suite=unittest.TestSuite(module.ConcurrentSuitesTests(name) for name in selection['names'])
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.setprofile(None)
threading.setprofile(None)
observed={'format':'C05-original-child-and-wrapper-observations/1','events':events,'interpreter_wrapper':wrappers,
    'observer_errors':errors,'actual_named_results':[{'id':'test_run_concurrent_suites.ConcurrentSuitesTests.'+name,
        'result':'PASSED' if not any(test._testMethodName==name for test,_ in result.errors+result.failures) else 'FAILED'} for name in selection['names']],
    'actual_tests_run':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'skipped':len(result.skipped),
    'source_modules':{'test':{'path':str(TEST),'sha256':digest(TEST.read_bytes())},'runner':{'path':str(RUNNER),'sha256':digest(RUNNER.read_bytes())}},
    'runtime':{'executable':sys.executable,'version':sys.version,'isolated':sys.flags.isolated,'no_site':sys.flags.no_site,
        'private_pycache_prefix':sys.pycache_prefix,'sys_path':sys.path},
    'limits':'Original unittest methods/assertions unchanged; profile forwards no replacements. Child termination remains the runner direct-child contract, not a process-tree/native-rundown proof.'}
(OUT/'observations.json').write_text(json.dumps(observed,indent=2)+'\n',encoding='utf-8',newline='\n')
raise SystemExit(0 if result.wasSuccessful() and not errors and result.testsRun==len(selection['names']) and not result.skipped else 1)
