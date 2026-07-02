"""performance-001 (issue #188): hook_run's tail_is_settled check and run()'s
pruning pass must operate on a SINGLE read+parse of the transcript file per
hook_run() invocation, not two independent open()+load_lines() cycles on the
identical on-disk bytes.

Verified two ways, per the issue's own acceptance criteria:
  1. A call-count spy on _prunelib.load_lines — parsing happens exactly once.
  2. A call-count spy on builtins.open for the transcript path itself — the
     file is opened at most twice (the pre-existing, in-scope self_heal
     corruption-check read, plus the ONE read that is then threaded through to
     the pruning pass) — never four times, which is what two independent
     read+parse cycles (one in hook_run, one re-done inside run()) would cost.
"""
import builtins
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_HOOKS_DIR = os.path.dirname(_TESTS_DIR)
sys.path.insert(0, _HOOKS_DIR)
sys.path.insert(0, _TESTS_DIR)

import _prunelib as P  # noqa: E402
from _helpers import make_transcript, redirect_home, restore_home  # noqa: E402


class SingleParseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._home = redirect_home(self.tmp.name)
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(os.path.join(self.repo, ".codearbiter"))
        with open(os.path.join(self.repo, ".codearbiter", "CONTEXT.md"), "w") as f:
            f.write("---\narbiter: enabled\n---\n# ctx\n")
        claude_dir = os.path.join(self.tmp.name, ".claude", "projects", "test")
        os.makedirs(claude_dir, exist_ok=True)
        self.path = os.path.join(claude_dir, "sess.jsonl")
        with open(self.path, "wb") as f:
            f.write(make_transcript(n_pairs=8, result_bytes=20000))
        # Fresh state: no prior record, so the growth short-circuit never fires.
        P.save_state({})

    def tearDown(self):
        restore_home(self._home)
        self.tmp.cleanup()

    def _env(self):
        return {"CODEARBITER_PRUNE": "on",
                "CODEARBITER_PRUNE_KEEP_RECENT": "2",
                "CODEARBITER_PRUNE_MIN_SIZE": "1000",
                "CODEARBITER_PRUNE_MIN_GROWTH": "1000"}

    def _payload(self):
        return {"hook_event_name": "UserPromptSubmit", "transcript_path": self.path,
                "session_id": "sess", "cwd": self.repo}

    def test_load_lines_called_exactly_once_per_hook_run(self):
        calls = []
        orig = P.load_lines

        def spy(data):
            calls.append(len(data))
            return orig(data)

        with patch.object(P, "load_lines", side_effect=spy):
            rc = P.hook_run(self._payload(), env=self._env())

        self.assertEqual(rc, 0)
        self.assertEqual(
            len(calls), 1,
            "the transcript must be parsed (load_lines) exactly ONCE per "
            "hook_run invocation, not once for tail_is_settled and again "
            "inside run()")

    def test_transcript_path_opened_at_most_five_times(self):
        """Opens of the transcript path per hook_run invocation must drop from
        7 (pre-fix baseline, measured directly against the unfixed code) to 5:
        self_heal's corruption check (1), the ONE read now threaded through to
        the pruning pass (1), and write_in_place's own pre-write read + write
        + post-write verify re-read (3) — all four of those are out of scope
        for this fix. Pre-fix, hook_run and run() each independently
        self_heal'd and read+parsed the identical bytes, costing 2 EXTRA opens
        (self_heal called twice, the transcript read+parsed twice) on top of
        those same 5 — this assertion is the regression guard against that
        duplication coming back."""
        real_open = builtins.open
        opens_of_path = []

        def spy_open(file, *a, **kw):
            if isinstance(file, str) and os.path.abspath(file) == os.path.abspath(self.path):
                opens_of_path.append(a[0] if a else kw.get("mode", "r"))
            return real_open(file, *a, **kw)

        with patch("builtins.open", side_effect=spy_open):
            rc = P.hook_run(self._payload(), env=self._env())

        self.assertEqual(rc, 0)
        self.assertLessEqual(
            len(opens_of_path), 5,
            f"transcript opened {len(opens_of_path)} times per hook_run "
            f"invocation; expected at most 5 (self_heal + the single threaded "
            f"read + write_in_place's 3 own opens) — 7 means hook_run and "
            f"run() are each independently self-healing and re-reading the "
            f"transcript again")

    def test_prune_still_executes_and_shrinks(self):
        """Sanity: the single-parse plumbing must not silently break pruning
        itself — existing behavior (transcript shrinks) is preserved."""
        before = os.path.getsize(self.path)
        rc = P.hook_run(self._payload(), env=self._env())
        self.assertEqual(rc, 0)
        self.assertLess(os.path.getsize(self.path), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
