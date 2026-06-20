# Minimal ca-sandbox python fixture entry point (AC-06).
#
# It imports a REAL dependency (six) installed out-of-tree at
# /deps/site-packages (PYTHONPATH) and prints a marker carrying:
#   - DEP_OK=<bool> : that the baked dep resolved at runtime (import succeeded
#     and a known attribute is present), and
#   - SRC=<tag>     : a source-version tag the layering test edits IN the volume
#     to prove the in-place edit takes effect on re-run.
#
# The layering test seeds a named volume with this file, runs it once (expects
# SRC=original + DEP_OK=True), then rewrites SRC in the volume and re-runs
# (expects SRC=edited + DEP_OK=True — deps survive the edit).
import six

SRC = "original"
DEP_OK = hasattr(six, "__version__") and six.PY3 is True

print(f"PY_FIXTURE SRC={SRC} DEP_OK={DEP_OK}")
