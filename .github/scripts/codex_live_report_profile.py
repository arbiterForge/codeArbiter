"""Explicit closed live-CLI dispatcher adapter; no label-only host admission."""
import _codex_cli_profile as profile
from codex_runtime_acquisition import reviewed_pins,policy_for

def admit(observation,*,req,job_id,authenticated_payloads,repo):
    profile.require(isinstance(observation,dict),'no qualified observer for this closed Codex profile')
    binding=observation.get('installed_binding',{})
    profile.require(isinstance(binding,dict) and observation.get('producer')==profile.PRODUCER and binding.get('profile')==profile.PROFILE,
                    'no qualified observer for this closed Codex profile')
    runtime=binding.get('runtime',{})
    profile.require(isinstance(runtime,dict),'closed Codex runtime required')
    version=runtime.get('version')
    policy=policy_for(reviewed_pins(repo,req['source_commit']),version)
    roles=binding.get('consumed_payloads')
    profile.require(isinstance(roles,list) and len(roles)==2 and all(isinstance(r,dict) for r in roles),
                    'two closed consumed roles required')
    release=[r for r in roles if r.get('role')=='release-packages']
    profile.require(len(release)==1,'exact release package role required')
    name=release[0].get('artifact_name')
    profile.require(isinstance(name,str) and name and isinstance(authenticated_payloads,dict),'authenticated named payload required')
    payload=authenticated_payloads.get(name,{})
    cohort=payload.get('documents',{}).get('artifact-package-cohort.json')
    profile.require(isinstance(cohort,bytes) and len(cohort)<=8*1024*1024,'authenticated bounded cohort raw unavailable')
    expected={k:req[k] for k in ('source_commit','source_tree','ci_run_id')};expected['producer_job_id']=job_id
    result=profile.admit(observation,expected=expected,authenticated_payloads=authenticated_payloads,
                         cohort_bytes=cohort,runtime_policy=policy)
    payloads=[]
    for role in binding['consumed_payloads']:
        value=authenticated_payloads[role['artifact_name']]
        payloads.append({k:value[k] for k in ('artifact_id','archive_sha256','members')})
    return {'tests':observation['tests'],'payload_artifact_ids':result['payload_artifact_ids'],
            'payloads':payloads,'primary_payload_name':name,'installed_cells':[result['cell']]}
