from pathlib import Path
import hashlib,json,subprocess,sys,time
D=Path(__file__).resolve().parent;R=Path('C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter');S=Path('C:/Users/brenn/AppData/Local/Temp/ca-S38-runtime-c2cf0a18/source');E='c2cf0a18b020ef426d7df94f70fe9770fa102c32';T='docs/state-contracts-major/execution/evidence/mapped-S38-current-native-c2cf0a18/'
sys.path.insert(0,str(S/'.github/scripts'));import major_readiness as owner
read=lambda p:json.loads(p.read_text('utf8'));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();proof=read(D/'target-failure-tested.json');ref={'kind':'test','commit':E,'ref':T+'target-failure-tested.json','sha256':sha(D/'target-failure-tested.json')};row={'status':'TESTED','evidence':[ref]};cell='disposition:transitions:S38:04';current=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R).decode().strip()
contract=next(x for x in json.loads(subprocess.check_output(['git','show',E+':docs/state-contracts-major/contracts/transition-coverage.json'],cwd=R))['transitions'] if x['transition_id']=='S38:04');paths=owner.evidence_paths(contract);assert paths=={'core/pysrc/_workgithub.py'}
cache={};gitcache={}
def load(commit,path):
 if path.startswith(T):return (D/path[len(T):]).read_bytes()
 key=(commit,path)
 if key not in gitcache:gitcache[key]=subprocess.check_output(['git','--no-lazy-fetch','show',commit+':'+path],cwd=R)
 return gitcache[key]
start=time.monotonic();original=owner.authenticate_recorded_disposition(R,E,cell,row,paths,load,cache);applicable=owner.disposition_input_applicability(R,current,proof,load,cache);assert applicable==(set(),set()),applicable
strict=owner.authenticate_disposition(R,current,cell,row,paths,load,cache)
record={'schema':'codearbiter.S38-full-original-owner-validation/1','state':'TEMP_OVERLAY_VALIDATED_NOT_APPLIED','source_commit':E,'candidate_checked':current,'cell':cell,'owning_paths_from_unmodified_evidence_paths':sorted(paths),'owner_sha256':sha(S/'.github/scripts/major_readiness.py'),'actual_top_level_argv':[sys.executable,*sys.orig_argv[1:]],'cwd':str(Path.cwd()),'original_owner_result':original,'current_strict_owner_result':strict,'current_applicability':{'changed_inputs':sorted(applicable[0]),'unavailable_inputs':sorted(applicable[1])},'exit_code':0,'seconds':time.monotonic()-start,'overlay_boundary':'OnlynewcandidateevidencepayloadpathsservedfromprivateD. Allsourceinputs/module/absencelookupsuseactualimmutableGit atitsrequestedcommit. No cachedPASS/marker/API fallback; noclaimmetadataalreadycommitted.','top_level_proof_commands_nonempty_actual':bool(proof['commands'] and proof['commands'][0]['argv'] and proof['commands'][0]['exit_code']==0)}
with (D/'owner-validation.json').open('x',encoding='utf8') as f:json.dump(record,f,indent=2)
print(json.dumps(record))
