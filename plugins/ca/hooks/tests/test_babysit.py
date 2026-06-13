import os
import sys
import unittest

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


if __name__ == "__main__":
    unittest.main()
