# codeArbiter pruner test package.
#
# Run from the repo root (or anywhere):
#     python3 -m unittest discover -s plugins/ca/hooks/tests -v
#
# Tests import _prunelib via the sys.path insert below (same idiom the hooks use
# for _hooklib). Stdlib unittest only — no third-party test runner, matching the
# "stock interpreter" constraint on the hook layer.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Strip the live harness's project signal for the whole suite. project_root()
# trusts CLAUDE_PROJECT_DIR first, so a value leaking in from the Claude
# session that runs the suite would point every spawned hook at the
# developer's real repo instead of the test's fixture repo. With the variable
# absent, hooks fall back to `git rev-parse --show-toplevel` from the fixture
# cwd — the pre-existing behavior the fixtures were written against. Fixtures
# that want the production-shaped path pin the variable themselves
# (test_pre_bash_activation._sh).
os.environ.pop("CLAUDE_PROJECT_DIR", None)
