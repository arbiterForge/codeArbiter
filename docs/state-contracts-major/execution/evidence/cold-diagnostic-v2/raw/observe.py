from pathlib import Path
import hashlib,importlib.util,io,json,os,sys,time,unittest
R=Path(__file__).resolve().parent
sys.path.insert(0,str(R/'.github/scripts'))
sys.path.insert(0,str(R/'core/pysrc'))
import test_artifact_package as T
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
T.INSTALLED_HOST=load('actual_cold_verifier',R/'.github/scripts/test_artifact_installed_host.py')
T.PACKAGER=load('actual_host_packager',R/'tools/build-host-packages.py')
def sha(b):return hashlib.sha256(b).hexdigest()
def hashes():return {p.relative_to(R).as_posix():sha(p.read_bytes()) for p in R.rglob('*.py') if p.name!='observe.py'}
before=hashes();outcomes=[];stream=io.StringIO();label=sys.argv[1]
real_run=T.subprocess.run
retained_children=[]
def record_run(argv,*args,**kwargs):
 completed=real_run(argv,*args,**kwargs)
 if (len(argv)==7 and argv[3]=='-c' and argv[-1] in {'network','nested','builtin','observer-failure'}):
  raw=completed.stdout
  closed=T.INSTALLED_HOST.decode_failure(raw)
  item={'mode':argv[-1],'exit_code':completed.returncode,'stdout_bytes':len(raw),'stdout_sha256':sha(raw),'closed_record_valid':closed is not None}
  if closed is not None:
   name=label+'.'+argv[-1]+'.stdout.json';(R/name).write_bytes(raw);item['retained_stdout']=name
  retained_children.append(item)
 return completed
T.subprocess.run=record_run
class Result(unittest.TextTestResult):
 def addSuccess(self,test):outcomes.append({'id':test.id(),'outcome':'PASS'});super().addSuccess(test)
 def addFailure(self,test,error):outcomes.append({'id':test.id(),'outcome':'FAIL'});super().addFailure(test,error)
 def addError(self,test,error):outcomes.append({'id':test.id(),'outcome':'ERROR'});super().addError(test,error)
runner=unittest.TextTestRunner(stream=stream,verbosity=2,resultclass=Result);result=runner._makeResult();result.startTestRun();start=time.time()
names=sys.argv[2:] or ['ColdFailureDiagnosticTests']
def flatten(suite):
 for c in suite:
  if isinstance(c,unittest.TestSuite):yield from flatten(c)
  else:yield c
for case in flatten(unittest.TestLoader().loadTestsFromNames(names,T)):case.run(result)
result.stopTestRun();duration=time.time()-start;result.printErrors()
raw=stream.getvalue().encode();(R/(label+'.stderr.log')).write_bytes(raw)
doc={'source_export':json.loads((R/'preparation.json').read_text())['source_commit'],'source_kind':'Temp exact production/test overlay','argv':[sys.executable,'-B',str(Path(__file__).resolve()),*sys.argv[1:]],'cwd':str(Path.cwd()),'runtime':sys.version,'runtime_executable_sha256':sha(Path(sys.executable).read_bytes()),'HOME_before_import':os.environ.get('HOME'),'exit_code':0 if result.wasSuccessful() else 1,'duration_seconds':duration,'named_outcomes':outcomes,'inputs_before':before,'inputs_after':hashes(),'observer_sha256':sha(Path(__file__).read_bytes()),'raw_stderr_sha256':sha(raw),'actual_child_outputs':retained_children,'fixture_boundary':'Actual existing owner globals loaded by file path; direct native-free TestCase.run invokes actual case setup/cleanup, intentionally no unrelated native-building module setup. Not full package acceptance.'}
(R/(label+'.json')).write_text(json.dumps(doc,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'label':label,'exit_code':doc['exit_code'],'outcomes':outcomes,'seconds':duration},indent=2));print(raw.decode())
assert before==doc['inputs_after']
sys.exit(doc['exit_code'])
