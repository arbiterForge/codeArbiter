import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _babysitlib as B  # noqa: E402


def active(_root):
    return True


def dormant(_root):
    return False


class TestBabysitConfig(unittest.TestCase):
    # ---- PB-8: default off ------------------------------------------------- #
    def test_absent_is_off(self):
        cfg = B.babysit_config({}, "/repo", arbiter_active=active)
        self.assertFalse(cfg["enabled"])

    def test_explicit_off_is_off(self):
        cfg = B.babysit_config({"CODEARBITER_BABYSIT": "off"}, "/repo",
                               arbiter_active=active)
        self.assertFalse(cfg["enabled"])

    def test_unknown_value_is_off(self):
        cfg = B.babysit_config({"CODEARBITER_BABYSIT": "maybe"}, "/repo",
                               arbiter_active=active)
        self.assertFalse(cfg["enabled"])

    def test_empty_value_is_off(self):
        cfg = B.babysit_config({"CODEARBITER_BABYSIT": ""}, "/repo",
                               arbiter_active=active)
        self.assertFalse(cfg["enabled"])

    # ---- on + arbiter active ---------------------------------------------- #
    def test_on_when_active(self):
        cfg = B.babysit_config({"CODEARBITER_BABYSIT": "on"}, "/repo",
                               arbiter_active=active)
        self.assertTrue(cfg["enabled"])

    def test_accepts_true_one_and_mixedcase(self):
        for spelling in ("true", "1", "ON", "True", "On"):
            cfg = B.babysit_config({"CODEARBITER_BABYSIT": spelling}, "/repo",
                                   arbiter_active=active)
            self.assertTrue(cfg["enabled"], spelling)

    # ---- PB-10: two-layer dormancy gate ----------------------------------- #
    def test_on_but_dormant_is_off(self):
        cfg = B.babysit_config({"CODEARBITER_BABYSIT": "on"}, "/repo",
                               arbiter_active=dormant)
        self.assertFalse(cfg["enabled"])

    # ---- PB-5: on_red default propose ------------------------------------- #
    def test_on_red_default_propose(self):
        cfg = B.babysit_config({}, "/repo", arbiter_active=active)
        self.assertEqual(cfg["on_red"], "propose")

    def test_on_red_branch(self):
        cfg = B.babysit_config({"CODEARBITER_BABYSIT_ONRED": "branch"}, "/repo",
                               arbiter_active=active)
        self.assertEqual(cfg["on_red"], "branch")

    def test_on_red_branch_mixedcase(self):
        cfg = B.babysit_config({"CODEARBITER_BABYSIT_ONRED": "BRANCH"}, "/repo",
                               arbiter_active=active)
        self.assertEqual(cfg["on_red"], "branch")

    def test_on_red_garbage_is_propose(self):
        cfg = B.babysit_config({"CODEARBITER_BABYSIT_ONRED": "explode"}, "/repo",
                               arbiter_active=active)
        self.assertEqual(cfg["on_red"], "propose")

    def test_on_red_propose_explicit(self):
        cfg = B.babysit_config({"CODEARBITER_BABYSIT_ONRED": "propose"}, "/repo",
                               arbiter_active=active)
        self.assertEqual(cfg["on_red"], "propose")


class TestBabysitCLI(unittest.TestCase):
    """The CLI shim /ca:pr and /ca:watch invoke: resolves against the live env +
    real dormancy gate and prints one JSON line. A dormant root (a temp dir with
    no .codearbiter/) exercises the PB-10 gate end-to-end."""

    def setUp(self):
        self._saved = {k: os.environ.get(k)
                       for k in ("CODEARBITER_BABYSIT", "CODEARBITER_BABYSIT_ONRED")}
        for k in self._saved:
            os.environ.pop(k, None)
        self.root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_no_such_repo_xyz")

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _run(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = B.main(["--root", self.root])
        self.assertEqual(rc, 0)
        return json.loads(buf.getvalue().strip())

    def test_prints_valid_json_with_keys(self):
        cfg = self._run()
        self.assertIn("enabled", cfg)
        self.assertIn("on_red", cfg)

    def test_default_is_off_and_propose(self):
        cfg = self._run()
        self.assertFalse(cfg["enabled"])
        self.assertEqual(cfg["on_red"], "propose")

    def test_on_but_dormant_root_stays_off(self):
        os.environ["CODEARBITER_BABYSIT"] = "on"
        cfg = self._run()
        self.assertFalse(cfg["enabled"])  # PB-10 dormancy gate, end-to-end

    def test_on_red_branch_surfaces(self):
        os.environ["CODEARBITER_BABYSIT_ONRED"] = "branch"
        cfg = self._run()
        self.assertEqual(cfg["on_red"], "branch")


if __name__ == "__main__":
    unittest.main()
