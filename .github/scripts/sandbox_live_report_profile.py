"""One closed shipped-Sandbox Docker profile, never a label-only promotion."""
import json
import _sandbox_docker_profile as profile
import observe_sandbox_installed_docker as producer


def admit(observation, *, req, job_id, authenticated_payloads, repo,
          producer_job, runtime_acquisition):
    profile.require(isinstance(producer_job, dict) and type(producer_job.get('id')) is int
                    and producer_job['id'] == job_id and producer_job.get('name') == '[CHECK] | [SBX ] | Installed shipped bundle <docker>'
                    and type(producer_job.get('run_id')) is int and producer_job['run_id'] == req['ci_run_id']
                    and producer_job.get('status') == 'in_progress'
                    and type(producer_job.get('run_attempt')) is int
                    and 0 < producer_job['run_attempt'] <= 9999,
                    'actual Sandbox producer attempt required')
    expected = {k: req[k] for k in ('source_commit', 'source_tree', 'ci_run_id')}
    expected.update(producer_job_id=job_id, execution_run_attempt=producer_job['run_attempt'])
    result = profile.admit(observation, expected=expected, authenticated_payloads=authenticated_payloads)
    binding = observation['installed_binding']
    profile.require(binding['source_before'] == producer.source_snapshot(repo, req['source_commit']),
                    'Sandbox actual complete source cone differs')
    profile.require(isinstance(runtime_acquisition, dict), 'independent reviewed Nixpacks receipt required')
    actual = binding['runtime_before']['nixpacks_acquisition']
    profile.require(json.loads(actual['document_utf8'], object_pairs_hook=profile.unique) == runtime_acquisition,
                    'Sandbox Nixpacks independent acquisition differs')
    binary = binding['runtime_before']['binaries']['nixpacks']
    profile.admit_nixpacks_acquisition(actual, binary['path'], binary['sha256'], binary['version'])
    profile.require(result['installed_cells'] == ['installed:sandbox:docker']
                    and len(result['payloads']) == len(result['payload_artifact_ids']) == 1,
                    'Sandbox requires exactly one original plugin artifact')
    return {key: result[key] for key in ('tests', 'installed_cells', 'payload_artifact_ids',
                                       'payloads', 'primary_payload_name')}
