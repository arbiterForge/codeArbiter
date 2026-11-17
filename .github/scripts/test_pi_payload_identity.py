"""HF03 actual payload predicate on owned files; no doctor/main/host probe."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "core/pysrc"
sys.path.insert(0, str(CORE))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


doctor = load("payload_identity_doctor", CORE / "doctor.py")
pi_owner = load("payload_identity_pi_host", ROOT / "plugins/ca-pi/hooks/_host.py")


class PiPayloadIdentityTest(unittest.TestCase):
    def setUp(self):
        self.owner = tempfile.TemporaryDirectory(prefix="ca-pi-payload-identity-")
        self.addCleanup(self.owner.cleanup)
        self.root = Path(self.owner.name)
        self.host = pi_owner.PiHost(str(self.root))
        self.source = json.loads((ROOT / "plugins/ca-pi/package.json").read_text(encoding="utf8"))
        self.saved = doctor.results[:]
        self.addCleanup(lambda: doctor.results.__setitem__(slice(None), self.saved))
        for name in doctor.HOOK_SCRIPTS + doctor.PI_BRIDGE_SCRIPTS:
            path = self.root / "hooks" / name
            path.parent.mkdir(exist_ok=True)
            path.write_text("# owned presence fixture\n", encoding="utf8")
        self.stop = mock.patch.object(doctor.subprocess, "run", side_effect=AssertionError("payload predicate must not launch"))
        self.stop.start()
        self.addCleanup(self.stop.stop)

    def check(self, value):
        (self.root / self.host.manifest_relpath()).write_text(json.dumps(value), encoding="utf8")
        doctor.results[:] = []
        doctor.check_payload(str(self.root), self.host)
        return doctor.results[:]

    def test_real_scoped_package_and_host_agree_without_a_probe(self):
        self.assertEqual(self.source["name"], self.host.adapter_name)
        self.assertTrue(self.source["name"].startswith("@"))
        rows = self.check(self.source)
        self.assertIn(("OK", "package.json declares only the ca-pi extension and generated skills"), rows)
        self.assertFalse(any(level == "FAIL" for level, _ in rows), rows)

    def test_missing_bare_foreign_prefix_and_wrong_type_identity_refuse(self):
        for name in (None, "", "ca-pi", "@other/ca-pi", "@arbiterforge/ca-pi-extra", 7, [], {}):
            with self.subTest(name=name):
                package = copy.deepcopy(self.source)
                if name is None:
                    package.pop("name")
                else:
                    package["name"] = name
                rows = self.check(package)
                self.assertTrue(any(level == "FAIL" and "package/discovery contract" in text for level, text in rows))
                self.assertNotIn(("OK", "package.json declares only the ca-pi extension and generated skills"), rows)

    def test_discovery_must_be_the_exact_single_extension_and_skills(self):
        for field, value in (("extensions", []), ("extensions", ["./extensions/other.js"]),
                             ("extensions", ["./extensions/codearbiter.js", "./other.js"]),
                             ("skills", []), ("skills", ["./skills", "./other"]), ("skills", "./skills")):
            with self.subTest(field=field, value=value):
                package = copy.deepcopy(self.source)
                package["pi"][field] = value
                self.assertTrue(any(level == "FAIL" and "package/discovery contract" in text
                                    for level, text in self.check(package)))

    def test_malformed_manifest_refuses_and_missing_core_stays_independent(self):
        for value in ([], None, "not an object"):
            with self.subTest(value=value):
                rows = self.check(value)
                self.assertTrue(any(level == "FAIL" for level, _ in rows))
                self.assertNotIn(("OK", "package.json declares only the ca-pi extension and generated skills"), rows)
        (self.root / "hooks/pi-bridge.py").unlink()
        rows = self.check(self.source)
        self.assertIn(("OK", "package.json declares only the ca-pi extension and generated skills"), rows)
        self.assertTrue(any(level == "FAIL" and "Pi shared core script(s) missing" in text for level, text in rows))


if __name__ == "__main__":
    unittest.main()
