"""Fault injection against the actual bounded generated-output publisher."""
import importlib.util
from pathlib import Path
import os
import sys
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from owned_output import publish_files, assert_complete

class GeneratedOutputTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.a=self.root/'a';self.b=self.root/'b'
        self.a.write_bytes(b'old-a');self.b.write_bytes(b'old-b')
    def test_late_stage_failure_preserves_old_complete_set(self):
        with self.assertRaises(TypeError): publish_files(self.root,'test',{self.a:b'new',self.b:None})
        self.assertEqual(self.a.read_bytes(),b'old-a');self.assertEqual(self.b.read_bytes(),b'old-b')
        assert_complete(self.root,'test')
    def test_late_rename_failure_rolls_back_and_clean_rerun_converges(self):
        real=os.replace
        def fail(src,dst):
            if Path(dst)==self.b and str(src).endswith('.new'):raise OSError('controlled rename')
            return real(src,dst)
        with mock.patch('os.replace',side_effect=fail),self.assertRaisesRegex(OSError,'controlled'):
            publish_files(self.root,'test',{self.a:b'new-a',self.b:b'new-b'})
        self.assertEqual(self.a.read_bytes(),b'old-a');self.assertEqual(self.b.read_bytes(),b'old-b')
        assert_complete(self.root,'test')
        publish_files(self.root,'test',{self.a:b'new-a',self.b:b'new-b'})
        self.assertEqual(self.a.read_bytes(),b'new-a');self.assertEqual(self.b.read_bytes(),b'new-b')
    def test_rollback_failure_retains_explicit_unusable_marker_and_journal(self):
        real=os.replace
        def fail(src,dst):
            if Path(dst)==self.b or Path(src).name=='rollback':raise OSError('controlled recovery failure')
            return real(src,dst)
        with mock.patch('os.replace',side_effect=fail),self.assertRaises(OSError):
            publish_files(self.root,'test',{self.a:b'new-a',self.b:b'new-b'})
        with self.assertRaisesRegex(OSError,'incomplete'): assert_complete(self.root,'test')
        journal=Path((self.root/'.generated-test.lock').read_text())
        self.assertTrue((journal/'journal.json').is_file())
    def test_concurrent_writer_refuses_without_deleting_other_marker(self):
        marker=self.root/'.generated-test.lock';marker.write_text('other owner')
        with self.assertRaises(FileExistsError): publish_files(self.root,'test',{self.a:b'new'})
        self.assertEqual(marker.read_text(),'other owner');self.assertEqual(self.a.read_bytes(),b'old-a')
    def test_foreign_target_refuses_and_handwritten_files_survive(self):
        with self.assertRaisesRegex(OSError,'escapes'): publish_files(self.root,'test',{self.root.parent/'foreign':b'bad'})
        publish_files(self.root,'test',{self.a:b'new'})
        self.assertEqual(self.b.read_bytes(),b'old-b')
    @unittest.skipUnless(os.name == 'nt', 'requires a real Windows junction')
    def test_windows_junction_ancestor_and_owner_refuse_before_any_effect(self):
        outside = tempfile.TemporaryDirectory();self.addCleanup(outside.cleanup)
        foreign = Path(outside.name)/'keep';foreign.write_bytes(b'outside')
        linked = self.root/'linked'
        subprocess.run(['cmd','/d','/c','mklink','/J',str(linked),outside.name],capture_output=True,check=True)
        self.assertFalse(linked.is_symlink(), 'fixture must cover junctions missed by is_symlink')
        for owner, target in [(self.root,linked/'keep'), (linked,linked/'keep')]:
            with self.subTest(owner=owner), self.assertRaisesRegex(OSError, 'reparse'):
                publish_files(owner,'test',{target:b'bad'})
            self.assertEqual(foreign.read_bytes(),b'outside')
            self.assertFalse((Path(outside.name)/'.generated-test.lock').exists())
        # Remove only the link itself; do not walk its destination at cleanup.
        linked.rmdir()

    def test_contract_generator_rename_failure_preserves_importable_canonical_helper(self):
        spec=importlib.util.spec_from_file_location('manifest_generator',ROOT/'tools/build-artifact-manifest-contract.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        contract=self.root/'core/artifact-release-manifest.json';contract.parent.mkdir()
        import json
        value=json.loads((ROOT/'core/artifact-release-manifest.json').read_text(encoding='utf8'))
        value['workflow']='changed-workflow';contract.write_text(json.dumps(value),encoding='utf8')
        target=self.root/'core/pysrc/_artifactmanifestlib.py';target.parent.mkdir()
        target.write_bytes((ROOT/'core/pysrc/_artifactmanifestlib.py').read_bytes())
        previous=target.read_bytes()
        real=os.replace
        def fail(src,dst):
            if Path(dst)==target:raise OSError('controlled contract rename failure')
            return real(src,dst)
        with mock.patch.object(module,'ROOT',self.root),mock.patch.object(sys,'argv',['generator']),mock.patch('os.replace',side_effect=fail):
            with self.assertRaisesRegex(OSError,'controlled contract'):module.main()
        self.assertEqual(target.read_bytes(),previous)
        with mock.patch.object(module,'ROOT',self.root),mock.patch.object(sys,'argv',['generator']):
            self.assertEqual(module.main(),0)
        compile(target.read_bytes(),str(target),'exec')
        self.assertNotEqual(target.read_bytes(),previous)

    def test_consumers_refuse_any_pending_contract_publication(self):
        (self.root/'.generated-artifact-manifest-contract.lock').write_text('interrupted')
        for consumer in ['core','surface']:
            with self.assertRaisesRegex(OSError,'incomplete'):assert_complete(self.root,consumer)

    def test_surface_write_success_changes_only_owned_drift_and_preserves_equal_files(self):
        spec=importlib.util.spec_from_file_location('surface_success',ROOT/'tools/build-surface.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        # Supply the already-rendered map at the rendering boundary; ownership
        # enumeration, equality checks, transactional publication and deletion
        # below are the real implementations operating on private files.
        descriptor=SimpleNamespace(name='fixture',plugin_dir='plugin',
            managed_subtrees=('generated',),catalog=None)
        plugin=self.root/'plugin';generated=plugin/'generated';generated.mkdir(parents=True)
        changed=generated/'changed.md';equal=generated/'equal.md';orphan=generated/'orphan.md'
        changed.write_bytes(b'old changed');equal.write_bytes(b'keep equal');orphan.write_bytes(b'owned orphan')
        handwritten=plugin/'handwritten.md';handwritten.write_bytes(b'handwritten keep')
        foreign=self.root/'foreign'/'generated'/'keep.md';foreign.parent.mkdir(parents=True);foreign.write_bytes(b'foreign keep')
        same=equal.stat();equal_identity=(same.st_dev,same.st_ino,same.st_mtime_ns,same.st_size)
        expected={'generated/changed.md':b'new changed','generated/equal.md':b'keep equal'}
        with mock.patch.object(module,'load_host_descriptors',return_value=(descriptor,)), \
             mock.patch.object(module,'render_all',return_value=expected) as render:
            self.assertEqual(module.write_all(str(self.root),hosts=('fixture',)),2)
        render.assert_called_once_with(str(self.root),'fixture',descriptors=(descriptor,))
        self.assertEqual(changed.read_bytes(),b'new changed')
        self.assertEqual(equal.read_bytes(),b'keep equal')
        same=equal.stat();self.assertEqual((same.st_dev,same.st_ino,same.st_mtime_ns,same.st_size),equal_identity)
        self.assertFalse(orphan.exists())
        self.assertEqual(handwritten.read_bytes(),b'handwritten keep')
        self.assertEqual(foreign.read_bytes(),b'foreign keep')
        self.assertEqual({p.relative_to(self.root).as_posix() for p in self.root.rglob('*') if p.is_file()},
            {'a','b','plugin/generated/changed.md','plugin/generated/equal.md',
             'plugin/handwritten.md','foreign/generated/keep.md'})
        assert_complete(self.root,'surface')

    def test_second_host_render_failure_has_no_first_host_effect(self):
        spec=importlib.util.spec_from_file_location('surface_fault',ROOT/'tools/build-surface.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        hosts=[SimpleNamespace(name=n,plugin_dir=n) for n in ['one','two']]
        target=self.root/'one/page';target.parent.mkdir();target.write_bytes(b'old')
        with mock.patch.object(module,'load_host_descriptors',return_value=hosts), mock.patch.object(module,'_disk_files',return_value={'page'}), mock.patch.object(module,'render_all',side_effect=[{'page':b'new'},module.SurfaceError('late render')]):
            with self.assertRaisesRegex(module.SurfaceError,'late render'):module.write_all(str(self.root))
        self.assertEqual(target.read_bytes(),b'old')

    def test_package_source_gate_refuses_pending_publication_before_git(self):
        spec = importlib.util.spec_from_file_location(
            'owned_package_generation_gate', ROOT / 'tools/build-host-packages.py')
        package = importlib.util.module_from_spec(spec)
        previous = sys.modules.get(spec.name)
        sys.modules[spec.name] = package
        self.addCleanup(lambda: sys.modules.pop(spec.name, None) if previous is None
                        else sys.modules.__setitem__(spec.name, previous))
        spec.loader.exec_module(package)
        for namespace in ('core', 'surface', 'artifact-manifest-contract'):
            marker = self.root / ('.generated-' + namespace + '.lock')
            with marker.open('x', encoding='utf8') as stream:
                stream.write('owned interrupted publication fixture')
            before = {p.relative_to(self.root).as_posix(): p.read_bytes()
                      for p in self.root.rglob('*') if p.is_file()}
            try:
                with self.subTest(namespace=namespace), \
                     mock.patch.object(package, '_git_package_output',
                                       side_effect=AssertionError('Git must not run for pending output')) as git:
                    with self.assertRaisesRegex(OSError, 'incomplete'):
                        package._source_identity(self.root, 'a' * 40)
                    git.assert_not_called()
                self.assertEqual(before, {p.relative_to(self.root).as_posix(): p.read_bytes()
                                          for p in self.root.rglob('*') if p.is_file()})
            finally:
                marker.unlink()

if __name__=='__main__':unittest.main()
