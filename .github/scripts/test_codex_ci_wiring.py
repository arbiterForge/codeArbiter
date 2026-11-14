"""Bounded pure contracts. Never runs a downloaded executable or network call."""
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import tarfile
import sys
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
import zipfile
from unittest import mock

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import codex_runtime_acquisition as acquisition
import coordinate_codex_host as coordinator
import pi_host_locks as pi
import codex_live_report_profile as adapter

def admission_fixture(version='0.143.0'):
    """Synthetic Linux join only; never installed, executed or retained as proof."""
    sha=lambda raw:hashlib.sha256(raw).hexdigest()
    encode=lambda value:json.dumps(value,sort_keys=True).encode()
    expected=dict(source_commit='a'*40,source_tree='b'*40,ci_run_id=17,producer_job_id=29)
    policy={version:{'linux_amd64':{'package':'@openai/codex','version':version+'-linux-x64',
        'integrity':'unit-only-synthetic-sri','members':[{'path':acquisition.BINARY,'sha256':'c'*64}]}}}
    pins={'versions':policy}
    files={p:p.encode() for p in ('hooks/hooks.json','hooks/_host.py','hooks/_artifactlib.py',
        'hooks/_artifactmanifestlib.py','helpers/artifacts/release.json','helpers/artifacts/ca-artifact-linux-amd64',
        '.codex-plugin/plugin.json','agents/unit.md')}
    cache={p:{'size':len(raw),'sha256':sha(raw)} for p,raw in files.items()}
    cohort={**{k:expected[k] for k in ('source_commit','source_tree')},'workflow':'.github/workflows/ci.yml','run_id':'17',
        'promotion_receipt_sha256':sha(b'promotion'),'packages':{'codex':{'file':'codex.tar.gz','sha256':sha(b'archive'),
        'members':{'plugins/ca-codex/'+p:{'type':'file',**v} for p,v in cache.items()}}}}
    raw=encode(cohort)
    packages={'artifact_id':71,'archive_sha256':'d'*64,'members':[{'path':'artifact-package-cohort.json','sha256':sha(raw)},
        {'path':'codex.tar.gz','sha256':sha(b'archive')}],'documents':{'artifact-package-cohort.json':raw}}
    stage={'artifact_id':72,'archive_sha256':'e'*64,'members':[{'path':'plugins/ca-codex/'+p,'sha256':cache[p]['sha256']}
        for p in ('helpers/artifacts/release.json','helpers/artifacts/ca-artifact-linux-amd64')]+[{'path':'artifact-promotion.json','sha256':sha(b'promotion')}]}
    runtime={'version':version,'platform':'linux/amd64','executable':'/private/unit/codex','sha256_before':'c'*64,
        'sha256_after':'c'*64,'provenance':'npm:@openai/codex@'+version+'-linux-x64','integrity':'unit-only-synthetic-sri',
        'version_stdout':'codex-cli '+version+'\n'}
    tails=[['--version'],['plugin','marketplace','add','/private/unit/package'],['plugin','add','ca-codex@codearbiter'],['plugin','list']]
    commands=[{'argv':[runtime['executable'],*tail],'exit_code':0,'timed_out':False,'containment':'exited',
        'stdout_projection_sha256':'1'*64,'stderr_projection_sha256':'2'*64} for tail in tails]
    binding={'format':'codearbiter.installed-observation-binding/1','profile':adapter.profile.PROFILE,**expected,
        'workflow':'.github/workflows/ci.yml','runtime':runtime,'consumed_payloads':[{'role':role,'artifact_name':name,
        **{k:payload[k] for k in ('artifact_id','archive_sha256','members')}} for role,name,payload in
        [('release-packages','packages',packages),('promoted-stage','stage',stage)]],
        'package_artifact_id':71,'cohort_path':'artifact-package-cohort.json','cohort_sha256':sha(raw),
        'package_path':'codex.tar.gz','package_sha256':sha(b'archive'),'marketplace_root':'/private/unit/package',
        'cache_before_checks':copy.deepcopy(cache),'cache_after_checks':copy.deepcopy(cache),'commands':commands,
        'checker_report':{'schema':'codearbiter-codex-host-v1','status':'pass','runtime':'codex-cli '+version,
            'results':[{'code':c,'status':'pass'} for c in adapter.profile.CASES]},'native_platform':'linux/amd64',
        'native_sha256':cache['helpers/artifacts/ca-artifact-linux-amd64']['sha256'],
        'manifest_sha256':cache['helpers/artifacts/release.json']['sha256'],
        'bridge_sha256':cache['hooks/_artifactlib.py']['sha256'],'scope':adapter.profile.SCOPE}
    observed={'format':'codearbiter.major-test-observation/1',**{k:expected[k] for k in ('source_commit','source_tree','ci_run_id')},
        'source_stable':True,'proof_kind':'live-host','producer':adapter.profile.PRODUCER,'argv':['unit-only-observer'],
        'exit_code':0,'tests':[{'id':'codex-cli:'+c,'result':'passed'} for c in adapter.profile.CASES],'installed_binding':binding}
    req={k:expected[k] for k in ('source_commit','source_tree','ci_run_id')}
    return observed,req,{'packages':packages,'stage':stage},pins

