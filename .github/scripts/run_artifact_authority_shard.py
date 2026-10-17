"""Run a deterministic, exhaustive half of the native authority adapter suite."""
import importlib.util
import os
from pathlib import Path
import unittest


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def main():
    shard = int(os.environ["AUTHORITY_SHARD"])
    if shard not in (0, 1):
        raise SystemExit("AUTHORITY_SHARD must be 0 or 1")
    path = Path(__file__).with_name("test_artifact_authority_adapter.py")
    spec = importlib.util.spec_from_file_location("test_artifact_authority_adapter", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cases = sorted(flatten(unittest.defaultTestLoader.loadTestsFromModule(module)), key=lambda t: t.id())
    if not cases:
        raise SystemExit("authority suite discovered zero tests")
    # Sorted contiguous halves provide stable coverage without hardcoded test names.
    midpoint = (len(cases) + 1) // 2
    selected = cases[:midpoint] if shard == 0 else cases[midpoint:]
    if not selected:
        raise SystemExit("authority shard discovered zero tests")
    print(f"authority shard {shard}: {len(selected)} of {len(cases)} tests", flush=True)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(selected))
    if not result.wasSuccessful() or result.testsRun != len(selected):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
