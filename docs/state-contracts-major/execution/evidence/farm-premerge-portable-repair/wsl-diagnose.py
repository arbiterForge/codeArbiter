import os,sys,json,subprocess,tempfile,pathlib,time,shutil,hashlib
OUT=pathlib.Path(sys.argv[1]);records=[]
for close_readers in [False,True]:
 root=pathlib.Path(tempfile.mkdtemp(prefix='farm-premerge-git-')).resolve();repo=root/'repo';repo.mkdir();home=root/'home';home.mkdir();env={'PATH':'/usr/bin:/bin','HOME':str(home),'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_OPTIONAL_LOCKS':'0'}
 def git(*a):return subprocess.check_output(['git','-C',str(repo),*a],env=env,stderr=subprocess.PIPE).decode().strip()
 child=None
 try:
  git('init','-b','main');git('config','user.email','fixture@example.invalid');git('config','user.name','Fixture');(repo/'README').write_text('owned\n');git('add','README');git('commit','-m','base');base=git('rev-parse','HEAD');git('checkout','-b','task');(repo/'task.txt').write_text('pending candidate\n');git('add','task.txt');git('commit','-m','candidate');candidate=git('rev-parse','HEAD');git('checkout','main')
  hooks=root/'hooks';hooks.mkdir();ack=root/'ack';release=root/'release';hook=hooks/'pre-merge-commit'
  hook.write_text('#!'+sys.executable+'\nimport pathlib,os,json,time\nack=pathlib.Path('+repr(str(ack))+');release=pathlib.Path('+repr(str(release))+')\nack.write_text(json.dumps({"pid":os.getpid(),"ppid":os.getppid()}))\ndeadline=time.monotonic()+5\nwhile not release.exists():\n if time.monotonic()>deadline:raise SystemExit(76)\n time.sleep(0.01)\nraise SystemExit(75)\n');hook.chmod(0o700);git('config','core.hooksPath',str(hooks))
  child=subprocess.Popen(['git','-C',str(repo),'merge','--no-ff','-m','merge','task'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
  deadline=time.monotonic()+5
  while not ack.exists():
   if time.monotonic()>deadline:raise RuntimeError('owned hook did not acknowledge')
   time.sleep(.01)
  a=json.loads(ack.read_text());assert a['ppid']==child.pid
  index=repo/'.git/index';merge=repo/'.git/MERGE_HEAD';before={'HEAD':git('rev-parse','HEAD'),'MERGE_HEAD_exists':merge.exists(),'staged':git('diff','--cached','--name-only')}
  if close_readers:child.stdout.close();child.stderr.close()
  release.write_text('release\n')
  if close_readers:code=child.wait(timeout=5);stderr='closed reader: no diagnostic bytes available'
  else:stdout,stderr=child.communicate(timeout=5);code=child.returncode;stderr=stderr.decode()
  after={'HEAD':git('rev-parse','HEAD'),'MERGE_HEAD_exists':merge.exists(),'MERGE_HEAD':merge.read_text().strip() if merge.exists() else None,'staged':git('diff','--cached','--name-only'),'implementation':(repo/'task.txt').read_text(),'index_sha256':hashlib.sha256(index.read_bytes()).hexdigest()}
  records.append({'close_parent_readers':close_readers,'git_version':git('--version'),'python':sys.version,'git_pid_matches_hook_parent':a['ppid']==child.pid,'returncode':code,'stderr':stderr,'base':base,'candidate':candidate,'before':before,'after':after})
 finally:
  if child is not None and child.poll() is None:child.kill();child.wait(timeout=5)
  assert root.parent==pathlib.Path('/tmp') and root.name.startswith('farm-premerge-git-');shutil.rmtree(root)
(OUT/'git-lifecycle-discriminator.json').write_text(json.dumps(records,indent=2)+'\n');print(json.dumps(records,indent=2))
