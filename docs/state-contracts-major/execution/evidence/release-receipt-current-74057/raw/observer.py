from pathlib import Path
import sys,json,unittest,importlib.util,hashlib,time
repo=Path(sys.argv[1]);out=Path(sys.argv[2]);sys.path.insert(0,str(repo/'.github/scripts'));sys.path.insert(0,str(repo/'core/pysrc'))
s=importlib.util.spec_from_file_location('test_release_target',repo/'.github/scripts/test_release_target.py');m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)
selectors=['EligibleTests.test_public_release_missing_its_receipt_is_eligible_for_recovery','CompletionModelTests','ReceiptReadbackTests','FaultInjectionTests','CompositionContractTests']
suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(n,m) for n in selectors)
observed=[]
class Result(unittest.TextTestResult):
 def startTest(self,t):self.started=time.monotonic();super().startTest(t)
 def addSuccess(self,t):super().addSuccess(t);observed.append({'id':t.id(),'status':'PASSED','seconds':time.monotonic()-self.started})
 def addFailure(self,t,e):super().addFailure(t,e);observed.append({'id':t.id(),'status':'FAILED'})
 def addError(self,t,e):super().addError(t,e);observed.append({'id':t.id(),'status':'ERROR'})
 def addSkip(self,t,why):super().addSkip(t,why);observed.append({'id':t.id(),'status':'SKIPPED'})
r=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(suite)
loaded={}
for name,module in list(sys.modules.items()):
 p=getattr(module,'__file__',None)
 if p:
  p=Path(p).resolve()
  try:key=p.relative_to(repo).as_posix()
  except ValueError:continue
  loaded[key]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'module':name}
record={'schema':'codearbiter.original-local-unittest-observation/1','selectors':selectors,'runtime':sys.version,'tests_run':r.testsRun,'failed':len(r.failures),'errors':len(r.errors),'skipped':len(r.skipped),'observed':observed,'loaded_repository_modules':loaded,'scope':'Actual planner/helper calls, in-process CLI plus hermetic PublicationRun model and source composition guards; no real external publisher/registry/npm/provider effects.'}
(out/'named-results.json').write_bytes((json.dumps(record,indent=2)+'\n').encode())
sys.exit(0 if r.wasSuccessful() else 1)
