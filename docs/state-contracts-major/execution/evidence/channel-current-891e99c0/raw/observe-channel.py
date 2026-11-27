from pathlib import Path
import hashlib,io,json,os,subprocess,sys,time,unittest
O=Path(__file__).resolve().parent
R=Path('C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter')
SOURCE='891e99c0a139b510eb8fb175886f6044b4c8d4a8'
GIT='C:/Program Files/Git/cmd/git.exe'
plan=json.loads((O/'plan.json').read_text(encoding='utf-8'))
def sha(b):return hashlib.sha256(b).hexdigest()
def git(*args):return subprocess.check_output([GIT,*args],cwd=R)
def write(name,data):(O/name).write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
assert os.environ['HOME']==str(O/'home') and os.environ['USERPROFILE']==str(O/'home')
head=git('rev-parse','HEAD').decode().strip();assert head==SOURCE
index=Path(git('rev-parse','--path-format=absolute','--git-path','index').decode().strip())
index_before=sha(index.read_bytes());assert not git('diff','--cached','--name-only').strip()
def capture():
 physical={p:sha((R/p).read_bytes()) for p in plan['owner_inputs']}
 immutable={p:sha(git('show',SOURCE+':'+p)) for p in plan['owner_inputs']}
 assert physical==immutable
 return {'physical':physical,'immutable_Git':immutable}
before=capture()
start={'source_commit':SOURCE,'cwd':str(R/'.github/scripts'),'argv':[sys.executable,'-B',str(Path(__file__).resolve())],'semantic_test_selection':plan['argv'][5:],'environment':dict(os.environ),'runtime':sys.version,'runtime_executable_sha256':sha(Path(sys.executable).read_bytes()),'inputs_before':before,'index_sha256_before':index_before,'observer_sha256':sha(Path(__file__).read_bytes())}
write('start.json',start)
os.chdir(R/'.github/scripts');sys.path.insert(0,str(R/'.github/scripts'))
import test_marketplace_git_channels
rows=[];stream=io.StringIO()
class Result(unittest.TextTestResult):
 def addSuccess(self,test):rows.append({'id':test.id(),'result':'PASSED'});super().addSuccess(test)
 def addFailure(self,test,err):rows.append({'id':test.id(),'result':'FAILED'});super().addFailure(test,err)
 def addError(self,test,err):rows.append({'id':test.id(),'result':'ERROR'});super().addError(test,err)
 def addSkip(self,test,reason):rows.append({'id':test.id(),'result':'SKIPPED'});super().addSkip(test,reason)
suite=unittest.TestLoader().loadTestsFromNames(plan['argv'][5:]);started=time.time()
result=unittest.TextTestRunner(verbosity=2,resultclass=Result,stream=stream).run(suite)
seconds=time.time()-started
raw=stream.getvalue().encode('utf-8');(O/'original16.stderr.log').write_bytes(raw)
after=capture();head_after=git('rev-parse','HEAD').decode().strip();index_after=sha(index.read_bytes())
document={'actual_source_commit':SOURCE,'source_after':head_after,'index_sha256_after':index_after,'inputs_after':after,'named_results':rows,'tests_run':result.testsRun,'seconds':seconds,'exit_code':0 if result.wasSuccessful() and not result.skipped else 1,'raw_stderr_sha256':sha(raw),'imported_repository_modules':sorted({str(Path(m.__file__).resolve().relative_to(R)).replace('\\','/') for m in sys.modules.values() if getattr(m,'__file__',None) and Path(m.__file__).resolve().is_relative_to(R)})}
write('result.json',document)
assert before==after and head_after==SOURCE and index_after==index_before
assert result.testsRun==16 and len(rows)==16 and all(x['result']=='PASSED' for x in rows)
assert document['exit_code']==0
print(json.dumps({'source':SOURCE,'passed':16,'seconds':seconds,'inputs':len(before['physical']),'HEAD_index_inputs_stable':True}))
