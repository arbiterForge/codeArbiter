"""Execute one credential-free Codex install against authenticated retained bytes.

`produce` is called by the owning CI coordinator with already authenticated
payload objects and an independently selected reviewed runtime policy digest.
It never downloads, builds, selects latest, uses a provider, or retrofits logs.
The private `_produce` dependency seams are for nonexecuting unit controls only.
The report dispatcher/reader and live CI wiring remain separate owners.
"""
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace, ModuleType

MAX_FILE=64*1024*1024
MAX_OUTPUT=16*1024*1024
PYTHON_ROOTS=('core/pysrc','.github/scripts','tools')
DATA_ROOTS=('core/surface',)
PRIVATE_MODULE_PATHS={
    '_release_mechanism':'core/pysrc/_releaselib.py',
    'codex_installed_checker':'.github/scripts/check_codex_host.py',
    'codex_retained_packager':'tools/build-host-packages.py',
    'install_artifact_payload':'tools/install-artifact-payload.py',
    'codearbiter_artifact_release_static_check':'.github/scripts/check_codex_static_package.py',
    'codearbiter_trusted_candidate_resources':'.github/scripts/check_codex_skill_resources.py',
}
def require(value,message):
    if not value:raise ValueError(message)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def ordinary(path):
    path=Path(path)
    # Inspect every component, including junctions and existing parent paths.
    for part in [*reversed(path.absolute().parents),path.absolute()]:
        info=part.lstat()
        require(not part.is_symlink() and not getattr(info,'st_file_attributes',0)&stat.FILE_ATTRIBUTE_REPARSE_POINT,
                'linked/reparse input or ancestor')
    return path
def raw(path,limit=MAX_FILE):
    path=ordinary(path);info=path.stat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and info.st_size<=limit,'bounded ordinary file required')
    data=path.read_bytes();require(len(data)==info.st_size,'file changed while reading');return data
def runtime_digest(path):
    path=ordinary(path);before=path.stat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and before.st_size<=512*1024*1024,'bounded ordinary runtime required')
    value=hashlib.sha256()
    with path.open('rb') as stream:
        while data:=stream.read(65536):value.update(data)
    after=path.stat()
    require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)==
            (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns),'runtime changed while hashing')
    return value.hexdigest()
def unique(pairs):
    result={}
    for key,value in pairs:
        require(key not in result,'duplicate JSON field');result[key]=value
    return result
