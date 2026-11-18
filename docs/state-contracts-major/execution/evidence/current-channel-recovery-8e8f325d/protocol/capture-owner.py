"""Fresh private wrapper around unchanged original owner assertions; never a Gov writer."""
import datetime,hashlib,json,os,re,stat,subprocess,sys,time
from pathlib import Path,PureWindowsPath
OUT=Path(sys.argv[1]).resolve();CONFIG=json.loads((OUT/'config.json').read_text(encoding='utf-8'))
REPO=Path(CONFIG['REPO']);SOURCE=CONFIG['source'];ROOTS=CONFIG['roots'];GIT='C:/Program Files/Git/cmd/git.exe'
sha=lambda b:hashlib.sha256(b).hexdigest()
def save(name,value):
 p=OUT/name;p.write_bytes(value if isinstance(value,bytes)else(json.dumps(value,ensure_ascii=True,indent=2)+'\n').encode())
def need(c,m):
 if not c:raise ValueError(m)
def git(*a):return subprocess.check_output([GIT,'--no-lazy-fetch',*a],cwd=REPO,timeout=30)
def identity():
 index=Path(git('rev-parse','--path-format=absolute','--git-path','index').decode().strip())
 return {'head':git('rev-parse','HEAD').decode().strip(),'tree':git('rev-parse','HEAD^{tree}').decode().strip(),'index_sha256':sha(index.read_bytes()),'status_sha256':sha(git('status','--porcelain=v1','-z','--untracked-files=all'))}
def namespace(root):
 rows=[];raw=git('ls-tree','-z','-l','-r','-t',SOURCE+':'+root);need(len(raw)<=2*1024*1024,'Git namespace exceeds bound')
 for row in raw.split(b'\0'):
  if not row:continue
  header,name=row.split(b'\t',1);mode,kind,oid,size=header.decode().split();name=name.decode('utf-8');need(name.isascii()and(mode,kind)in[('040000','tree'),('100644','blob'),('100755','blob')],'unsupported namespace entry');rows.append([name,mode,kind])
 need(len(rows)<=4096 and len({x[0].casefold()for x in rows})==len(rows),'namespace bound/ambiguity');return sorted(rows,key=lambda x:PureWindowsPath(x[0]))
def inventory(base,relative_root=None):
 answer={}
 def visit(folder):
  info=folder.lstat();need(stat.S_ISDIR(info.st_mode)and not folder.is_symlink()and not getattr(info,'st_file_attributes',0)&0x400,'unsupported directory')
  entries=sorted(folder.iterdir());names=[p.name for p in entries];need(len({n.casefold()for n in names})==len(names),'ambiguous physical names')
  for p in entries:
   info=p.lstat();need(not p.is_symlink()and not getattr(info,'st_file_attributes',0)&0x400,'unsupported link');name=p.relative_to(base).as_posix();kind='directory'if stat.S_ISDIR(info.st_mode)else'file'if stat.S_ISREG(info.st_mode)else'unsupported';need(kind!='unsupported','unsupported physical kind');answer[name]={'kind':kind,'physical_mode':oct(stat.S_IMODE(info.st_mode))}
   if kind=='directory':visit(p)
   else:answer[name].update(sha256=sha(p.read_bytes()),bytes=info.st_size)
 visit(base);return answer
def runtime():
 rows=[]
 for folder,ds,fs in os.walk('C:/Python314',followlinks=False):
  ds.sort();fs.sort()
  for name in fs:
   p=Path(folder)/name;info=p.lstat();need(stat.S_ISREG(info.st_mode)and not p.is_symlink()and not getattr(info,'st_file_attributes',0)&0x400,'unsupported runtime member');rows.append({'path':str(p),'sha256':sha(p.read_bytes())})
 need(bool(rows),'empty runtime');return rows
