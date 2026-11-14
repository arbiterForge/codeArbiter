"""Observe exactly three missing existing C33 methods; no fixture or product rewrite."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
repo, output = Path(sys.argv[1]), Path(sys.argv[2])
selected = json.loads((output / "selectors.json").read_bytes())
assert len(selected) == len(set(selected)) == 3
assert Path.home() == output / "private-home"
assert Path(tempfile.gettempdir()) == output / "fixtures"
assert sys.pycache_prefix == str(output / "private-home/.pycache")
assert not any(os.environ.get(k) for k in ("PYTHONPATH", "GITHUB_ACTIONS", "FARM_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"))

sys.path.insert(0, str(repo / ".github/scripts"))
spec = importlib.util.spec_from_file_location("test_check_skill_proof_fresh", repo / ".github/scripts/test_check_skill_proof_fresh.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class Recorded(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.observed = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.observed.append({"id": test.id(), "outcome": "PASS"})

    def addFailure(self, test, error):
        super().addFailure(test, error)
        self.observed.append({"id": test.id(), "outcome": "FAIL"})

    def addError(self, test, error):
        super().addError(test, error)
        self.observed.append({"id": test.id(), "outcome": "ERROR"})

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.observed.append({"id": test.id(), "outcome": "SKIP", "reason": reason})


suite = unittest.TestLoader().loadTestsFromNames(selected, module)
result = unittest.TextTestRunner(verbosity=2, resultclass=Recorded).run(suite)
loaded = {}
for name, imported in list(sys.modules.items()):
    path = getattr(imported, "__file__", None)
    if path:
        path = Path(path).resolve()
        if path.is_relative_to(repo):
            loaded[name] = {"path": path.relative_to(repo).as_posix(),
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
observation = {"source_commit": sys.argv[3], "reference_scope_commit": "46e29a796e89e0eaa3250cf171e4c9bea97ac437",
               "tests_run": result.testsRun, "outcomes": result.observed,
               "success": result.wasSuccessful(), "loaded_repo_modules": loaded,
               "actual_host_lookup": {"owner": "check_skill_proof_fresh.full_prose_release_skill_payloads",
                   "source": "tools/host_descriptors.py:load_host_descriptors",
                   "positive_registry": "core/hosts.json",
                   "positive_tool_module": "tools/host_descriptors.py",
                   "no_hostapi_adapter_lookup_claim": True},
               "python": {"executable": sys.executable, "version": sys.version},
               "home": str(Path.home()), "temp": tempfile.gettempdir(),
               "pycache_prefix": sys.pycache_prefix}
with (output / "actual-result.json").open("x", encoding="utf8", newline="\n") as stream:
    json.dump(observation, stream, indent=2)
    stream.write("\n")
    stream.flush()
    os.fsync(stream.fileno())
raise SystemExit(0 if result.wasSuccessful() else 1)