def load(path):return json.loads(raw(path,MAX_OUTPUT),object_pairs_hook=unique)
def save(path,value):
    data=(json.dumps(value,indent=2,ensure_ascii=True,allow_nan=False)+'\n').encode()
    require(len(data)<=MAX_OUTPUT,'durable record exceeds bound')
    with Path(path).open('xb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
def bytes_file(path,data):
    require(isinstance(data,bytes) and len(data)<=MAX_OUTPUT,'output exceeds bound')
    with Path(path).open('xb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
def inventory(root):
    root=ordinary(root);require(root.is_dir(),'ordinary inventory root required')
    result={};total=0
    for path in sorted(root.rglob('*'),key=lambda p:p.relative_to(root).as_posix()):
        ordinary(path)
        if path.is_dir():continue
        data=raw(path);total+=len(data)
        require(total<=256*1024*1024 and len(result)<4096,'inventory exceeds bound')
        result[path.relative_to(root).as_posix()]={'size':len(data),'sha256':sha(data)}
    return result
def owned_cache(home):
    matches=list(home.glob('plugins/cache/*/ca-codex/*'))
    require(len(matches)==1,'cache root missing/ambiguous')
    root=ordinary(matches[0]);require(root.is_dir(),'cache root is not an ordinary directory')
    return root
def minimal_environment(workspace,git_executable=None):
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','SYSTEMDRIVE','COMSPEC','PATHEXT'}}
    home=workspace/'profile';tmp=workspace/'tmp'
    for p in [home,tmp,home/'appdata',home/'localappdata',home/'config',home/'cache']:p.mkdir(parents=True,exist_ok=True)
    paths=[str(Path(sys.executable).parent)]
    if git_executable:paths.append(str(Path(git_executable).parent))
    env.update(HOME=str(home),USERPROFILE=str(home),APPDATA=str(home/'appdata'),LOCALAPPDATA=str(home/'localappdata'),
       TEMP=str(tmp),TMP=str(tmp),XDG_CONFIG_HOME=str(home/'config'),XDG_CACHE_HOME=str(home/'cache'),
       CODEX_HOME=str(workspace/'codex-home'),PATH=os.pathsep.join(paths),
       PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',
       GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=str(home/'absent-gitconfig'))
    return env
@contextmanager
def process_environment(env):
    before=dict(os.environ)
    try:os.environ.clear();os.environ.update(env);yield
    finally:os.environ.clear();os.environ.update(before)

def source_binding(root,expected,git):
    """Bind code lookup membership and the verifier's physical data consumers.

    All Python sources in the three actual lookup roots are checked, including
    the script shim that precedes core/pysrc on the packager's sys.path. Data
    includes host_descriptors' recursive condition-tag scan. Git archive inputs
    themselves remain the existing verifier's exact-commit reads.
    """
    require(git('rev-parse','HEAD').decode().strip()==expected['source_commit'],'selected source HEAD differs')
    require(git('rev-parse','HEAD^{tree}').decode().strip()==expected['source_tree'],'selected source tree differs')
    listing=git('ls-tree','-r','-z','-l',expected['source_commit'],'--',*PYTHON_ROOTS,*DATA_ROOTS,'core/hosts.json')
    require(len(listing)<=2*1024*1024 and listing.endswith(b'\0'),'source inventory exceeds bound or is malformed')
    selected={};total=0
    for row in listing.split(b'\0')[:-1]:
        header,name=row.split(b'\t',1);name=name.decode('utf8');fields=header.decode('ascii').split()
        require(len(fields)==4,'malformed immutable source entry')
        mode,kind,oid,size=fields
        require(not any(ord(ch)<32 or ord(ch)==127 for ch in name) and '\\' not in name and ':' not in name,
                'unsupported source inventory path')
        data=name=='core/hosts.json' or any(name.startswith(p+'/') for p in DATA_ROOTS)
        python=any(name.startswith(p+'/') for p in PYTHON_ROOTS) and name.endswith('.py')
        if not(data or python):continue
        require(mode in ('100644','100755') and kind=='blob' and size.isdigit()
                and len(oid) in (40,64) and all(ch in '0123456789abcdef' for ch in oid),'unsupported immutable source object')
        total+=int(size);require(total<=64*1024*1024 and len(selected)<8192,'source scope exceeds bound')
        selected[name]=(oid,int(size))
    physical=set()
    for scope in (*PYTHON_ROOTS,*DATA_ROOTS):
        folder=ordinary(root/scope);require(folder.is_dir(),'source lookup/data root is absent')
        for path in folder.rglob('*'):
            if scope in PYTHON_ROOTS and '__pycache__' in path.relative_to(folder).parts:continue
            ordinary(path)
            if path.is_dir():continue
            require(path.suffix.casefold() not in ('.pyc','.pyo','.pyd','.so'),'unbound compiled source lookup candidate')
            if scope in DATA_ROOTS or path.suffix.casefold()=='.py':physical.add(path.relative_to(root).as_posix())
    physical.add('core/hosts.json')
    require(physical==set(selected),'source lookup/data membership differs from immutable Git')
    names=sorted(selected);queries=(''.join(selected[name][0]+'\n' for name in names)).encode('ascii')
    objects=git('cat-file','--batch',input=queries);require(len(objects)<=66*1024*1024,'source object response exceeds bound')
    offset=0;values={};entries={scope:[] for scope in (*PYTHON_ROOTS,*DATA_ROOTS)}
    for name in names:
        end=objects.find(b'\n',offset);require(end>=offset,'incomplete source object header')
        header=objects[offset:end].decode('ascii').split();oid,size=selected[name]
        require(header==[oid,'blob',str(size)],'immutable source object identity differs')
        data=objects[end+1:end+1+size];offset=end+2+size
        require(objects[offset-1:offset]==b'\n' and len(data)==size,'incomplete immutable source object')
        require(raw(root/name)==data,'source physical bytes differ from selected immutable Git: '+name)
        values[name]=sha(data)
        for scope in entries:
            if name.startswith(scope+'/'):entries[scope].append({'path':name[len(scope)+1:],'bytes':size,'sha256':values[name]})
    require(offset==len(objects),'unexpected extra source object bytes')
    return {'positive_inputs':values,'selected_source':expected['source_commit'],'tree':expected['source_tree'],
            'lookup_membership':{scope:{'entries':rows,'sha256':sha(json.dumps(rows,sort_keys=True,separators=(',',':')).encode())}
                                 for scope,rows in entries.items()},
            'git_index_sha256':sha(git('diff','--cached','--binary')),
            'git_status_sha256':sha(git('status','--porcelain=v1','-uall'))}

def prior_owner_modules(root,binding,modules):
    """Permit bound prior owners only; fresh imports never reuse their globals."""
    allowed={}
    for name in binding['positive_inputs']:
        if name.endswith('.py'):allowed.setdefault(Path(name).stem,set()).add(str((root/name).resolve(strict=True)))
    for alias,path in PRIVATE_MODULE_PATHS.items():allowed.setdefault(alias,set()).add(str((root/path).resolve(strict=True)))
    names=set(allowed)
    # A private arbitrary alias with a selected-source file must also be evicted.
    for name,module in modules.items():
        attributes=vars(module) if isinstance(module,ModuleType) else {}
        path=attributes.get('__file__')
        if isinstance(path,str):
            try:
                if Path(path).resolve().is_relative_to(root):names.add(name)
            except OSError:pass
    for name in names.intersection(modules):
        module=modules[name]
        require(isinstance(module,ModuleType),'preloaded owner module has no bound source: '+name)
        path=vars(module).get('__file__')
        require(isinstance(path,str),'preloaded owner module has no bound source: '+name)
        actual=str(Path(path).resolve())
        expected_paths=allowed.get(name,{str(root/p) for p in binding['positive_inputs'] if p.endswith('.py')})
        require(actual in expected_paths,'preloaded owner module points outside selected immutable source: '+name)
    return names

def _produce(config,services):
    """One execution only; services are fixed owners or pure unit seams."""
    c=config;s=services;out=ordinary(c['output']);workspace=ordinary(c['workspace'])
    require(out.is_dir() and not any(out.iterdir()),'new empty output directory required')
    bootstrap={workspace/'profile',workspace/'tmp'} if c.get('_bootstrapped') is True else set()
    require(workspace.is_dir() and set(workspace.iterdir())<=bootstrap,'new empty private workspace required')
    sequence=0;commands=[];native_count=0;cache_before=None;failure=None;observation=None
    created=list(sorted(bootstrap));old_run=s.checker._run
    def event(kind,**values):
        nonlocal sequence
        sequence+=1;save(out/('event-%04d.json'%sequence),{'sequence':sequence,'kind':kind,**values})
    def ensure(path):
        path.mkdir();created.append(path);return path
    def terminal_snapshot():
        result={}
        for key,reader in [('source',s.snapshot_source),('runtime_sha256',lambda:runtime_digest(c['runtime_executable'])),
                           ('payload',lambda:{'packages':inventory(c['package_root']),'stage':inventory(c['stage_root'])})]:
            try:result[key]=reader()
            except BaseException as error:result[key]={'read_failed':type(error).__name__}
        return result
    try:
        expected=c['expected'];version=c['runtime_version']
        require(version in ('0.143.0','0.145.0'),'unsupported Codex version')
        policy_bytes=raw(c['runtime_policy'],MAX_OUTPUT)
        require(sha(policy_bytes)==c['trusted_runtime_policy_sha256'],'independently trusted runtime policy digest differs')
        policy=json.loads(policy_bytes,object_pairs_hook=unique)
        pin=policy.get(version,{})
        s.profile.closed(pin,'platform executable_sha256 provenance integrity','independent runtime policy')
        require(s.profile.digest(pin['executable_sha256']),'independent runtime policy lacks executable pin')
        require(pin.get('platform')==s.platform,'runtime policy platform does not match actual OS/architecture')
        runtime_before=runtime_digest(c['runtime_executable'])
        require(runtime_before==pin.get('executable_sha256'),'runtime executable differs from reviewed acquisition policy')
        source_before=s.snapshot_source()
        payload_before={'packages':inventory(c['package_root']),'stage':inventory(c['stage_root'])}
        save(out/'inputs-before.json',{'source':source_before,'runtime_sha256':runtime_before,'payload':payload_before,
             'runtime_policy_sha256':sha(policy_bytes),'runtime_policy':policy})
        role_bindings=[]
        for role in c['roles']:
            name=role['artifact_name'];authenticated=s.authenticated_payloads.get(name,{})
            root_key={'release-packages':'packages','promoted-stage':'stage'}.get(role['role'])
            require(root_key is not None and authenticated.get('members'),'authenticated payload role absent')
            actual=[{'path':name,'sha256':value['sha256']} for name,value in payload_before[root_key].items()]
            require(actual==authenticated['members'],'authenticated payload bytes/member population differs')
            role_bindings.append({**role,**{k:authenticated[k] for k in ('artifact_id','archive_sha256','members')}})
        require(len(role_bindings)==2 and {r['role'] for r in role_bindings}=={'release-packages','promoted-stage'},'two exact payload roles required')
        cohort_bytes=raw(c['package_root']/'artifact-package-cohort.json',MAX_OUTPUT)
        cohort=json.loads(cohort_bytes,object_pairs_hook=unique)
        promotion_digest=payload_before['stage'].get('artifact-promotion.json',{}).get('sha256')
        require(promotion_digest==cohort.get('promotion_receipt_sha256'),'cohort differs from independently authenticated promotion payload')
        verified=s.verify(package_root=c['package_root'],source_repo=c['source_root'],
            source_commit=expected['source_commit'],workflow='.github/workflows/ci.yml',run_id=str(expected['ci_run_id']),
            promotion_receipt_sha256=promotion_digest,stage=c['stage_root'],require_production=True)
        require(verified==cohort,'owning production verifier result differs from exact cohort')
        save(out/'production-admission.json',{'require_production':True,'cohort_sha256':sha(cohort_bytes),
              'promotion_receipt_sha256':cohort['promotion_receipt_sha256'],'source_commit':expected['source_commit']})
        event('production-admitted-before-effects')
        package=cohort['packages']['codex'];archive=c['package_root']/package['file']
        require(sha(raw(archive))==package['sha256'],'verified package archive drifted')
        extracted=workspace/'package';s.extract(archive,extracted,host='codex');created.append(extracted)
        plugin=extracted/'plugins/ca-codex';expected_inventory=inventory(plugin)
        wanted={k.removeprefix('plugins/ca-codex/'):{'size':v['size'],'sha256':v['sha256']}
                for k,v in package['members'].items() if k.startswith('plugins/ca-codex/')}
        require(expected_inventory==wanted,'extracted package inventory differs')
        metadata=workspace/'qualified-members.json';save(metadata,{'members':{'package/'+k:v for k,v in wanted.items()}});created.append(metadata)
        home=ensure(workspace/'codex-home')
        env=minimal_environment(workspace,c.get('git_executable'))
        for path in [workspace/'profile',workspace/'tmp']:
            if path not in created:created.append(path)
        def command(argv,home_arg=None,*,timeout=300):
            nonlocal cache_before
            number=len(commands)+1;argv=[str(c['runtime_executable']),*argv[1:]]
            event('cli-command-start',ordinal=number,argv=argv,environment_keys=sorted(env))
            save(out/('command-%02d.start.json'%number),{'argv':argv,'cwd':str(workspace),'timeout_seconds':timeout,'environment_keys':sorted(env)})
            result=s.spawn(argv,timeout=timeout,env=env,cwd=str(workspace))
            stdout=result.stdout.encode('utf8');stderr=result.stderr.encode('utf8')
            bytes_file(out/('command-%02d.stdout-utf8-projection.log'%number),stdout)
            bytes_file(out/('command-%02d.stderr-utf8-projection.log'%number),stderr)
            record={'argv':argv,'exit_code':result.returncode,'timed_out':result.timed_out,'containment':result.containment,
                    'stdout_projection_sha256':sha(stdout),'stderr_projection_sha256':sha(stderr)}
            save(out/('command-%02d.exit.json'%number),record);commands.append(record)
            event('cli-command-exit',ordinal=number,**record)
            require(not result.timed_out,'CLI command timed out; containment='+result.containment)
            require(type(result.returncode) is int and result.returncode==0 and result.containment=='exited','CLI command failed or containment unknown')
            if argv[1:]==['plugin','list']:
                cache_before=inventory(owned_cache(home));save(out/'cache-before-checks.json',cache_before)
                require(cache_before==wanted,'cache incomplete/different before installed checks')
            return subprocess.CompletedProcess(argv,result.returncode,result.stdout,result.stderr)
        version_result=command(['codex','--version'])
        require(version_result.stdout.strip()=='codex-cli '+version,'runtime exact version differs')
        def native_exchange(original,argv,request,fd,timeout):
            nonlocal native_count
            native_count+=1;number=native_count
            save(out/('native-command-%02d.start.json'%number),{'argv':argv,'request_sha256':sha(request),'timeout_seconds':timeout,'scope':'original installed bridge verified descriptor exchange'})
            require(len(argv)>1 and argv[1]=='capabilities','unexpected native operation; no context/grant/activation permitted')
            try:code,stdout,stderr=original(argv,request,fd,timeout)
            except BaseException as error:
                save(out/('native-command-%02d.failure.json'%number),{'exception_type':type(error).__name__,'cleanup':'owned by unchanged installed bridge; no stronger containment inference'})
                raise
            bytes_file(out/('native-command-%02d.stdout.raw'%number),stdout)
            bytes_file(out/('native-command-%02d.stderr.raw'%number),stderr)
            save(out/('native-command-%02d.exit.json'%number),{'argv':argv,'exit_code':code,'stdout_sha256':sha(stdout),'stderr_sha256':sha(stderr),'cleanup':'returned by original installed bridge'})
            return code,stdout,stderr
        s.checker._run=command
        event('actual-checker-start',checker='check_codex_host.check_install',once=True)
        with process_environment(env):
            results=s.checker.check_install(home,marketplace_source=extracted,
                expected_plugin_root=plugin,require_artifact_capability=True,qualified_npm_metadata=metadata,
                artifact_exchange_observer=native_exchange,
                capability_observer=lambda value:save(out/'native-capabilities-result.json',value))
        report={'schema':'codearbiter-codex-host-v1','status':'pass' if results and all(r['status']=='pass' for r in results) else 'fail',
                'runtime':version_result.stdout.strip(),'results':results}
        save(out/'checker-result.json',report);event('actual-checker-returned',status=report['status'])
        require(report['status']=='pass','installed native/checker case failed')
        require(native_count==1,'actual installed native capabilities exchange missing/repeated')
        cache_after=inventory(owned_cache(home));save(out/'cache-after-checks.json',cache_after)
        require(cache_before==cache_after==wanted,'cache drift after installed checks')
        source_after=s.snapshot_source();runtime_after=runtime_digest(c['runtime_executable'])
        payload_after={'packages':inventory(c['package_root']),'stage':inventory(c['stage_root'])}
        save(out/'inputs-after.json',{'source':source_after,'runtime_sha256':runtime_after,'payload':payload_after})
        require(source_after==source_before,'selected source drift after checker')
        require(runtime_after==runtime_before,'runtime drift after checker')
        require(payload_after==payload_before,'payload drift after checker')
        native='helpers/artifacts/ca-artifact-'+s.platform.replace('/','-')+('.exe' if s.platform.startswith('windows/') else '')
        runtime={'version':version,'platform':s.platform,'executable':str(c['runtime_executable']),
                 'sha256_before':runtime_before,'sha256_after':runtime_after,'provenance':pin['provenance'],
                 'integrity':pin['integrity'],'version_stdout':version_result.stdout}
        binding={'format':'codearbiter.installed-observation-binding/1','profile':s.profile.PROFILE,**expected,
          'workflow':'.github/workflows/ci.yml','runtime':runtime,'consumed_payloads':role_bindings,
          'package_artifact_id':next(r['artifact_id'] for r in role_bindings if r['role']=='release-packages'),
          'cohort_path':'artifact-package-cohort.json','cohort_sha256':sha(cohort_bytes),
          'package_path':package['file'],'package_sha256':package['sha256'],'marketplace_root':str(extracted),
          'cache_before_checks':cache_before,'cache_after_checks':cache_after,'commands':commands,'checker_report':report,
          'native_platform':s.platform,'native_sha256':wanted[native]['sha256'],
          'manifest_sha256':wanted['helpers/artifacts/release.json']['sha256'],'bridge_sha256':wanted['hooks/_artifactlib.py']['sha256'],
          'scope':s.profile.SCOPE}
        observation={'format':'codearbiter.major-test-observation/1',**{k:expected[k] for k in ('source_commit','source_tree','ci_run_id')},
          'source_stable':True,'proof_kind':'live-host','producer':s.profile.PRODUCER,
          'argv':[sys.executable,*sys.argv],
          'exit_code':0,'tests':[{'id':'codex-cli:'+r['code'],'result':'passed'} for r in results],'installed_binding':binding}
        s.profile.admit(observation,expected=expected,authenticated_payloads=s.authenticated_payloads,
                        cohort_bytes=cohort_bytes,runtime_policy=policy)
    except BaseException as error:
        failure=error;save(out/'failure.json',{'exception_type':type(error).__name__,'reason':str(error)[:2048]})
    finally:
        s.checker._run=old_run
        save(out/'inputs-terminal-before-cleanup.json',terminal_snapshot())
        cleanup=[]
        for path in reversed(created):
            try:
                ordinary(path)
                require(path.resolve(strict=True).is_relative_to(workspace.resolve(strict=True)),'cleanup outside owned workspace')
                if path.is_dir():shutil.rmtree(path)
                else:path.unlink()
                cleanup.append({'path':str(path),'removed':True})
            except BaseException as error:cleanup.append({'path':str(path),'removed':False,'exception_type':type(error).__name__})
        save(out/'cleanup.json',{'owned_created_paths':cleanup,'complete':all(r['removed'] for r in cleanup)})
        terminal=terminal_snapshot();save(out/'inputs-terminal-after-cleanup.json',terminal)
    if failure is not None:raise failure
    try:
        require(all(r['removed'] for r in cleanup),'private workspace cleanup incomplete')
        require(terminal=={'source':source_before,'runtime_sha256':runtime_before,'payload':payload_before},
                'source/runtime/payload drift or unavailable after cleanup')
    except BaseException as error:
        save(out/'failure.json',{'exception_type':type(error).__name__,'reason':str(error)[:2048]});raise
    if c.get('_defer_emit') is not True:save(out/'observation.json',observation)
    return observation

def produce(config,*,authenticated_payloads):
    """Production entry. No injectable checker/spawn/verifier and no log intake.

    authenticated_payloads is supplied in-process by the owning API/archive
    coordinator. runtime_policy's trusted digest is selected independently by
    the reviewed acquisition dispatch, never read from this observation.
    """
    c=dict(config);root=ordinary(c['source_root']).resolve(strict=True)
    workspace=Path(c['workspace']).absolute();output=Path(c['output']).absolute()
    original_temp=Path(tempfile.gettempdir()).resolve(strict=True)
    require(not workspace.is_relative_to(original_temp),'Codex helper home requires a private workspace outside system Temp')
    require(not workspace.is_relative_to(root) and not root.is_relative_to(workspace),'workspace must be separate from selected source')
    require(not output.is_relative_to(workspace),'durable output must survive workspace cleanup')
    for path in [workspace,output]:
        ordinary(path.parent);require(not path.exists() and not path.is_symlink(),'new owned workspace/output required');path.mkdir()
    c.update(source_root=root,workspace=workspace,output=output)
    for key in ['package_root','stage_root','runtime_executable','runtime_policy','git_executable']:
        c[key]=ordinary(c[key]).resolve(strict=True)
    env=minimal_environment(workspace,c['git_executable'])
    # Bootstrap directories exist before repository imports; the core owns their
    # cleanup. They can contain no previous user profile/cache/trust state.
    c['_bootstrapped']=True
    def git(*args,input=None):
        result=subprocess.run([str(c['git_executable']),'--no-replace-objects','--no-lazy-fetch',*args],
                              cwd=root,env=env,capture_output=True,timeout=30,check=True,input=input)
        return result.stdout
    def snapshot():
        return source_binding(root,c['expected'],git)
    def module(name,path):
        spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec)
        sys.modules[name]=m;spec.loader.exec_module(m);return m
    original_path=sys.path[:];old_bytecode=sys.dont_write_bytecode;old_tempdir=tempfile.tempdir
    old_cache_prefix=sys.pycache_prefix;saved_modules=dict(sys.modules);observation=None
    try:
        binding=snapshot();isolated=prior_owner_modules(root,binding,saved_modules)
        with process_environment(env):
            sys.dont_write_bytecode=True;tempfile.tempdir=None
            sys.pycache_prefix=str(workspace/'fresh-bytecode-prefix')
            for name in isolated:sys.modules.pop(name,None)
            sys.path.insert(0,str(root/'.github/scripts'))
            supervisor=module('_boundedproc',root/'.github/scripts/_boundedproc.py')
            checker=module('codex_installed_checker',root/'.github/scripts/check_codex_host.py')
            packager=module('codex_retained_packager',root/'tools/build-host-packages.py')
            profile=module('_codex_cli_profile',root/'.github/scripts/_codex_cli_profile.py')
            system={'Windows':'windows','Linux':'linux','Darwin':'darwin'}.get(platform.system())
            arch={'amd64':'amd64','x86_64':'amd64','arm64':'arm64','aarch64':'arm64'}.get(platform.machine().lower())
            require(system and arch,'unsupported actual producer platform')
            services=SimpleNamespace(checker=checker,verify=packager.verify_artifact_release_packages,
                extract=packager.extract_artifact_release_package,snapshot_source=snapshot,
                spawn=supervisor.run,authenticated_payloads=authenticated_payloads,platform=system+'/'+arch,profile=profile)
            c['_defer_emit']=True
            observation=_produce(c,services)
    except BaseException as error:
        if not (output/'failure.json').exists():
            save(output/'bootstrap-failure.json',{'exception_type':type(error).__name__,'reason':str(error)[:2048]})
            cleanup=[]
            for path in [workspace/'profile',workspace/'tmp']:
                try:
                    if path.exists():
                        ordinary(path)
                        require(path.resolve(strict=True).is_relative_to(workspace.resolve(strict=True)),'bootstrap cleanup escaped workspace')
                        shutil.rmtree(path)
                    cleanup.append({'path':str(path),'removed':True})
                except BaseException as cleanup_error:
                    cleanup.append({'path':str(path),'removed':False,'exception_type':type(cleanup_error).__name__})
            if not (output/'cleanup.json').exists():save(output/'cleanup.json',{'bootstrap_cleanup':cleanup})
        raise
    finally:
        sys.path[:]=original_path;sys.dont_write_bytecode=old_bytecode;tempfile.tempdir=old_tempdir
        sys.pycache_prefix=old_cache_prefix
        for name in set(sys.modules)-set(saved_modules):sys.modules.pop(name,None)
        sys.modules.update(saved_modules)
    save(output/'bootstrap-cleanup.json',{'source_modules_isolated':sorted(isolated),'complete_prior_module_registry_restored':True,
          'source_bytecode_cache':'fresh private prefix; writes disabled; caller prefix restored'})
    save(output/'observation.json',observation)
    return observation

if __name__=='__main__':
    print('Use the reviewed owning coordinator to supply authenticated payload objects and independently trusted runtime acquisition policy; direct/log-only invocation is unavailable.',file=sys.stderr)
    raise SystemExit(2)
