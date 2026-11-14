"""Trusted program-push coordinator for one original credential-free CLI run."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace,ModuleType

REPOSITORY='arbiterForge/codeArbiter'
WORKFLOW='.github/workflows/ci.yml'
VERSIONS=('0.143.0','0.145.0')
def require(value,message):
    if not value:raise ValueError(message)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def save(path,value):
    with Path(path).open('x',encoding='utf8') as f:json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def program_mode(env,marker_present):
    return (marker_present is True and env.get('GITHUB_ACTIONS')=='true'
        and env.get('GITHUB_REPOSITORY')==REPOSITORY and env.get('GITHUB_EVENT_NAME')=='push'
        and env.get('GITHUB_REF') in ('refs/heads/main','refs/heads/major/state-contracts'))
def coordinate_sequence(services):
    services.verify()  # Must complete before acquisition or any host action.
    runtime=services.acquire()
    observed=services.produce(runtime)
    return services.report(observed)
def _verified_bootstrap_module(repo,source,relative,name,git):
    """Load only one immutable-byte bootstrap owner, bypassing source pycache."""
    path=repo/relative;expected=git('show',source+':'+relative)
    require(path.is_file() and not path.is_symlink() and path.read_bytes()==expected,'bootstrap physical source differs')
    module=ModuleType(name);module.__file__=str(path);sys.modules[name]=module
    exec(compile(expected,str(path),'exec'),module.__dict__)
    return module
def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--stage',type=Path,required=True)
    parser.add_argument('--package-root',type=Path,required=True)
    parser.add_argument('--codex-version',choices=VERSIONS,required=True)
    parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--output-root',type=Path,required=True)
    a=parser.parse_args(argv);a.repo=a.repo.resolve(strict=True)
    require(program_mode(os.environ,(a.repo/'.github/integration-candidate.json').is_file()),'not a trusted explicit program push')
    require(not a.output_root.exists() and not a.output_root.is_symlink(),'new coordinator output required')
    a.output_root.mkdir();state={'phase':'bootstrap'}
    try:
        source=os.environ['GITHUB_SHA'];git_executable=shutil.which('git')
        require(re.fullmatch(r'(?!0{40}$)[0-9a-f]{40}',source) is not None,'exact workflow source required')
        require(git_executable is not None,'Git unavailable before bootstrap')
        def git(*args,input=None):
            env=dict(os.environ)
            for key in list(env):
                if key.startswith('GIT_'):env.pop(key,None)
            env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull,GIT_TERMINAL_PROMPT='0')
            return subprocess.run([git_executable,'--no-replace-objects','--no-lazy-fetch','-C',str(a.repo),*args],
                   env=env,input=input,capture_output=True,timeout=30,check=True).stdout
        require(git('rev-parse','HEAD').decode().strip()==source,'bootstrap checkout differs from workflow source')
        cold=_verified_bootstrap_module(a.repo,source,'.github/scripts/retained_archive_cli_observation.py',
                                       'codex_existing_control_owner',git)
        with tempfile.TemporaryDirectory(prefix='codex-api-control-') as raw:
            with cold.private_environment(Path(raw)):
                producer=_verified_bootstrap_module(a.repo,source,'.github/scripts/observe_codex_installed_cli.py',
                                                   'codex_verified_producer_owner',git)
                producer.source_binding(a.repo,{'source_commit':source,
                    'source_tree':git('rev-parse','HEAD^{tree}').decode().strip()},git)
                return _run_control(a,cold,producer,Path(raw),state)
    except BaseException as error:
        save(a.output_root/'coordinator-failure.json',{'phase':state['phase'],'exception_type':type(error).__name__,
             'diagnostic_sha256':digest(str(error).encode('utf8',errors='replace'))})
        raise

def _run_control(a,cold,producer,private,state):
    with cold._project_imports(a.repo,private/'bytecode'):
        import major_readiness as readiness
        import major_qualification_report as reports
        import codex_runtime_acquisition as acquisition
        source=os.environ['GITHUB_SHA'];run_id=int(os.environ['GITHUB_RUN_ID'])
        reports.validate_emitter_environment()
        readiness.candidate_marker(readiness.blob(a.repo,source,'.github/integration-candidate.json'))
        req,run,artifacts,jobs=readiness.collect(a.repo,source,run_id,producing=True,
              allow_program_branch=True,producer_scope=True)
        require(str(run.get('run_attempt'))==os.environ['GITHUB_RUN_ATTEMPT']
                and run.get('head_branch')==os.environ['GITHUB_REF'].removeprefix('refs/heads/'),
                'actual workflow attempt/branch differs')
        require(reports.git(a.repo,'rev-parse','HEAD')==source,'actual checkout differs from workflow source')
        name='[CHECK] | [CDX ] | Installed retained package <codex: '+a.codex_version+'>'
        cell='installed:codex:'+a.codex_version
        require(req['cell_jobs'].get(cell)==name,'finite installed Codex owner routing differs')
        current=[j for j in jobs if j.get('name')==name and j.get('status')=='in_progress'
            and str(j.get('run_attempt'))==os.environ['GITHUB_RUN_ATTEMPT']]
        assembly=[j for j in jobs if j.get('name')=='[CHECK] | [CORE] | Structured artifact package assembly'
            and j.get('conclusion')=='success']
        require(len(current)==len(assembly)==1,'actual original Codex/assembly job unavailable or ambiguous')
        expected={k:req[k] for k in ('source_commit','source_tree','ci_run_id')}
        expected['producer_job_id']=current[0]['id']
        authenticated={};roles=[]
        for role,prefix,root,step in (
            ('promoted-stage','artifact-host-payloads-',a.stage,'Preserve the exact multi-host package overlay'),
            ('release-packages','artifact-release-packages-',a.package_root,'Preserve the exact normal release package cohort')):
            artifact_name=prefix+source;matches=[x for x in artifacts if x.get('name')==artifact_name]
            require(len(matches)==1,'original consumed artifact absent/ambiguous')
            readiness.validate_upload(assembly[0],matches[0],step)
            authenticated[artifact_name]=reports.authenticated_payload(matches[0],req,root)
            roles.append({'role':role,'artifact_name':artifact_name})
        save(a.output_root/'coordinator-inputs.json',{'source_commit':source,'source_tree':req['source_tree'],
            'run_id':run_id,'job_id':current[0]['id'],'version':a.codex_version,
            'consumed':{name:{k:v[k] for k in ('artifact_id','archive_sha256','members')} for name,v in authenticated.items()}})
        cohort_raw=(a.package_root/'artifact-package-cohort.json').read_bytes()
        promotion=(a.stage/'artifact-promotion.json').read_bytes();promotion_sha=digest(promotion)
        state['phase']='production-admission'
        def verify():
            result=cold._verify_production(a.repo,a.package_root,a.stage,req,promotion_sha)
            require(result==json.loads(cohort_raw),'production cohort differs from authenticated physical bytes')
            save(a.output_root/'production-admission.json',{'require_production':True,'source_commit':source,
                  'cohort_sha256':digest(cohort_raw),'promotion_sha256':promotion_sha})
        def acquire():
            state['phase']='runtime-acquisition'
            parent=a.output_root/'runtime';parent.mkdir()
            return acquisition.acquire(a.repo,source,a.codex_version,parent)
        def produce(runtime):
            state['phase']='original-installed-cli-execution'
            git=shutil.which('git');require(git is not None,'absolute selected Git unavailable')
            config={'expected':expected,'source_root':a.repo,'workspace':a.workspace,
                'output':a.output_root/'producer','package_root':a.package_root,'stage_root':a.stage,
                'runtime_version':a.codex_version,'git_executable':Path(git).resolve(strict=True),
                'roles':roles,**{k:runtime[k] for k in ('runtime_executable','runtime_policy','trusted_runtime_policy_sha256')}}
            return producer.produce(config,authenticated_payloads=authenticated)
        def report(observed):
            state['phase']='closed-report-admission'
            selections=json.loads(readiness.blob(a.repo,source,'.github/major-test-selections.json'))
            value=reports.build_report(req,job_name=name,job_id=current[0]['id'],selections=selections,
                observations={'codex-live':observed},payloads=authenticated)
            require(value.get('schema')=='codearbiter-major-qualification/3','closed dual-payload v3 report unavailable')
            save(a.output_root/'qualification.json',value);return value
        coordinate_sequence(SimpleNamespace(verify=verify,acquire=acquire,produce=produce,report=report))
        state['phase']='complete'
        save(a.output_root/'coordinator-complete.json',{'phase':'complete','source_commit':source,'run_id':run_id,'job_id':current[0]['id']})
        return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as error:
        print('::error::Codex coordinator refused; diagnostic_sha256='+digest(str(error).encode('utf8',errors='replace')),file=sys.stderr)
        raise SystemExit(1)