def lookup_host():
 physical=[];immutable=[];parent=REPO;rel=''
 for component in ['core','pysrc','_host.py']:
  info=parent.lstat();need(stat.S_ISDIR(info.st_mode)and not parent.is_symlink()and not getattr(info,'st_file_attributes',0)&0x400,'host parent unsupported');names=sorted(p.name for p in parent.iterdir());need(all(n.isascii()for n in names),'unsupported host path Unicode');matches=[n for n in names if n.casefold()==component.casefold()];raw=git('ls-tree','-z',SOURCE+(':'+rel if rel else ''));entries=[]
  for row in raw.split(b'\0'):
   if not row:continue
   header,name=row.split(b'\t',1);need(name.isascii(),'host Git name unsupported');entries.append({'name':name.decode(),'entry':header.decode()})
  found=[v for v in entries if v['name'].casefold()==component.casefold()];physical.append({'parent':rel or'.','successful_enumeration':True,'names':names,'matches':matches,'directory_identity':[info.st_dev,info.st_ino]});immutable.append({'parent':rel or'.','successful_enumeration':True,'entries':entries,'matches':found,'stdout_sha256':sha(raw)})
  if component=='_host.py':need(not matches and not found,'owned host unexpectedly present')
  else:need(matches==[component]and len(found)==1 and found[0]['name']==component and found[0]['entry'].startswith('040000 tree '),'host parent identity');parent/=component;rel=(rel+'/'+component).lstrip('/')
 return {'descriptor':{'path':'core/pysrc/_host.py','path_style':'windows'},'physical':physical,'immutable':immutable}
def config_lookup():
 if CONFIG['owner']!='benchmark':return None
 rows={}
 for name in CONFIG['inputs']:
  if not name.endswith('.ts'):continue
  for parent in (REPO/name).parents:
   if parent==REPO.parent:break
   for leaf in ['package.json','tsconfig.json']:
    p=parent/leaf;rows[p.relative_to(REPO).as_posix()]=sha(p.read_bytes())if p.is_file()else None
 return rows
def snapshot():
 values={name:sha((REPO/name).read_bytes())for name in sorted(CONFIG['inputs'])};need(all(sha(git('show',SOURCE+':'+name))==h for name,h in values.items()),'positive bytes differ Git')
 extra={}
 if CONFIG['owner']=='benchmark':
  for rel in ['plugins/ca-pi/tools/node_modules/esbuild','plugins/ca-pi/tools/node_modules/@esbuild/win32-x64']:extra[rel]=inventory(REPO/rel)
  node=Path('C:/Users/brenn/AppData/Local/Temp/ca-node22.19-offline-repro-vtod7t5h/node.EXE');need(sha(node.read_bytes())=='995a3fb3cefad590cd3f4b321532a4b9582fb9c6575320ed2e3e894caac3e362','approved Node changed');extra['Node']={'path':str(node),'sha256':sha(node.read_bytes())}
 return {'identity':identity(),'inputs':values,'Git_namespaces':{s:namespace(s)for s in ROOTS},'physical_namespaces':{s:inventory(REPO/s)for s in ROOTS},'runtime':runtime(),'Git_executable':{'path':GIT,'sha256':sha(Path(GIT).read_bytes())},'owning_host_lookup':lookup_host(),'JS_config_lookups':config_lookup(),'extra_runtime':extra,'fixture_parameters':{name:sha((REPO/name).read_bytes())for name in ['docs/state-contracts-major/execution/coverage-ledger.json','docs/state-contracts-major/execution/progress.json']}}
def projection(snapshot):
 answer={}
 for root in ROOTS:
  tracked={v[0]for v in snapshot['Git_namespaces'][root]};seen=snapshot['physical_namespaces'][root];need(not tracked-set(seen),'tracked namespace path missing');extra=sorted(set(seen)-tracked);legacy=[p for p in extra if '__pycache__'in p.split('/')];other=[p for p in extra if p not in legacy];causal=[p for p in other if seen[p]['kind']=='directory'or p.casefold().endswith(('.py','.pyc','.pyo','.pyw','.pyd','.so'))];need(not causal,'causal untracked import shadow');answer[root]={'Git_names_equal_physical_names':tracked==set(seen),'legacy_cache_entries_preserved':legacy,'other_entries_preserved':other,'causal_untracked_shadows':causal,'private_prefix_before_import':'Private cache prefix redirects import cache lookup; no legacy entry removed or assumed absent.'}
 return answer
