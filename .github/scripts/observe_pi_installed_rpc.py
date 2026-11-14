"""One reviewed Pi install and one original retained-package RPC owner test.

Called by the owning authenticated CI coordinator, never a log/receipt importer.
No upstream TUI, physical consent, external provider, or authorship qualification.
"""
from contextlib import contextmanager
import argparse
import base64
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
VERSION="1.5.0"
WORKFLOW=".github/workflows/ci.yml"
MAX_JSON=16*1024*1024
LOCK_NAMES=('package.json','package-lock.json','.npmrc','review.json')

def require(value,message):
    if not value:raise ValueError(message)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def ordinary(path):
    path=Path(path).absolute()
    for part in [*reversed(path.parents),path]:
        info=part.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info,'st_file_attributes',0)&0x400,'linked/reparse observer path')
    require(path.resolve(strict=True)==path,'aliased observer path')
    return path
def raw(path,limit=MAX_JSON):
    path=ordinary(path);before=path.stat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size<=limit,'bounded regular observer file required')
    data=path.read_bytes()
    require(len(data)==before.st_size,'observer input changed during read')
    return data
def file_digest(path):
    path=ordinary(path);before=path.stat()
    require(stat.S_ISREG(before.st_mode) and before.st_size<=512*1024*1024,'bounded runtime file required')
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(65536),b''):value.update(block)
    after=path.stat()
    require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns),'runtime changed while hashing')
    return value.hexdigest()
