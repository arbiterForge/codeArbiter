"""Prepared original-M Pi1.5 RPC observation; no execution until Root dispatches it."""
from __future__ import annotations
import argparse,base64,hashlib,importlib.util,json,os,pathlib,platform,shutil,stat,subprocess,sys,time,unittest
from unittest import mock
HERE=pathlib.Path(__file__).resolve().parent
M='46e29a796e89e0eaa3250cf171e4c9bea97ac437'
R=43582198115
SOURCE=HERE/'source-M'
PY=pathlib.Path(r'C:/Python314/python.exe')
NODE=pathlib.Path(r'C:/Users/brenn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
PI=pathlib.Path(r'C:/Users/brenn/AppData/Local/Temp/ca-pi-supported-1.5.0-msc-20261113')
GIT=pathlib.Path(r'C:/Program Files/Git/cmd/git.exe')
NPM_BIN=pathlib.Path(r'C:/Program Files/nodejs')
sha=lambda b:hashlib.sha256(b).hexdigest()
def require(v,label):
 if not v:raise ValueError(label)
def read(p):return json.loads(p.read_bytes())
def write(p,v):
 with p.open('x',encoding='utf8',newline='\n') as stream:json.dump(v,stream,indent=2);stream.write('\n')
def git(repo,*args):return subprocess.check_output([str(GIT),'--no-lazy-fetch',*args],cwd=repo,timeout=60)
def regular(p):
 s=p.lstat();require(stat.S_ISREG(s.st_mode) and not s.st_file_attributes&0x400,'regular file required');return p.read_bytes()
def no_links(p):
 for ancestor in [p,*p.parents]:
  if ancestor.exists():
   s=ancestor.lstat();require(not s.st_file_attributes&0x400,'reparse path refused')
 return p

def configure(home):
 require(not home.exists(),'private home must be fresh')
 for p in [home,home/'appdata',home/'localappdata',home/'xdg',home/'cache',home/'temp']:
  p.mkdir(parents=True,exist_ok=True)
 system={k:os.environ[k] for k in ('SystemRoot','WINDIR','ComSpec','PATHEXT') if k in os.environ}
 require(pathlib.Path(system.get('SystemRoot','')).is_dir(),'Windows system root required')
 e={**system,'HOME':str(home),'USERPROFILE':str(home),'APPDATA':str(home/'appdata'),'LOCALAPPDATA':str(home/'localappdata'),'XDG_CONFIG_HOME':str(home/'xdg'),'XDG_CACHE_HOME':str(home/'cache'),'TEMP':str(home/'temp'),'TMP':str(home/'temp'),
    'PATH':os.pathsep.join(map(str,[NODE.parent,PI/'node_modules/.bin',GIT.parent,NPM_BIN,PY.parent,pathlib.Path(system['SystemRoot'])/'System32'])),
    'PYTHONDONTWRITEBYTECODE':'1','PYTHONIOENCODING':'utf-8','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':os.devnull,'GIT_TERMINAL_PROMPT':'0','PI_TELEMETRY':'0','PI_OFFLINE':'1'}
 os.environ.clear();os.environ.update(e);return e

def lookup_inventory(repo):
 """Fresh successful ASCII Windows sibling inventories, not failed-open absence."""
 facts=[]
 for parent,target in [(repo,'core'),(repo/'core','pysrc'),(repo/'core/pysrc','_host.py')]:
  no_links(parent);names=sorted(p.name for p in parent.iterdir())
  require(all(n.isascii() for n in names),'unsupported nonASCII lookup inventory')
  matches=[n for n in names if n.lower()==target.lower()]
  require(len(matches)<=1,'ambiguous Windows lookup')
  facts.append({'parent':str(parent),'names':names,'target':target,'matches':matches,'enumeration_succeeded':True})
  if target!='_host.py':require(matches==[target],'literal source parent required')
  else:require(not matches,'owned host override present')
 return {'path':'core/pysrc/_host.py','path_style':'windows','physically_absent':True,'inventories':facts}

def snapshot(repo,acquisition):
 bindings=read(HERE/'source-inputs.json');require(bindings['product_M']==M,'source manifest mismatch')
 actual={}
 for p,h in bindings['inputs'].items():
  b=regular(SOURCE/p);require(sha(b)==h,'Temp source differs');require(git(repo,'show',M+':'+p)==b,'Git source differs');require(regular(repo/p)==b,'physical source differs');actual[p]=h
 # Capture successful module membership, including any newly introduced Python leaf.
 for directory in [repo/'core/pysrc',SOURCE/'core/pysrc']:
  observed=[]
  for p in directory.rglob('*.py'):
   no_links(p);observed.append('core/pysrc/'+p.relative_to(directory).as_posix())
  require(sorted(observed)==bindings['core_python_members'],'Python module membership differs')
 sys.path.insert(0,str(SOURCE/'.github/scripts'))
 import major_readiness as owner
 absent={'path':'core/pysrc/_host.py','path_style':'windows'}
 require(not owner._lookup_present(repo,M,absent,{}),'immutable host lookup present')
 runtime_paths=[PY,NODE,GIT,NPM_BIN/'node.exe',NPM_BIN/'npm.cmd',NPM_BIN/'node_modules/npm/bin/npm-cli.js',PI/'package.json',PI/'package-lock.json',PI/'node_modules/.bin/pi.cmd',PI/'node_modules/@earendil-works/pi-coding-agent/package.json']
 manifest=read(PI/'node_modules/@earendil-works/pi-coding-agent/package.json');require(manifest['name']=='@earendil-works/pi-coding-agent' and manifest['version']=='1.5.0','unsupported installed Pi')
 cli=PI/'node_modules/@earendil-works/pi-coding-agent'/manifest['bin']['pi'];runtime_paths.append(cli)
 runtime={str(p):sha(regular(p)) for p in runtime_paths}
 ac=read(acquisition);archive_members={}
 for entry in ac['artifacts']:
  folder=acquisition.parent/entry['directory'];no_links(folder)
  for member in entry['members']:
   p=folder.joinpath(*pathlib.PurePosixPath(member['path']).parts);require(p.is_relative_to(folder),'artifact member outside original scope');no_links(p);b=regular(p);require(sha(b)==member['sha256'],'original acquisition member drift');archive_members[str(p)]=sha(b)
  require(sorted(p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file())==sorted(m['path'] for m in entry['members']),'original artifact membership drift')
  z=acquisition.parent/(entry['directory']+'.zip');require(sha(regular(z))==entry['archive_sha256'],'original archive digest drift');archive_members[str(z)]=entry['archive_sha256']
 return {'product_source_M':M,'actual_HEAD':git(repo,'rev-parse','HEAD').decode().strip(),'index_sha256':sha(git(repo,'diff','--cached','--binary')),'source_inputs':actual,'core_python_members':bindings['core_python_members'],
         'absent_inputs':[absent],'immutable_lookup_absent':True,'physical_lookup_Gov':lookup_inventory(repo),'physical_lookup_Temp_M':lookup_inventory(SOURCE),
         'runtime_files':runtime,'runtime_scope':'Finite installed Node/Python/Git/npm/Pi launcher, CLI bundle/manifests/lock identities, not full OS DLL or all node_modules bytes. Original package/native payload members are separately complete.', 'original_artifact_files':archive_members,'acquisition_sha256':sha(regular(acquisition)),'control_Q_sha256':sha(regular(pathlib.Path(__file__))),'control_Q_source_commit':None,'source_manifest_sha256':sha(regular(HERE/'source-inputs.json'))}

def context(a):
 acq=a.acquisition.resolve(strict=True);require(sha(regular(acq))==a.acquisition_sha256,'selected acquisition digest mismatch');x=read(acq)
 require(x['repository']=='arbiterForge/codeArbiter' and x['run_id']==R and x['event']=='push' and x['actual_checkout_commit']==M and x['event_head_commit']==M,'not original selected integration push')
 require(x['run_status_at_acquisition']=='completed' and x['run_conclusion_at_acquisition']=='success','original integration run not completed successfully')
 require(x['source_tree']==git(a.repo,'rev-parse',M+'^{tree}').decode().strip(),'selected source tree differs')
 require(x['promotion_receipt_sha256']==sha(regular(acq.parent/'stage/artifact-promotion.json')),'promotion identity differs')
 require(x['cohort_sha256']==sha(regular(acq.parent/'packages/artifact-package-cohort.json')),'cohort identity differs')
 require({e['directory'] for e in x['artifacts']}=={'stage','packages'},'original artifact pair missing')
 for e in x['artifacts']:
  prefix='artifact-host-payloads-' if e['directory']=='stage' else 'artifact-release-packages-'
  require(e['metadata']['name']==prefix+M and e['metadata']['workflow_run']['id']==R and e['metadata']['workflow_run']['head_sha']==M,'original artifact source/run mismatch')
 return acq,x

def worker(a):
 out=a.output.resolve(strict=True);configure(out/'worker-home') # Before all project imports.
 acq,x=context(a);before=snapshot(a.repo,acq);write(out/'worker-before.json',before)
 spec=importlib.util.spec_from_file_location('original_pi_M_packager',SOURCE/'tools/build-host-packages.py');pack=importlib.util.module_from_spec(spec);spec.loader.exec_module(pack)
 # All production/source/promotion/admission controls precede Pi extraction or CLI installation.
 cohort=pack.verify_artifact_release_packages(package_root=acq.parent/'packages',source_repo=a.repo,source_commit=M,workflow='.github/workflows/ci.yml',run_id=str(R),promotion_receipt_sha256=x['promotion_receipt_sha256'],stage=acq.parent/'stage',require_production=True,repo=SOURCE)
 require(sha(regular(acq.parent/'packages/artifact-package-cohort.json'))==x['cohort_sha256'],'verified cohort changed')
 write(out/'production-admission.json',{'source_M':M,'run_R':R,'acquisition_sha256':a.acquisition_sha256,'promotion_sha256':x['promotion_receipt_sha256'],'cohort_sha256':x['cohort_sha256'],'require_production':True,'state':'PASSED','before_Pi_extraction_or_install':True})
 entry=cohort['packages']['pi'];archive=acq.parent/'packages'/entry['file'];require(sha(regular(archive))==entry['sha256'],'Pi archive differs');extracted=pack.extract_artifact_release_package(archive,out/'pi-original-extracted',host='pi');package=extracted/'package';require(package.is_dir(),'original package directory missing')
 for name,member in entry['members'].items():require(sha(regular(extracted/name))==member['sha256'],'extracted original Pi member drift')
 pi_members_before={name:sha(regular(extracted/name)) for name in entry['members']};write(out/'pi-extracted-members-before.json',pi_members_before)
 sys.path.insert(0,str(SOURCE/'.github/scripts'));import test_pi_package as owner
 node,cli=owner.live_pi_cli();require(pathlib.Path(node).resolve()==NODE.resolve(),'Node resolution differs');require(cli.resolve().is_relative_to(PI.resolve()),'Pi CLI outside supported isolated install')
 actual_run=owner.run_rpc_commands;routes=[];retained=[];original_temporary=owner.tempfile.TemporaryDirectory
 def retain_fixture(*args,**kwargs):
  require(not args and kwargs=={'prefix':'ca-pi-rpc-'},'unexpected fixture retention call');kwargs.update(dir=out,prefix='pi-rpc-owned-',delete=False);value=original_temporary(**kwargs);retained.append(str(pathlib.Path(value.name).resolve()));return value
 def original_run(cwd,agent_dir,home,**kwargs):
  require('package_source' not in kwargs,'unexpected package source');route='doctor' if kwargs.get('invoke_doctor') else 'alias' if kwargs.get('invoke_alias') else 'bare';started=time.monotonic();records=actual_run(cwd,agent_dir,home,package_source=package,**kwargs)
  write(out/('pi-rpc-'+route+'-records.json'),records);(out/('pi-rpc-'+route+'-settings.json')).write_bytes((agent_dir/'settings.json').read_bytes())
  for rec in records:
   if rec.get('id')=='capture' and rec.get('success'):
    expanded=base64.b64decode(rec['data']['text'].removeprefix('CA_PI_CAPTURE:'),validate=True).decode('utf8');(out/('pi-rpc-'+route+'-capture.txt')).write_text(expanded,encoding='utf8',newline='\n')
    if route=='doctor':
     prefix='<codearbiter-doctor-report>\n';start=expanded.index(prefix)+len(prefix);end=expanded.index('\n</codearbiter-doctor-report>',start);write(out/'pi-original-doctor.json',json.loads(expanded[start:end]))
  routes.append({'route':route,'rpc_returned':True,'seconds':time.monotonic()-started,'records':len(records),'package_source':str(package)});write(out/('pi-route-'+route+'.json'),routes[-1]);return records
 # Only explicit original package source + fixture expectation roots and supported retention change.
 # The original complete method assertions, real CLI/install/extension/provider/RPC/doctor remain unchanged.
 owner.REPO=package;owner.PLUGIN=package/'plugins/ca-pi';owner.TOOLS=owner.PLUGIN/'tools';owner.run_rpc_commands=original_run
 suite=unittest.TestSuite([owner.PiPackageTests('test_real_isolated_rpc_command_discovery_and_keyed_status')]);started=time.monotonic()
 try:
  with mock.patch.object(owner.tempfile,'TemporaryDirectory',retain_fixture):
   with (out/'pi-original-installed-rpc-unittest.log').open('x',encoding='utf8') as stream:result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
  write(out/'pi-original-installed-rpc-summary.json',{'source_M':M,'run_R':R,'original_acquisition_sha256':a.acquisition_sha256,'cohort_sha256':x['cohort_sha256'],'pi_package_sha256':entry['sha256'],'fixture_owner_source_sha256':sha(regular(SOURCE/'.github/scripts/test_pi_package.py')),'test_name':'PiPackageTests.test_real_isolated_rpc_command_discovery_and_keyed_status','test_count':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skips':len(result.skipped),'state':'PASSED' if result.wasSuccessful() else 'FAILED','seconds':time.monotonic()-started,'routes':routes,'retained_fixture_roots':retained,'runtime':{'node':node,'cli':str(cli),'Pi_version':'1.5.0','python':sys.version,'platform':platform.platform()},'limits':['Original local Windows Pi1.5 CLI/native/hook fixture only; no real external provider, visible parent TUI or physical consent claim.','Doctor active-dispatch remains honestly DEGRADED; no wrapper-self-test relabeling.','No installed update/disable/uninstall/rollback, other OS, publication or later-source qualification.','Private deterministic fixture/provider outputs retained; no user credentials/config copied.']})
  require(len(retained)==1,'expected exactly one owning fixture');return 0 if result.wasSuccessful() else 1
 finally:
  pi_members_after={name:sha(regular(extracted/name)) for name in entry['members']};write(out/'pi-extracted-members-after.json',pi_members_after)
  require(pi_members_after==pi_members_before,'original extracted Pi/native payload drift')
  after=snapshot(a.repo,acq);write(out/'worker-after.json',after);write(out/'worker-input-stability.json',{'source_M':M,'stable':before==after,'before_sha256':sha(regular(out/'worker-before.json')),'after_sha256':sha(regular(out/'worker-after.json'))});require(before==after,'worker dependency drift')

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',type=pathlib.Path,required=True);p.add_argument('--acquisition',type=pathlib.Path,required=True);p.add_argument('--acquisition-sha256',required=True);p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--worker',action='store_true');a=p.parse_args();a.repo=a.repo.resolve(strict=True)
 require(os.name=='nt' and platform.machine().lower() in ('amd64','x86_64'),'Windows amd64 scope only')
 if a.worker:return worker(a)
 a.output=a.output.absolute();require(not a.output.exists(),'fresh owning output required');a.output.mkdir();env=configure(a.output/'supervisor-home');acq,x=context(a);before=snapshot(a.repo,acq);write(a.output/'supervisor-before.json',before)
 sys.path.insert(0,str(SOURCE/'.github/scripts'));from _boundedproc import run
 argv=[str(PY),'-I','-B',str(pathlib.Path(__file__)), '--worker','--repo',str(a.repo),'--acquisition',str(acq),'--acquisition-sha256',a.acquisition_sha256,'--output',str(a.output)]
 started=time.monotonic();done=run(argv,timeout=240,cwd=str(HERE),env=env)
 # Persist actual subprocess completion/timeout/containment before any post-run assertion.
 write(a.output/'supervision-result.json',{'source_M':M,'run_R':R,'argv':argv,'cwd':str(HERE),'returncode':done.returncode,'timed_out':done.timed_out,'containment':done.containment,'seconds':time.monotonic()-started,'stdout_utf8_sha256':sha(done.stdout.encode()),'stdout_utf8_bytes':len(done.stdout.encode()),'stderr_utf8_sha256':sha(done.stderr.encode()),'stderr_utf8_bytes':len(done.stderr.encode()),'stdio_scope':'Owning boundedproc UTF8 replacement projection, not original stream-byte claim.','environment_keys':sorted(env),'control_Q_source_commit':None})
 (a.output/'supervised.stdout.log').write_text(done.stdout,encoding='utf8',newline='\n');(a.output/'supervised.stderr.log').write_text(done.stderr,encoding='utf8',newline='\n')
 after=snapshot(a.repo,acq);write(a.output/'supervisor-after.json',after);stable=before==after;write(a.output/'supervisor-input-stability.json',{'stable':stable,'actual_HEAD_before':before['actual_HEAD'],'actual_HEAD_after':after['actual_HEAD'],'index_before':before['index_sha256'],'index_after':after['index_sha256'],'control_Q_source_commit':None})
 require(stable,'supervised dependency drift');require(not done.timed_out and done.containment=='exited' and done.returncode==0,'owning Pi RPC worker failed or containment unknown')
 require(read(a.output/'pi-original-installed-rpc-summary.json')['state']=='PASSED','owning result not passed');print(json.dumps({'state':'PASSED','source_M':M,'run_R':R,'output':str(a.output)}));return 0
if __name__=='__main__':
 try:sys.exit(main())
 except Exception as error:
  # No arbitrary exception property/message/path/argv is printed by this controller.
  print(json.dumps({'state':'FAILED','family':'controller-refusal','exception_text_sha256':sha(str(error).encode('utf8',errors='replace'))}),file=sys.stderr);sys.exit(1)
