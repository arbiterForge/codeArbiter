from __future__ import annotations
import os,sys,pathlib,subprocess,json,hashlib,datetime,platform,time,stat
ROOT=pathlib.Path(r'C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter')
OUT=pathlib.Path(__file__).resolve().parent
SOURCE='7f741ba5bf56cb785bc9c54e0d1fd8faa97a8cbb'
GIT='C:/Program Files/Git/cmd/git.exe'
sha=lambda b:hashlib.sha256(b).hexdigest()
def save(name,data):(OUT/name).write_text(json.dumps(data,indent=2,ensure_ascii=True)+'\n',encoding='utf-8',newline='\n')
def git(*args):return subprocess.check_output([GIT,'-C',str(ROOT),*args])
paths=json.loads((OUT/'positive-paths.json').read_text())
def inventory():
 result={}
 for p in paths:
  raw=(ROOT/p).read_bytes();immutable=git('show',SOURCE+':'+p)
  assert raw==immutable,p
  result[p]={'sha256':sha(raw),'git_blob':git('rev-parse',SOURCE+':'+p).decode().strip(),'size':len(raw)}
 return result
LOOKUP='plugins/ca/hooks/_host.py'
def physical_lookup():
 inventories=[];parent=ROOT
 for index,name in enumerate(LOOKUP.split('/')):
  info=parent.lstat();assert stat.S_ISDIR(info.st_mode) and not parent.is_symlink() and not getattr(info,'st_file_attributes',0)&0x400
  with os.scandir(parent) as it:names=sorted(entry.name for entry in it)
  assert len(names)<=4096 and all(n.isascii() for n in names)
  matches=[n for n in names if n.lower()==name.lower()];assert len(matches)<=1
  inventories.append({'relative_parent':parent.relative_to(ROOT).as_posix(),'successful_directory_enumeration':True,'names':names,'directory_identity':[info.st_dev,info.st_ino],'directory_attributes':getattr(info,'st_file_attributes',0),'lookup_segment':name,'case_insensitive_matches':matches})
  if index==3:
   assert len(matches)==1
   observed=(parent/matches[0]).lstat();assert stat.S_ISREG(observed.st_mode) and not getattr(observed,'st_file_attributes',0)&0x400
  else:assert len(matches)==1;parent=parent/matches[0]
 return {'path':LOOKUP,'path_style':'windows','present':True,'casefold_profile':'ASCII ordinal-ignore-case equivalent; every inspected entry ASCII, no ambiguous matching segment','inventories':inventories}
def immutable_lookup():
 inventories=[];root=''
 for index,name in enumerate(LOOKUP.split('/')):
  tree=SOURCE+(':'+root if root else '^{tree}')
  argv=[GIT,'--no-lazy-fetch','ls-tree','-z','-l',tree]
  cp=subprocess.run(argv,cwd=ROOT,capture_output=True,check=True)
  assert len(cp.stdout)<=2*1024*1024 and cp.stdout.endswith(b'\0')
  rows=[]
  for raw in cp.stdout.split(b'\0')[:-1]:
   header,n=raw.split(b'\t',1);n=n.decode('utf-8');assert n.isascii();rows.append({'name':n,'header':header.decode('ascii')})
  assert len(rows)<=4096
  matches=[x for x in rows if x['name'].lower()==name.lower()];assert len(matches)<=1
  inventories.append({'argv':argv,'exit_code':cp.returncode,'stderr_sha256':sha(cp.stderr),'stdout_sha256':sha(cp.stdout),'entries':rows,'lookup_segment':name,'case_insensitive_matches':matches})
  if index==3:assert len(matches)==1 and matches[0]['header'].split()[:2] in (['100644','blob'],['100755','blob'])
  else:
   assert len(matches)==1 and matches[0]['header'].split()[:2]==['040000','tree']
   root=root+'/'+matches[0]['name'] if root else matches[0]['name']
 return {'path':LOOKUP,'path_style':'windows','present':True,'successful_immutable_tree_walk':True,'inventories':inventories}
head=git('rev-parse','HEAD').decode().strip();assert head==SOURCE
status=git('status','--porcelain=v1').decode();index=sha(git('diff','--cached','--raw'))
before=inventory();physical_before=physical_lookup();immutable_before=immutable_lookup()
save('inputs-before.json',before);save('host-lookup-before.json',{'physical':physical_before,'immutable':immutable_before})
home=OUT/'private-home';home.mkdir();scratch=OUT/'fixtures';scratch.mkdir()
env={k:v for k,v in os.environ.items() if k.upper() in {'PATH','SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','SYSTEMDRIVE','NUMBER_OF_PROCESSORS','PROCESSOR_ARCHITECTURE'}}
env.update(HOME=str(home),USERPROFILE=str(home),HOMEDRIVE=home.drive,HOMEPATH=str(home)[len(home.drive):],TMP=str(scratch),TEMP=str(scratch),PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1')
argv=[sys.executable,'-B',str(OUT/'run-selected.py'),str(ROOT),str(OUT)]
started=datetime.datetime.now(datetime.timezone.utc).isoformat();t=time.monotonic()
cp=subprocess.run(argv,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
seconds=time.monotonic()-t
# Retain original child outcome before any post-run assertions/inventories.
(OUT/'original.stdout.log').write_bytes(cp.stdout);(OUT/'original.stderr.log').write_bytes(cp.stderr)
save('child-exit.json',{'argv':argv,'cwd':str(ROOT),'exit_code':cp.returncode,'started_at':started,'finished_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'seconds':seconds,'stdout_sha256':sha(cp.stdout),'stderr_sha256':sha(cp.stderr)})
after=inventory();physical_after=physical_lookup();immutable_after=immutable_lookup()
save('inputs-after.json',after);save('host-lookup-after.json',{'physical':physical_after,'immutable':immutable_after})
endhead=git('rev-parse','HEAD').decode().strip();endstatus=git('status','--porcelain=v1').decode();endindex=sha(git('diff','--cached','--raw'))
save('observation.json',{'source_commit':head,'head_after':endhead,'started_at':started,'finished_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':{'argv':argv,'cwd':str(ROOT),'exit_code':cp.returncode},'observer_command':{'argv':[sys.executable,'-B',str(OUT/'observe.py')],'cwd':str(ROOT)},'python':{'executable':sys.executable,'version':sys.version,'platform':platform.platform()},'input_count':len(before),'positive_inputs_stable':before==after,'physical_lookup_stable':physical_before==physical_after,'immutable_lookup_stable':immutable_before==immutable_after,'initial_status':status,'final_status':endstatus,'index_before_sha256':index,'index_after_sha256':endindex,'home_empty_after':not list(home.rglob('*')),'fixture_temp_empty_after':not list(scratch.iterdir()),'secrets_environment':'minimal runtime allowlist; all HOME/TEMP aliases redirected before imports','scope':'Same10 existing real temporary-settings tests, executing main/load/save and mocked adapter identity only. No actual host install/provider/build.','original_packet':'ca-seq21-owned-settings-326a5zp2 preserved unchanged; this is a fresh positive adapter-input/runtime precondition observation. The requested absence premise was disproved in a separate preflight before any test child; tracked Claude _host.py is present.'})
assert before==after and physical_before==physical_after and immutable_before==immutable_after
assert head==endhead and index==endindex and status==endstatus
assert not list(home.rglob('*')) and not list(scratch.iterdir())
assert cp.returncode==0
print(json.dumps({'packet':str(OUT),'source_commit':head,'count':10,'exit_code':cp.returncode,'positive_count':len(before),'host_lookup':'PRESENT, included14th positive input, physical+immutable Windows ASCII casefold walk before/after'}))
