"""Pure join validator for one closed Codex installed-cache admission profile.

This module neither authenticates artifacts nor runs/emits observations. Its
caller must supply authenticated_payload() results and reviewed runtime policy,
not deserialize a caller-authored `authenticated: true` flag. The execution
producer captures the actual original commands and cache snapshots. Passing
synthetic unit controls here is not any installed-cell qualification.
"""
import hashlib
import json
from pathlib import PurePosixPath, PureWindowsPath
import re

PROFILE = 'codex-cli-installed-cache-v1'
PRODUCER = 'codex-cli-installed-cache-observer-v1'
SCOPE = 'credential-free-cli-install-readback;no-turn-hooks-provider-or-consent'
CASES = tuple('CODEX-HOST-' + suffix for suffix in (
    'MARKETPLACE','INSTALL','LIST','ENABLED','VERSION','RESOLVED-VERSION',
    'HOOKS-INSTALLED','HOOKS-MATCH','HOOK-SCRIPTS','AGENT-ROUTES',
    'PACKAGE-MEMBERS','ARTIFACT-CAPABILITY'))
DIGEST = re.compile(r'[0-9a-f]{64}')
SHA = re.compile(r'[0-9a-f]{40}')

def require(value, message):
    if not value: raise ValueError(message)
def sha(raw): return hashlib.sha256(raw).hexdigest()
def unique(pairs):
    value={}
    for k,v in pairs:
        require(k not in value,'duplicate cohort field');value[k]=v
    return value
def digest(value): return isinstance(value,str) and DIGEST.fullmatch(value) is not None
def closed(value, fields, label):
    require(isinstance(value,dict) and set(value)==set(fields.split()), 'closed '+label+' fields differ')
def positive(value): return type(value) is int and value>0
def relative(path):
    require(isinstance(path,str) and path and len(path.encode('utf8'))<=4096
            and str(PurePosixPath(path))==path and not PurePosixPath(path).is_absolute()
            and '..' not in PurePosixPath(path).parts and ':' not in path and '\\' not in path
            and not any(ord(c)<32 or ord(c)==127 for c in path),'unsafe member path')
    return path
def absolute(path):
    require(isinstance(path,str) and len(path.encode('utf8'))<=4096
            and (PureWindowsPath(path).is_absolute() or PurePosixPath(path).is_absolute())
            and '..' not in PurePosixPath(path.replace('\\','/')).parts
            and not any(ord(c)<32 or ord(c)==127 for c in path),'absolute owned path required')
def member_map(members):
    require(isinstance(members,list) and 0<len(members)<=4096,'bounded authenticated members required')
    value={}
    for item in members:
        require(isinstance(item,dict) and set(item)=={'path','sha256'} and digest(item['sha256']),
                'authenticated member shape differs')
        path=relative(item['path']);require(path not in value,'duplicate member path')
        value[path]=item['sha256']
    return value

