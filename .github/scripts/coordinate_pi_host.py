"""Authenticate a normal program push before one reviewed Pi install/RPC owner."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from types import ModuleType

REPOSITORY='arbiterForge/codeArbiter'
PLATFORMS=('linux/amd64','windows/amd64','darwin/arm64')

def require(value,message):
    if not value:raise ValueError(message)

def digest(value):return hashlib.sha256(value).hexdigest()

def save(path,value):
    with Path(path).open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=True,indent=2,allow_nan=False);stream.write('\n');stream.flush();os.fsync(stream.fileno())

def program_mode(env,marker_present):
    return (marker_present is True and env.get('GITHUB_ACTIONS')=='true'
        and env.get('GITHUB_REPOSITORY')==REPOSITORY and env.get('GITHUB_EVENT_NAME')=='push'
        and env.get('GITHUB_REF') in ('refs/heads/main','refs/heads/major/state-contracts'))

def coordinate_sequence(verify,produce,read_acquisition,report):
    verify()  # No acquisition/effects until original production admission.
    observed=produce()  # Existing producer exclusively owns install ONCE + RPC ONCE.
    acquisition=read_acquisition()  # Independent original durable same-job file.
    return report(observed,acquisition)

def _verified_bootstrap_module(repo,source,relative,name,git):
    path=repo/relative;literal=git('show',source+':'+relative)
    require(path.is_file() and not path.is_symlink() and path.read_bytes()==literal,'bootstrap physical source differs')
    value=ModuleType(name);value.__file__=str(path);sys.modules[name]=value
    exec(compile(literal,str(path),'exec'),value.__dict__);return value

def _python_lookup_membership(repo,inputs):
    """Refuse unbound packages/compiled lookup entries before control imports."""
    roots=('core/pysrc','.github/scripts','tools');physical=set();seen=0
    expected={p for p in inputs if any(p.startswith(root+'/') for root in roots) and p.endswith('.py')}
    for scope in roots:
        folder=repo/scope
        require(folder.resolve(strict=True)==folder,'aliased Python lookup root')
        pending=[folder]
        while pending:
            parent=pending.pop();info=parent.lstat()
            require(stat.S_ISDIR(info.st_mode) and not getattr(info,'st_file_attributes',0)&0x400,'linked Python lookup directory')
            for path in parent.iterdir():
                seen+=1;require(seen<=8192,'Python lookup membership exceeds bound')
                info=path.lstat()
                require(not stat.S_ISLNK(info.st_mode) and not getattr(info,'st_file_attributes',0)&0x400,'linked Python lookup entry')
                if stat.S_ISDIR(info.st_mode):pending.append(path);continue
                require(stat.S_ISREG(info.st_mode) and info.st_nlink==1,'ordinary Python lookup file required')
                # Existing cold owner always imports under a fresh private pycache
                # prefix. In-tree cache bytes cannot supply those imports.
                if '__pycache__' in path.relative_to(folder).parts:continue
                require(path.suffix.casefold() not in ('.pyc','.pyo','.pyd','.so'),'unbound compiled Python lookup candidate')
                if path.suffix.casefold()=='.py':physical.add(path.relative_to(repo).as_posix())
    require(physical==expected,'Python source lookup membership differs from immutable Git')

def selected_runtime():
    values={name:shutil.which(name) for name in ('node','git')}
    npm=shutil.which('npm.cmd' if os.name=='nt' else 'npm')
    require(all(values.values()) and npm,'selected runtime unavailable before private control environment')
    launcher=Path(npm).absolute();node=Path(values['node']).resolve(strict=True)
    cli=launcher.parent/'node_modules/npm/bin/npm-cli.js' if os.name=='nt' else launcher.resolve(strict=True)
    npm_node=launcher.parent/'node.exe' if os.name=='nt' and (launcher.parent/'node.exe').exists() else node
    return {'python':str(Path(sys.executable).resolve(strict=True)),'node':str(node),
        'git':str(Path(values['git']).resolve(strict=True)),'npm_launcher':str(launcher),
        'npm_cli':str(cli.resolve(strict=True)),'npm_node':str(npm_node.resolve(strict=True))}

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('repo','stage','package-root','workspace','output-root'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--expected-platform',choices=PLATFORMS,required=True)
    a=parser.parse_args(argv);a.repo=a.repo.resolve(strict=True)
    require(program_mode(os.environ,(a.repo/'.github/integration-candidate.json').is_file()),'not a trusted explicit program push')
    require(not a.output_root.exists() and not a.output_root.is_symlink(),'new coordinator output required')
    a.output_root.mkdir();state={'phase':'bootstrap'}
    try:
        source=os.environ['GITHUB_SHA']
        require(re.fullmatch(r'(?!0{40}$)[0-9a-f]{40}',source) is not None,'exact workflow source required')
        runtime=selected_runtime()
        def git(*args):
            # Immutable local reads need no API/provider credentials or user config.
            env={k:os.environ[k] for k in ('SystemRoot','SYSTEMROOT','WINDIR','ComSpec','PATHEXT') if k in os.environ}
            env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull,GIT_TERMINAL_PROMPT='0')
            return subprocess.run([runtime['git'],'--no-replace-objects','--no-lazy-fetch','-C',str(a.repo),*args],
                env=env,capture_output=True,timeout=30,check=True).stdout
        require(git('rev-parse','HEAD').decode().strip()==source,'bootstrap checkout differs from workflow source')
        cold=_verified_bootstrap_module(a.repo,source,'.github/scripts/retained_archive_cli_observation.py','pi_existing_control_owner',git)
        inputs=cold._literal_source_inputs(a.repo,source)
        _python_lookup_membership(a.repo,inputs)
        with tempfile.TemporaryDirectory(prefix='pi-api-control-') as raw:
            with cold.private_environment(Path(raw)):
                producer=_verified_bootstrap_module(a.repo,source,'.github/scripts/observe_pi_installed_rpc.py','pi_verified_producer_owner',git)
                require(producer.actual_platform()==a.expected_platform,'actual Pi platform differs from matrix owner')
                return _run_control(a,cold,producer,Path(raw),state,runtime)
    except BaseException as error:
        save(a.output_root/'coordinator-failure.json',{'phase':state['phase'],
            'diagnostic_sha256':digest(str(error).encode('utf-8',errors='replace'))})
        raise

def _run_control(a,cold,producer,private,state,runtime):
    with cold._project_imports(a.repo,private/'bytecode'):
        import major_readiness as readiness
        import major_qualification_report as reports
        source=os.environ['GITHUB_SHA'];run_id=int(os.environ['GITHUB_RUN_ID'])
        reports.validate_emitter_environment()
        readiness.candidate_marker(readiness.blob(a.repo,source,'.github/integration-candidate.json'))
        req,run,artifacts,jobs=readiness.collect(a.repo,source,run_id,producing=True,allow_program_branch=True,producer_scope=True)
        require(str(run.get('run_attempt'))==os.environ['GITHUB_RUN_ATTEMPT']
            and run.get('head_branch')==os.environ['GITHUB_REF'].removeprefix('refs/heads/'),'actual workflow attempt/branch differs')
        require(reports.git(a.repo,'rev-parse','HEAD')==source,'actual checkout differs from workflow source')
        os_name=a.expected_platform.split('/')[0]
        name='[CHECK] | [PI  ] | Installed retained package <pi: '+os_name+' 1.5.0>'
        require(req['cell_jobs'].get('installed:pi:'+os_name+':1.5.0')==name,'finite installed Pi owner routing differs')
        attempt=os.environ['GITHUB_RUN_ATTEMPT']
        current=[j for j in jobs if j.get('name')==name and j.get('status')=='in_progress' and str(j.get('run_attempt'))==attempt]
        assembly=[j for j in jobs if j.get('name')=='[CHECK] | [CORE] | Structured artifact package assembly'
            and j.get('conclusion')=='success' and str(j.get('run_attempt'))==attempt]
        require(len(current)==len(assembly)==1,'actual original Pi/assembly job unavailable or ambiguous')
        expected={k:req[k] for k in ('source_commit','source_tree','ci_run_id')};expected['producer_job_id']=current[0]['id']
        authenticated={}
        for prefix,root,step in (
            ('artifact-host-payloads-',a.stage,'Preserve the exact multi-host package overlay'),
            ('artifact-release-packages-',a.package_root,'Preserve the exact normal release package cohort')):
            artifact_name=prefix+source;matches=[x for x in artifacts if x.get('name')==artifact_name]
            require(len(matches)==1,'original consumed artifact absent/ambiguous')
            readiness.validate_upload(assembly[0],matches[0],step)
            authenticated[artifact_name]=reports.authenticated_payload(matches[0],req,root)
        cohort_raw=producer.raw(a.package_root/'artifact-package-cohort.json',4<<20)
        promotion_sha=digest(producer.raw(a.stage/'artifact-promotion.json',4<<20))
        save(a.output_root/'coordinator-inputs.json',{'source_commit':source,'source_tree':req['source_tree'],
            'run_id':run_id,'attempt':int(attempt),'job_id':current[0]['id'],'platform':a.expected_platform,
            'consumed':{n:{k:v[k] for k in ('artifact_id','archive_sha256','members')} for n,v in authenticated.items()}})
        def verify():
            state['phase']='production-admission'
            value=cold._verify_production(a.repo,a.package_root,a.stage,req,promotion_sha)
            require(value==json.loads(cohort_raw,object_pairs_hook=producer.pairs),'production cohort differs from authenticated physical bytes')
            save(a.output_root/'production-admission.json',{'require_production':True,'source_commit':source,
                'cohort_sha256':digest(cohort_raw),'promotion_sha256':promotion_sha})
        def produce():
            state['phase']='reviewed-install-and-original-rpc'
            config={'repo':str(a.repo),'workspace':str(a.workspace),'output':str(a.output_root/'producer'),
                'stage':str(a.stage),'packages':str(a.package_root),'expected':expected,**runtime}
            return producer.produce(config,authenticated_payloads=authenticated)
        def read_acquisition():return producer.load(a.output_root/'producer/runtime-acquisition.json')
        def report(observed,acquisition):
            state['phase']='closed-report-admission'
            selections=json.loads(readiness.blob(a.repo,source,'.github/major-test-selections.json'))
            result=reports.build_report(req,job_name=name,job_id=current[0]['id'],selections=selections,
                observations={'pi-live':observed},payloads=authenticated,runtime_acquisitions={'pi-live':acquisition})
            require(result.get('schema')=='codearbiter-major-qualification/3','closed dual-payload v3 report unavailable')
            save(a.output_root/'qualification.json',result);return result
        coordinate_sequence(verify,produce,read_acquisition,report)
        state['phase']='complete'
        save(a.output_root/'coordinator-complete.json',{'phase':'complete','source_commit':source,'run_id':run_id,'job_id':current[0]['id']})
        return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as error:
        print('::error::Pi coordinator refused; diagnostic_sha256='+digest(str(error).encode('utf-8',errors='replace')),file=sys.stderr)
        raise SystemExit(1)
