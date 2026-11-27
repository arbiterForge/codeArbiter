from pathlib import Path
import hashlib,io,json,os,subprocess,sys,time,unittest,collections
P=Path(__file__).resolve().parent
R=Path(r'C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter')
SOURCE='a0f4bc274c78613b739757743616bd23b1fe63ef'
PATHS=['tools/sync-core.py','tools/owned_output.py','tools/host_descriptors.py','core/hosts.json','.github/scripts/test_sync_core.py']
GIT=r'C:/Program Files/Git/cmd/git.exe'
sha=lambda b:hashlib.sha256(b).hexdigest()
def git(*args):return subprocess.check_output([GIT,'--no-replace-objects','--no-lazy-fetch','-C',str(R),*args],timeout=30)
def capture():
 head=git('rev-parse','HEAD').decode().strip();assert head==SOURCE
 rows={}
 for name in PATHS:
  physical=(R/name).read_bytes();literal=git('show',SOURCE+':'+name);assert physical==literal,name;rows[name]=sha(physical)
 index=Path(git('rev-parse','--path-format=absolute','--git-path','index').decode().strip());assert git('diff','--cached','--raw')==b''
 return {'source_commit':head,'inputs':rows,'index_sha256':sha(index.read_bytes()),'index_empty':True}
before=capture();(P/'inputs-before.json').write_text(json.dumps(before,indent=2)+'\n',encoding='utf-8')
assert Path(os.environ['HOME']).resolve()==(P/'home').resolve()
sys.path.insert(0,str(R/'.github/scripts'))
import test_sync_core as T
selectors=json.loads((P/'selectors.json').read_text(encoding='utf-8'));outcomes=[];stream=io.StringIO()
class Result(unittest.TextTestResult):
 def addSuccess(self,test):outcomes.append({'id':test.id(),'outcome':'PASS'});super().addSuccess(test)
 def addFailure(self,test,err):outcomes.append({'id':test.id(),'outcome':'FAIL'});super().addFailure(test,err)
 def addError(self,test,err):outcomes.append({'id':test.id(),'outcome':'ERROR'});super().addError(test,err)
 def addSkip(self,test,why):outcomes.append({'id':test.id(),'outcome':'SKIP'});super().addSkip(test,why)
start=time.time();result=unittest.TextTestRunner(stream=stream,verbosity=2,resultclass=Result).run(unittest.TestLoader().loadTestsFromNames(selectors,T));duration=time.time()-start
raw=stream.getvalue().encode('utf-8');(P/'original-fifteen.stderr.log').write_bytes(raw);after=capture();(P/'inputs-after.json').write_text(json.dumps(after,indent=2)+'\n',encoding='utf-8')
expected=['test_sync_core.'+s for s in selectors];exact=collections.Counter(x['id'] for x in outcomes)==collections.Counter(expected) and len(outcomes)==15 and all(x['outcome']=='PASS' for x in outcomes)
doc={'schema':'codearbiter.sync-owner-named-observation/1','source_commit':SOURCE,'source_kind':'Actual committed Gov source/test execution; not a Temp overlay or future source join','argv':[sys.executable,'-B',str(Path(__file__).resolve())],'cwd':str(Path.cwd()),'runtime':sys.version,'runtime_executable_sha256':sha(Path(sys.executable).read_bytes()),'home_before_import':os.environ['HOME'],'environment_keys':sorted(os.environ),'started_at_unix':start,'duration_seconds':duration,'exit_code':0 if result.wasSuccessful() else 1,'selectors':selectors,'outcomes':outcomes,'all_fifteen_passed_once':exact,'inputs_before':before,'inputs_after':after,'observer_sha256':sha(Path(__file__).read_bytes()),'raw_sha256':sha(raw),'scope':'Exactly15 selected sync-owner methods on actual5 admitted source/descriptor/test inputs, using owned synthetic filesystem fixtures. No full suite/native build/installed/provider/package/host proof.'}
(P/'result.json').write_text(json.dumps(doc,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'exit_code':doc['exit_code'],'source_commit':SOURCE,'actual15pass':exact,'inputs_stable':before==after,'duration_seconds':duration},indent=2))
assert before==after and exact and result.wasSuccessful()
