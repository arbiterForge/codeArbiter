"""Canonical Claude transcript component containment, before any healing/read effect.

Owned unit fixtures only; no real user transcript, hook subprocess or provider.
Canonical-path checks do not establish race-free ancestor/OS containment.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _prunelib as P


class PruneContainmentTests(unittest.TestCase):
    def setUp(self):
        self.owner = tempfile.TemporaryDirectory()
        self.root = Path(self.owner.name).resolve()
        self.claude = self.root / ".claude"
        self.claude.mkdir()

    def tearDown(self):
        self.owner.cleanup()

    def transcript(self, relative):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'{"type":"assistant"}\n')
        return path

    def invoke(self, path, *, mode="on", base=None):
        base = self.claude if base is None else base
        with mock.patch.object(P.os.path, "expanduser", return_value=str(base)), \
                mock.patch.object(P._hooklib, "arbiter_active", return_value=True) as active, \
                mock.patch.object(P, "self_heal", return_value=(False, "clean")) as heal, \
                mock.patch.object(P, "load_state", side_effect=AssertionError("small fixture must not process content")):
            result = P.hook_run({"transcript_path": str(path), "cwd": str(self.root),
                                 "session_id": "owned"}, env={"CODEARBITER_PRUNE": mode})
        return result, active, heal

    def test_prefix_siblings_are_refused_before_self_heal(self):
        for name in (".claude-other", ".claude.old", ".claude2"):
            with self.subTest(sibling=name):
                path = self.transcript(name + "/session.jsonl")
                result, active, heal = self.invoke(path)
                self.assertEqual(result, 0)
                heal.assert_not_called()
                active.assert_not_called()
                self.assertEqual(path.read_bytes(), b'{"type":"assistant"}\n')

    def test_contained_descendants_preserve_original_healing_route(self):
        path = self.transcript(".claude/projects/owned/session.jsonl")
        for selected in (path, path.parent / ".." / "owned" / path.name):
            with self.subTest(normalized=selected == path):
                result, active, heal = self.invoke(selected)
                self.assertEqual(result, 0)
                active.assert_called_once_with(str(self.root))
                heal.assert_called_once_with(str(selected), "owned")

    def test_unrelated_and_escaping_paths_are_refused_before_processing(self):
        path = self.transcript("outside/session.jsonl")
        escape = self.claude / "projects" / ".." / ".." / "outside" / path.name
        (self.claude / "projects").mkdir()
        for selected in (path, escape):
            with self.subTest(path_form=selected == path):
                result, active, heal = self.invoke(selected)
                self.assertEqual(result, 0)
                active.assert_not_called()
                heal.assert_not_called()

    def test_claude_base_itself_is_not_a_descendant_even_if_regular(self):
        base = self.transcript("other-owned-home/.claude")
        result, active, heal = self.invoke(base, base=base)
        self.assertEqual(result, 0)
        active.assert_not_called()
        heal.assert_not_called()

    def test_canonicalization_and_cross_root_errors_refuse_without_processing(self):
        path = self.transcript(".claude/projects/owned/session.jsonl")
        with mock.patch.object(P.os.path, "realpath", side_effect=OSError("owned unavailable")):
            result, active, heal = self.invoke(path)
        self.assertEqual(result, 0)
        active.assert_not_called()
        heal.assert_not_called()
        with mock.patch.object(P.os.path, "commonpath", side_effect=ValueError("different roots")):
            result, active, heal = self.invoke(path)
        self.assertEqual(result, 0)
        active.assert_not_called()
        heal.assert_not_called()

    def test_outside_symlink_is_canonicalized_before_admission(self):
        outside = self.transcript(".claude-other/session.jsonl")
        link = self.claude / "linked-session.jsonl"
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError):
            self.skipTest("owned symlink creation unavailable on this host")
        result, active, heal = self.invoke(link)
        self.assertEqual(result, 0)
        active.assert_not_called()
        heal.assert_not_called()
        self.assertEqual(outside.read_bytes(), b'{"type":"assistant"}\n')

    def test_disabled_and_dry_modes_keep_their_existing_no_heal_behavior(self):
        path = self.transcript(".claude/projects/owned/session.jsonl")
        for mode in ("off", "dry", "unknown"):
            with self.subTest(mode=mode):
                result, active, heal = self.invoke(path, mode=mode)
                self.assertEqual(result, 0)
                heal.assert_not_called()
                self.assertEqual(active.call_count, 1 if mode == "dry" else 0)


if __name__ == "__main__":
    unittest.main()
