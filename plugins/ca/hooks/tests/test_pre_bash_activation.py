"""Shell-flank coverage for pre-bash.py's #159 (CONTEXT.md) and #160 (gate
markers) guards.

The Write/Edit tools are guarded by pre-write/pre-edit; these prove the shell
flank: a redirect or write-verb that would rewrite the activation switch, or
forge a gate-pass marker, is blocked — while reads and the sanctioned
`touch adr-authoring-active` / producer-script invocation still pass.

Stdlib only; hook JSON piped to pre-bash.py on stdin in a throwaway
arbiter-enabled git repo (mirrors .github/scripts/test_hook_guards.py).
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRE_BASH = os.path.join(HOOKS, "pre-bash.py")


def _sh(args, cwd, **kw):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=60, **kw)


def _git(args, cwd):
    r = _sh(["git"] + args, cwd)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr}")
    return r


class _PreBashFixture(unittest.TestCase):
    ARBITER = "---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\n"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self._tmp.name, "repo")
        os.makedirs(self.root)
        _git(["init", "-q", "-b", "feat/work"], self.root)
        _git(["config", "user.email", "h@example.com"], self.root)
        _git(["config", "user.name", "harness"], self.root)
        os.makedirs(os.path.join(self.root, ".codearbiter"))
        with open(os.path.join(self.root, ".codearbiter", "CONTEXT.md"), "w",
                  encoding="utf-8") as f:
            f.write(self.ARBITER)

    def tearDown(self):
        self._tmp.cleanup()

    def run_bash(self, command):
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        return _sh([sys.executable, PRE_BASH], self.root, input=payload)

    def assertBlocked(self, res, tag):
        self.assertEqual(res.returncode, 2,
                         f"expected BLOCK (exit 2); got {res.returncode} / {res.stderr[:200]!r}")
        self.assertIn(tag, res.stderr)

    def assertAllowed(self, res):
        self.assertEqual(res.returncode, 0,
                         f"expected ALLOW (exit 0); got {res.returncode} / {res.stderr[:200]!r}")


class TestContextShellFlank(_PreBashFixture):
    def test_redirect_into_context_is_blocked(self):
        self.assertBlocked(self.run_bash("echo x > .codearbiter/CONTEXT.md"), "H-18")

    def test_sed_inplace_on_context_is_blocked(self):
        self.assertBlocked(self.run_bash("sed -i s/enabled/disabled/ .codearbiter/CONTEXT.md"), "H-18")

    def test_rm_context_is_blocked(self):
        self.assertBlocked(self.run_bash("rm .codearbiter/CONTEXT.md"), "H-18")

    def test_read_context_is_allowed(self):
        self.assertAllowed(self.run_bash("cat .codearbiter/CONTEXT.md"))


class TestGateMarkerShellFlank(_PreBashFixture):
    def test_redirect_forge_security_marker_is_blocked(self):
        self.assertBlocked(
            self.run_bash("echo deadbeef > .codearbiter/.markers/security-gate-passed"), "H-19")

    def test_cp_forge_migration_marker_is_blocked(self):
        self.assertBlocked(
            self.run_bash("cp good .codearbiter/.markers/migration-gate-passed"), "H-19")

    def test_touch_adr_marker_is_allowed(self):
        # /adr legitimately touches the ADR-authoring marker.
        self.assertAllowed(self.run_bash("touch .codearbiter/.markers/adr-authoring-active"))

    def test_running_producer_script_is_allowed(self):
        # The sanctioned producer names the script, not the marker file.
        self.assertAllowed(self.run_bash('python "$CLAUDE_PLUGIN_ROOT/hooks/security-pass.py"'))


if __name__ == "__main__":
    unittest.main()