def fixture_archive():
    manifest=json.dumps({'name':'@openai/codex','version':'0.143.0-linux-x64','license':'Apache-2.0'}).encode()
    elf=bytearray(64);elf[:7]=b'\x7fELF\x02\x01\x01';elf[18:20]=(62).to_bytes(2,'little')
    files={'package/package.json':manifest,'package/vendor/x86_64-unknown-linux-musl/bin/codex':bytes(elf)}
    b=io.BytesIO()
    with tarfile.open(fileobj=b,mode='w:gz') as tar:
        for name,data in files.items():
            item=tarfile.TarInfo(name);item.size=len(data);item.mode=0o755 if name.endswith('/codex') else 0o644
            tar.addfile(item,io.BytesIO(data))
    raw=b.getvalue();pin={'package':'@openai/codex','version':'0.143.0-linux-x64',
       'integrity':'sha512-'+base64.b64encode(hashlib.sha512(raw).digest()).decode(),
       'archive_sha256':hashlib.sha256(raw).hexdigest(),'archive_bytes':len(raw),
       'members':[{'path':n,'size':len(v),'mode':oct(0o755 if n.endswith('/codex') else 0o644),
                   'sha256':hashlib.sha256(v).hexdigest()} for n,v in files.items()]}
    return raw,pin