def admit(observation, *, expected, authenticated_payloads, cohort_bytes, runtime_policy):
    """Return only a validated finite selection, never an emitted major report."""
    closed(expected,'source_commit source_tree ci_run_id producer_job_id','expected identity')
    require(all(isinstance(expected[k],str) and SHA.fullmatch(expected[k]) for k in ('source_commit','source_tree'))
            and positive(expected['ci_run_id']) and positive(expected['producer_job_id']),'invalid expected identity')
    closed(observation,'format source_commit source_tree ci_run_id source_stable proof_kind producer argv exit_code tests installed_binding','observation')
    require(observation['producer']==PRODUCER and observation['proof_kind']=='live-host','wrong producer or proof kind')
    require(observation['format']=='codearbiter.major-test-observation/1'
            and observation['source_stable'] is True and type(observation['exit_code']) is int
            and observation['exit_code']==0,'failed or unstable original observation')
    for key in ('source_commit','source_tree','ci_run_id'):
        require(observation[key]==expected[key] and type(observation[key]) is type(expected[key]),'outer source/run differs')
    require(isinstance(observation['argv'],list) and observation['argv']
            and all(isinstance(x,str) and x for x in observation['argv']),'original observer argv missing')
    b=observation['installed_binding']
    closed(b,'format profile source_commit source_tree ci_run_id producer_job_id workflow runtime consumed_payloads package_artifact_id cohort_path cohort_sha256 package_path package_sha256 marketplace_root cache_before_checks cache_after_checks commands checker_report native_platform native_sha256 manifest_sha256 bridge_sha256 scope','installed_binding')
    require(b['format']=='codearbiter.installed-observation-binding/1'
            and b['profile']==PROFILE and b['workflow']=='.github/workflows/ci.yml' and b['scope']==SCOPE,'wrong profile/workflow/scope')
    for key,value in expected.items():
        require(b[key]==value and type(b[key]) is type(value),'installed source/run/job differs')
    runtime=b['runtime']
    closed(runtime,'version platform executable sha256_before sha256_after provenance integrity version_stdout','runtime')
    version=runtime['version'];require(version in ('0.143.0','0.145.0'),'unsupported runtime version')
    pin=runtime_policy.get(version,{})
    closed(pin,'platform executable_sha256 provenance integrity','reviewed runtime policy')
    require(digest(pin['executable_sha256']) and runtime['sha256_before']==runtime['sha256_after']==pin['executable_sha256']
            and runtime['platform']==pin['platform'] and runtime['provenance']==pin['provenance']
            and runtime['integrity']==pin['integrity'],'runtime policy/pin/platform differs')
    require(runtime['version_stdout'].strip()=='codex-cli '+version,'exact runtime version output differs')
    absolute(runtime['executable']);absolute(b['marketplace_root'])
    require(isinstance(b['commands'],list) and len(b['commands'])==4,'four original CLI commands required')
    arguments=[['--version'],['plugin','marketplace','add',b['marketplace_root']],
               ['plugin','add','ca-codex@codearbiter'],['plugin','list']]
    for command,tail in zip(b['commands'],arguments):
        closed(command,'argv exit_code timed_out containment stdout_projection_sha256 stderr_projection_sha256','command')
        require(command['argv']==[runtime['executable'],*tail] and type(command['exit_code']) is int
                and command['exit_code']==0 and command['timed_out'] is False
                and command['containment']=='exited'
                and digest(command['stdout_projection_sha256']) and digest(command['stderr_projection_sha256']),
                'original command order/exit/containment differs')
    report=b['checker_report']
    closed(report,'schema status runtime results','checker report')
    require(report['schema']=='codearbiter-codex-host-v1' and report['status']=='pass'
            and report['runtime']=='codex-cli '+version,'checker report failed/version differs')
    require(isinstance(report['results'],list) and len(report['results'])==12,'twelve original cases required')
    require(all(isinstance(x,dict) and set(x)<= {'code','status','detail'} and x.get('status')=='pass'
                for x in report['results'])
            and [x.get('code') for x in report['results']]==list(CASES),'original cases missing/repeated/skipped/failed')
    require(observation['tests']==[{'id':'codex-cli:'+c,'result':'passed'} for c in CASES],
            'named observation differs from twelve original cases')
    require(isinstance(authenticated_payloads,dict) and authenticated_payloads
            and isinstance(b['consumed_payloads'],list)
            and len(b['consumed_payloads'])==2,'two authenticated consumed payload roles required')
    payloads={};roles={}
    for declaration in b['consumed_payloads']:
        closed(declaration,'role artifact_name artifact_id archive_sha256 members','consumed payload role')
        role=declaration['role']
        require(role in ('promoted-stage','release-packages') and role not in roles,'payload role missing/duplicated')
        payload=authenticated_payloads.get(declaration['artifact_name'],{})
        require(isinstance(payload,dict) and {'artifact_id','archive_sha256','members'}<=set(payload)
                and {k:declaration[k] for k in ('artifact_id','archive_sha256','members')}
                =={k:payload[k] for k in ('artifact_id','archive_sha256','members')},
                'authenticated consumed payload differs')
        require(positive(payload['artifact_id']) and digest(payload['archive_sha256'])
                and payload['artifact_id'] not in payloads,'ambiguous payload artifact identity')
        payloads[payload['artifact_id']]=member_map(payload['members'])
        roles[role]=payload['artifact_id']
    require(type(b['package_artifact_id']) is int and b['package_artifact_id'] in payloads,'package payload absent')
    require(b['package_artifact_id']==roles['release-packages'],'package primary role differs')
    members=payloads[b['package_artifact_id']]
    require(isinstance(cohort_bytes,bytes) and len(cohort_bytes)<=16*1024*1024,'bounded cohort bytes required')
    require(relative(b['cohort_path'])=='artifact-package-cohort.json'
            and members.get(b['cohort_path'])==b['cohort_sha256']==sha(cohort_bytes),'authenticated cohort bytes differ')
    cohort=json.loads(cohort_bytes,object_pairs_hook=unique)
    require(isinstance(cohort,dict) and all(cohort.get(k)==expected[k] for k in ('source_commit','source_tree'))
            and cohort.get('workflow')==b['workflow'] and cohort.get('run_id')==str(expected['ci_run_id']),
            'cohort source/workflow/run differs')
    package=cohort.get('packages',{}).get('codex',{})
    require(relative(b['package_path'])==package.get('file')
            and members.get(b['package_path'])==b['package_sha256']==package.get('sha256')
            and digest(b['package_sha256']),'authenticated Codex archive differs')
    prefix='plugins/ca-codex/'
    require(isinstance(package.get('members'),dict) and len(package['members'])<=4096,'bounded package inventory required')
    inventory={}
    for path,item in package['members'].items():
        relative(path)
        require(isinstance(item,dict) and item.get('type')=='file' and type(item.get('size')) is int
                and 0<=item['size']<=64*1024*1024 and digest(item.get('sha256')),'package member unsupported')
        if path.startswith(prefix):
            inventory[relative(path[len(prefix):])]={'size':item['size'],'sha256':item['sha256']}
    require(inventory and b['cache_before_checks']==b['cache_after_checks']==inventory,'exact installed cache inventory differs')
    platform=b['native_platform']
    require(platform==runtime['platform'] and platform in ('linux/amd64','linux/arm64','windows/amd64','windows/arm64','darwin/amd64','darwin/arm64'), 'native/runtime platform differs')
    native='helpers/artifacts/ca-artifact-'+platform.replace('/','-')+('.exe' if platform.startswith('windows/') else '')
    for path,key in [(native,'native_sha256'),('helpers/artifacts/release.json','manifest_sha256'),('hooks/_artifactlib.py','bridge_sha256')]:
        require(path in inventory and inventory[path]['sha256']==b[key] and digest(b[key]),'native/manifest/bridge package pin differs')
    stage=payloads[roles['promoted-stage']]
    require(stage.get('artifact-promotion.json')==cohort.get('promotion_receipt_sha256')
            and digest(cohort.get('promotion_receipt_sha256'))
            and stage.get(prefix+native)==b['native_sha256']
            and stage.get(prefix+'helpers/artifacts/release.json')==b['manifest_sha256'],
            'native/promotion stage differs from consumed package')
    require(all(k in inventory for k in ('hooks/_host.py','hooks/hooks.json','hooks/_artifactmanifestlib.py','.codex-plugin/plugin.json')),
            'installed package has no actual host/helper identity')
    return {'cell':'installed:codex:'+version,'selected_population':12,'scope':SCOPE,
            'profile':PROFILE,'payload_artifact_ids':sorted(payloads),
            'result':'VALIDATED_FINITE_JOIN_ONLY;NOT_EXECUTED_OR_EMITTED'}
