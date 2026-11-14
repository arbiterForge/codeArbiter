from pathlib import Path
import ast, hashlib, io, json, linecache, os, subprocess, sys, time, types, unittest

OUT = Path(__file__).resolve().parent
ROOT = Path('C:/Users/brenn/.codex/worktrees/program-governance-prep/codeArbiter')
TEST = '.github/scripts/test_work_github.py'
REGISTRY = '.github/scripts/test_artifact_conformance.py'
SOURCE = ROOT / 'core/pysrc/_workgithub.py'
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
assert sha(SOURCE) == '79a1ce36cc360eb1eb095b45ab08ecc50c50fe10670dc10e2d9c5cd21be8ca1f'
assert sha(ROOT / TEST) == sha(OUT / 'baseline' / TEST)
assert sha(ROOT / REGISTRY) == sha(OUT / 'baseline' / REGISTRY)
def methods(path):
    tree = ast.parse(path.read_bytes())
    return {node.name: ast.dump(node, include_attributes=False)
            for cls in tree.body if isinstance(cls, ast.ClassDef)
            for node in cls.body if isinstance(node, ast.FunctionDef) and node.name.startswith('test_')}
old = methods(OUT / 'baseline' / TEST)
new = methods(OUT / 'candidate' / TEST)
added = sorted(set(new) - set(old))
assert len(old) == 77 and len(new) == 79 and len(added) == 2
assert all(new[name] == value for name, value in old.items())
def registry(path):
    tree = ast.parse(path.read_bytes())
    return ast.literal_eval(next(node.value for node in tree.body
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'EXPECTED_SUITES'
                                               for t in node.targets)))
before = registry(OUT / 'baseline' / REGISTRY)
after = registry(OUT / 'candidate' / REGISTRY)
assert before[Path(TEST).name] == set(old)
assert after[Path(TEST).name] == set(new)
assert {k:v for k,v in before.items() if k != Path(TEST).name} == {
    k:v for k,v in after.items() if k != Path(TEST).name}
sys.path.insert(0, str(ROOT / '.github/scripts'))
sys.path.insert(0, str(ROOT / 'core/pysrc'))
raw = (OUT / 'candidate' / TEST).read_bytes()
module = types.ModuleType('test_work_github')
module.__file__ = str(ROOT / TEST)
sys.modules[module.__name__] = module
linecache.cache[module.__file__] = (len(raw), None, raw.decode().splitlines(keepends=True), module.__file__)
exec(compile(raw, module.__file__, 'exec'), module.__dict__)
names = ['GithubWorkTest.test_mapped_preclaim_transport_failure_keeps_pending_and_continues_independent_target']
names += ['GithubWorkTest.' + name for name in added]
suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name, module) for name in names)
counts = {}
def trace(frame, event, arg):
    if event == 'line' and frame.f_code.co_filename == str(SOURCE):
        number = str(frame.f_lineno)
        counts[number] = counts.get(number, 0) + 1
    return trace
stream = io.StringIO()
start = time.monotonic()
sys.settrace(trace)
try:
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
finally:
    sys.settrace(None)
elapsed = time.monotonic() - start
log = stream.getvalue().encode()
(OUT / 'actual-focused.log').write_bytes(log)
record = {'tests': names, 'tests_run': result.testsRun, 'failures': len(result.failures),
          'errors': len(result.errors), 'skipped': len(result.skipped), 'successful': result.wasSuccessful(),
          'seconds': elapsed, 'source_sha256': sha(SOURCE), 'test_sha256': sha(OUT / 'candidate' / TEST),
          'registry_sha256': sha(OUT / 'candidate' / REGISTRY), 'log_sha256': hashlib.sha256(log).hexdigest(),
          'baseline_methods_preserved': len(old), 'candidate_methods': len(new),
          'strict_inventory_exact': True, 'source_line_hits': counts,
          'native_fixture_build': 'Existing build_installation once in GithubWorkTest.setUpClass; no supplied installation',
          'scope': 'Ordinary controlled native fixture plus fake transport. No live provider, installed host, or platform cohort qualification.'}
(OUT / 'actual-focused.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf8')
print(log.decode())
print(json.dumps({k:v for k,v in record.items() if k != 'source_line_hits'}))
raise SystemExit(0 if result.wasSuccessful() else 1)
