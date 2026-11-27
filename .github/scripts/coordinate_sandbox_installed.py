"""Trusted same-job plain-plugin admission before one installed Sandbox run."""
import argparse
from datetime import datetime,timedelta
import hashlib,json,os,re,shutil,subprocess,sys,tempfile
from pathlib import Path
from types import ModuleType

REPOSITORY='arbiterForge/codeArbiter'
JOB='[CHECK] | [SBX ] | Installed shipped bundle <docker>'
UPLOAD_STEP='Upload exact Sandbox plugin payload'
PREFIX='artifact-sandbox-plugin-'

def require(value,message):
    if not value:raise ValueError(message)

def sha(raw):return hashlib.sha256(raw).hexdigest()

def save(path,value):
    with Path(path).open('x',encoding='utf8') as f:
        json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())

def program_mode(env,marker):
    return (marker is True and env.get('GITHUB_ACTIONS')=='true'
        and env.get('GITHUB_REPOSITORY')==REPOSITORY and env.get('GITHUB_EVENT_NAME')=='push'
        and env.get('GITHUB_REF') in ('refs/heads/main','refs/heads/major/state-contracts'))

def select_job(req,run,jobs,env):
    attempt=env.get('GITHUB_RUN_ATTEMPT','')
    require(re.fullmatch(r'[1-9][0-9]{0,3}',attempt) is not None,'bounded actual attempt required')
    require(type(run.get('run_attempt')) is int and run['run_attempt']==int(attempt)
            and run.get('head_branch')==env['GITHUB_REF'].removeprefix('refs/heads/'),
            'actual Sandbox workflow attempt/branch differs')
    require(req['cell_jobs'].get('installed:sandbox:docker')==JOB,'Sandbox policy job differs')
    found=[j for j in jobs if j.get('name')==JOB and j.get('status')=='in_progress'
           and type(j.get('id')) is int and j['id']>0
           and type(j.get('run_id')) is int and j['run_id']==req['ci_run_id']
           and type(j.get('run_attempt')) is int and j['run_attempt']==int(attempt)]
    require(len(found)==1,'one original current Sandbox job required')
    return found[0]

def validate_early_upload(job,artifact,*,source,attempt,upload_id,upload_digest):
    # Current-job logs are not complete yet. Independently join exact successful
    # step API/time and trusted action outputs with original run/archive API.
    # Final qualification still requires successful job/run/report attribution.
    require(type(upload_id) is int and upload_id>0 and artifact.get('id')==upload_id
            and isinstance(upload_digest,str) and re.fullmatch(r'[a-f0-9]{64}',upload_digest)
            and artifact.get('digest')=='sha256:'+upload_digest
            and artifact.get('name')==PREFIX+source+'-'+str(attempt),
            'same-job Sandbox upload action identity differs')
    steps=[s for s in job.get('steps',[]) if s.get('name')==UPLOAD_STEP]
    require(len(steps)==1 and steps[0].get('status')=='completed'
            and steps[0].get('conclusion')=='success','Sandbox payload upload step did not complete')
    try:
        start=datetime.fromisoformat(steps[0]['started_at'].replace('Z','+00:00'))
        end=datetime.fromisoformat(steps[0]['completed_at'].replace('Z','+00:00'))+timedelta(seconds=1)
        created=datetime.fromisoformat(artifact['created_at'].replace('Z','+00:00'))
        require(start.tzinfo and end.tzinfo and created.tzinfo and start<=created<=end,
                'Sandbox artifact outside original upload window')
    except (KeyError,TypeError,ValueError) as error:
        raise ValueError('Sandbox upload window unavailable or invalid') from error

