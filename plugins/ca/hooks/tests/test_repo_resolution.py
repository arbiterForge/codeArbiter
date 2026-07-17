"""Issue #190 — hook-repo-resolution group (reliability-004/005/007).

Three sites shared one bug class: a hook resolved "the project root" using a
rule that can point at the WRONG repository when a git operation is indirected
(`git -C <other>`) or the hook's own execution context is not
`CLAUDE_PROJECT_DIR` (a `.git/hooks` script).

  * reliability-007: session-start.py / taskwrite.py each defined a LOCAL
    project_root() that skips the CLAUDE_PROJECT_DIR-first contract
    _hooklib.project_root() exists for.
  * reliability-005: git-enforce.py resolved its root via
    _hooklib.project_root() (CLAUDE_PROJECT_DIR-first), but it runs as a
    `.git/hooks/pre-commit|pre-push` script IN the repo the git operation
    targets — which can differ from the session's CLAUDE_PROJECT_DIR.
  * reliability-004: pre-bash.py's git_cwd()/GIT_C_DIR_RE only matched `-C` as
    the FIRST token after `git`, so global options before it
    (`--no-pager`, `-c k=v`) hid the -C target and the guards scanned the
    wrong repo.

Each test class proves BOTH directions: the wrong-repo bug is fixed, AND no
fail-open regression is introduced (a genuine commit-to-main in the actually-
targeted repo is still blocked).
"""
import importlib.util as _ilu
import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRE_BASH = os.path.join(HOOKS, "pre-bash.py")
ENFORCE = os.path.join(HOOKS, "git-enforce.py")

sys.path.insert(0, HOOKS)
import _githooks  # noqa: E402


def _load_module(name, path):
    """Import a hyphenated-filename hook fresh as a module (mirrors
    test_git_hooks.py's _load_git_enforce) — a fresh module per call means no
    monkeypatch state leaks between tests."""
    spec = _ilu.spec_from_file_location(name, path)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sh(args, cwd, env=None, **kw):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=60,
                          env=env, **kw)


def _git(args, cwd, check=True):
    r = _sh(["git"] + args, cwd, env=os.environ.copy())
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr}")
    return r


ARBITER = "---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\n"


def _init_repo(root, branch="main"):
    os.makedirs(root)
    _git(["init", "-q", "-b", branch], root)
    _git(["config", "user.email", "h@example.com"], root)
    _git(["config", "user.name", "harness"], root)
    os.makedirs(os.path.join(root, ".codearbiter"))
    with open(os.path.join(root, ".codearbiter", "CONTEXT.md"), "w",
              encoding="utf-8") as f:
        f.write(ARBITER)


