import pathlib,sys,importlib.util,unittest,json,hashlib,time
root=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2])
spec=importlib.util.spec_from_file_location('test_wire_statusline',root/'plugins/ca/hooks/tests/test_wire_statusline.py')
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
selectors=json.loads((out/'selectors.json').read_text())
class Recorded(unittest.TextTestResult):
 def __init__(self,*a,**kw):super().__init__(*a,**kw);self.observed=[]
 def addSuccess(self,test):super().addSuccess(test);self.observed.append({'id':test.id(),'outcome':'PASS'})
 def addFailure(self,test,err):super().addFailure(test,err);self.observed.append({'id':test.id(),'outcome':'FAIL'})
 def addError(self,test,err):super().addError(test,err);self.observed.append({'id':test.id(),'outcome':'ERROR'})
 def addSkip(self,test,why):super().addSkip(test,why);self.observed.append({'id':test.id(),'outcome':'SKIP','reason':why})
suite=unittest.TestLoader().loadTestsFromNames(selectors,module)
result=unittest.TextTestRunner(verbosity=2,resultclass=Recorded).run(suite)
loaded={}
for name,m in list(sys.modules.items()):
 p=getattr(m,'__file__',None)
 if p:
  p=pathlib.Path(p).resolve()
  if p.is_relative_to(root):loaded[p.relative_to(root).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
(out/'result.json').write_text(json.dumps({'run':result.testsRun,'outcomes':result.observed,'success':result.wasSuccessful(),'loaded_repo_modules':loaded},indent=2)+'\n',encoding='utf-8',newline='\n')
assert result.testsRun==10 and len(result.observed)==10 and all(x['outcome']=='PASS' for x in result.observed)
