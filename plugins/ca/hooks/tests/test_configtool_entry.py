"""configtool.py CLI-level tests — main(argv) dispatch, the `list --json`
contract /ca:config consumes, exit codes, and the no-args non-tty behavior
(must print, never hang on key input)."""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

_HOOKS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _HOOKS_DIR)
import configtool  # noqa: E402

_CONTRACT_FIELDS = {"name", "group", "type", "values", "default", "effective",
                    "source", "pending", "layers", "description", "status",
                    "scope", "sensitive"}


def _run(argv, tmp):
    """main(argv) with all three layers pointed into tmp; returns (code, out)."""
    args = argv + [
        "--settings-user", os.path.join(tmp, "u.json"),
        "--settings-project", os.path.join(tmp, "p.json"),
        "--settings-local", os.path.join(tmp, "l.json"),
    ]
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            code = configtool.main(args)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
    return code, buf.getvalue()


class TestListContract(unittest.TestCase):
    def test_json_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = _run(["list", "--json"], tmp)
            self.assertEqual(code, 0)
            data = json.loads(out)
            self.assertEqual(data["version"], 1)
            self.assertGreaterEqual(len(data["settings"]), 50)
            for rec in data["settings"]:
                self.assertEqual(set(rec), _CONTRACT_FIELDS, rec["name"])

    def test_group_filter_and_unknown_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = _run(["list", "--json", "--group", "sandbox"], tmp)
            data = json.loads(out)
            self.assertEqual({r["group"] for r in data["settings"]}, {"sandbox"})
            code, _ = _run(["list", "--group", "nope"], tmp)
            self.assertNotEqual(code, 0)

    def test_human_list_mentions_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, out = _run(["list"], tmp)
            self.assertIn("NEXT session start", out)


class TestSetGetUnset(unittest.TestCase):
    def test_set_then_get_reads_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = _run(["set", "CODEARBITER_PRUNE", "dry", "--scope", "local"], tmp)
            self.assertEqual(code, 0)
            self.assertIn("NEXT session start", out)
            code, out = _run(["get", "CODEARBITER_PRUNE"], tmp)
            self.assertIn("dry", out)
            self.assertIn("local", out)
            code, out = _run(["unset", "CODEARBITER_PRUNE", "--scope", "local"], tmp)
            self.assertEqual(code, 0)
            _, out = _run(["get", "CODEARBITER_PRUNE"], tmp)
            self.assertIn("default", out)

    def test_invalid_value_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _ = _run(["set", "CODEARBITER_PRUNE", "sideways"], tmp)
            self.assertNotEqual(code, 0)

    def test_sensitive_refused_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _ = _run(["set", "FARM_API_KEY", "sk-x"], tmp)
            self.assertNotEqual(code, 0)

    def test_explain_names_requires(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, out = _run(["explain", "CODEARBITER_PRUNE_NUDGE"], tmp)
            self.assertIn("requires", out)
            self.assertIn("CODEARBITER_PRUNE", out)


class TestDoctor(unittest.TestCase):
    def test_error_finding_sets_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "u.json"), "w", encoding="utf-8") as f:
                json.dump({"env": {"CODEARBITER_COMPACT_AT": "lots"}}, f)
            code, out = _run(["doctor"], tmp)
            self.assertEqual(code, 1)
            self.assertIn("ERROR", out)

    def test_healthy_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = _run(["doctor", "--json"], tmp)
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out), {"findings": []})


class TestNoArgsNonTty(unittest.TestCase):
    def test_prints_inventory_instead_of_hanging(self):
        # Subprocess with piped stdio — the exact shape of Claude's Bash tool
        # and any CI runner. Must exit 0 promptly with the table, never block
        # on key input.
        script = os.path.join(_HOOKS_DIR, "configtool.py")
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        proc = subprocess.run([sys.executable, script], input=b"",
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=30, env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(b"no tty detected", proc.stdout)


if __name__ == "__main__":
    unittest.main()
