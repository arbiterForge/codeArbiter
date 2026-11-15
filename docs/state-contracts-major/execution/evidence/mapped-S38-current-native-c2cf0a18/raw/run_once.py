from pathlib import Path
import subprocess,os,shutil,json,time,hashlib
O=Path(__file__).resolve().parent;S=O/'source';P=Path('C:/Users/brenn/AppData/Local/Temp/ca-S38-current-native-08y3_j82/extracted/artifact-candidate'); assert P.is_dir()
private=O/'private';private.mkdir()
for n in ['tmp','home','appdata','localappdata','config','cache']:(private/n).mkdir()
git=Path(shutil.which('git')).resolve();env={k:v for k,v in os.environ.items() if k.upper() in ['SYSTEMROOT','WINDIR','SYSTEMDRIVE','COMSPEC','PATHEXT']}
env.update(PATH=str(git.parent)+os.pathsep+str(Path(os.environ['SYSTEMROOT'])/'System32'),HOME=str(private/'home'),USERPROFILE=str(private/'home'),APPDATA=str(private/'appdata'),LOCALAPPDATA=str(private/'localappdata'),TEMP=str(private/'tmp'),TMP=str(private/'tmp'),XDG_CONFIG_HOME=str(private/'config'),XDG_CACHE_HOME=str(private/'cache'),PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull,GIT_TERMINAL_PROMPT='0',GOTOOLCHAIN='local',GOPROXY='off',GOSUMDB='off',ARTIFACT_TEST_INSTALLATION=str(P))
assert not any(k.upper().startswith('GITHUB_') or k.upper() in ['CI','GH_TOKEN','GITHUB_TOKEN','FARM_API_KEY','CLAUDE_CODE_OAUTH_TOKEN'] for k in env)
assert shutil.which('go',path=env['PATH']) is None
prefix='test_work_github.GithubWorkTest.'; methods=[prefix+x for x in ['test_mapped_preclaim_transport_failure_keeps_pending_and_continues_independent_target','test_mapped_target_local_native_claim_conflict_keeps_pending_and_continues_independent_target','test_mapped_target_local_remote_identity_failure_keeps_pending_and_continues_independent_target']]
cmd=['C:/Python314/python.exe','-B','-X','utf8',str(O/'observe_unittest.py'),*methods];start=time.monotonic();p=subprocess.run(cmd,cwd=S/'.github/scripts',env=env,capture_output=True,timeout=180)
for n,b in [('stdout',p.stdout),('stderr',p.stderr)]:
 with (O/('actual.'+n)).open('xb') as f:f.write(b)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();record={'command':cmd,'cwd':str(S/'.github/scripts'),'exit_code':p.returncode,'seconds':time.monotonic()-start,'python_sha256':sha(Path(cmd[0])),'python_version':subprocess.check_output([cmd[0],'--version'],env=env,text=True).strip(),'git_executable':str(git),'git_sha256':sha(git),'observer_sha256':sha(O/'observe_unittest.py'),'environment_keys':sorted(env),'ARTIFACT_TEST_INSTALLATION':str(P),'go_on_PATH':False,'no_CI_identity_or_provider_credentials':True,'selection':'exact3existingmethods once, suppliedoriginalnativecandidate, no builder invocation'}
with (O/'actual-command.json').open('x',encoding='utf8') as f:json.dump(record,f,indent=2)
print(p.stdout.decode('utf8',errors='replace'));print(p.stderr.decode('utf8',errors='replace'));print(json.dumps(record));raise SystemExit(p.returncode)
