from pathlib import Path
import ast,importlib.util,sys,unittest
R=Path('C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter')
O=Path(__file__).resolve().parent
sys.path.insert(0,str(R/'.github/scripts'))
spec=importlib.util.spec_from_file_location('site_ci_contract_owner',R/'.github/scripts/test_ci_impact.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
# Execute the exact candidate class with the unchanged existing owner helpers.
tree=ast.parse((O/'candidate/.github/scripts/test_ci_impact.py').read_text(encoding='utf8'))
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='SiteBrowserPublicationWorkflowTest')
exec(compile(ast.Module(body=[cls],type_ignores=[]),str(O/'candidate/.github/scripts/test_ci_impact.py'),'exec'),module.__dict__)
module.REPO_ROOT=O/'candidate';module.DOCS_WORKFLOW=O/'candidate/.github/workflows/docs.yml'
names=sys.argv[1:] or ['test_component_suite_is_discovered_and_success_gates_pages_upload']
suite=unittest.TestSuite(module.SiteBrowserPublicationWorkflowTest(n) for n in names)
result=unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
