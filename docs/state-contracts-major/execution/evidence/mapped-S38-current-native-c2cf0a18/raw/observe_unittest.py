from pathlib import Path
import hashlib, json, os, sys, time, unittest
O=Path(__file__).resolve().parent; S=O/'source'; sys.path.insert(0,str(S/'.github/scripts')); sys.path.insert(0,str(S/'core/pysrc'))
import ci20_native_binding
from _contextverificationlib import hash_go_module
NATIVE=Path(os.environ['ARTIFACT_TEST_INSTALLATION']); EXPECTED='f79741ca03192962140efae78835b72d09c3eaf6167ea09d8b9fe6904b4495cf'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def write(n,d):
 p=O/n
 with p.open('x',encoding='utf8') as f:json.dump(d,f,indent=2)
def host_lookup():
 current=S; observations=[]
 for name in ['core','pysrc','_host.py']:
  names=[p.name for p in current.iterdir()]
  if any(not n.isascii() for n in names):raise AssertionError('unsupported non-ASCII Windows lookup')
  matching=[n for n in names if n.lower()==name.lower()]
  if len(matching)>1:raise AssertionError('ambiguous Windows lookup')
  observations.append({'parent':str(current.relative_to(S)),'wanted':name,'inventory_sha256':hashlib.sha256(json.dumps(sorted(names),separators=(',',':')).encode()).hexdigest(),'matching_names':matching,'entry_count':len(names)})
  if not matching:return {'path':'core/pysrc/_host.py','path_style':'windows','present':False,'owner':'core/pysrc/hostapi.py','observations':observations}
  current=current/matching[0]
  if current.is_symlink():raise AssertionError('lookup symlink')
  if name!='_host.py' and not current.is_dir():raise AssertionError('lookup ancestor notdirectory')
 raise AssertionError('unexpected core _host.py present')
def closure(stage):
 inv={p.relative_to(S).as_posix():sha(p) for p in S.rglob('*') if p.is_file()}
 baseline=json.loads((O/'source-snapshot.json').read_text('utf8'))['members']
 if inv!={p['path']:p['sha256'] for p in baseline}:raise AssertionError('source inputs changed')
 m=hash_go_module(S/'core/artifacts')
 if m!=EXPECTED:raise AssertionError('module membership differs')
 identity=ci20_native_binding.candidate_identity(NATIVE,'windows/amd64')
 expected=json.loads((O/'candidate-preflight.json').read_text('utf8'))['identity']
 if identity!=expected:raise AssertionError('suppliedpayload identity changed')
 value={'stage':stage,'module_membership':{'profile':'go-module-v1','root':'core/artifacts','path_order':'windows','sha256':m},'module_files':len(list((S/'core/artifacts').rglob('*'))),'source_positive_inputs':inv,'host_lookup':host_lookup(),'original_payload_identity':identity}
 write(stage+'-closure.json',value);return value
before=closure('before'); events=[]; outcomes=[]
def observe(test,stage):
 if not hasattr(test.__class__,'installation'):
  events.append({'stage':stage,'test':test.id(),'class_installation':'unavailable; original unittest import/setup error retained'});return
 location=Path(test.__class__.installation)
 identity=ci20_native_binding.candidate_identity(location,'windows/amd64')
 if identity!=before['original_payload_identity']:raise AssertionError('classcopy identity differs')
 plugin=location.parents[1]
 resources={p.relative_to(plugin).as_posix():sha(p) for p in plugin.rglob('*') if p.is_file()}
 events.append({'stage':stage,'test':test.id(),'installation':str(location),'payload_identity':identity,'copied_plugin_regular_inputs':resources})
class Result(unittest.TextTestResult):
 def startTest(self,test):observe(test,'before-case-after-setUpClass');super().startTest(test)
 def stopTest(self,test):observe(test,'after-case-before-class-cleanup');super().stopTest(test)
 def addSuccess(self,test):outcomes.append({'id':test.id(),'result':'passed'});super().addSuccess(test)
 def addError(self,test,err):outcomes.append({'id':test.id(),'result':'error'});super().addError(test,err)
 def addFailure(self,test,err):outcomes.append({'id':test.id(),'result':'failed'});super().addFailure(test,err)
 def addSkip(self,test,reason):outcomes.append({'id':test.id(),'result':'skipped','reason':reason});super().addSkip(test,reason)
loader=unittest.defaultTestLoader; suite=loader.loadTestsFromNames(sys.argv[1:]); assert suite.countTestCases()==3
start=time.monotonic();result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(suite)
after=closure('after')
imports={}
for name,module in list(sys.modules.items()):
 p=getattr(module,'__file__',None)
 if p:
  try:q=Path(p).resolve().relative_to(S)
  except (ValueError,OSError):continue
  if (S/q).is_file():imports[q.as_posix()]=sha(S/q)
write('actual-results.json',{'testsRun':result.testsRun,'successful':result.wasSuccessful(),'outcomes':outcomes,'errors':len(result.errors),'failures':len(result.failures),'skips':len(result.skipped),'seconds':time.monotonic()-start,'observer_events':events,'imported_source_modules':imports,'after_class_cleanup_installation_exists':Path(events[-1]['installation']).exists() if events and 'installation' in events[-1] else None,'source_api_claim':'Originalunmodified methods andnormalunittestloader/TextTestRunner; observation-only resultsubclass capturescopyidentity, notproductionfunctionreplacement. Native/providercodeoracles areexactassertions inpassing sourcecallbacks, notseparatelyinventedtraceoutput.'})
sys.exit(0 if result.wasSuccessful() and result.testsRun==3 and not result.skipped else 1)
