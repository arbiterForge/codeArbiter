import pathlib,json,hashlib,subprocess,os,sys,datetime,platform,time
R=pathlib.Path(r'C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter');O=pathlib.Path(__file__).parent;G='C:/Program Files/Git/cmd/git.exe';S='bf2f4b412cb1a81fde0e4c32fa2d4623ded3f63b';H=lambda b:hashlib.sha256(b).hexdigest()
def save(n,x):(O/n).write_text(json.dumps(x,indent=2,ensure_ascii=True)+'\n',encoding='utf-8',newline='\n')
def git(*a):return subprocess.check_output([G,'-C',str(R),*a])
paths=json.loads((O/'source-paths.json').read_text())
def capture():
 d={}
 for p in paths:
  b=(R/p).read_bytes();g=git('show',S+':'+p);assert b==g,p
  d[p]={'sha256':H(b),'size':len(b),'git_blob':git('rev-parse',S+':'+p).decode().strip()}
 return d
assert git('rev-parse','HEAD').decode().strip()==S
before=capture();status=git('status','--porcelain=v1').decode();index=H(git('diff','--cached','--raw'));save('inputs-before.json',before)
home=O/'private-home';home.mkdir();scratch=O/'scratch';scratch.mkdir()
env={k:v for k,v in os.environ.items() if k.upper() in {'PATH','SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','SYSTEMDRIVE'}};env.update(HOME=str(home),USERPROFILE=str(home),HOMEDRIVE=home.drive,HOMEPATH=str(home)[len(home.drive):],TEMP=str(scratch),TMP=str(scratch),PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1')
a=[sys.executable,'-B',str(O/'run-selected.py'),str(R),str(O)];start=datetime.datetime.now(datetime.timezone.utc).isoformat();t=time.monotonic();c=subprocess.run(a,cwd=R,env=env,capture_output=True,timeout=30);seconds=time.monotonic()-t
(O/'original.stdout.log').write_bytes(c.stdout);(O/'original.stderr.log').write_bytes(c.stderr);save('child-exit.json',{'argv':a,'cwd':str(R),'exit_code':c.returncode,'start':start,'finish':datetime.datetime.now(datetime.timezone.utc).isoformat(),'seconds':seconds,'stdout_sha256':H(c.stdout),'stderr_sha256':H(c.stderr)})
after=capture();save('inputs-after.json',after);end=git('rev-parse','HEAD').decode().strip();endstatus=git('status','--porcelain=v1').decode();endindex=H(git('diff','--cached','--raw'))
save('observation.json',{'source_commit':S,'end_HEAD':end,'before_status':status,'after_status':endstatus,'index_before':index,'index_after':endindex,'inputs_stable':before==after,'positive_inputs':len(before),'python':{'executable':sys.executable,'version':sys.version,'platform':platform.platform()},'command':{'argv':a,'cwd':str(R),'exit_code':c.returncode},'secrets_environment':'Minimal runtime allowlist/private HOME+TEMP before imports; no source copies, provider secrets or installed-host initialization.','home_empty_after':not list(home.iterdir()),'scratch_empty_after':not list(scratch.iterdir()),'scope':'Existing source-conformance assertions reading real canonical/generated guidance only. No installed model turn, scheduler/dependency analysis or store operation is executed.'})
assert c.returncode==0 and before==after and end==S and status==endstatus and index==endindex and not list(home.iterdir()) and not list(scratch.iterdir())
print(json.dumps({'packet':str(O),'source':S,'input_count':len(before),'exit_code':c.returncode}))
