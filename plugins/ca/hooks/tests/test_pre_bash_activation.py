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
    # Pin CLAUDE_PROJECT_DIR to the fixture repo: project_root() trusts the
    # harness signal first, and a value leaking in from a live Claude session
    # would silently point every guard at the developer's real repo.
    env = {**os.environ, "CLAUDE_PROJECT_DIR": cwd}
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=60,
                          env=env, **kw)


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


class TestCommitMessageParsing(_PreBashFixture):
    """Regression: a commit message whose body contains `;`/`|`/`&` (heredoc or
    quoted `-m`) must not truncate the args capture — the truncated fragment's
    words were parsed as pathspecs, a `/`-leading token made `git diff HEAD --`
    fatal, and H-09b failed CLOSED on a clean commit (2026-07-01, 2.6.1)."""

    def setUp(self):
        super().setUp()
        # A real history + a staged benign change, so the H-09b/H-14 scans run
        # against genuine diffs instead of an unborn HEAD.
        with open(os.path.join(self.root, "notes.txt"), "w", encoding="utf-8") as f:
            f.write("hello\n")
        _git(["add", "notes.txt"], self.root)
        _git(["commit", "-q", "-m", "init"], self.root)
        with open(os.path.join(self.root, "notes.txt"), "a", encoding="utf-8") as f:
            f.write("more\n")
        _git(["add", "notes.txt"], self.root)

    def test_heredoc_command_substitution_message_with_semicolon_is_allowed(self):
        cmd = ('git commit -m "$(cat <<\'EOF\'\n'
               "fix: scoped change\n\n"
               "routine lanes (/ca:review, /ca:checkpoint) are fast\n"
               "and diff-scoped; nothing convenes a deep pass.\n"
               "EOF\n"
               ')"')
        self.assertAllowed(self.run_bash(cmd))

    def test_stdin_heredoc_message_with_semicolon_is_allowed(self):
        cmd = ("git commit -F - <<'EOF'\n"
               "fix: scoped change\n\n"
               "fast and diff-scoped; covers /ca:review & /ca:checkpoint.\n"
               "EOF")
        self.assertAllowed(self.run_bash(cmd))

    def test_quoted_message_with_semicolon_is_allowed(self):
        self.assertAllowed(self.run_bash(
            'git commit -m "fix: a; b (see /ca:review)"'))

    def test_message_mentioning_git_dash_c_does_not_poison_cwd(self):
        cmd = ("git commit -F - <<'EOF'\n"
               "fix: docs\n\n"
               "documents the git -C /nonexistent/dir spelling.\n"
               "EOF")
        self.assertAllowed(self.run_bash(cmd))

    def test_commit_then_force_push_is_still_blocked(self):
        self.assertBlocked(self.run_bash(
            'git commit -m "ok" && git push --force origin feat/work'), "H-02")

    def test_heredoc_operator_line_tail_pathspec_is_still_scanned(self):
        # `git commit -F - <<EOF crypto.js` names crypto.js as a pathspec whose
        # WORKTREE content the commit records — the scan must still see it.
        # The file must be tracked (a pathspec commit can't add untracked
        # files) with the sensitive line as an unstaged worktree edit, which
        # is exactly what the --cached scan misses.
        path = os.path.join(self.root, "crypto.js")
        with open(path, "w", encoding="utf-8") as f:
            f.write("// helpers\n")
        _git(["add", "crypto.js"], self.root)
        _git(["commit", "-q", "-m", "add crypto.js"], self.root)
        with open(path, "a", encoding="utf-8") as f:
            f.write('const h = createHash("sha256");\n')
        cmd = ("git commit -F - <<'EOF' crypto.js\n"
               "feat: add hashing\n"
               "EOF")
        self.assertBlocked(self.run_bash(cmd), "H-09b")

    def test_shell_fed_heredoc_commit_is_still_guarded(self):
        # A heredoc piped TO a shell executes its body — the raw-command
        # fallback matcher must keep guarding it (here: H-01 on main).
        _git(["checkout", "-q", "-b", "main"], self.root)
        cmd = ("bash <<'EOF'\n"
               "git commit -a -m x\n"
               "EOF")
        self.assertBlocked(self.run_bash(cmd), "H-01")


if __name__ == "__main__":
    unittest.main()
