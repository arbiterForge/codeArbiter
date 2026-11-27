import pathlib,sys,importlib.util,unittest,json,hashlib,copy
root=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2])
spec=importlib.util.spec_from_file_location('test_wire_statusline',root/'plugins/ca/hooks/tests/test_wire_statusline.py')
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
selectors=json.loads((out/'selectors.json').read_text())
class RefreshWholeRowPreservation(module._WireStatuslineTest):
 setUp=module.TestRefreshStalePathOnSessionStart.setUp
 tearDown=module.TestRefreshStalePathOnSessionStart.tearDown
 def test_refresh_preserves_spinner_backups_and_unrelated_settings(self):
  ws=module.ws
  before={'statusLine':{'type':'command','command':self.stale_cmd},ws.OWNER_KEY:self.stale_cmd,
   ws.BACKUP_KEY:{'type':'command','command':'prior-safe-line','padding':17},
   'spinnerVerbs':{'mode':'replace','verbs':['private-custom-spinner']},
   ws.SPINNER_BACKUP_KEY:{'mode':'append','verbs':['private-prior-spinner']},
   ws.SPINNER_OWNER_KEY:{'mode':'replace','verbs':['old-owned-spinner']},
   'theme':'private-theme','permissions':{'allow':['private-inert-entry']},'nested':{'unchanged':[1,True,None]}}
  self.settings=module._make_settings(self.tmp.name,copy.deepcopy(before))
  ws.main(['refresh','--settings',self.settings,'--plugin-root',self.root,'--interp','python'])
  after=module._read(self.settings);expected_command=ws.build_command('python',self.script_abs)
  expected=copy.deepcopy(before);expected['statusLine']=ws.owned_statusline(expected_command);expected[ws.OWNER_KEY]=expected_command
  self.assertNotEqual(before['statusLine'],after['statusLine']);self.assertEqual(after,expected)
  (out/'whole-row-preservation.json').write_text(json.dumps({'source_entry':'ws.main(refresh)','before':before,'after':after,'exact_expected':expected,'only_changed_top_level_keys':sorted(k for k in before if before[k]!=after[k]),'exact_preservation_assertion':after==expected},indent=2)+'\n',encoding='utf8',newline='\n')
class Recorded(unittest.TextTestResult):
 def __init__(self,*a,**kw):super().__init__(*a,**kw);self.observed=[]
 def addSuccess(self,test):super().addSuccess(test);self.observed.append({'id':test.id(),'outcome':'PASS'})
 def addFailure(self,test,err):super().addFailure(test,err);self.observed.append({'id':test.id(),'outcome':'FAIL'})
 def addError(self,test,err):super().addError(test,err);self.observed.append({'id':test.id(),'outcome':'ERROR'})
 def addSkip(self,test,why):super().addSkip(test,why);self.observed.append({'id':test.id(),'outcome':'SKIP'})
suite=unittest.TestLoader().loadTestsFromNames([name.removeprefix('test_wire_statusline.') for name in selectors],module);suite.addTest(RefreshWholeRowPreservation('test_refresh_preserves_spinner_backups_and_unrelated_settings'))
result=unittest.TextTestRunner(verbosity=2,resultclass=Recorded).run(suite)
(out/'named-results.json').write_text(json.dumps({'run':result.testsRun,'outcomes':result.observed,'success':result.wasSuccessful()},indent=2)+'\n',encoding='utf8',newline='\n')
sys.exit(0 if result.wasSuccessful() and result.testsRun==10 else 1)
