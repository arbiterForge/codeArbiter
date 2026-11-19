import sys,pathlib,unittest,importlib.util,json
r=pathlib.Path(sys.argv[1]);o=pathlib.Path(sys.argv[2]);path=r/'.github/scripts/test_routing_and_cleanup_surface.py'
spec=importlib.util.spec_from_file_location('test_routing_and_cleanup_surface',path);m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
class Recorded(unittest.TextTestResult):
 def __init__(self,*a,**k):super().__init__(*a,**k);self.named=[];self.subcases=[]
 def addSuccess(self,t):super().addSuccess(t);self.named.append({'id':t.id(),'result':'PASS'})
 def addFailure(self,t,e):super().addFailure(t,e);self.named.append({'id':t.id(),'result':'FAIL'})
 def addError(self,t,e):super().addError(t,e);self.named.append({'id':t.id(),'result':'ERROR'})
 def addSkip(self,t,w):super().addSkip(t,w);self.named.append({'id':t.id(),'result':'SKIP'})
 def addSubTest(self,t,s,e):super().addSubTest(t,s,e);self.subcases.append({'id':t.id(),'parameters':dict(s.params),'result':'PASS' if e is None else 'FAIL'})
suite=unittest.TestLoader().loadTestsFromTestCase(m.TestDependentConflictScope)
x=unittest.TextTestRunner(verbosity=2,resultclass=Recorded).run(suite)
(o/'named-results.json').write_text(json.dumps({'tests_run':x.testsRun,'success':x.wasSuccessful(),'named':x.named,'subcases':x.subcases},indent=2)+'\n',encoding='utf-8',newline='\n')
assert x.testsRun==3 and len(x.named)==3 and all(y['result']=='PASS' for y in x.named) and len(x.subcases)==14 and all(y['result']=='PASS' for y in x.subcases)