def _bootstrap(repo,source,relative,name,git):
    path=repo/relative;raw=git('show',source+':'+relative)
    require(path.is_file() and not path.is_symlink() and path.read_bytes()==raw,'bootstrap source differs')
    value=ModuleType(name);value.__file__=str(path);sys.modules[name]=value
    exec(compile(raw,str(path),'exec'),value.__dict__);return value

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation',choices=('stage','observe'))
    p.add_argument('--repo',type=Path,required=True)
    p.add_argument('--payload-root',type=Path,required=True)
    p.add_argument('--output-root',type=Path)
    p.add_argument('--artifact-id',type=int)
    p.add_argument('--artifact-digest')
    a=p.parse_args(argv);a.repo=a.repo.resolve(strict=True)
    require(program_mode(os.environ,(a.repo/'.github/integration-candidate.json').is_file()),'trusted marked normal push required')
    source=os.environ['GITHUB_SHA'];require(re.fullmatch(r'(?!0{40}$)[a-f0-9]{40}',source),'exact workflow source required')
    git_path=shutil.which('git');require(git_path,'Git unavailable before imports')
    def git(*args):
        env={k:v for k,v in os.environ.items() if not k.upper().startswith('GIT_')}
        env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull,GIT_TERMINAL_PROMPT='0')
        return subprocess.run([git_path,'--no-replace-objects','--no-lazy-fetch','-C',str(a.repo),*args],
                              env=env,capture_output=True,timeout=30,check=True).stdout
    require(git('rev-parse','HEAD').decode().strip()==source,'actual checkout differs')
    cold=_bootstrap(a.repo,source,'.github/scripts/retained_archive_cli_observation.py','sandbox_control_owner',git)
    with tempfile.TemporaryDirectory(prefix='sandbox-coordinator-') as raw:
        with cold.private_environment(Path(raw)):
            producer=_bootstrap(a.repo,source,'.github/scripts/observe_sandbox_installed_docker.py','sandbox_verified_owner',git)
            producer.source_snapshot(a.repo,source)
        if a.operation=='stage':
            attempt=int(os.environ['GITHUB_RUN_ATTEMPT'])
            producer.stage_payload(a.repo,source,a.payload_root,run_attempt=attempt)
            return 0
        require(a.output_root is not None and not a.output_root.exists() and not a.output_root.is_symlink(),
                'new durable coordinator output required')
        a.output_root.mkdir();state={'phase':'authentication'}
        try:
            return _run(a,producer,Path(raw),state)
        except BaseException as error:
            save(a.output_root/'coordinator-failure.json',{'phase':state['phase'],
                'diagnostic_sha256':sha(str(error).encode('utf8',errors='replace'))})
            raise

def _run(a,producer,private,state):
    runtime_paths=[]
    for name in ('node','npm','docker','git','nixpacks','gh'):
        path=shutil.which(name)
        if path:runtime_paths.append(str(Path(path).resolve(strict=True).parent))
    runtime_paths.append(str(Path(sys.executable).parent))
    original_env=dict(os.environ)
    with producer.control_environment(private/'api-home',runtime_paths,api_token=True), producer.project_modules(a.repo,private/'bytecode'):
        import major_readiness as readiness
        import major_qualification_report as reports
        source=os.environ['GITHUB_SHA'];run_id=int(os.environ['GITHUB_RUN_ID'])
        reports.validate_emitter_environment()
        readiness.candidate_marker(readiness.blob(a.repo,source,'.github/integration-candidate.json'))
        req,run,artifacts,jobs=readiness.collect(a.repo,source,run_id,producing=True,allow_program_branch=True,producer_scope=True)
        job=select_job(req,run,jobs,os.environ);attempt=job['run_attempt']
        name=PREFIX+source+'-'+str(attempt)
        found=[x for x in artifacts if x.get('name')==name]
        require(len(found)==1,'one original Sandbox plugin upload required')
        validate_early_upload(job,found[0],source=source,attempt=attempt,upload_id=a.artifact_id,upload_digest=a.artifact_digest)
        auth=reports.authenticated_payload(found[0],req,a.payload_root)
        expected={k:req[k] for k in ('source_commit','source_tree','ci_run_id')}
        expected.update(producer_job_id=job['id'],execution_run_attempt=attempt)
        save(a.output_root/'coordinator-inputs.json',{'expected':expected,'artifact':{k:auth[k] for k in ('artifact_id','archive_sha256','members')},'job':{k:job[k] for k in ('id','name','run_id','run_attempt')}})
    # The API token/control import home ends before the original test process.
    state['phase']='original-installed-suite'
    observed=producer.produce({'repo':a.repo,'payload_root':a.payload_root,
        'output_dir':a.output_root/'producer','expected':expected},authenticated_payloads={name:auth})
    state['phase']='closed-report'
    with producer.control_environment(private/'report-home',runtime_paths),producer.project_modules(a.repo,private/'report-bytecode'):
        import major_qualification_report as reports
        import major_readiness as readiness
        receipt=json.loads(producer.raw(Path(original_env['RUNNER_TEMP'])/'nixpacks-acquisition.json',8192),object_pairs_hook=producer.pairs)
        selections=json.loads(readiness.blob(a.repo,source,'.github/major-test-selections.json'))
        report=reports.build_report(req,job_name=JOB,job_id=job['id'],selections=selections,
            observations={'sandbox-live':observed},payloads={name:auth},producer_job=job,
            runtime_acquisitions={'sandbox-live':receipt})
        require(report['schema']=='codearbiter-major-qualification/3','Sandbox one-payload report3 unavailable')
        save(a.output_root/'qualification.json',report)
    state['phase']='complete'
    save(a.output_root/'coordinator-complete.json',{'source_commit':source,'run_id':run_id,'job_id':job['id']})
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as error:
        print('::error::Sandbox coordinator refused; diagnostic_sha256='+sha(str(error).encode('utf8',errors='replace')),file=sys.stderr)
        raise SystemExit(1)