def save(path,value):
    data=(json.dumps(value,ensure_ascii=True,indent=2,allow_nan=False)+'\n').encode()
    require(len(data)<=MAX_JSON,'Pi observer JSON exceeds bound')
    with Path(path).open('xb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
def pairs(items):
    result={}
    for key,value in items:
        require(key not in result,'duplicate Pi observer JSON key');result[key]=value
    return result
def load(path):return json.loads(raw(path),object_pairs_hook=pairs)
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    require(spec is not None and spec.loader is not None,'Pi observer source unavailable')
    value=importlib.util.module_from_spec(spec);sys.modules[name]=value;spec.loader.exec_module(value);return value
def actual_platform():
    system={'Windows':'windows','Linux':'linux','Darwin':'darwin'}.get(platform.system())
    arch={'amd64':'amd64','x86_64':'amd64','arm64':'arm64','aarch64':'arm64'}.get(platform.machine().lower())
    require(system and arch,'unsupported actual Pi platform')
    return system+'/'+arch

def runtime_snapshot(config):
    launcher=Path(config['npm_launcher']).absolute()
    selected=shutil.which('npm.cmd' if os.name=='nt' else 'npm')
    require(selected is not None and Path(selected).resolve(strict=True)==launcher.resolve(strict=True),'actual npm selection differs')
    expected_cli=(launcher.parent/'node_modules/npm/bin/npm-cli.js') if os.name=='nt' else launcher.resolve(strict=True)
    expected_node=(launcher.parent/'node.exe') if os.name=='nt' and (launcher.parent/'node.exe').exists() else Path(config['node'])
    require(Path(config['npm_cli']).resolve(strict=True)==expected_cli.resolve(strict=True)
            and Path(config['npm_node']).resolve(strict=True)==expected_node.resolve(strict=True),'actual npm CLI/adjacent Node differs')
    values={}
    for name in ('python','node','git','npm_launcher','npm_cli','npm_node'):
        path=Path(config[name]).absolute()
        # npm itself is commonly a symlink on POSIX. Its resolved regular CLI
        # and the adjacent Node actually selected by that launcher are explicit.
        if name=='npm_launcher' and path.is_symlink():
            require(path.parent.resolve(strict=True)==path.parent,'aliased npm launcher parent')
            path=path.resolve(strict=True)
        path=ordinary(path)
        values[name]={'path':str(path),'sha256':file_digest(path)}
    return values

def source_snapshot(cold,config):
    value=cold._source_snapshot(Path(config['repo']))
    for name in LOCK_NAMES:
        relative='.github/fixtures/pi-hosts/'+VERSION+'/'+name
        literal=subprocess.run([config['git'],'--no-replace-objects','--no-lazy-fetch','-C',config['repo'],'show',config['expected']['source_commit']+':'+relative],capture_output=True,check=True,timeout=30).stdout
        require(raw(Path(config['repo'])/relative)==literal,'reviewed Pi lock differs from immutable source')
        value['inputs'][relative]=sha(literal)
    return value

def graph_snapshot(prefix):
    """Full executable host graph; only declared, contained npm bin links."""
    prefix=ordinary(prefix)
    require(prefix.is_dir(),'reviewed Pi prefix absent')
    paths=[];queue=[prefix];count=0
    while queue:
        parent=queue.pop()
        for path in sorted(parent.iterdir()):
            if path==prefix/'.npm-cache':
                ordinary(path);require(path.is_dir(),'invalid nonexecutable npm cache');continue
            count+=1;require(count<=32768,'Pi graph entry bound exceeded')
            info=path.lstat()
            if stat.S_ISLNK(info.st_mode):
                paths.append(path);continue
            require(not getattr(info,'st_file_attributes',0)&0x400,'Pi graph reparse point refused')
            if stat.S_ISDIR(info.st_mode):queue.append(path)
            else:
                require(stat.S_ISREG(info.st_mode),'unsupported Pi graph member');paths.append(path)
    allowed={}
    for path in paths:
        if path.name!='package.json' or path.is_symlink() or 'node_modules' not in path.relative_to(prefix).parts:continue
        value=load(path);bins=value.get('bin',{})
        if isinstance(bins,str):bins={value.get('name','').split('/')[-1]:bins}
        require(isinstance(bins,dict),'unsupported installed bin declaration')
        package=path.parent;parent=package.parent
        if parent.name.startswith('@'):parent=parent.parent
        if parent.name!='node_modules':continue
        for name,target in bins.items():
            require(isinstance(name,str) and name and '/' not in name and '\\' not in name and ':' not in name and isinstance(target,str),'invalid installed bin declaration')
            destination=(package/target).resolve(strict=True)
            require(destination.is_relative_to(prefix) and destination.is_file(),'bin target escapes runtime graph')
            key=parent/'.bin'/name
            require(key not in allowed or allowed[key]==destination,'ambiguous installed bin target')
            allowed[key]=destination
    entries={};total=0
    for path in sorted(paths):
        name=path.relative_to(prefix).as_posix()
        if path.is_symlink():
            target=path.resolve(strict=True)
            require(path in allowed and allowed[path]==target and target.is_relative_to(prefix) and target.is_file(),'undeclared/escaping/directory npm link')
            literal=os.readlink(path)
            require(not Path(literal).is_absolute() and len(literal)<=4096,'unbounded/absolute npm link')
            entries[name]={'kind':'bin-link','target':literal,'resolved':target.relative_to(prefix).as_posix(),'sha256':file_digest(target)}
        else:
            info=path.stat();total+=info.st_size
            require(info.st_size<=256*1024*1024 and total<=1024*1024*1024,'Pi graph byte bound exceeded')
            entries[name]={'kind':'file','bytes':info.st_size,'sha256':file_digest(path)}
    require(entries,'empty Pi host graph')
    return {'entries':entries,'sha256':sha(json.dumps(entries,sort_keys=True,separators=(',',':')).encode())}

def environment(home,config,pi_prefix=None):
    for part in [home,home/'appdata',home/'localappdata',home/'xdg',home/'cache',home/'tmp']:part.mkdir(parents=True,exist_ok=True)
    result={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','SYSTEMDRIVE','COMSPEC','PATHEXT'}}
    paths=[Path(config['node']).parent,Path(config['git']).parent,Path(config['npm_launcher']).parent,Path(config['python']).parent]
    if pi_prefix is not None:paths.insert(1,Path(pi_prefix)/'node_modules/.bin')
    if result.get('SystemRoot'):paths.append(Path(result['SystemRoot'])/'System32')
    result.update(HOME=str(home),USERPROFILE=str(home),APPDATA=str(home/'appdata'),LOCALAPPDATA=str(home/'localappdata'),XDG_CONFIG_HOME=str(home/'xdg'),XDG_CACHE_HOME=str(home/'cache'),TEMP=str(home/'tmp'),TMP=str(home/'tmp'),
        PATH=os.pathsep.join(dict.fromkeys(map(str,paths))),PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8',GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull,GIT_TERMINAL_PROMPT='0',PI_OFFLINE='1',PI_TELEMETRY='0')
    return result
@contextmanager
def process_environment(value):
    original=dict(os.environ)
    try:os.environ.clear();os.environ.update(value);yield
    finally:os.environ.clear();os.environ.update(original)

@contextmanager
def owners(repo,expected,git_executable,home):
    """Reuse the committed cold import owner after its own literal Git join."""
    repo=ordinary(repo).resolve(strict=True)
    require(Path(__file__).resolve()==repo/'.github/scripts/observe_pi_installed_rpc.py','Pi observer source checkout differs')
    path=repo/'.github/scripts/retained_archive_cli_observation.py'
    literal=subprocess.run([str(git_executable),'--no-replace-objects','--no-lazy-fetch','-C',str(repo),'show',expected['source_commit']+':.github/scripts/retained_archive_cli_observation.py'],capture_output=True,check=True,timeout=30).stdout
    require(raw(path)==literal,'cold import owner differs from immutable source')
    prior=dict(sys.modules);old_prefix=sys.pycache_prefix;old_write=sys.dont_write_bytecode
    try:
        sys.pycache_prefix=str(home/'bootstrap-bytecode');sys.dont_write_bytecode=True
        cold=module('pi_cold_source_owner',path)
        with cold._project_imports(repo,home/'project-bytecode'):
            snapshot=cold._source_snapshot(repo)
            require(snapshot['source_commit']==expected['source_commit'] and snapshot['source_tree']==expected['source_tree'],'Pi selected source differs')
            yield cold
    finally:
        sys.pycache_prefix,sys.dont_write_bytecode=old_prefix,old_write
        for name in set(sys.modules)-set(prior):sys.modules.pop(name,None)
        sys.modules.update(prior)

def completion(result,argv):
    return {'argv':list(map(str,argv)),'returncode':result.returncode,'timed_out':result.timed_out,'containment':result.containment}
def successful(value):return type(value.get('returncode')) is int and value['returncode']==0 and value.get('timed_out') is False and value.get('containment')=='exited'

def acquire_runtime(config,cold,output,spawn):
    prefix=Path(config['workspace'])/'pi-host';parent=ordinary(prefix.parent)
    names=[p.name for p in parent.iterdir()]
    require(prefix.name not in names and not prefix.is_symlink(),'Pi host prefix is not fresh')
    locks=Path(config['repo'])/'.github/fixtures/pi-hosts'/VERSION
    source_locks={name:sha(raw(locks/name)) for name in LOCK_NAMES}
    before=runtime_snapshot(config)
    argv=[config['python'],'-I','-B',str(Path(config['repo'])/'.github/scripts/pi_host_locks.py'),'install','--version',VERSION,'--prefix',str(prefix)]
    result=spawn(argv,timeout=240,cwd=str(config['repo']),env=environment(Path(config['workspace'])/'install-home',config))
    done=completion(result,argv)
    save(output/'install-exit.json',{**done,'stdout_sha256':sha(result.stdout.encode()),'stderr_sha256':sha(result.stderr.encode())})
    require(successful(done),'reviewed Pi installer failed/timed out/unknown')
    require(all(raw(prefix/name)==raw(locks/name) for name in ['package.json','package-lock.json','.npmrc']),'installed reviewed Pi lock/config differs')
    host=load(prefix/'node_modules/@earendil-works/pi-coding-agent/package.json')
    require(host.get('name')=='@earendil-works/pi-coding-agent' and host.get('version')==VERSION,'installed Pi version differs')
    after=runtime_snapshot(config);require(before==after,'Pi acquisition runtime drift')
    result={'format':'codearbiter.pi-reviewed-acquisition/1',**config['expected'],'version':VERSION,'prefix':str(prefix),'fresh_prefix':{'enumeration_succeeded':True,'present':False},'source_locks':source_locks,'command':done,'runtime_before':before,'runtime_after':after,'graph_after':graph_snapshot(prefix)}
    save(output/'runtime-acquisition.json',result)
    return result

def installed_members(cold,extracted,expected):
    actual=cold.physical_members(extracted)['members']
    require(actual=={p:v['sha256'] for p,v in expected.items()},'complete original installed Pi membership changed')
    require(all((Path(extracted)/p).stat().st_size==v['size'] for p,v in expected.items()),'installed Pi member sizes changed')
    return copy.deepcopy(expected)

def run_owner(config,cold,output):
    """Actual unchanged test; only original package and retention seams."""
    repo=Path(config['repo']);stage=Path(config['stage']);packages=Path(config['packages']);expected=config['expected'];acq=config['acquisition']
    cold._verify_production(repo,packages,stage,expected,config['promotion_sha256'])
    packager=cold._load_packager(repo);cohort=load(packages/'artifact-package-cohort.json');entry=cohort['packages']['pi']
    extracted=packager.extract_artifact_release_package(packages/entry['file'],Path(config['workspace'])/'installed-pi',host='pi');package=extracted/'package'
    before=installed_members(cold,extracted,entry['members'])
    runtime=runtime_snapshot(config);graph=graph_snapshot(Path(acq['prefix']));source=source_snapshot(cold,config)
    payload={role:cold.physical_members(path)['members'] for role,path in [('promoted-stage',stage),('release-packages',packages)]}
    owner=module('test_pi_package',repo/'.github/scripts/test_pi_package.py')
    node,cli=owner.live_pi_cli()
    require(Path(node).resolve()==Path(config['node']).resolve() and cli.resolve().is_relative_to(Path(acq['prefix']).resolve()),'Pi resolved runtime outside reviewed acquisition')
    original=owner.run_rpc_commands;original_temp=owner.tempfile.TemporaryDirectory;routes=[];retained=[];doctor=None
    def retain(*args,**kwargs):
        require(not args and kwargs=={'prefix':'ca-pi-rpc-'},'unexpected owning fixture retention')
        value=original_temp(dir=config['workspace'],prefix='pi-rpc-owned-',delete=False);retained.append(Path(value.name));return value
    def route(cwd,agent_dir,home,**kwargs):
        nonlocal doctor
        require(set(kwargs)<= {'invoke_alias','invoke_doctor'} and 'package_source' not in kwargs,'unexpected substituted RPC route')
        name='doctor' if kwargs.get('invoke_doctor') else 'alias' if kwargs.get('invoke_alias') else 'bare'
        records=original(cwd,agent_dir,home,package_source=package,**kwargs)
        value={'name':name,'records':records,'settings':load(agent_dir/'settings.json')};save(output/('route-'+name+'.json'),value);routes.append(value)
        if name=='doctor':
            captures=[r for r in records if r.get('id')=='capture' and r.get('success') is True]
            require(len(captures)==1,'doctor capture missing')
            text=base64.b64decode(captures[0]['data']['text'].removeprefix('CA_PI_CAPTURE:'),validate=True).decode('utf8')
            marker='<codearbiter-doctor-report>\n';start=text.index(marker)+len(marker);end=text.index('\n</codearbiter-doctor-report>',start);doctor=json.loads(text[start:end],object_pairs_hook=pairs)
        return records
    owner.REPO=package;owner.PLUGIN=package/'plugins/ca-pi';owner.TOOLS=owner.PLUGIN/'tools';owner.run_rpc_commands=route
    case=owner.PiPackageTests('test_real_isolated_rpc_command_discovery_and_keyed_status');test_id='python:.github/scripts/test_pi_package.py:'+case.id()
    result=unittest.TestResult()
    with mock.patch.object(owner.tempfile,'TemporaryDirectory',retain):case.run(result)
    test={'id':test_id,'run_count':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skips':len(result.skipped),'result':'passed' if result.wasSuccessful() and not result.skipped else 'failed'}
    save(output/'original-test-result.json',{**test,'failure_sha256':[sha(text.encode()) for _,text in result.failures+result.errors]})
    require(test['result']=='passed' and result.testsRun==1 and len(retained)==1,'original installed Pi RPC owner failed/skipped/missing')
    value={'format':'codearbiter.pi-installed-rpc-result/1','test':test,'routes':routes,'doctor':doctor,'source_before':source,'source_after':source_snapshot(cold,config),'runtime_before':runtime,'runtime_after':runtime_snapshot(config),'graph_before':graph,'graph_after':graph_snapshot(Path(acq['prefix'])),'payload_before':payload,'payload_after':{role:cold.physical_members(path)['members'] for role,path in [('promoted-stage',stage),('release-packages',packages)]},'installed_before':before,'installed_after':installed_members(cold,extracted,entry['members'])}
    save(output/'worker-result.json',value)
    return value

def worker(config):
    home=Path(config['workspace'])/'worker-home'
    with process_environment(environment(home,config,config['acquisition']['prefix'])):
        with owners(Path(config['repo']),config['expected'],config['git'],home) as cold:
            return run_owner(config,cold,Path(config['output']))

def _produce(config,cold,spawn):
    """Effect seams used only by inert unit controls, never public arguments."""
    output=Path(config['output']);workspace=Path(config['workspace']);repo=Path(config['repo']);expected=config['expected']
    payloads=config['authenticated_payloads'];binding=None;failure=None;cleanup={'complete':False}
    try:
        source=source_snapshot(cold,config)
        require(source['source_commit']==expected['source_commit'] and source['source_tree']==expected['source_tree'],'Pi source before admission differs')
        physical={r:cold.physical_members(p)['members'] for r,p in [('promoted-stage',config['stage']),('release-packages',config['packages'])]}
        consumed={}
        for role,prefix in [('promoted-stage','artifact-host-payloads-'),('release-packages','artifact-release-packages-')]:
            name=prefix+expected['source_commit'];value=cold.payload_projection(payloads.get(name))
            require(cold.members(value['members'])==physical[role],'Pi physical consumed payload differs')
            consumed[role]={'artifact_name':name,**value}
        cohort_raw=raw(Path(config['packages'])/'artifact-package-cohort.json');cohort=json.loads(cohort_raw,object_pairs_hook=pairs)
        promotion=sha(raw(Path(config['stage'])/'artifact-promotion.json'))
        cold._verify_production(repo,Path(config['packages']),Path(config['stage']),expected,promotion)
        save(output/'production-admission.json',{'source_commit':expected['source_commit'],'ci_run_id':expected['ci_run_id'],'promotion_sha256':promotion,'cohort_sha256':sha(cohort_raw),'require_production':True})
        acq=acquire_runtime(config,cold,output,spawn)
        worker_config={k:v for k,v in config.items() if k!='authenticated_payloads'};worker_config.update(acquisition=acq,promotion_sha256=promotion)
        path=workspace/'worker-config.json';save(path,worker_config)
        argv=[config['python'],'-I','-B',str(repo/'.github/scripts/observe_pi_installed_rpc.py'),'--worker',str(path)]
        done=spawn(argv,timeout=240,cwd=str(repo),env=environment(workspace/'supervisor-home',config,acq['prefix']))
        supervision=completion(done,argv)
        save(output/'worker-exit.json',{**supervision,'stdout_sha256':sha(done.stdout.encode()),'stderr_sha256':sha(done.stderr.encode())})
        require(successful(supervision),'Pi worker failed/timed out/unconfirmed')
        observed=load(output/'worker-result.json')
        require(source_snapshot(cold,config)==source,'Pi source changed after worker')
        binding={'format':'codearbiter.installed-observation-binding/1','profile':'pi-installed-rpc-v1',**expected,'workflow':WORKFLOW,'platform':actual_platform(),'runtime_version':VERSION,'consumed_payloads':consumed,'cohort_json':cohort_raw.decode('utf8'),'acquisition':acq,'worker':observed,'supervision':supervision,'cleanup':{'complete':True}}
    except Exception as error:
        failure=error
        save(output/'failure.json',{'family':'pi-installed-rpc-refusal','diagnostic_sha256':sha(str(error).encode('utf8',errors='replace'))})
    finally:
        try:
            ordinary(workspace);shutil.rmtree(workspace);cleanup={'complete':not workspace.exists()}
        except Exception as error:cleanup={'complete':False,'diagnostic_sha256':sha(str(error).encode('utf8',errors='replace'))}
        save(output/'cleanup.json',cleanup)
    if failure is not None:raise failure
    require(cleanup=={'complete':True} and binding is not None,'Pi cleanup unknown')
    profile=module('_pi_rpc_profile',repo/'.github/scripts/_pi_rpc_profile.py')
    observation={'format':'codearbiter.major-test-observation/1',**{k:expected[k] for k in ['source_commit','source_tree','ci_run_id']},'source_stable':True,'proof_kind':'live-host','producer':profile.PRODUCER,'argv':binding['supervision']['argv'],'exit_code':0,'tests':[{'id':binding['worker']['test']['id'],'result':'passed'}],'installed_binding':binding}
    req={k:expected[k] for k in ['source_commit','source_tree','ci_run_id']}
    profile.admit(observation,req=req,job_id=expected['producer_job_id'],authenticated_payloads=payloads,runtime_acquisition=binding['acquisition'])
    return observation

def produce(config,*,authenticated_payloads):
    """Public same-job coordinator entry; no supplied checker/spawn/receipt flag."""
    config={k:str(v) if isinstance(v,Path) else v for k,v in config.items()}
    repo=ordinary(config['repo']).resolve(strict=True);workspace=Path(config['workspace']).absolute();output=Path(config['output']).absolute()
    require(not workspace.is_relative_to(repo) and not repo.is_relative_to(workspace) and not output.is_relative_to(workspace),'Pi owned paths overlap source/retention')
    for path in [workspace,output]:
        ordinary(path.parent);require(not path.exists() and not path.is_symlink(),'new Pi owned path required');path.mkdir()
    config.update(repo=str(repo),workspace=str(workspace),output=str(output),authenticated_payloads=authenticated_payloads)
    try:
        home=workspace/'control-home'
        with process_environment(environment(home,config)):
            with owners(repo,config['expected'],config['git'],home) as cold:
                from _boundedproc import run
                observation=_produce(config,cold,run)
        save(output/'observation.json',observation)
        return observation
    except Exception as error:
        if not (output/'failure.json').exists():save(output/'bootstrap-failure.json',{'family':'pi-observer-bootstrap','diagnostic_sha256':sha(str(error).encode('utf8',errors='replace'))})
        if workspace.exists():
            try:ordinary(workspace);shutil.rmtree(workspace)
            except OSError:pass  # original failure stays primary; no success record exists
        raise

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--worker',type=Path,required=True);args=parser.parse_args()
    try:worker(load(args.worker))
    except Exception as error:
        print(json.dumps({'state':'FAILED','family':'pi-observer-worker','diagnostic_sha256':sha(str(error).encode('utf8',errors='replace'))}),file=sys.stderr);raise SystemExit(1)