def _commit(root, name="seed.txt", content="seed\n", msg="seed"):
    """A trivial commit — `git worktree add` needs at least one commit to
    check anything out from (an unborn-HEAD repo has nothing to branch off)."""
    path = os.path.join(root, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    _git(["add", name], root)
    _git(["commit", "-q", "-m", msg], root)


# ---------------------------------------------------------------------------
# reliability-004: pre-bash.py's git_cwd() must extract -C past global options
# ---------------------------------------------------------------------------

class TestGitCwdUnit(unittest.TestCase):
    """Pure unit coverage of git_cwd() — no subprocess, no git spawn."""

    def setUp(self):
        self.pb = _load_module("pre_bash_direct", PRE_BASH)

    def test_bare_dash_c_is_still_extracted(self):
        # Control: the pre-existing first-token spelling must keep working.
        self.assertEqual(self.pb.git_cwd("git -C /abs/other commit -m x", "/root"),
                         "/abs/other")

    def test_dash_c_after_no_pager_is_extracted(self):
        # The bug: --no-pager preceding -C used to hide it entirely (git_cwd
        # fell back to `root`).
        self.assertEqual(
            self.pb.git_cwd("git --no-pager -C /abs/other commit -m x", "/root"),
            "/abs/other")

    def test_dash_c_after_config_option_is_extracted(self):
        self.assertEqual(
            self.pb.git_cwd("git -c user.name=x -C /abs/other commit -m x", "/root"),
            "/abs/other")

    def test_relative_dash_c_resolves_against_project_root_not_hook_cwd(self):
        # Acceptance criterion: a relative -C path resolves against
        # project_root, regardless of the hook process's own cwd.
        joined = self.pb.git_cwd("git --no-pager -C ../other commit -m x", "/root/work")
        self.assertEqual(os.path.normpath(joined),
                         os.path.normpath("/root/work/../other"))

    def test_no_dash_c_falls_back_to_root(self):
        self.assertEqual(self.pb.git_cwd("git --no-pager commit -m x", "/root"), "/root")

    # -- security-reviewer MEDIUM follow-up (#190): -C COMPOSES sequentially,
    # not last-wins. A relative -C is relative to the ACCUMULATED result of
    # every preceding -C; an absolute -C REPLACES the accumulator entirely.

    def test_repeated_dash_c_absolute_then_relative_composes_onto_absolute(self):
        # `git -C /abs/main -C . commit`: the `.` is relative to /abs/main
        # (already seen), NOT to root — a last-wins-only reading would wrongly
        # resolve "." against root instead.
        self.assertEqual(
            os.path.normpath(self.pb.git_cwd("git -C /abs/main -C . commit -m x", "/root")),
            os.path.normpath("/abs/main/."))

    def test_repeated_dash_c_absolute_then_relative_subdir_joins_onto_absolute(self):
        # `git -C /abs/main -C sub commit` -> /abs/main/sub.
        self.assertEqual(
            os.path.normpath(self.pb.git_cwd("git -C /abs/main -C sub commit -m x", "/root")),
            os.path.normpath("/abs/main/sub"))

    def test_repeated_dash_c_relative_then_absolute_resets_to_absolute(self):
        # `git -C feat -C /abs/other commit`: the LATER absolute value resets
        # the accumulator, discarding the earlier relative "feat" entirely —
        # not joined, not ignored in favor of a stale last-wins read.
        self.assertEqual(
            self.pb.git_cwd("git -C feat -C /abs/other commit -m x", "/root"),
            "/abs/other")


class TestGitCwdEndToEnd(unittest.TestCase):
    """Subprocess-level proof: pre-bash.py judges H-01 against the -C TARGET
    repo, not the session's CLAUDE_PROJECT_DIR root — for both the bare -C
    spelling and the --no-pager-prefixed spelling (reliability-004)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.session_root = os.path.join(self._tmp.name, "session-repo")
        _init_repo(self.session_root, branch="feat/work")  # session repo is NOT on main
        self.other_root = os.path.join(self._tmp.name, "other-repo")
        _init_repo(self.other_root, branch="main")  # the -C target IS on main

    def tearDown(self):
        self._tmp.cleanup()

    def _env(self):
        # The session's CLAUDE_PROJECT_DIR is the session repo — pinned exactly
        # as the production harness pins it — while the git op fires in
        # other_root via -C.
        return {**os.environ, "CLAUDE_PROJECT_DIR": self.session_root}

    def run_bash(self, command):
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        return _sh([sys.executable, PRE_BASH], self.session_root, input=payload,
                  env=self._env())

    def test_bare_dash_c_commit_is_judged_against_other_repo_main(self):
        # Bug: previously scanned session_root (feat/work -> allowed); fixed:
        # scans other_root (main -> BLOCKED).
        res = self.run_bash(f'git -C "{self.other_root}" commit -m x')
        self.assertEqual(res.returncode, 2, res.stderr)
        self.assertIn("H-01", res.stderr)

    def test_no_pager_prefixed_dash_c_commit_is_judged_against_other_repo_main(self):
        # The exact reliability-004 evidence spelling.
        res = self.run_bash(f'git --no-pager -C "{self.other_root}" commit -m x')
        self.assertEqual(res.returncode, 2, res.stderr)
        self.assertIn("H-01", res.stderr)

    def test_no_fail_open_session_repo_itself_still_blocked_on_main(self):
        # No-fail-open direction: a DIRECT commit (no -C) in a session repo
        # that itself sits on main is still blocked — the -C fix must not
        # weaken the ordinary (no -C) H-01 path.
        main_root = os.path.join(self._tmp.name, "main-session")
        _init_repo(main_root, branch="main")
        res = _sh([sys.executable, PRE_BASH], main_root,
                  input=json.dumps({"tool_name": "Bash",
                                   "tool_input": {"command": 'git commit -m x'}}),
                  env={**os.environ, "CLAUDE_PROJECT_DIR": main_root})
        self.assertEqual(res.returncode, 2, res.stderr)
        self.assertIn("H-01", res.stderr)

    def test_dash_c_commit_onto_other_repo_feature_branch_is_allowed(self):
        # Converse: the -C target repo is genuinely on a feature branch ->
        # allowed, proving the fix doesn't over-block a legitimate cross-repo
        # commit either.
        feature_other = os.path.join(self._tmp.name, "other-repo-2")
        _init_repo(feature_other, branch="feat/other")
        res = self.run_bash(f'git --no-pager -C "{feature_other}" commit -m x')
        self.assertNotIn("H-01", res.stderr)

    # -- security-reviewer MEDIUM follow-up (#190): repeated -C composition,
    # end to end. A last-wins-only fix fails OPEN on these crafted spellings —
    # it resolves "." or "feat" against `root` (the session repo, feature
    # branch -> ALLOWED) instead of the real git-composed target (other_root,
    # main -> must BLOCK).

    def test_absolute_then_relative_dot_dash_c_is_judged_against_absolute_target(self):
        # `git -C /abs/main -C . commit`: "." composes onto /abs/main (already
        # seen), not onto root/session_root.
        res = self.run_bash(f'git -C "{self.other_root}" -C . commit -m x')
        self.assertEqual(res.returncode, 2, res.stderr)
        self.assertIn("H-01", res.stderr)

    def test_relative_then_absolute_dash_c_is_judged_against_the_absolute_reset(self):
        # `git -C feat -C /abs/main commit`: the later absolute -C RESETS the
        # accumulator — "feat" (relative to session_root) is discarded
        # entirely, not joined or left standing as a prior last-wins target.
        os.makedirs(os.path.join(self.session_root, "feat"), exist_ok=True)
        res = self.run_bash(f'git -C feat -C "{self.other_root}" commit -m x')
        self.assertEqual(res.returncode, 2, res.stderr)
        self.assertIn("H-01", res.stderr)

    # -- #223 (A-1): a `git commit` run inside a LINKED WORKTREE (no -C at
    # all — the ordinary, everyday spelling) must be judged against the
    # worktree's OWN branch, not CLAUDE_PROJECT_DIR's (the main checkout,
    # which another agent may be sitting in on an unrelated branch). Both
    # directions matter: the false NEGATIVE (a worktree on main/master
    # sidesteps H-01 because the main checkout happens to be on a feature
    # branch) is the more serious one — it lets a protected-branch commit
    # through — but the false POSITIVE (a worktree on a feature branch is
    # wrongly blocked because the main checkout is on main) must not regress
    # either.

    def test_worktree_on_main_is_blocked_even_when_main_checkout_is_on_a_feature_branch(self):
        # The false negative: today, CLAUDE_PROJECT_DIR (main_checkout, on a
        # feature branch) is judged instead of the worktree's actual branch
        # (main) — so this commit wrongly sails through. Must BLOCK.
        main_checkout = os.path.join(self._tmp.name, "wt-main-checkout")
        _init_repo(main_checkout, branch="feat/other-work")
        _commit(main_checkout)
        wt_dir = os.path.join(self._tmp.name, "wt-on-main")
        _git(["worktree", "add", "-b", "main", wt_dir], main_checkout)
        res = _sh([sys.executable, PRE_BASH], wt_dir,
                  input=json.dumps({"tool_name": "Bash",
                                    "tool_input": {"command": "git commit -m x"}}),
                  env={**os.environ, "CLAUDE_PROJECT_DIR": main_checkout})
        self.assertEqual(res.returncode, 2, res.stderr)
        self.assertIn("H-01", res.stderr)

    def test_worktree_on_feature_branch_is_allowed_even_when_main_checkout_is_on_main(self):
        # The false positive: today, CLAUDE_PROJECT_DIR (main_checkout, on
        # main) is judged instead of the worktree's actual branch (a feature
        # branch) — so this legitimate commit is wrongly blocked. Must NOT
        # block.
        main_checkout = os.path.join(self._tmp.name, "wt-main-checkout-2")
        _init_repo(main_checkout, branch="main")
        _commit(main_checkout)
        wt_dir = os.path.join(self._tmp.name, "wt-on-feature")
        _git(["worktree", "add", "-b", "feat/from-worktree", wt_dir], main_checkout)
        res = _sh([sys.executable, PRE_BASH], wt_dir,
                  input=json.dumps({"tool_name": "Bash",
                                    "tool_input": {"command": "git commit -m x"}}),
                  env={**os.environ, "CLAUDE_PROJECT_DIR": main_checkout})
        self.assertNotIn("H-01", res.stderr)


# ---------------------------------------------------------------------------
# #223 (A-2): heredoc BODY prose must not be mistaken for a real command
# (D-3) — but a heredoc actually FED TO A SHELL still executes its body and
# must still be guarded.
# ---------------------------------------------------------------------------

class TestHeredocFallbackNarrowing(unittest.TestCase):
    """pre-bash.py's raw-cmd fallback (the one that lets a heredoc genuinely
    fed to a shell still trip H-01) must be narrowed to shell-consuming
    heredocs only (D-3) — a heredoc whose consumer is NOT a shell (`cat`,
    inert text later substituted into `gh`'s --body) must not false-trip H-01
    merely because its body happens to CONTAIN the text "git commit"."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self._tmp.name, "repo")
        _init_repo(self.root, branch="main")  # on main: a REAL commit here blocks

    def tearDown(self):
        self._tmp.cleanup()

    def _run_bash(self, command):
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        return _sh([sys.executable, PRE_BASH], self.root, input=payload,
                  env={**os.environ, "CLAUDE_PROJECT_DIR": self.root})

    def test_heredoc_prose_inside_gh_pr_create_body_does_not_trip_h01(self):
        # The exact #223 evidence spelling: `cat <<'EOF' ... EOF` substituted
        # into gh's --body. The heredoc's DIRECT consumer is `cat` (inert
        # text), not a shell — must NOT block.
        cmd = ('gh pr create --body "$(cat <<\'EOF\'\n'
               'This PR includes a git commit -m x as part of the change\n'
               'EOF\n)"')
        res = self._run_bash(cmd)
        self.assertNotIn("H-01", res.stderr)

    def test_heredoc_fed_to_bash_still_blocks(self):
        # A heredoc fed directly to `bash` genuinely executes its body — must
        # still BLOCK (ambiguity resolves closed, D-3).
        cmd = "bash <<'EOF'\ngit commit -m x\nEOF\n"
        res = self._run_bash(cmd)
        self.assertEqual(res.returncode, 2, res.stderr)
        self.assertIn("H-01", res.stderr)

    def test_heredoc_prose_inside_gh_issue_create_body_does_not_trip_h01(self):
        # Same shape as the pr-create case, different subcommand — must NOT
        # block either.
        cmd = ('gh issue create --body "$(cat <<\'EOF\'\n'
               'This issue references a git commit -m x from another PR\n'
               'EOF\n)"')
        res = self._run_bash(cmd)
        self.assertNotIn("H-01", res.stderr)

    # -- review finding: `_heredoc_fed_to_shell` alone keys on the heredoc's
    # DIRECT consumer only. `bash -c "$(cat <<EOF … EOF)"` has `cat` as the
    # direct consumer (non-shell, correctly), but `bash -c` EXECUTES the
    # substituted result of that `cat` — the heredoc body genuinely reaches a
    # shell by a route the direct-consumer check cannot see. Narrowing must
    # also fail closed whenever the command invokes ANY shell/interpreter
    # executor ANYWHERE (`bash -c`, `eval`, `sh -c`, …), not only when the
    # heredoc's immediate consumer is one.

    def test_heredoc_via_command_substitution_fed_to_bash_dash_c_still_blocks(self):
        cmd = ('bash -c "$(cat <<\'EOF\'\n'
               'git commit -m x\n'
               'EOF\n)"')
        res = self._run_bash(cmd)
        self.assertEqual(res.returncode, 2, res.stderr)
        self.assertIn("H-01", res.stderr)

    def test_heredoc_via_command_substitution_fed_to_eval_still_blocks(self):
        cmd = ('eval "$(cat <<\'EOF\'\n'
               'git commit -m x\n'
               'EOF\n)"')
        res = self._run_bash(cmd)
        self.assertEqual(res.returncode, 2, res.stderr)
        self.assertIn("H-01", res.stderr)

    def test_heredoc_via_command_substitution_fed_to_sh_dash_c_still_blocks(self):
        cmd = ('sh -c "$(cat <<\'EOF\'\n'
               'git commit -m x\n'
               'EOF\n)"')
        res = self._run_bash(cmd)
        self.assertEqual(res.returncode, 2, res.stderr)
        self.assertIn("H-01", res.stderr)


# ---------------------------------------------------------------------------
# reliability-005: git-enforce.py must scan the repo the git hook fires in
# ---------------------------------------------------------------------------

class TestGitEnforceOwnRepoResolution(unittest.TestCase):
    """git-enforce.py runs as a .git/hooks/pre-commit|pre-push script of
    whatever repo the git operation targets. It must resolve THAT repo, never
    the session's CLAUDE_PROJECT_DIR (reliability-005)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.session_root = os.path.join(self._tmp.name, "session-repo")
        _init_repo(self.session_root, branch="feat/work")  # clean feature branch
        self.other_root = os.path.join(self._tmp.name, "other-repo")
        _init_repo(self.other_root, branch="main")  # the repo actually committing

    def tearDown(self):
        self._tmp.cleanup()

    def _stage(self, root, name, content):
        path = os.path.join(root, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        _git(["add", name], root)

    def test_pre_commit_scans_the_repo_it_runs_in_not_claude_project_dir(self):
        # Bug: git-enforce.py used _hooklib.project_root(), which trusts
        # CLAUDE_PROJECT_DIR (session_root, clean feature branch) first, so a
        # commit physically happening in other_root (on main) was scanned
        # against session_root and ALLOWED (fail-open). Fixed: git-enforce
        # ignores CLAUDE_PROJECT_DIR and resolves its own execution context.
        self._stage(self.other_root, "f.txt", "x\n")
        env = {**os.environ, "CLAUDE_PROJECT_DIR": self.session_root}
        res = _sh([sys.executable, ENFORCE, "pre-commit"], self.other_root, env=env)
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn("H-01", res.stderr)

    def test_installed_hook_fires_correctly_in_its_own_repo(self):
        # End-to-end via the real installed shim: a genuine commit onto main
        # in other_root is blocked even though CLAUDE_PROJECT_DIR points
        # elsewhere.
        _githooks.install(self.other_root)
        self._stage(self.other_root, "g.txt", "y\n")
        env = {**os.environ, "CLAUDE_PROJECT_DIR": self.session_root}
        res = _sh(["git", "commit", "-q", "-m", "sneaky"], self.other_root, env=env)
        self.assertNotEqual(res.returncode, 0, "commit onto main should have been blocked")
        self.assertIn("H-01", res.stderr + res.stdout)
        log = _git(["rev-list", "--all", "--count"], self.other_root, check=False)
        self.assertEqual(log.stdout.strip(), "0")

    def test_no_fail_open_feature_branch_commit_in_own_repo_still_allowed(self):
        # No-fail-open converse: a clean feature-branch commit IN THE REPO
        # GIT-ENFORCE ACTUALLY RUNS IN is still allowed — proves the fix
        # didn't flip to over-blocking every commit regardless of branch.
        feat_root = os.path.join(self._tmp.name, "feat-repo")
        _init_repo(feat_root, branch="feat/x")
        self._stage(feat_root, "f.txt", "x\n")
        env = {**os.environ, "CLAUDE_PROJECT_DIR": self.session_root}
        res = _sh([sys.executable, ENFORCE, "pre-commit"], feat_root, env=env)
        self.assertEqual(res.returncode, 0, res.stderr)


# ---------------------------------------------------------------------------
# reliability-007: session-start.py / taskwrite.py must use
# _hooklib.project_root (CLAUDE_PROJECT_DIR-first)
# ---------------------------------------------------------------------------

class TestSessionStartTaskwriteProjectRoot(unittest.TestCase):
    """Unify session-start.py and taskwrite.py on _hooklib.project_root: with
    CLAUDE_PROJECT_DIR pointed at a fixture repo and cwd elsewhere, both hooks
    must resolve the fixture repo (reliability-007)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.fixture_root = os.path.join(self._tmp.name, "fixture-repo")
        _init_repo(self.fixture_root, branch="main")
        self.elsewhere = os.path.join(self._tmp.name, "elsewhere")
        os.makedirs(self.elsewhere)
        # elsewhere is itself a distinct repo — `git rev-parse --show-toplevel`
        # from cwd would resolve HERE if CLAUDE_PROJECT_DIR were ignored.
        _git(["init", "-q", "-b", "main"], self.elsewhere)

        self._saved_cwd = os.getcwd()
        self._saved_env = os.environ.get("CLAUDE_PROJECT_DIR")
        os.chdir(self.elsewhere)
        os.environ["CLAUDE_PROJECT_DIR"] = self.fixture_root

    def tearDown(self):
        os.chdir(self._saved_cwd)
        if self._saved_env is None:
            os.environ.pop("CLAUDE_PROJECT_DIR", None)
        else:
            os.environ["CLAUDE_PROJECT_DIR"] = self._saved_env
        self._tmp.cleanup()

    def test_session_start_uses_hooklib_project_root(self):
        mod = _load_module("session_start_repo_res", os.path.join(HOOKS, "session-start.py"))
        self.assertEqual(os.path.normpath(mod.project_root()),
                         os.path.normpath(self.fixture_root))

    def test_taskwrite_uses_hooklib_project_root(self):
        mod = _load_module("taskwrite_repo_res", os.path.join(HOOKS, "taskwrite.py"))
        self.assertEqual(os.path.normpath(mod.project_root()),
                         os.path.normpath(self.fixture_root))

    def test_session_start_project_root_is_the_hooklib_function(self):
        # Structural: the fix deletes the local copy and imports _hooklib's —
        # not merely reimplements the same behavior under the same name.
        import _hooklib
        mod = _load_module("session_start_repo_res2", os.path.join(HOOKS, "session-start.py"))
        self.assertIs(mod.project_root, _hooklib.project_root)

    def test_taskwrite_project_root_is_the_hooklib_function(self):
        import _hooklib
        mod = _load_module("taskwrite_repo_res2", os.path.join(HOOKS, "taskwrite.py"))
        self.assertIs(mod.project_root, _hooklib.project_root)


if __name__ == "__main__":
    unittest.main()
