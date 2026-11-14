import json,runpy,sys,time,unittest
from pathlib import Path
script=Path(sys.argv[1]);report=Path(sys.argv[2]);events=[]
class Observed(unittest.TextTestResult):
 def startTest(self,test):
  super().startTest(test);events.append({'id':test.id(),'status':'RUNNING','started':time.monotonic()});print('ORIGINAL_TEST_START '+test.id(),flush=True)
 def finish(self,test,status,detail=None):
  for item in reversed(events):
   if item['id']==test.id() and item['status']=='RUNNING':
    item.update(status=status,seconds=time.monotonic()-item.pop('started'))
    if detail is not None:item['detail']=str(detail)
    break
  print('ORIGINAL_TEST_'+status+' '+test.id(),flush=True)
 def addSuccess(self,test):super().addSuccess(test);self.finish(test,'PASSED')
 def addFailure(self,test,err):super().addFailure(test,err);self.finish(test,'FAILED',err[1])
 def addError(self,test,err):super().addError(test,err);self.finish(test,'ERROR',err[1])
 def addSkip(self,test,reason):super().addSkip(test,reason);self.finish(test,'SKIPPED',reason)
unittest.TextTestRunner.resultclass=Observed
sys.argv=[str(script)];code=0
try:runpy.run_path(str(script),run_name='__main__')
except SystemExit as exc:code=exc.code if isinstance(exc.code,int) else 1
finally:report.write_text(json.dumps({'schema':'codearbiter.original-local-python-observation/1','script':str(script),'python':sys.version,'platform':sys.platform,'results':events,'exit_code':code},indent=2)+'\n',encoding='utf8')
sys.exit(code)
