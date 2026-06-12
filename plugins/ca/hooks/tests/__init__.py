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
