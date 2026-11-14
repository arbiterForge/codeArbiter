"""A failed contract refresh cannot truncate or publish an invalid runtime owner."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
spec = importlib.util.spec_from_file_location("recovery_generator", ROOT / "tools/build-workflow-recovery-contract.py")
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class RecoveryGeneratorTest(unittest.TestCase):
    def setUp(self):
        owner = tempfile.TemporaryDirectory(prefix="ca-recovery-generator-")
        self.addCleanup(owner.cleanup)
        self.root = Path(owner.name).resolve()
        self.target = self.root / "core/pysrc/_workflowrecoverylib.py"
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes((ROOT / "core/pysrc/_workflowrecoverylib.py").read_bytes())
        contract = self.root / "core/workflow-recovery-contract.json"
        value = json.loads((ROOT / "core/workflow-recovery-contract.json").read_text())
        value["generator_fixture"] = "A deliberate temporary source refresh"
        contract.write_text(json.dumps(value))
        patch = mock.patch.multiple(generator, REPO=self.root, CONTRACT=contract, TARGET=self.target)
        patch.start()
        self.addCleanup(patch.stop)

    def test_partial_write_failure_preserves_complete_prior_owner(self):
        before = self.target.read_bytes()
        text, binary = Path.write_text, Path.write_bytes

        def fail(path, data):
            with path.open("wb") as stream:
                stream.write(data[:16])
                stream.flush()
            raise OSError("controlled partial generator write")

        def write_text(path, data, *args, **kwargs):
            if path == self.target:
                return fail(path, data.encode("utf-8"))
            return text(path, data, *args, **kwargs)

        def write_bytes(path, data):
            if path.name.endswith(".new"):
                return fail(path, data)
            return binary(path, data)

        with mock.patch.object(Path, "write_text", write_text), mock.patch.object(Path, "write_bytes", write_bytes):
            with self.assertRaisesRegex(OSError, "controlled partial"):
                generator.main([])
        self.assertEqual(self.target.read_bytes(), before)
        self.assertEqual(generator.main([]), 0)
        self.assertEqual(generator.main(["--check"]), 0)

    def test_invalid_python_is_refused_before_any_publication(self):
        self.target.write_bytes(self.target.read_bytes() + b"\ndef invalid(\n")
        before = self.target.read_bytes()
        with self.assertRaises(SyntaxError):
            generator.main([])
        self.assertEqual(self.target.read_bytes(), before)

    def test_pending_generator_marker_cannot_be_labeled_current(self):
        marker = self.root / ".generated-other-owner.lock"
        marker.write_text("pending; do not consume")
        before = self.target.read_bytes()
        with self.assertRaises(OSError):
            generator.main(["--check"])
        self.assertEqual(self.target.read_bytes(), before)
        self.assertEqual(marker.read_text(), "pending; do not consume")


if __name__ == "__main__":
    unittest.main()