class WiringContracts(unittest.TestCase):
    def test_program_context_is_closed_and_all_other_events_use_legacy(self):
        env={'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY':'arbiterForge/codeArbiter',
             'GITHUB_EVENT_NAME':'push','GITHUB_REF':'refs/heads/major/state-contracts'}
        self.assertTrue(coordinator.program_mode(env,True))
        for key,value in [('GITHUB_EVENT_NAME','pull_request'),('GITHUB_EVENT_NAME','merge_group'),
                          ('GITHUB_REPOSITORY','fork/codeArbiter'),('GITHUB_REF','refs/heads/other')]:
            changed=dict(env,**{key:value});self.assertFalse(coordinator.program_mode(changed,True))
        self.assertFalse(coordinator.program_mode(env,False))

    def test_program_sequence_verifies_production_before_acquisition_or_actual_producer(self):
        events=[]
        s=SimpleNamespace(verify=lambda:events.append('require_production'),
             acquire=lambda:events.append('acquire') or {'runtime':'fixed-unit'},
             produce=lambda runtime:events.append('actual_producer') or {'observed':'unit'},
             report=lambda observed:events.append('closed_v3_report') or {'schema':'unit'})
        self.assertEqual(coordinator.coordinate_sequence(s),{'schema':'unit'})
        self.assertEqual(events,['require_production','acquire','actual_producer','closed_v3_report'])
        events.clear()
        def refused():events.append('refused');raise ValueError('cohort refused')
        s.verify=refused
        with self.assertRaisesRegex(ValueError,'cohort'):coordinator.coordinate_sequence(s)
        self.assertEqual(events,['refused'])

    def test_closed_archive_checks_sri_manifest_exact_members_and_linux_elf(self):
        raw,pin=fixture_archive()
        result=acquisition.verify_archive(raw,pin)
        self.assertEqual(result['binary_sha256'],pin['members'][1]['sha256'])
        for change in [lambda p:p.__setitem__('integrity','sha512-'+base64.b64encode(b'0'*64).decode()),
                       lambda p:p['members'].pop(),
                       lambda p:p['members'][1].__setitem__('sha256','0'*64),
                       lambda p:p.__setitem__('version','0.145.0-linux-x64')]:
            changed=copy.deepcopy(pin);change(changed)
            with self.assertRaises(ValueError):acquisition.verify_archive(raw,changed)

    def test_links_and_oversize_refuse_without_extracting(self):
        for kind in ('link','oversize'):
            raw,pin=fixture_archive();b=io.BytesIO()
            with tarfile.open(fileobj=b,mode='w:gz') as tar:
                item=tarfile.TarInfo('package/package.json')
                if kind=='link':item.type=tarfile.SYMTYPE;item.linkname='/outside';tar.addfile(item)
                else:
                    # Header-only invalid body: admission must reject the declared
                    # size before any attempt to consume/decompress its contents.
                    item.size=512*1024*1024+1
                    tar.fileobj.write(item.tobuf());tar.offset+=512
            raw=b.getvalue();pin.update(archive_bytes=len(raw),archive_sha256=hashlib.sha256(raw).hexdigest(),
                  integrity='sha512-'+base64.b64encode(hashlib.sha512(raw).digest()).decode())
            with self.assertRaises(ValueError):acquisition.verify_archive(raw,pin)

    def test_pi_default_ceiling_is_unchanged_and_codex_profile_is_closed(self):
        self.assertEqual(pi.MAX_ARCHIVE_MEMBER_BYTES,256*1024*1024)
        self.assertEqual(acquisition.MAX_MEMBER_BYTES,512*1024*1024)
        self.assertEqual(acquisition.VERSIONS,('0.143.0','0.145.0'))

    def test_ci_and_route_proposal_preserve_legacy_boundaries_and_exact_versions(self):
        repo=HERE.parents[1];text=(repo/'.github/workflows/ci.yml').read_text(encoding='utf8')
        import re
        job=re.split(r'(?m)^  [a-z0-9-]+:\n',text.split('  codex-host:\n',1)[1],maxsplit=1)[0]
        self.assertIn('codex-version: ["0.143.0", "0.145.0"]',job)
        self.assertIn('timeout-minutes: 15',job)
        self.assertIn('npm install -g @openai/codex@${{ matrix.codex-version }}',job)
        self.assertIn('python3 .github/scripts/check_codex_host.py',job)
        self.assertNotIn('coordinate_codex_host.py',job)
        self.assertNotIn('artifact-package-assembly',job)
        self.assertNotIn('if: ${{',job)
        self.assertTrue('  codex-installed-package:\n' in text,'dedicated installed-package job missing')
        # Capture through the next top-level job, not step indentation.
        import re
        installed=re.split(r'(?m)^  [a-z0-9-]+:\n',text.split('  codex-installed-package:\n',1)[1],maxsplit=1)[0]
        self.assertIn('codex-version: ["0.143.0", "0.145.0"]',installed)
        self.assertIn('timeout-minutes: 15',installed)
        self.assertIn('coordinate_codex_host.py',installed)
        self.assertIn('artifact-package-assembly',installed)
        self.assertIn('actions: read',installed)
        self.assertIn('refs/heads/major/state-contracts',installed)
        self.assertNotIn('npm install',installed)
        selections=json.loads((repo/'.github/major-test-selections.json').read_bytes())['groups']
        groups=[g for g in selections if g['id'].startswith('codex-live-')]
        self.assertEqual(len(groups),2)
        self.assertTrue(all(g['proof_kind']=='live-host' and len(g['selectors'])==12 for g in groups))
        self.assertEqual({g['cells'][0] for g in groups},{'installed:codex:0.143.0','installed:codex:0.145.0'})

    def test_acquisition_policy_is_independent_and_wrong_version_never_downloads(self):
        with mock.patch.object(acquisition.platform,'system',return_value='Linux'),mock.patch.object(acquisition.platform,'machine',return_value='x86_64'),mock.patch.object(acquisition,'reviewed_pins',return_value={'versions':{}}),mock.patch.object(pi,'_download_registry_archive_bytes') as download:
            with tempfile.TemporaryDirectory() as raw:
                with self.assertRaises(ValueError):acquisition.acquire(Path(raw),'a'*40,'0.146.0',Path(raw))
        download.assert_not_called()

    def test_real_acquisition_owner_uses_committed_pins_and_never_executes_fixture_bytes(self):
        def archive(files,version):
            b=io.BytesIO()
            with tarfile.open(fileobj=b,mode='w:gz') as tar:
                for name,data in files.items():
                    item=tarfile.TarInfo(name);item.size=len(data);item.mode=0o755 if name.endswith('/codex') else 0o644
                    tar.addfile(item,io.BytesIO(data))
            raw=b.getvalue()
            return raw,{'package':'@openai/codex','version':version,
                'url':'https://registry.npmjs.org/@openai/codex/-/codex-'+version+'.tgz',
                'integrity':'sha512-'+base64.b64encode(hashlib.sha512(raw).digest()).decode(),
                'archive_sha256':hashlib.sha256(raw).hexdigest(),'archive_bytes':len(raw),
                'members':[{'path':n,'size':len(v),'mode':oct(0o755 if n.endswith('/codex') else 0o644),
                            'sha256':hashlib.sha256(v).hexdigest()} for n,v in files.items()]}
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);repo=root/'source';repo.mkdir();parent=root/'acquired';parent.mkdir()
            pins={'schema':'codearbiter.codex-linux-runtime-pins/1','registry':'https://registry.npmjs.org',
                  'platform':'linux/amd64','versions':{}};downloads={};expected={}
            for version in acquisition.VERSIONS:
                manifest={'name':'@openai/codex','version':version,'license':'Apache-2.0',
                          'optionalDependencies':{'@openai/codex-linux-x64':'npm:@openai/codex@'+version+'-linux-x64'}}
                wrapper,pin=archive({'package/package.json':json.dumps(manifest).encode()},version)
                manifest['version']=version+'-linux-x64';manifest.pop('optionalDependencies')
                elf=bytearray(64);elf[:7]=b'\x7fELF\x02\x01\x01';elf[18:20]=(62).to_bytes(2,'little')
                native,npin=archive({'package/package.json':json.dumps(manifest).encode(),acquisition.BINARY:bytes(elf)},version+'-linux-x64')
                pins['versions'][version]={'root':pin,'linux_amd64':npin}
                downloads[pin['url']]=wrapper;downloads[npin['url']]=native;expected[version]=bytes(elf)
            path=repo/acquisition.PIN_PATH;path.parent.mkdir(parents=True);path.write_text(json.dumps(pins))
            def git(*a):return subprocess.run(['git',*a],cwd=repo,capture_output=True,check=True).stdout
            git('init','-q');git('add','.');git('-c','user.name=Disposable acquisition fixture','-c','user.email=fixture@example.invalid','commit','-qm','Independent immutable pins')
            source=git('rev-parse','HEAD').decode().strip();calls=[]
            def download(url,integrity,destination,**kw):
                self.assertIn(url,downloads);self.assertEqual(kw['byte_budget'],256*1024*1024)
                calls.append(url);destination.write_bytes(downloads[url])
            with mock.patch.object(acquisition.platform,'system',return_value='Linux'),mock.patch.object(acquisition.platform,'machine',return_value='x86_64'),mock.patch.object(pi,'_download_registry_archive_bytes',side_effect=download),mock.patch.object(acquisition,'reviewed_pins',wraps=acquisition.reviewed_pins) as read_pins:
                for version in acquisition.VERSIONS:
                    result=acquisition.acquire(repo,source,version,parent)
                    self.assertEqual(result['runtime_executable'].read_bytes(),expected[version])
                    policy_raw=result['runtime_policy'].read_bytes()
                    self.assertEqual(hashlib.sha256(policy_raw).hexdigest(),result['trusted_runtime_policy_sha256'])
                    self.assertEqual(json.loads(policy_raw),acquisition.policy_for(pins,version))
                    receipt=json.loads(result['acquisition_receipt'].read_bytes())
                    self.assertEqual(receipt['source_commit'],source)
                    self.assertEqual(receipt['binary_sha256'],hashlib.sha256(expected[version]).hexdigest())
            self.assertEqual(len(calls),4)
            self.assertEqual(read_pins.call_count,2)
            self.assertTrue(all(c.args==(repo,source) for c in read_pins.call_args_list))

    def test_runtime_parent_rejects_nonliteral_traversal_before_acquisition(self):
        with tempfile.TemporaryDirectory() as raw:
            parent=Path(raw);(parent/'child').mkdir()
            with self.assertRaisesRegex(ValueError,'linked or nonliteral'):
                acquisition._new_parent(parent/'child/..')

    def test_closed_adapter_joins_both_payloads_and_independent_linux_runtime_policy(self):
        for version in acquisition.VERSIONS:
            observed,req,payloads,pins=admission_fixture(version)
            with mock.patch.object(adapter,'reviewed_pins',return_value=pins):
                result=adapter.admit(observed,req=req,job_id=29,authenticated_payloads=payloads,repo=Path('.'))
                self.assertEqual(result['installed_cells'],['installed:codex:'+version])
                self.assertEqual(result['payload_artifact_ids'],[71,72])
                self.assertEqual(len(result['tests']),12)
                for change in ('self-reported-native','windows-is-not-linux','cohort-not-retained','string-relabel','malformed-binding','malformed-runtime','malformed-roles'):
                    bad=copy.deepcopy(observed);auth=copy.deepcopy(payloads)
                    if change=='self-reported-native':bad['installed_binding']['runtime'].update(sha256_before='f'*64,sha256_after='f'*64)
                    elif change=='windows-is-not-linux':bad['installed_binding']['runtime']['platform']='windows/amd64'
                    elif change=='cohort-not-retained':auth['packages'].pop('documents')
                    elif change=='string-relabel':bad['producer']='python-test-result-observer'
                    elif change=='malformed-binding':bad['installed_binding']=None
                    elif change=='malformed-runtime':bad['installed_binding']['runtime']=[]
                    else:bad['installed_binding']['consumed_payloads']={}
                    with self.subTest(change=change),self.assertRaises(ValueError):
                        adapter.admit(bad,req=req,job_id=29,authenticated_payloads=auth,repo=Path('.'))

    def test_report_dispatch_is_closed_to_exact_installed_codex_cells_and_v3(self):
        import major_qualification_report as reports
        observed,req,payloads,pins=admission_fixture();cell='installed:codex:0.143.0';job='unit-only-installed-job'
        req.update(cells=[cell],cell_jobs={cell:job})
        groups={'schema':reports.SELECTIONS,'groups':[{'id':'unit-codex','job':job,'payload_name':'packages',
            'observation':'live','proof_kind':'live-host','selectors':[x['id'] for x in observed['tests']],
            'cells':[cell],'scope':'synthetic unit transport only'}]}
        with mock.patch.object(adapter,'reviewed_pins',return_value=pins):
            report=reports.build_report(req,job_name=job,job_id=29,selections=groups,observations={'live':observed},payloads=payloads)
            self.assertEqual(report['schema'],'codearbiter-major-qualification/3')
            self.assertEqual(report['results'][0]['payload_artifact_ids'],[71,72])
            self.assertEqual(len(report['payloads']),2)
            self.assertNotIn('documents',json.dumps(report))
            for wrong in ('installed:claude:workflow','task:P-00'):
                req.update(cells=[wrong],cell_jobs={wrong:job});groups['groups'][0]['cells']=[wrong]
                with self.subTest(wrong=wrong),self.assertRaisesRegex(ValueError,'cannot qualify'):
                    reports.build_report(req,job_name=job,job_id=29,selections=groups,observations={'live':observed},payloads=payloads)

    def test_cohort_document_retention_reuses_verified_archive_member_bytes(self):
        import major_qualification_report as reports
        raw=b'{"unit":"authenticated bytes only"}'
        archive=io.BytesIO()
        with zipfile.ZipFile(archive,'w') as z:z.writestr('artifact-package-cohort.json',raw)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);path=root/'artifact-package-cohort.json';path.write_bytes(raw)
            with mock.patch.object(reports.readiness,'artifact_bytes',return_value=archive.getvalue()) as fetch:
                result=reports.authenticated_payload({'id':71},{},root)
                self.assertEqual(result['documents'],{'artifact-package-cohort.json':raw})
                self.assertEqual(fetch.call_count,1)
                path.write_bytes(b'changed physical bytes')
                with self.assertRaisesRegex(ValueError,'differs'):
                    reports.authenticated_payload({'id':71},{},root)

    def test_source_pr_unit_reachability_and_merge_gate_registry_are_preserved(self):
        from test_ci_impact import workflow_jobs,paths_filter,aggregate_required_results
        root=HERE.parents[1];text=(root/'.github/workflows/ci.yml').read_text();jobs=workflow_jobs(text)
        resource=jobs['codex-resource-contract']
        self.assertIn('python .github/scripts/test_observe_codex_installed_cli.py',resource)
        self.assertIn('python .github/scripts/test_codex_ci_wiring.py',resource)
        for path in ('.github/scripts/observe_codex_installed_cli.py','.github/scripts/_codex_cli_profile.py',
                     '.github/scripts/test_observe_codex_installed_cli.py','.github/scripts/codex_runtime_acquisition.py',
                     '.github/scripts/coordinate_codex_host.py','.github/scripts/codex_live_report_profile.py',
                     '.github/scripts/test_codex_ci_wiring.py','.github/fixtures/codex-host-runtime-linux.json'):
            self.assertIn(path,paths_filter(text,'codex-resources'))
        self.assertNotIn('codex-installed-package',aggregate_required_results(text))
        self.assertNotIn('continue-on-error:',jobs['codex-installed-package'])
        self.assertIn("github.event_name == 'push'",jobs['codex-installed-package'])

if __name__=='__main__':unittest.main(verbosity=2)
