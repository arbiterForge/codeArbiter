"""Tiny original-shard retention controls; never native/host qualification."""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / '.github/scripts/run_artifact_authority_shard.py'
# The controlled fixture copies unchanged observer dependencies from the actual
# checkout when this file is executed in a Temp author overlay.
DEPENDENCY_REPO = Path(os.environ.get('CA_AUTHORITY_RETENTION_DEPENDENCY_REPO', str(REPO)))


def module(path):
    spec = importlib.util.spec_from_file_location('authority_retention_subject_' + path.parent.parent.parent.name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class AuthorityRetentionTest(unittest.TestCase):
    def _fixture(self):
        owner = tempfile.TemporaryDirectory(prefix='ca-authority-retention-test-')
        self.addCleanup(owner.cleanup)
        base = Path(owner.name).resolve()
        root, scratch = base / 'repo', base / 'scratch'
        scripts = root / '.github/scripts'; scripts.mkdir(parents=True)
        scratch.mkdir()
        shutil.copyfile(SCRIPT, scripts / SCRIPT.name)
        for name in ('major_qualification_report.py','major_readiness.py','_immutable_git_blobs.py','ci20_native_binding.py','_boundedproc.py','_contextverificationlib.py'):
            shutil.copyfile(DEPENDENCY_REPO / '.github/scripts' / name, scripts / name)
        shared = root / 'core/pysrc'; shared.mkdir(parents=True)
        for name in ('_artifactmanifestlib.py', '_gitexec.py'):
            shutil.copyfile(DEPENDENCY_REPO / 'core/pysrc' / name, shared / name)
        (scripts / 'test_artifact_authority_adapter.py').write_text(
            'import os\nfrom pathlib import Path\nimport unittest\n'
            'def effect(name):\n    (Path(os.environ["AUTHORITY_FIXTURE_EFFECTS"])/name).open("x").close()\n'
            + '\n'.join('class Case'+name+'(unittest.TestCase):\n    def test_effect(self):\n        effect("'+name+'")\n' for name in 'ABCD')
            + '\nCaseA.test_skip = unittest.skip("synthetic supported skip")(lambda self: None)\n', encoding='utf-8')
        timing = root / '.github/fixtures/artifact-authority-timings.json'
        timing.parent.mkdir(parents=True)
        timing.write_text(json.dumps({'format':'codearbiter.authority-timing-hints/1','classes':{}}), encoding='utf-8')
        fixture_home = scratch / 'home'; fixture_home.mkdir()
        git_env = {key:value for key,value in os.environ.items() if key.upper() in ('SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','SYSTEMDRIVE','PATH')}
        git_env.update(HOME=str(fixture_home),USERPROFILE=str(fixture_home),TEMP=str(scratch),TMP=str(scratch),
                       GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull)
        git = shutil.which('git')
        self.assertIsNotNone(git)
        for argv in ([git,'init','-q',str(root)], [git,'-C',str(root),'config','core.autocrlf','false'],
                     [git,'-C',str(root),'add','.'],
                     [git,'-C',str(root),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture']):
            subprocess.run(argv,env=git_env,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
        effects = scratch / 'effects'; effects.mkdir()
        home = fixture_home
        env = {key:value for key,value in os.environ.items() if key.upper() in ('SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','SYSTEMDRIVE','PATH')}
        env.update(HOME=str(home),USERPROFILE=str(home),TEMP=str(scratch),TMP=str(scratch),
                   PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',PYTHONNOUSERSITE='1',
                   RUNNER_TEMP=str(scratch), AUTHORITY_OBSERVATION_DIR=str(scratch / 'retained'),
                   AUTHORITY_FIXTURE_EFFECTS=str(effects), AUTHORITY_CHILD_TIMEOUT_SECONDS='20',
                   GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull)
        sys.path.insert(0,str(scripts))
        self.addCleanup(lambda: sys.path.remove(str(scripts)) if str(scripts) in sys.path else None)
        subject = module(scripts / SCRIPT.name)
        source = {'source_commit':subprocess.check_output([git,'-C',str(root),'rev-parse','HEAD'],env=git_env).decode().strip(),
                  'source_tree':subprocess.check_output([git,'-C',str(root),'rev-parse','HEAD^{tree}'],env=git_env).decode().strip(),'clean':True}
        metadata = scratch / 'ci20-native-tested.json'
        metadata.write_text('{"synthetic_unit_fixture":true}\n',encoding='utf-8')
        context = {'source':source,'run_id':0,'candidate_identity':{'manifest_sha256':'a'*64,'binary_sha256':'b'*64},
                   'native_binding':{'synthetic_unit_fixture':True}, 'native_metadata_path':str(metadata),
                   'native_metadata_sha256':hashlib.sha256(metadata.read_bytes()).hexdigest()}
        return subject, env, effects, context

    def test_real_four_original_shards_retain_observations_and_execute_once(self):
        subject,env,effects,context = self._fixture()
        # Only native CI context is a unit double. The four child processes,
        # Git source checks, unittest events and original observer JSON are real.
        with mock.patch.dict(os.environ,env,clear=True), mock.patch.object(subject,'retention_context',return_value=context,create=True):
            cases=subject.discover(); shards,_=subject.partition(cases,4,subject.load_weights())
            expected=[case.id() for case in cases]
            self.assertTrue(subject.run_all(4,expected,plan_sha256=subject.plan_digest(shards)))
        retained=Path(env['AUTHORITY_OBSERVATION_DIR'])
        self.assertTrue(retained.is_dir(),'successful original shard observations must survive parent temporary cleanup')
        self.assertEqual(sorted(p.name for p in effects.iterdir()),list('ABCD'))
        self.assertEqual(sorted(p.name for p in retained.glob('shard-*-timing.json')),[f'shard-{i}-timing.json' for i in range(4)])
        observations=[json.loads((retained/f'shard-{i}-observation.json').read_bytes()) for i in range(4)]
        self.assertTrue(all(o['producer']=='python-test-result-observer' and o['ci_run_id']==0 and o['source_stable'] for o in observations))
        terminals=[row for o in observations for row in o['tests']]
        self.assertEqual(len(terminals),5)
        self.assertEqual(sum(row['result']=='passed' for row in terminals),4)
        self.assertEqual(sum(row['result']=='skipped' for row in terminals),1)
        bundle=json.loads((retained/'bundle.json').read_bytes())
        self.assertEqual(bundle['state'],'VALIDATED_ORIGINAL_SHARDS')

    def _observations(self):
        subject = module(SCRIPT)
        source = {'source_commit':'a'*40,'source_tree':'b'*40,'clean':True}
        context = {'source':source,'run_id':0,'candidate_identity':{'manifest_sha256':'c'*64,'binary_sha256':'d'*64}}
        reports,observed=[],[]
        for i in range(4):
            name=f'tiny.Case{i}.test_effect'
            reports.append({'format':'codearbiter.authority-shard-observation/1','shard':i,'shard_count':4,
                            'discovered_count':4,'selected_ids':[name],'tests_run':1,
                            'observations':[{'id':name,'class':f'tiny.Case{i}','seconds':0.01,'outcome':'pass'}]})
            observed.append({'format':'codearbiter.major-test-observation/1',**source,'source_stable':True,
                             'ci_run_id':0,'proof_kind':'source-test','producer':'python-test-result-observer',
                             'argv':['python','original-shard.py'],'exit_code':0,
                             'tests':[{'id':'python:.github/scripts/run_artifact_authority_shard.py:'+name,'result':'passed'}]})
        return subject,context,reports,observed

    def test_wrong_epoch_candidate_or_original_command_refuses(self):
        subject,context,reports,observed=self._observations()
        self.assertEqual(subject.observation_problems(reports,observed,context,context,['python','original-shard.py']),[])
        for key,value in [('source_commit','e'*40),('source_tree','e'*40),('ci_run_id',7),
                          ('source_stable',False),('clean',False),('producer','caller-pass-flag'),
                          ('proof_kind','live-host'),('exit_code',1),('exit_code',False),('argv',['different'])]:
            with self.subTest(field=key):
                changed=copy.deepcopy(observed);changed[0][key]=value
                self.assertTrue(subject.observation_problems(reports,changed,context,context,['python','original-shard.py']))
        for field in ('manifest_sha256','binary_sha256'):
            changed=copy.deepcopy(context);changed['candidate_identity'][field]='e'*64
            self.assertTrue(subject.observation_problems(reports,observed,context,changed,['python','original-shard.py']))

    def test_missing_extra_repeated_or_malformed_named_membership_refuses(self):
        subject,context,reports,observed=self._observations()
        for change in ('missing','repeat','extra','skip-substitution','malformed'):
            with self.subTest(change=change):
                changed=copy.deepcopy(observed)
                if change=='missing':changed[0]['tests']=[]
                elif change=='repeat':changed[0]['tests']*=2
                elif change=='extra':changed[0]['tests'].append({'id':'uncited','result':'passed'})
                elif change=='skip-substitution':changed[0]['tests'][0]['result']='skipped'
                else:changed[0]=None
                self.assertTrue(subject.observation_problems(reports,changed,context,context,['python','original-shard.py']))
        for field,value in [('shard',1),('shard_count',8),('discovered_count',3),('tests_run',True)]:
            changed=copy.deepcopy(reports);changed[0][field]=value
            self.assertTrue(subject.observation_problems(changed,observed,context,context,['python','original-shard.py']))
        self.assertTrue(subject.observation_problems(reports,observed[:3],context,context,['python','original-shard.py']))

    def test_retention_output_is_exclusive_direct_runner_temp_child(self):
        subject=module(SCRIPT)
        with tempfile.TemporaryDirectory(prefix='ca-authority-target-') as root:
            base=Path(root).resolve(); outside=base/'outside'; outside.mkdir()
            runner=base/'runner';runner.mkdir()
            target=runner/'new'
            with mock.patch.dict(os.environ,{'RUNNER_TEMP':str(runner),'AUTHORITY_OBSERVATION_DIR':str(target)}):
                self.assertEqual(subject.retention_directory(4,list(range(4))),target)
                with self.assertRaises(FileExistsError):subject.retention_directory(4,list(range(4)))
            for value,indexes in [(outside/'new',list(range(4))),(runner/'partial',[0,1]),(Path('relative'),list(range(4)))]:
                with mock.patch.dict(os.environ,{'RUNNER_TEMP':str(runner),'AUTHORITY_OBSERVATION_DIR':str(value)}):
                    with self.assertRaises(ValueError):subject.retention_directory(4,indexes)


class AuthorityRetentionWorkflowTest(unittest.TestCase):
    def _check(self,text):
        authority=text.split('  artifact-authority:\n',1)[1].split('  artifact-browser:\n',1)[0]
        self.assertIn('AUTHORITY_OBSERVATION_DIR: ${{ runner.temp }}/authority-observations',authority)
        self.assertIn('AUTHORITY_SHARD_COUNT: "4"',authority)
        self.assertIn('timeout-minutes: 45',authority)
        self.assertIn('    permissions:\n      contents: read\n',authority)
        self.assertNotIn('contents: write',authority)
        self.assertNotIn('actions: write',authority)
        self.assertNotIn('continue-on-error:',authority)
        for platform in ('linux/amd64','linux/arm64','windows/amd64','windows/arm64','darwin/amd64','darwin/arm64'):
            self.assertEqual(authority.count('expected_platform: '+platform+'\n'),1)
        before=authority.index('- name: Verify tested candidate bytes, source and native toolchain')
        run=authority.index('- name: Run exhaustive authority partitions')
        after=authority.index('- name: Recheck tested candidate after authority coverage')
        upload=authority.index('- name: Retain original authority observations')
        self.assertLess(before,run);self.assertLess(run,after);self.assertLess(after,upload)
        step=authority[upload:]
        self.assertIn('uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9',step)
        self.assertIn('name: authority-observations-${{ matrix.os }}-${{ github.run_attempt }}\n',step)
        self.assertIn('path: ${{ runner.temp }}/authority-observations/*.json',step)
        self.assertIn('if-no-files-found: error',step)
        self.assertIn('retention-days: 14',step)
        self.assertIn('include-hidden-files: false',step)
        self.assertIn('overwrite: false',step)
        self.assertNotIn('        if:',step)

    def test_original_data_retention_follows_final_verification_with_existing_pin(self):
        self._check((REPO/'.github/workflows/ci.yml').read_text(encoding='utf-8'))

    def test_unconditional_or_unpinned_upload_and_missing_capture_are_rejected(self):
        text=(REPO/'.github/workflows/ci.yml').read_text(encoding='utf-8')
        self._check(text)
        begin=text.index('      - name: Retain original authority observations\n')
        end=text.index('  artifact-browser:\n',begin)
        step=text[begin:end]
        reordered=text[:begin]+text[end:]
        marker='      - name: Recheck tested candidate after authority coverage\n'
        reordered=reordered.replace(marker,step+marker,1)
        for mutated in (text.replace('AUTHORITY_OBSERVATION_DIR:', 'IGNORED_OBSERVATION_DIR:'),
                        text.replace('      - name: Retain original authority observations\n',
                                     '      - name: Retain original authority observations\n        if: always()\n'),
                        text.replace('uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9',
                                     'uses: actions/upload-artifact@v7'),reordered):
            with self.assertRaises((AssertionError,ValueError)):
                self._check(mutated)


if __name__=='__main__':
    unittest.main(verbosity=2)
