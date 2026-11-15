import pathlib,sys,importlib.util,unittest,json,tempfile,builtins
from unittest import mock
root=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);mods={}
for name in ('test_durabilitylib','test_wire_statusline','test_atomic_writes'):
 spec=importlib.util.spec_from_file_location(name,root/'plugins/ca/hooks/tests'/(name+'.py'));m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);mods[name]=m
selectors=json.loads((out/'selectors.json').read_text())
suite=unittest.TestSuite()
for name in selectors:
 mod,cls,method=name.split('.');case=getattr(mods[mod],cls)(method)
 assert isinstance(case,unittest.TestCase) and case.id()==name and callable(getattr(case,method))
 suite.addTest(case)
assert suite.countTestCases()==35
(out/'validated-selection.json').write_text(json.dumps({'validated_existing_test_ids':selectors,'unique':35,'loader_failed_tests':0},indent=2)+'\n',encoding='utf8',newline='\n')
dl=mods['test_durabilitylib'].dl
class PrivateDurabilityBoundaries(unittest.TestCase):
 def record(self,name,value):
  p=out/'private-controls.json';d=json.loads(p.read_text()) if p.exists() else {};d[name]=value;p.write_text(json.dumps(d,indent=2)+'\n',encoding='utf8',newline='\n')
 def test_permission_error_falls_back_durable_without_acl_mutation(self):
  with tempfile.TemporaryDirectory(prefix='p-') as tmp:
   folder=pathlib.Path(tmp);marker=folder/'.git';marker.write_text('gitdir: /fixed/.git/worktrees/owned-private\n',encoding='utf8');hooks=folder/'hooks';hooks.mkdir()
   self.assertTrue(dl.in_linked_worktree(str(hooks)))
   with mock.patch.object(dl,'open',side_effect=PermissionError('private injected refusal'),create=True) as injected:
    self.assertFalse(dl.in_linked_worktree(str(hooks)));self.assertFalse(dl.is_ephemeral_path(str(hooks)));self.assertEqual(injected.call_count,2)
    self.assertTrue(all(pathlib.Path(call.args[0])==marker for call in injected.call_args_list))
   self.record('permission_error',{'in_bound_positive_detected':True,'two_injected_open_refusals_durable':True,'os_acl_mutated':False})
 def test_ancestor_limit_excludes_only_marker_just_outside_64(self):
  with tempfile.TemporaryDirectory(prefix='b-') as tmp:
   folder=pathlib.Path(tmp);(folder/'.git').write_text('gitdir: /fixed/.git/worktrees/owned-private\n',encoding='utf8');deep=folder
   for _ in range(64):deep=deep/'d';deep.mkdir()
   walked=list(dl._ancestors(str(deep)));self.assertEqual(dl.MAX_ANCESTOR_WALK,64);self.assertEqual(len(walked),64);self.assertNotIn(str(folder),walked)
   self.assertFalse(dl.in_linked_worktree(str(deep)));self.assertFalse(dl.is_ephemeral_path(str(deep)))
   self.assertTrue(dl.in_linked_worktree(str(deep.parent)))
   self.record('ancestor_limit',{'actual_nested_directories':64,'actual_enumerated_ancestors':len(walked),'marker_just_outside_bound_durable':True,'same_marker_one_level_inside_detected':True})
 def test_gitfile_read_caps_at_4096_with_worktree_suffix_beyond_bound(self):
  with tempfile.TemporaryDirectory(prefix='r-') as tmp:
   folder=pathlib.Path(tmp);marker=folder/'.git';data=b'gitdir: /'+b'x'*4096+b'/worktrees/owned-private\n';marker.write_bytes(data);offset=data.index(b'/worktrees/');self.assertGreaterEqual(offset,4096)
   reads=[]
   class ActualFile:
    def __init__(self,*a,**kw):self.file=builtins.open(*a,**kw)
    def __enter__(self):return self
    def read(self,n=-1):reads.append(n);return self.file.read(n)
    def __exit__(self,*a):self.file.close()
   with mock.patch.object(dl,'open',side_effect=ActualFile,create=True):self.assertFalse(dl.in_linked_worktree(str(folder)))
   self.assertEqual(dl.GITFILE_READ_BYTES,4096);self.assertEqual(reads,[4096])
   marker.write_bytes(b'gitdir: /fixed/.git/worktrees/owned-private\n');self.assertTrue(dl.in_linked_worktree(str(folder)))
   self.record('gitfile_read_cap',{'actual_read_requests':reads,'target_suffix_offset':offset,'suffix_beyond_bound_durable':True,'short_in_bound_marker_detected':True})
for n in ('test_permission_error_falls_back_durable_without_acl_mutation','test_ancestor_limit_excludes_only_marker_just_outside_64','test_gitfile_read_caps_at_4096_with_worktree_suffix_beyond_bound'):suite.addTest(PrivateDurabilityBoundaries(n))
class Recorded(unittest.TextTestResult):
 def __init__(self,*a,**kw):super().__init__(*a,**kw);self.observed=[]
 def addSuccess(self,test):super().addSuccess(test);self.observed.append({'id':test.id(),'outcome':'PASS'})
 def addFailure(self,test,err):super().addFailure(test,err);self.observed.append({'id':test.id(),'outcome':'FAIL'})
 def addError(self,test,err):super().addError(test,err);self.observed.append({'id':test.id(),'outcome':'ERROR'})
 def addSkip(self,test,why):super().addSkip(test,why);self.observed.append({'id':test.id(),'outcome':'SKIP'})
assert suite.countTestCases()==38
result=unittest.TextTestRunner(verbosity=2,resultclass=Recorded,failfast=True).run(suite)
(out/'named-results.json').write_text(json.dumps({'run':result.testsRun,'outcomes':result.observed,'success':result.wasSuccessful()},indent=2)+'\n',encoding='utf8',newline='\n')
sys.exit(0 if result.wasSuccessful() and result.testsRun==38 else 1)