def lookups(snapshot):
 p=OUT/'lookup-candidates.json'
 if not p.exists():return None
 answer={}
 for module,v in json.loads(p.read_text(encoding='utf-8')).items():
  present=[];absent=[]
  for name in v['candidates']:
   root=next(root for root in ROOTS if name.startswith(root+'/'));rel=name[len(root)+1:];matches=[n for n in snapshot['physical_namespaces'][root]if n.casefold()==rel.casefold()];need(len(matches)<=1,'lookup ambiguous');(present if matches else absent).append(name)
  answer[module]={'candidates':v['candidates'],'present':present,'absent':absent}
 need(sum(len(v['absent'])for v in answer.values())==7,'original seven causal lookup facts changed');return answer
def env_for():
 base=OUT/'profile'
 for rel in ['home','appdata','localappdata','xdg/config','xdg/cache','tmp','pycache']:(base/rel).mkdir(parents=True,exist_ok=False)
 env={k:os.environ[k]for k in ['SystemRoot','WINDIR','COMSPEC','PATHEXT']if k in os.environ};paths=[str(Path(GIT).parent),str(Path(os.environ['SystemRoot'])/'System32')]
 if CONFIG['owner']=='benchmark':paths.insert(0,'C:/Users/brenn/AppData/Local/Temp/ca-node22.19-offline-repro-vtod7t5h')
 env.update(PATH=os.pathsep.join(paths),HOME=str(base/'home'),USERPROFILE=str(base/'home'),APPDATA=str(base/'appdata'),LOCALAPPDATA=str(base/'localappdata'),XDG_CONFIG_HOME=str(base/'xdg/config'),XDG_CACHE_HOME=str(base/'xdg/cache'),TEMP=str(base/'tmp'),TMP=str(base/'tmp'),PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONPYCACHEPREFIX=str(base/'pycache'),PYTHONPATH=str(OUT/'observer'),GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=str(base/'home/no-global-config'),GIT_TERMINAL_PROMPT='0',GIT_NO_LAZY_FETCH='1',GIT_NO_REPLACE_OBJECTS='1');return env

