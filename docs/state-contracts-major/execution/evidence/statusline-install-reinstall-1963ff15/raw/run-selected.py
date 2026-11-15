"""Exactly three private main-based software characterizations; no live host."""
import contextlib,copy,hashlib,importlib.util,io,json,os,pathlib,sys,tempfile,unittest
from unittest import mock
ROOT=pathlib.Path(sys.argv[1]);OUT=pathlib.Path(sys.argv[2])
spec=importlib.util.spec_from_file_location('test_wire_statusline',ROOT/'plugins/ca/hooks/tests/test_wire_statusline.py')
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
ws=module.ws
class PrivateInstallJourney(module._WireStatuslineTest):
 def setUp(self):
  self.owned=tempfile.TemporaryDirectory(prefix='statusline-owned-')
  self.base=pathlib.Path(self.owned.name)
  self.root=module._make_plugin_root(str(self.base))
  self.spinner=copy.deepcopy(ws.ARBITER_SPINNER_VERBS)
  self.readbacks=[]
 def tearDown(self):
  path=OUT/(self._testMethodName+'.readbacks.json')
  path.write_text(json.dumps({'method':self.id(),'observations':self.readbacks},indent=2)+'\n',encoding='utf8',newline='\n')
  self.owned.cleanup()
 def write(self,value,folder=None):
  self.settings=module._make_settings(str(folder or self.base),copy.deepcopy(value))
 def read(self):return module._read(self.settings)
 def snapshot(self,folder):
  return {p.relative_to(folder).as_posix():('directory' if p.is_dir() else hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(folder.rglob('*'))}
 def command(self):return '"python" "'+os.path.realpath(os.path.join(self.root,'hooks','statusline.py'))+'"'
 def invoke(self,action,requested=None):
  output=io.StringIO()
  with contextlib.redirect_stdout(output):ws.main([action,'--settings',self.settings,'--plugin-root',requested or self.root,'--interp','python'])
  return hashlib.sha256(output.getvalue().encode()).hexdigest()
 def compare(self,label,expected):
  actual=self.read();self.readbacks.append({'phase':label,'actual':actual,'expected':copy.deepcopy(expected),'whole_object_equal':actual==expected})
  self.assertEqual(actual,expected)
 def test_install_reinstall_user_takeover_and_restore_preserves_whole_settings(self):
  prior_line={'type':'command','command':'private-first-line --theme','padding':7,'extra':{'keep':[1,2]}}
  prior_spinner={'mode':'append','verbs':['private-first-spinner']}
  original={'statusLine':prior_line,'spinnerVerbs':prior_spinner,'theme':'private-theme','nested':{'unchanged':[1,True,None]}}
  self.write(original);self.invoke('install')
  expected=copy.deepcopy(original)
  expected.update(statusLine={'type':'command','command':self.command(),'padding':0},spinnerVerbs=self.spinner)
  expected[ws.BACKUP_KEY]=copy.deepcopy(prior_line);expected[ws.OWNER_KEY]=self.command()
  expected[ws.SPINNER_BACKUP_KEY]=copy.deepcopy(prior_spinner);expected[ws.SPINNER_OWNER_KEY]=copy.deepcopy(self.spinner)
  self.compare('foreign-install-exact-backups-and-owned-values',expected)
  old_command=self.command();self.root=module._make_plugin_root(str(self.base/'second-durable-version'));self.assertNotEqual(self.command(),old_command)
  self.invoke('install');expected['statusLine']={'type':'command','command':self.command(),'padding':0};expected[ws.OWNER_KEY]=self.command()
  self.compare('owned-reinstall-new-root-original-backups-survive',expected)
  user_line={'type':'command','command':'private-new-user-line','padding':11,'extra':{'new':True}}
  user_spinner={'mode':'append','verbs':['private-new-user-spinner']}
  user=copy.deepcopy(expected);user['statusLine']=copy.deepcopy(user_line);user['spinnerVerbs']=copy.deepcopy(user_spinner);self.write(user)
  raw=pathlib.Path(self.settings).read_bytes();self.invoke('refresh');self.assertEqual(pathlib.Path(self.settings).read_bytes(),raw)
  self.compare('automatic-refresh-does-not-take-over-user-choice',user)
  self.invoke('install');takeover=copy.deepcopy(user)
  takeover.update(statusLine={'type':'command','command':self.command(),'padding':0},spinnerVerbs=self.spinner)
  takeover[ws.BACKUP_KEY]=copy.deepcopy(user_line);takeover[ws.OWNER_KEY]=self.command()
  takeover[ws.SPINNER_BACKUP_KEY]=copy.deepcopy(user_spinner);takeover[ws.SPINNER_OWNER_KEY]=copy.deepcopy(self.spinner)
  self.compare('explicit-reinstall-backs-up-current-user-choices',takeover)
  self.invoke('uninstall');restored=copy.deepcopy(original);restored['statusLine']=user_line;restored['spinnerVerbs']=user_spinner
  self.compare('uninstall-restores-new-user-choices-exactly',restored)
 def test_legacy_source_and_cache_reinstall_preserves_original_backup(self):
  variants={
   'source':'"python" "C:\\src\\codeArbiter\\plugins\\ca\\hooks\\statusline.py"',
   'cache':'"python" "C:\\Users\\fixture\\.claude\\plugins\\cache\\codearbiter\\ca\\1.0.0\\hooks\\statusline.py"',
  }
  for kind,legacy in variants.items():
   with self.subTest(kind=kind):
    prior={'type':'command','command':'private-original-'+kind,'padding':8,'extra':{'keep':[1,2]}}
    original={'statusLine':{'type':'command','command':legacy},ws.BACKUP_KEY:copy.deepcopy(prior),'spinnerVerbs':copy.deepcopy(self.spinner),ws.SPINNER_OWNER_KEY:copy.deepcopy(self.spinner),ws.SPINNER_BACKUP_KEY:{'mode':'append','verbs':['private-original-spinner']},'nested':{'preserve':kind}}
    self.write(original,self.base/kind);self.invoke('install');expected=copy.deepcopy(original)
    expected['statusLine']={'type':'command','command':self.command(),'padding':0};expected[ws.OWNER_KEY]=self.command()
    self.compare(kind+'-recognized-legacy-preserves-original-backup',expected)
  foreign={'type':'command','command':'"python" "C:\\tools\\statusline.py"','padding':9,'extra':{'foreign':True}}
  stale_backup={'type':'command','command':'private-obsolete-backup'}
  before={'statusLine':foreign,ws.BACKUP_KEY:stale_backup,'spinnerVerbs':{'mode':'append','verbs':['private-current-spinner']},'nested':{'preserve':True}}
  self.write(before,self.base/'near-match');self.invoke('install');expected=copy.deepcopy(before)
  expected[ws.BACKUP_KEY]=copy.deepcopy(foreign);expected[ws.OWNER_KEY]=self.command()
  expected[ws.SPINNER_BACKUP_KEY]=copy.deepcopy(before['spinnerVerbs']);expected[ws.SPINNER_OWNER_KEY]=copy.deepcopy(self.spinner)
  expected['statusLine']={'type':'command','command':self.command(),'padding':0};expected['spinnerVerbs']=copy.deepcopy(self.spinner)
  self.compare('near-match-foreign-live-choice-replaces-obsolete-backup',expected)
 def test_install_refusals_preserve_existing_settings(self):
  for kind in ('mismatched-root','missing-adapter','ephemeral-root','missing-renderer','invalid-json','unreadable-settings'):
   with self.subTest(kind=kind):
    folder=self.base/kind;folder.mkdir();self.root=module._make_plugin_root(str(folder))
    self.write({'statusLine':{'type':'command','command':'private-keep-line'},'spinnerVerbs':{'mode':'append','verbs':['private-keep-spinner']},'nested':{'unchanged':[1,None]}},folder)
    requested=self.root
    if kind=='mismatched-root':requested=module._make_plugin_root(str(folder/'foreign'))
    if kind=='ephemeral-root':self.root=module._make_worktree_plugin_root(str(folder));requested=self.root
    if kind=='missing-renderer':pathlib.Path(self.root,'hooks','statusline.py').unlink()
    if kind=='invalid-json':pathlib.Path(self.settings).write_bytes(b'{private-invalid-json')
    before_bytes=pathlib.Path(self.settings).read_bytes();before_tree=self.snapshot(folder)
    with contextlib.ExitStack() as stack:
     expected_error=SystemExit;injected=None
     if kind=='missing-adapter':
      expected_error=ws.hostapi.PluginRootError
      stack.enter_context(mock.patch.object(ws._hooklib,'get_host',side_effect=expected_error('private-missing-boundary')))
     if kind=='unreadable-settings':
      expected_error=PermissionError
      injected=stack.enter_context(mock.patch.object(ws,'open',side_effect=PermissionError('private-injected-read-refusal'),create=True))
     with self.assertRaises(expected_error) as caught:self.invoke('install',requested)
     if injected is not None:
      self.assertEqual(injected.call_count,1);self.assertEqual(pathlib.Path(injected.call_args.args[0]),pathlib.Path(self.settings))
    after_bytes=pathlib.Path(self.settings).read_bytes();after_tree=self.snapshot(folder)
    self.readbacks.append({'phase':kind,'error_type':type(caught.exception).__name__,'before_sha256':hashlib.sha256(before_bytes).hexdigest(),'after_sha256':hashlib.sha256(after_bytes).hexdigest(),'tree_before':before_tree,'tree_after':after_tree,'settings_bytes_unchanged':before_bytes==after_bytes,'tree_unchanged':before_tree==after_tree,'actual_OS_ACL_mutation':False})
    self.assertEqual(after_bytes,before_bytes);self.assertEqual(after_tree,before_tree)
METHODS=(
 'test_install_reinstall_user_takeover_and_restore_preserves_whole_settings',
 'test_legacy_source_and_cache_reinstall_preserves_original_backup',
 'test_install_refusals_preserve_existing_settings',
)
suite=unittest.TestSuite(PrivateInstallJourney(name) for name in METHODS)
assert suite.countTestCases()==3
assert all(case.id()=='__main__.PrivateInstallJourney.'+name for case,name in zip(suite,METHODS))
(OUT/'validated-selection.json').write_text(json.dumps({'ids':[case.id() for case in suite],'count':3,'no_original_test_methods_selected':True},indent=2)+'\n',encoding='utf8',newline='\n')
class Recorded(unittest.TextTestResult):
 def __init__(self,*a,**kw):super().__init__(*a,**kw);self.observed=[]
 def addSuccess(self,test):super().addSuccess(test);self.observed.append({'id':test.id(),'outcome':'PASS'})
 def addFailure(self,test,err):super().addFailure(test,err);self.observed.append({'id':test.id(),'outcome':'FAIL'})
 def addError(self,test,err):super().addError(test,err);self.observed.append({'id':test.id(),'outcome':'ERROR'})
 def addSkip(self,test,why):super().addSkip(test,why);self.observed.append({'id':test.id(),'outcome':'SKIP'})
result=unittest.TextTestRunner(verbosity=2,resultclass=Recorded,failfast=True).run(suite)
(OUT/'named-results.json').write_text(json.dumps({'run':result.testsRun,'outcomes':result.observed,'success':result.wasSuccessful()},indent=2)+'\n',encoding='utf8',newline='\n')
sys.exit(0 if result.wasSuccessful() and result.testsRun==3 else 1)
