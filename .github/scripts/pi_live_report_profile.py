"""Closed Pi installed-RPC admission, including independent immutable lock joins."""
import hashlib
import major_readiness as readiness
import _pi_rpc_profile as profile

LOCK_NAMES=('package.json','package-lock.json','.npmrc','review.json')

def admit(observation,*,req,job_id,authenticated_payloads,runtime_acquisition,repo):
    profile.require(isinstance(observation,dict),'closed Pi observation required')
    binding=observation.get('installed_binding',{})
    profile.require(isinstance(binding,dict) and observation.get('producer')==profile.PRODUCER
        and binding.get('profile')==profile.PROFILE,'no qualified observer for this closed Pi profile')
    profile.require(isinstance(runtime_acquisition,dict),'original same-job Pi acquisition required')
    locks={name:hashlib.sha256(readiness.blob(repo,req['source_commit'],
        '.github/fixtures/pi-hosts/1.5.0/'+name)).hexdigest() for name in LOCK_NAMES}
    profile.require(runtime_acquisition.get('source_locks')==locks,'Pi acquisition differs from immutable reviewed graph')
    return profile.admit(observation,req=req,job_id=job_id,authenticated_payloads=authenticated_payloads,
                         runtime_acquisition=runtime_acquisition)
