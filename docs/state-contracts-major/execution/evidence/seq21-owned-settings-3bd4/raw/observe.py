from __future__ import annotations
import os,sys,pathlib,subprocess,json,hashlib,datetime,platform,time
ROOT=pathlib.Path(r"C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter")
OUT=pathlib.Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
def save(name,data):
 (OUT/name).write_text(json.dumps(data,indent=2,ensure_ascii=True)+'\n',encoding='utf-8',newline='\n')
def git(*args):return subprocess.check_output(['git','-C',str(ROOT),*args])
paths=sorted([p.relative_to(ROOT).as_posix() for p in (ROOT/'plugins/ca/hooks').glob('*.py')]+['plugins/ca/hooks/tests/test_wire_statusline.py','core/pysrc/wire-statusline.py'])
def inventory():
 result={}
 for p in paths:
  physical=(ROOT/p).read_bytes();immutable=git('show','HEAD:'+p)
  assert physical==immutable,p
  result[p]={'sha256':sha(physical),'git_blob':git('rev-parse','HEAD:'+p).decode().strip(),'size':len(physical)}
 return result
before=inventory(); head=git('rev-parse','HEAD').decode().strip(); status=git('status','--porcelain=v1').decode(); index=sha(git('diff','--cached','--raw'))
save('inputs-before.json',before)
selectors=['TestSpinnerOwnershipIsExact.'+s for s in [
 'test_install_stamps_the_exact_owned_value','test_still_owned_uninstall_restores_previous_value',
 'test_user_custom_spinner_after_install_survives_uninstall','test_user_removed_spinner_after_install_is_not_recreated',
 'test_reinstall_after_user_change_does_not_overwrite_silently_then_uninstall_restores_it',
 'test_legacy_backup_without_stamp_is_conservative','test_repeated_uninstall_is_a_noop',
 'test_spinner_ownership_is_independent_of_statusline_replacement']]+[
 'TestUninstall.test_restores_exact_third_party_statusline_setting',
 'TestFreshInstall.test_uninstall_removes_statusline_when_no_prior_existed']
save('selectors.json',selectors)
home=OUT/'private-home'; home.mkdir(); scratch=OUT/'fixtures';scratch.mkdir()
env={k:v for k,v in os.environ.items() if k.upper() in {'PATH','SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','SYSTEMDRIVE','NUMBER_OF_PROCESSORS','PROCESSOR_ARCHITECTURE'}}
env.update(HOME=str(home),USERPROFILE=str(home),HOMEDRIVE=home.drive,HOMEPATH=str(home)[len(home.drive):],TMP=str(scratch),TEMP=str(scratch),PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1')
argv=[sys.executable,'-B',str(OUT/'run-selected.py'),str(ROOT),str(OUT)]
started=datetime.datetime.now(datetime.timezone.utc).isoformat();t=time.monotonic()
cp=subprocess.run(argv,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
(OUT/'original.stdout.log').write_bytes(cp.stdout);(OUT/'original.stderr.log').write_bytes(cp.stderr)
after=inventory();save('inputs-after.json',after)
assert before==after
endhead=git('rev-parse','HEAD').decode().strip()
assert head==endhead
assert status==git('status','--porcelain=v1').decode()
assert index==sha(git('diff','--cached','--raw'))
assert not list(home.rglob('*'))
assert not list(scratch.iterdir())
save('observation.json',{'source_commit':head,'head_after':endhead,'started_at':started,'finished_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'elapsed_seconds':time.monotonic()-t,'command':{'argv':argv,'cwd':str(ROOT),'exit_code':cp.returncode},'observer_command':{'argv':[sys.executable,'-B',str(OUT/'observe.py')],'cwd':str(ROOT)},'python':{'executable':sys.executable,'version':sys.version,'platform':platform.platform()},'input_count':len(before),'literal_git_join':True,'inputs_stable':True,'initial_status':status,'index_raw_sha256':index,'home_empty_after':True,'fixture_temp_empty_after':True,'secrets_environment':'minimal runtime allowlist, private home and private TEMP set before any test imports; no inherited provider variables','scope':'Existing unittest main-function calls with real settings files and mocked authenticated adapter identity only. No host installation/native build/browser/provider/network.'})
if cp.returncode:sys.exit(cp.returncode)
print(json.dumps({'packet':str(OUT),'source_commit':head,'count':len(selectors),'exit_code':cp.returncode}))