def main():
 need(identity()['head']==SOURCE,'HEAD not dispatched source');before=snapshot();proj=projection(before);lookup=lookups(before);env=env_for();save('run-start.json',{'format':'finite-current-software54-start/1','owner':CONFIG['owner'],'source_commit':SOURCE,'snapshot':before,'namespace_projection':proj,'module_resolution':lookup,'environment':env,'argv':CONFIG['argv'],'cwd':CONFIG['cwd'],'started_utc':datetime.datetime.now(datetime.UTC).isoformat(),'wrapper_sha256':sha(Path(__file__).read_bytes()),'observer_sha256':sha((OUT/'observer/sitecustomize.py').read_bytes())});started=time.monotonic()
 try:p=subprocess.run(CONFIG['argv'],cwd=CONFIG['cwd'],env=env,capture_output=True,timeout=CONFIG['timeout']);code=p.returncode;stdout=p.stdout;stderr=p.stderr;timed=False
 except subprocess.TimeoutExpired as error:code=None;stdout=error.stdout or b'';stderr=error.stderr or b'';timed=True
 seconds=time.monotonic()-started;save('original.stdout.log',stdout);save('original.stderr.log',stderr);save('process-exit.json',{'argv':CONFIG['argv'],'cwd':CONFIG['cwd'],'exit_code':code,'timed_out':timed,'seconds':seconds,'stdout_sha256':sha(stdout),'stderr_sha256':sha(stderr)})
 after=snapshot();save('after-snapshot.json',after);print(json.dumps({'AFTER_SNAPSHOT_PERSISTED':True,'owner':CONFIG['owner'],'exit':code,'timed_out':timed,'stable':before==after}),flush=True)
 imports=[json.loads(p.read_text(encoding='utf-8'))for p in sorted(OUT.glob('actual-imports-*.json'))];loaded={};errors=[]
 for ob in imports:
  errors.extend(ob.get('observer_errors',[]));loaded.update(ob.get('executed_repository_modules',{}));loaded.update({v['path']:v['sha256']for v in ob.get('loaded_repository_modules',{}).values()})
 benchmark=None
 if CONFIG['owner']=='benchmark'and(OUT/'boundary-observation.json').exists():benchmark=json.loads((OUT/'boundary-observation.json').read_text(encoding='utf-8'));loaded.update(benchmark['loaded_source_first_call_sha256']);errors.extend(benchmark['observer_errors'])
 named=[]
 if CONFIG['owner']=='statusline'and(OUT/'named-results.json').exists():named=json.loads((OUT/'named-results.json').read_text(encoding='utf-8'))['outcomes']
 elif CONFIG['owner']=='channel'and(OUT/'result.json').exists():named=json.loads((OUT/'result.json').read_text(encoding='utf-8'))['named_results']
 elif CONFIG['selectors']:
  for name in CONFIG['selectors']:
   pattern=r'(?m)^'+re.escape(name.rsplit('.',1)[1])+r' \('+re.escape(name)+r'\) \.\.\. ([^\r\n]+)\r?$';named.append({'id':name,'outcomes':re.findall(pattern,stderr.decode('utf-8'))})
 closure_errors=[]
 for name,h in loaded.items():
  root=next((root for root in ROOTS if name.startswith(root+'/')),None)
  if root is None:closure_errors.append('outside-captured-root:'+name);continue
  rel=name[len(root)+1:]
  if before['physical_namespaces'][root].get(rel,{}).get('sha256')!=h or after['physical_namespaces'][root].get(rel,{}).get('sha256')!=h or sha(git('show',SOURCE+':'+name))!=h:closure_errors.append('loaded-byte-mismatch:'+name)
 observations=benchmark and[benchmark]or imports
 cache_ok=any(ob.get('parent_no_user_site')==1 and ob.get('parent_pycache_prefix')and Path(ob['parent_pycache_prefix']).resolve()==Path(env['PYTHONPYCACHEPREFIX']).resolve()for ob in observations)
 result={'format':'finite-current-software54-result/1','owner':CONFIG['owner'],'source_commit':SOURCE,'source_tree':before['identity']['tree'],'exit_code':code,'timed_out':timed,'seconds':seconds,'before_after_all_closure_equal':before==after,'namespace_projection':proj,'module_resolution':lookup,'actual_repository_imports':loaded,'checked_inputs':{**before['inputs'],**loaded},'named_results':named,'actual_import_observations':[p.name for p in sorted(OUT.glob('actual-imports-*.json'))],'runtime_records':len(before['runtime']),'observer_errors':errors,'closure_errors':closure_errors,'private_prefix_no_user_site_observed':cache_ok,'benchmark_observation':benchmark,'scope_limits':CONFIG['original_scope']};save('run-result.json',result)
 need(code==0 and not timed,'original owner command did not pass');need(before==after,'before/after closure changed');need(observations and not errors and not closure_errors and cache_ok,'actual import/closure observer refused')
 if CONFIG['owner']=='statusline':need(len(named)==67 and all(n['outcome']=='PASS'for n in named),'statusline named assertion refusal')
 elif CONFIG['owner']=='channel':need(len(named)==16 and all(n['result']=='PASSED'for n in named),'channel named assertion refusal')
 elif CONFIG['selectors']:need(len(named)==len(CONFIG['selectors'])and all(n['outcomes']==['ok']for n in named),'unittest named assertion refusal')
 else:need(benchmark is not None and len(benchmark['observations'])==2,'benchmark original boundary observations absent')
 save('capture-complete.json',{'state':'ACTUAL_CAPTURE_SEALED','owner':CONFIG['owner'],'source_commit':SOURCE,'source_tree':before['identity']['tree'],'exit_code':code,'seconds':seconds,'PASS':len(named)if CONFIG['selectors']else'original --samples100 benchmark','positive_inputs':len(result['checked_inputs']),'runtime_records':len(before['runtime']),'actual_imports':len(loaded),'HEAD_index_source_runtime_namespaces_stable':True});print(json.dumps({'SEALED':CONFIG['owner'],'out':str(OUT),'seconds':seconds,'named':len(named),'inputs':len(result['checked_inputs']),'runtime':len(before['runtime'])}),flush=True)
if __name__=='__main__':
 try:main()
 except BaseException as error:
  save('wrapper-failure.json',{'state':'CAPTURE_OR_VALIDATION_REFUSED','error_type':type(error).__name__,'bounded_reason':str(error)if isinstance(error,ValueError)else None});raise
