#!/usr/bin/env python3
"""codeArbiter — T-73a/T-73b/T-79: the scratch consumer fixture and the
reference-resolution guard (issue #563, AC-6.6/AC-6.8,
.codearbiter/specs/release-portable-fixture.md,
.codearbiter/plans/portable-release-and-protected-state.md). Reference
resolution started as a T-73b ratchet (committed known-unresolved-refs.txt,
compared for equality) and was retired into a strict "the set is empty"
assertion by T-79 once the release-skill rewrite resolved every entry.

The maintainer's completion bar for this campaign is that the portable
release lane is proven to work AND to port. Verifying against this
repository's own hand-built `.codearbiter/` state is the documented way a
consumer-facing bug stays hidden (memory: dev-repo-state-masks-consumer-
bugs), so this module never reads project state from THIS repo's checkout
to prove portability — it builds throwaway trees instead:

  ConsumerFixtureTest              T-73a — the fixture itself: THREE plugin
                                    payloads materialized by `git archive
                                    HEAD -- <plugin_dir>` (one per governance
                                    host: `plugins/ca`, `plugins/ca-codex`,
                                    `plugins/ca-pi`), and a throwaway
                                    single-package consumer git repo.
  ReferenceResolutionTest          T-73b/T-79 — extracts every executed-or-
                                    read path reference from EVERY INSTALLED
                                    copy of the release skill (the spec's
                                    own "Source of truth" list, plus
                                    `ca-codex/routines/release/SKILL.md`,
                                    which ships an identically-contaminated
                                    copy the spec's enumeration omits — see
                                    the adversarial-review remediation on
                                    2026-07-31) and asserts the UNIONED
                                    unresolved set is EMPTY outright. T-79
                                    retired the T-73b ratchet (a committed
                                    `known-unresolved-refs.txt` compared for
                                    equality in either direction) into this
                                    strict zero-form once the skill rewrite
                                    (T-41a-d/T-41f) resolved all 24 entries —
                                    see `test_reference_resolution_is_empty`.
  ResolverUnitTest                 direct, synthetic-input coverage of the
                                    three-armed `_resolves` classifier, so a
                                    mutant on any one arm cannot survive on
                                    a live skill's single real example of
                                    that arm.
  HermeticGitEnvTest               proves the two concrete, load-bearing
                                    claims `_isolated_git_env`/`_git`'s
                                    docstrings make (issue #556) rather than
                                    merely asserting the guard is CONFIGURED:
                                    an ambient `GIT_CONFIG_GLOBAL` poison
                                    must not reach a fixture-initialized
                                    repo, and a poisoned default
                                    `.git/hooks/pre-commit` must not fire
                                    through the per-call `core.hooksPath`
                                    override.

Materialization — why `git archive`, not the two rejected alternatives:

  - Pointing `CLAUDE_PLUGIN_ROOT` at the in-repo `plugins/ca/` tree is the
    dev tree wearing a costume: every file the skill reads is there, dev-
    tree-only artifacts and all, so a reference that only happens to
    resolve because THIS checkout has it lying around would pass here and
    fail in a real install. This project has a standing directive
    (dev-repo-state-masks-consumer-bugs) precisely because that shape has
    hidden consumer bugs before.
  - A recursive copy (`shutil.copytree`) carries whatever is on disk right
    now, uncommitted edits and gitignored build artifacts included
    (`__pycache__`, `node_modules`, ...). A skill referencing a file that
    exists locally but was never committed would still pass.
  - `git archive HEAD -- <plugin_dir>` reads the committed tree straight out
    of the object database: no working-tree state, no history walk beyond
    the current commit, no network, no `.git` directory in the output.
    `ConsumerFixtureTest` proves this with two REAL injected artifacts
    (a gitignored `__pycache__` entry and a genuinely untracked file) that
    a recursive copy would have carried and `git archive` does not. Both
    probes inject their sentinel into a THROWAWAY `git clone --shared` of
    this repo's own HEAD commit, never into this checkout directly: the
    premise requires the sentinel to sit inside the exact tree `git
    archive HEAD` reads (so it cannot simply move outside the plugin
    directory — that would prove nothing about `git archive` at all), but
    writing directly into this checkout would violate the fixture's own
    "no writes inside this repo" contract and would survive an ABNORMAL
    termination (`os._exit`, a killed process) since no `finally` ever
    runs then. The clone keeps that residual entirely inside a scratch
    tree — the same residual this module's overall scratch dir already
    carries (declared, not newly introduced) — while a write straight into
    `plugins/ca/` would leak into a path that ships.

`git archive` preserves the full repo-relative path (`plugins/ca/...`), not
the plugin-root-relative shape `CLAUDE_PLUGIN_ROOT` actually points at for
an installed plugin, so the archived tar is extracted with the leading
`<plugin_dir>` prefix stripped — done here via `tarfile` (stdlib), member by
member, rather than shelling out to a platform `tar` binary. The tar
member's own permission bits are preserved on extraction (`tarfile`
carries them; `git archive` marks an executable blob `0o775` and an
ordinary one `0o664`), since 10 files under `plugins/ca` ship
executable and a forward task (T-74/T-75) runs a lane that depends on it.

Each governance host spells its `{{PLUGIN_ROOT}}`/`{{PROJECT_DIR}}` template
tokens differently once rendered (`core/hosts.json` is the single source of
truth this module reads rather than re-declaring a second copy): `claude`
uses `${CLAUDE_PLUGIN_ROOT}`/`${CLAUDE_PROJECT_DIR}`, `codex` uses
`${CLAUDE_PLUGIN_ROOT}`/`<project-root>`, and `pi` uses
`<plugin-root>`/`<project-root>`. The extractor and resolver are
host-token-parameterized for exactly this reason: scanning a `pi`-rendered
skill file with the `claude` spelling hard-coded would misclassify every
already-portable `<plugin-root>/...` reference in it as a bare,
this-repo-relative contamination — a false positive that would pin a
harmless entry onto the ratchet FOREVER, the same "T-79 unreachable" failure
mode MEDIUM-4 names for a different reason.

Stdlib only. No third-party imports.
"""

from __future__ import annotations

import datetime
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))

GIT_TIMEOUT = 60

# --------------------------------------------------------------------------- #
# Hermetic git helpers — every scratch-repo git invocation is severed from the
# HOST's ambient global/system config.
# --------------------------------------------------------------------------- #


def _isolated_git_env():
    """Environment for every git invocation this module makes. Repoints the
    global AND system config file locations at paths that cannot exist, AND
    drops the env-injected config channel plus the two ambient overrides that
    a file-location repoint does not reach.

    The file repoint alone is NOT sufficient, and an earlier version of this
    docstring overclaimed that it was: `GIT_CONFIG_COUNT` with its numbered
    `GIT_CONFIG_KEY_n`/`GIT_CONFIG_VALUE_n` pairs injects config directly from
    the environment and bypasses config files entirely, while
    `GIT_ALTERNATE_OBJECT_DIRECTORIES` and `GIT_SSH_COMMAND` are ambient
    settings no config-file path can neutralize. Those are the same class the
    `init.templateDir` poison test exists to prove closed.

    Load-bearing (memory: stale-git-hook-enforcer, issue #556): a developer's
    REAL global `core.hooksPath` can point at an arbitrarily old, cross-host
    codeArbiter git-hooks cache, which would then run its own enforcement
    logic against this module's throwaway repos and can BLOCK a commit for
    reasons that have nothing to do with this fixture. A CI runner's ambient
    `commit.gpgsign`/`tag.gpgsign` can likewise fail an unattended commit with
    no signing key configured. Both failure modes make this fixture's outcome
    depend on the machine it runs on, which is the opposite of what a
    hermetic fixture is for."""
    env = dict(os.environ)
    # The env-injected config channel: GIT_CONFIG_COUNT declares how many
    # GIT_CONFIG_KEY_n / GIT_CONFIG_VALUE_n pairs git should apply, and it
    # bypasses config FILES entirely, so repointing those files does not
    # neutralize it. Drop the counter and every numbered pair.
    count = env.pop("GIT_CONFIG_COUNT", None)
    if count is not None:
        try:
            n = int(count)
        except ValueError:
            n = 0
        for i in range(max(n, 0)):
            env.pop("GIT_CONFIG_KEY_%d" % i, None)
            env.pop("GIT_CONFIG_VALUE_%d" % i, None)
    # Ambient overrides no config-file path can reach.
    env.pop("GIT_ALTERNATE_OBJECT_DIRECTORIES", None)
    env.pop("GIT_SSH_COMMAND", None)
    env["GIT_CONFIG_GLOBAL"] = os.path.join(
        tempfile.gettempdir(), "codearbiter-consumer-smoke-no-global-config")
    env["GIT_CONFIG_SYSTEM"] = os.path.join(
        tempfile.gettempdir(), "codearbiter-consumer-smoke-no-system-config")
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    return env


def _git(args, cwd, check=True):
    """Run one git command against `cwd`, with the ambient host config
    severed (see `_isolated_git_env`) and a per-repo, deliberately
    nonexistent `core.hooksPath` — belt-and-suspenders on top of the env
    redirection above, in case some other layer (e.g. a `.git/config`
    inherited via `git clone --config` in a future caller) ever tries to
    set one locally."""
    no_hooks = os.path.join(cwd, ".ca-fixture-no-hooks-dir")
    result = subprocess.run(
        ["git",
         "-c", f"core.hooksPath={no_hooks}",
         "-c", "commit.gpgsign=false",
         "-c", "tag.gpgsign=false",
         "-c", "init.defaultBranch=main",
         "-c", "user.name=codeArbiter consumer-smoke fixture",
         "-c", "user.email=fixture@example.invalid",
         *args],
        cwd=cwd, capture_output=True, encoding="utf-8", timeout=GIT_TIMEOUT,
        env=_isolated_git_env())
    if check and result.returncode != 0:
        raise RuntimeError(
            f"git {args!r} failed (cwd={cwd!r}): {result.stderr}")
    return result


def _force_rmtree(path):
    """`shutil.rmtree` that survives read-only objects under `.git` on
    Windows (git marks packed objects read-only; a plain rmtree there raises
    PermissionError and would leave scratch state behind on failure, which
    the fixture's hermeticity contract forbids)."""
    if not os.path.exists(path):
        return

    def _onerror(func, target, _exc_info):
        try:
            os.chmod(target, stat.S_IWRITE)
        except OSError:
            pass
        try:
            func(target)
        except OSError:
            pass

    shutil.rmtree(path, onerror=_onerror)


def _clone_head(dest):
    """Clone THIS repo's checked-out HEAD commit into `dest` (a throwaway
    scratch directory) via `git clone --shared --no-checkout`, then check
    out that exact commit sha, detached. `--shared` links the clone's
    object store to this repo's own (an `alternates` reference, not a
    hardlink requirement — no same-filesystem constraint) so the clone is
    cheap, and it needs no network.

    Exists so a caller that must inject a REAL artifact into a
    `git`-archived tree (a gitignored file, an untracked file) can do so
    WITHOUT writing into this checkout — see the module docstring's
    "Materialization" section for why writing directly into
    `plugins/ca/...` here would be wrong twice over. Checking out the exact
    HEAD sha (rather than trusting the clone's default branch) keeps the
    probe correct even if `REPO_ROOT`'s current branch pointer and its
    checked-out commit have diverged (a detached HEAD, or a branch moved
    since checkout)."""
    head_sha = _git(["rev-parse", "HEAD"], REPO_ROOT).stdout.strip()
    result = subprocess.run(
        ["git", "clone", "--quiet", "--shared", "--no-checkout",
         REPO_ROOT, dest],
        cwd=tempfile.gettempdir(), capture_output=True, encoding="utf-8",
        timeout=GIT_TIMEOUT, env=_isolated_git_env())
    if result.returncode != 0:
        raise RuntimeError(f"git clone --shared HEAD failed: {result.stderr}")
    _git(["checkout", "--quiet", head_sha], dest)


# --------------------------------------------------------------------------- #
# T-73a — plugin materialization via `git archive`
# --------------------------------------------------------------------------- #


def materialize_plugin(repo_root, dest, subpath="plugins/ca"):
    """Materialize the COMMITTED `subpath` tree at `repo_root`'s HEAD into
    `dest`, with the leading `subpath` prefix stripped so `dest` itself is
    the plugin root (matching what an installed plugin's `CLAUDE_PLUGIN_ROOT`
    actually points at — `dest/.claude-plugin/plugin.json`, not
    `dest/plugins/ca/.claude-plugin/plugin.json`).

    Reads `git archive --format=tar HEAD -- <subpath>` and walks the tar
    stream with the stdlib `tarfile` module rather than shelling out to a
    platform `tar` binary, so this has no external-tool dependency beyond
    git itself. Hard-fails with a named cause on any git or archive-shape
    problem — never silently produces an empty or partial tree."""
    result = subprocess.run(
        ["git", "archive", "--format=tar", "HEAD", "--", subpath],
        cwd=repo_root, capture_output=True, timeout=GIT_TIMEOUT)
    if result.returncode != 0:
        raise RuntimeError(
            f"'git archive HEAD -- {subpath}' failed in {repo_root!r}: "
            f"{result.stderr.decode('utf-8', 'replace')}")
    if not result.stdout:
        raise RuntimeError(
            f"'git archive HEAD -- {subpath}' produced an EMPTY archive in "
            f"{repo_root!r} — {subpath!r} is not a committed path at HEAD")

    prefix = subpath.rstrip("/") + "/"
    os.makedirs(dest, exist_ok=True)
    extracted_any = False
    with tarfile.open(fileobj=io.BytesIO(result.stdout)) as tf:
        for member in tf.getmembers():
            if not member.name.startswith(prefix):
                continue
            rel = member.name[len(prefix):]
            if not rel:
                continue
            if member.issym() or member.islnk():
                raise RuntimeError(
                    "unexpected symlink/hardlink in the archived plugin "
                    f"payload: {member.name!r} — the plugin payload is "
                    "expected to carry only regular files and directories")
            target = os.path.join(dest, *rel.split("/"))
            if member.isdir():
                os.makedirs(target, exist_ok=True)
            elif member.isfile():
                os.makedirs(os.path.dirname(target), exist_ok=True)
                fh = tf.extractfile(member)
                with open(target, "wb") as out:
                    out.write(fh.read())
                # Preserve the tar member's permission bits (git archive
                # marks an executable blob 0o775, an ordinary one 0o664).
                # LOW finding (adversarial review 2026-07-31): 10 files under
                # plugins/ca ship executable at HEAD and a forward task
                # (T-74/T-75) runs a lane that depends on it; `open(...,
                # "wb")` alone always writes 644. Best-effort on Windows,
                # where there is no POSIX exec bit to set.
                try:
                    os.chmod(target, member.mode & 0o777)
                except OSError:
                    pass
                extracted_any = True
            else:
                raise RuntimeError(
                    f"unexpected tar member type for {member.name!r}")
    if not extracted_any:
        raise RuntimeError(
            f"'git archive HEAD -- {subpath}' extracted zero files into "
            f"{dest!r} — the archive shape has changed")


# --------------------------------------------------------------------------- #
# T-73a — the throwaway consumer repo
# --------------------------------------------------------------------------- #


def _write_text(path, content):
    """Write `content` verbatim, LF-only — Windows text-mode `open()`
    translates every `\\n` in the string to `os.linesep` on WRITE, not only
    on rewrite of an existing CRLF file, so `newline=""` is required here to
    avoid introducing CRLF into a fixture meant to be platform-neutral."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(content)


CONSUMER_TRACKED_FILES = frozenset({"CHANGELOG.md", "package.json", "src/widget.py"})


def build_consumer_repo(dest):
    """Build a throwaway single-package consumer repo at `dest`: one
    `package.json`, one `CHANGELOG.md`, a `v1.2.3` tag, and two synthetic
    Conventional-Commits (`feat`, `fix`) carrying `CHANGELOG:` footers —
    exactly the shape T-73a's task description specifies, and no file from
    this repository."""
    os.makedirs(dest, exist_ok=True)
    _git(["init", "-q"], dest)

    _write_text(
        os.path.join(dest, "package.json"),
        json.dumps({"name": "acme-widgets", "version": "1.2.3", "private": True},
                   indent=2) + "\n")
    _write_text(
        os.path.join(dest, "CHANGELOG.md"),
        "# Changelog\n\n## [1.2.3] - 2026-01-01\n\n### Added\n"
        "- Initial release.\n")
    _git(["add", "-A"], dest)
    _git(["commit", "-q", "-m", "chore: seed v1.2.3 baseline"], dest)
    _git(["tag", "-a", "v1.2.3", "-m", "v1.2.3"], dest)

    _write_text(
        os.path.join(dest, "src", "widget.py"),
        "def make_widget():\n    return {\"kind\": \"widget\"}\n")
    _git(["add", "-A"], dest)
    _git(["commit", "-q", "-m",
          "feat: add widget export\n\n"
          "CHANGELOG: Added a widget export helper."], dest)

    _write_text(
        os.path.join(dest, "src", "widget.py"),
        "def make_widget(count=1):\n    return [{\"kind\": \"widget\"}] * count\n")
    _git(["add", "-A"], dest)
    _git(["commit", "-q", "-m",
          "fix: correct widget off-by-one\n\n"
          "CHANGELOG: Fixed an off-by-one when counting widgets."], dest)


# --------------------------------------------------------------------------- #
# Shared, module-level fixture — built once, torn down once.
# --------------------------------------------------------------------------- #


class _Fixture:
    def __init__(self):
        self.scratch = tempfile.mkdtemp(prefix="ca-consumer-smoke-")
        self.plugin_root = os.path.join(self.scratch, "plugin-root")
        self.consumer_root = os.path.join(self.scratch, "consumer-repo")
        # MEDIUM-3 (adversarial review 2026-07-31): the release skill ships
        # THREE plugin payloads, not one — a second, identically-contaminated
        # copy (`ca-pi`'s, and — the spec's own "Source of truth" list omits
        # this — `ca-codex`'s too) would otherwise ship while T-79's "the
        # list is empty" certified only `ca`. Materialize all three
        # governance-host payloads so the ratchet cannot go green while a
        # sibling payload stays contaminated.
        self.codex_plugin_root = os.path.join(self.scratch, "codex-plugin-root")
        self.pi_plugin_root = os.path.join(self.scratch, "pi-plugin-root")
        try:
            materialize_plugin(REPO_ROOT, self.plugin_root, subpath="plugins/ca")
            materialize_plugin(REPO_ROOT, self.codex_plugin_root,
                                subpath="plugins/ca-codex")
            materialize_plugin(REPO_ROOT, self.pi_plugin_root,
                                subpath="plugins/ca-pi")
            build_consumer_repo(self.consumer_root)
        except Exception:
            self.cleanup()
            raise

    def cleanup(self):
        _force_rmtree(self.scratch)


_FIXTURE = None


def setUpModule():
    global _FIXTURE
    _FIXTURE = _Fixture()


def tearDownModule():
    if _FIXTURE is not None:
        _FIXTURE.cleanup()


# --------------------------------------------------------------------------- #
# T-73a — the fixture itself
# --------------------------------------------------------------------------- #


class ConsumerFixtureTest(unittest.TestCase):
    """T-73a: the scratch consumer fixture stands up correctly, and the
    materialization mechanism is hermetic by construction — proven against
    two REAL artifacts of the exact classes a recursive copy would have
    carried and `git archive` does not."""

    def test_plugin_root_carries_the_committed_release_skill_byte_identically(self):
        # LOW finding (adversarial review 2026-07-31): text-mode `open()`
        # and `_git`'s `encoding="utf-8"` `subprocess.run` BOTH apply
        # universal-newline translation, so a prior version of this
        # assertion compared two ALREADY-CRLF-NORMALIZED strings and could
        # not have caught EOL drift introduced by materialization. Compare
        # raw bytes on both sides instead. Verified: injecting a CRLF flip
        # into the archived copy makes the OLD text-mode comparison pass
        # (a blind spot) while this raw-bytes comparison catches it.
        path = os.path.join(_FIXTURE.plugin_root, "skills", "release", "SKILL.md")
        self.assertTrue(os.path.isfile(path))
        with open(path, "rb") as fh:
            archived = fh.read()
        committed = subprocess.run(
            ["git",
             "-c", f"core.hooksPath={os.path.join(REPO_ROOT, '.ca-fixture-no-hooks-dir')}",
             "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false",
             "show", "HEAD:plugins/ca/skills/release/SKILL.md"],
            cwd=REPO_ROOT, capture_output=True, timeout=GIT_TIMEOUT,
            env=_isolated_git_env())
        self.assertEqual(committed.returncode, 0, committed.stderr)
        self.assertEqual(archived, committed.stdout)

    def test_plugin_root_preserves_executable_bits(self):
        # LOW finding: `materialize_plugin` used to write every extracted
        # file `wb`, which is always 0o644 regardless of what git tracked.
        # 10 files under plugins/ca are 100755 at HEAD; a forward task
        # (T-74/T-75) runs a lane that depends on that surviving
        # materialization. Windows has no POSIX exec bit to assert on.
        if sys.platform == "win32":
            self.skipTest("no POSIX executable bit on win32")
        executable_files = (
            "hooks/_hooklib.py", "hooks/init-codearbiter.py",
            "hooks/post-write-edit.py", "hooks/pre-bash.py",
            "hooks/pre-edit.py", "hooks/pre-write.py",
            "hooks/session-start.py", "hooks/statusline.py",
            "hooks/wire-statusline.py", "tools/farm.js",
        )
        for rel in executable_files:
            path = os.path.join(_FIXTURE.plugin_root, *rel.split("/"))
            self.assertTrue(os.path.isfile(path), path)
            mode = stat.S_IMODE(os.stat(path).st_mode)
            self.assertTrue(
                mode & stat.S_IXUSR,
                f"{rel!r} is 100755 at HEAD but lost its executable bit "
                f"during materialization (mode={oct(mode)})")

    def test_plugin_root_has_no_git_directory(self):
        self.assertFalse(os.path.isdir(os.path.join(_FIXTURE.plugin_root, ".git")))

    def test_plugin_root_is_not_the_in_repo_dev_tree(self):
        dev_tree = os.path.join(REPO_ROOT, "plugins", "ca")
        self.assertNotEqual(os.path.normcase(os.path.abspath(_FIXTURE.plugin_root)),
                             os.path.normcase(os.path.abspath(dev_tree)))
        self.assertFalse(
            os.path.abspath(_FIXTURE.plugin_root).lower()
            .startswith(os.path.abspath(REPO_ROOT).lower()),
            "the materialized plugin root must not live inside this checkout")

    def test_plugin_archive_excludes_gitignored_artifacts(self):
        # plugins/ca/hooks/__pycache__/ is a REAL .gitignore:42 pattern
        # (`__pycache__/`). A recursive copy of the dev tree would carry
        # whatever compiled bytecode happens to be on disk right now;
        # `git archive` must not, since it reads the committed tree only.
        #
        # MEDIUM-5 (adversarial review 2026-07-31): this sentinel is
        # injected into a THROWAWAY `--shared` clone of this repo's own
        # HEAD (`_clone_head`), never into this checkout — see the module
        # docstring's "Materialization" section for why. An earlier version
        # wrote directly into `plugins/ca/hooks/__pycache__/` in THIS
        # checkout, which both violated the fixture's own "no writes inside
        # this repo" contract and would have left the sentinel inside the
        # SHIPPED payload path if the process terminated abnormally
        # (`os._exit`, a kill) between the write and the `finally` cleanup.
        clone_root = tempfile.mkdtemp(prefix="ca-consumer-smoke-clone-")
        try:
            _clone_head(clone_root)
            sentinel_dir = os.path.join(clone_root, "plugins", "ca", "hooks", "__pycache__")
            sentinel_file = os.path.join(sentinel_dir, "_consumer_smoke_sentinel.pyc")
            os.makedirs(sentinel_dir, exist_ok=True)
            with open(sentinel_file, "wb") as fh:
                fh.write(b"not real bytecode -- a fixture marker only")
            ignored = _git(["check-ignore", "-q", sentinel_file], clone_root, check=False)
            self.assertEqual(
                ignored.returncode, 0,
                f"{sentinel_file!r} is not actually gitignored in the clone "
                "— this test's premise is wrong and must be fixed, not the "
                "assertion below")
            with tempfile.TemporaryDirectory() as scratch:
                probe_root = os.path.join(scratch, "plugin-root")
                materialize_plugin(clone_root, probe_root)
                self.assertFalse(
                    os.path.isfile(os.path.join(
                        probe_root, "hooks", "__pycache__",
                        "_consumer_smoke_sentinel.pyc")),
                    "a gitignored dev-tree artifact leaked into the "
                    "git-archive-materialized plugin payload")
        finally:
            _force_rmtree(clone_root)

    def test_plugin_archive_excludes_uncommitted_untracked_files(self):
        # The exact defect class named in AC-6.6: "a skill referencing a
        # file that exists locally but was never committed would still
        # pass" under a recursive copy. This file is real, on disk, in a
        # throwaway clone of THIS repo's own HEAD, and genuinely untracked
        # there — `git archive HEAD` must not see it. See MEDIUM-5 above:
        # the clone keeps the write, and its abnormal-termination residual,
        # entirely inside a scratch tree rather than this checkout.
        clone_root = tempfile.mkdtemp(prefix="ca-consumer-smoke-clone-")
        try:
            _clone_head(clone_root)
            sentinel = os.path.join(
                clone_root, "plugins", "ca", "_consumer_smoke_uncommitted_sentinel.md")
            _write_text(sentinel, "uncommitted -- must never ship\n")
            status = _git(["status", "--porcelain", "--", sentinel], clone_root)
            self.assertIn(
                "??", status.stdout,
                f"{sentinel!r} is not actually untracked in the clone — "
                "this test's premise is wrong and must be fixed, not the "
                "assertion below")
            with tempfile.TemporaryDirectory() as scratch:
                probe_root = os.path.join(scratch, "plugin-root")
                materialize_plugin(clone_root, probe_root)
                self.assertFalse(
                    os.path.isfile(os.path.join(
                        probe_root, "_consumer_smoke_uncommitted_sentinel.md")),
                    "an uncommitted dev-tree file leaked into the "
                    "git-archive-materialized plugin payload")
        finally:
            _force_rmtree(clone_root)

    def test_consumer_repo_tracked_files_are_exactly_the_declared_set(self):
        # Exact-set, not subset: a subset check would silently tolerate a
        # later contamination of this repo's own files into the fixture.
        result = _git(["ls-files"], _FIXTURE.consumer_root)
        tracked = {line for line in result.stdout.splitlines() if line}
        self.assertEqual(tracked, set(CONSUMER_TRACKED_FILES))

    def test_consumer_repo_has_exactly_one_v_tag(self):
        result = _git(["tag", "--list"], _FIXTURE.consumer_root)
        tags = [line for line in result.stdout.splitlines() if line]
        self.assertEqual(tags, ["v1.2.3"])

    def test_consumer_repo_v_tag_is_annotated(self):
        # MEDIUM-LOW-7 (adversarial review 2026-07-31): AC-6.7 rev 4.4
        # justifies creating NO tag in THIS repository on the grounds that
        # "real annotated-tag mechanics are exercised inside the AC-6.6
        # scratch fixture" — a claim that only holds if this fixture's own
        # tag is actually annotated. `git tag -a` in `build_consumer_repo`
        # creates a tag object; `git cat-file -t` distinguishes that from a
        # lightweight tag (a bare ref), which a mutated
        # `git tag v1.2.3` (no `-a`) would silently produce instead.
        obj_type = _git(
            ["cat-file", "-t", "v1.2.3"], _FIXTURE.consumer_root).stdout.strip()
        self.assertEqual(obj_type, "tag")

    def test_consumer_repo_v_tag_names_the_baseline_commit(self):
        tag_commit = _git(
            ["rev-list", "-n", "1", "v1.2.3"], _FIXTURE.consumer_root).stdout.strip()
        head_commit = _git(
            ["rev-parse", "HEAD"], _FIXTURE.consumer_root).stdout.strip()
        self.assertNotEqual(tag_commit, head_commit,
                             "the tag must sit BEHIND HEAD (two commits follow it)")
        first_commit = _git(
            ["rev-list", "--max-parents=0", "HEAD"], _FIXTURE.consumer_root
        ).stdout.strip()
        self.assertEqual(tag_commit, first_commit)

    def test_consumer_repo_commits_carry_changelog_footers(self):
        log = _git(
            ["log", "--format=%B%x03", "HEAD"], _FIXTURE.consumer_root).stdout
        bodies = [b for b in log.split("\x03") if b.strip()]
        footer_bodies = [b for b in bodies if "CHANGELOG:" in b]
        self.assertEqual(
            len(footer_bodies), 2,
            "expected exactly the feat and fix commits to carry a "
            "CHANGELOG: footer")

    def test_consumer_repo_contains_no_file_from_this_repository(self):
        self.assertFalse(
            os.path.isdir(os.path.join(_FIXTURE.consumer_root, ".codearbiter")))
        self.assertFalse(
            os.path.isdir(os.path.join(_FIXTURE.consumer_root, "plugins")))
        with open(os.path.join(_FIXTURE.consumer_root, "package.json"),
                   encoding="utf-8") as fh:
            consumer_pkg = json.load(fh)
        with open(os.path.join(REPO_ROOT, "package.json"), encoding="utf-8") as fh:
            this_repo_pkg = json.load(fh)
        self.assertNotEqual(consumer_pkg["name"], this_repo_pkg["name"])


# --------------------------------------------------------------------------- #
# T-73b/T-79 — reference resolution (started as a ratchet, retired to a
# strict "the unresolved set is empty" assertion)
# --------------------------------------------------------------------------- #

# Matches a slash-separated, extensioned path reference inside a backtick
# code span: an optional placeholder prefix (`${ALL_CAPS_ENV_VAR}/` for
# `claude`/`codex`'s PLUGIN_ROOT/PROJECT_DIR spelling, or
# `<lowercase-hyphenated>/` for `codex`/`pi`'s PROJECT_DIR and `pi`'s
# PLUGIN_ROOT — see `_load_host_tokens`), zero or more `../` hops, one or
# more `segment/` directory components, and a final `name.ext` segment.
# Segments may contain `*`/`?` (HIGH-1, adversarial review 2026-07-31): the
# release skill's badge-count sync EXECUTES three globs
# (`ls plugins/ca/commands/*.md`, `ls -d plugins/ca/skills/*/`,
# `ls plugins/ca/agents/*.md`) that the pre-fix charset could not see at
# all — `plugins/ca/agents/` has no OTHER representative anywhere in this
# file, so all three were invisible to the ratchet and could keep shipping
# after the tracked list went empty.
#
# Stated matching rule (mirrors the docstring obligation A-6.1 places on
# `check_skill_portability.py`): a candidate MUST contain both a `/` and a
# recognizable `.<ext>` file suffix, OR (new) be a directory-only reference
# that is EXECUTED as a glob (contains `*`/`?` — see `_GLOB_DIR_REF_RE`
# below). Deliberately does NOT match:
#
#   - a bare filename with no directory qualifier at all (`CHANGELOG.md`,
#     `package.json` used as literal `$CHANGELOG`/`$MANIFEST` table VALUES).
#     This is the CORRECT portable form for a single-target consumer — the
#     spec's own single-artifact example declares `changelog: CHANGELOG.md`
#     — so naming it bare is not a portability defect and is not extracted;
#   - a PLAIN trailing-slash directory reference with no glob metacharacter
#     (`plugins/ca/`, `plugins/ca-pi/tools/` — the `$PAYLOAD` column). These
#     are SCOPE patterns, not one executed-or-read file. A glob-BEARING
#     trailing-slash reference (`plugins/ca/skills/*/`) is different: `ls -d`
#     EXECUTES it, so the scope-pattern rationale does not reach it —
#     `_GLOB_DIR_REF_RE` matches ONLY when a `*`/`?` is present, never a
#     plain directory mention, which is the discriminator that keeps the
#     whole `$PAYLOAD` column from being pulled in as a side effect;
#   - a dotted module/attribute reference with no slash
#     (`_releaselib.RELEASE_TAG_PREFIXES`, `MAJOR.MINOR.PATCH`).
_PLACEHOLDER_PREFIX = r'(?:\$\{[A-Z_]+\}/|<[a-z][a-z-]*>/)?'
_PATH_REF_RE = re.compile(
    _PLACEHOLDER_PREFIX +
    r'(?:\.\./)*(?:[A-Za-z0-9_.*?-]+/)+[A-Za-z0-9_.*?-]+\.[A-Za-z0-9]+'
)
_GLOB_DIR_REF_RE = re.compile(
    _PLACEHOLDER_PREFIX +
    r'(?:\.\./)*(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]*[*?][A-Za-z0-9_.*?-]*/'
)

# Liveness floor for the extraction, not a permanent contract: the SUM of
# references extracted across every scanned payload (`_RELEASE_SKILL_PAYLOADS`)
# must clear this floor, AND the floor itself must not sit trivially far
# below the live total (see the ratio assertion in
# `test_extraction_is_not_vacuous` — M4, adversarial review 2026-07-31: an
# unasserted floor survived being mutated 15 -> 1, since `total >= 1` is as
# true as `total >= 15` and the test never read the floor's OWN value). As
# T-41a-d replace hardcoded literals with loader-driven values the true
# count WILL drop; lower this floor in the SAME commit that causes it to
# fall, rather than treating a red run here as a reason to widen the regex.
# The exact live count is derived and reported in the assertion failure
# message, never restated here as a second hardcoded figure (LOW finding:
# an earlier version of this comment claimed "22 total references" against
# a live count of 23 — the third unverified-number error in this campaign).
#
# BOTH assertions in `test_extraction_is_not_vacuous` must be re-satisfied
# when lowering this value, not just "total >= floor": the ratio check
# (`floor >= total // 2`) constrains it from the other side. The three full
# skill copies (`ca`, `ca-codex`/`ca-pi` routines) shrink together toward
# T-41's portable form while the two stub payloads hold at 1 reference
# each and never shrink, so pick a floor inside BOTH bounds against the
# post-migration total, not just the pre-migration one.
#
# Lowered by T-41a-d (issue #563): the Targets table -> loader rewrite
# removed the bulk of the previously-extracted literals (measured live total
# post-rewrite: 14, across all five payloads — 4 for `ca`, 1 each for the
# two stubs, 4 each for the `ca-codex`/`ca-pi` routines copies). 12 sits
# inside both bounds (14 >= 12, and 12 >= 14 // 2 = 7) with a small margin
# rather than pinning the floor to the exact live count.
_EXTRACTION_FLOOR = 12
_STABLE_ANCHOR_REF = "${CLAUDE_PLUGIN_ROOT}/includes/anti-slop-design/core.md"

# T-73b payload list — one entry per shipped copy of the release skill.
# (label, host, path relative to that host's materialized plugin root,
# anchor suffix appended to that host's PLUGIN_ROOT token). The anchor is a
# reference expected to ALWAYS be present, unrelated to this campaign's
# migration, so a regression in extraction (or a materialization reading
# the wrong file) shows up as a vacuous-extraction failure rather than a
# silent, wrongly-empty unresolved set.
#
# MEDIUM-3 (adversarial review 2026-07-31): the spec's own "Source of
# truth" section names `plugins/ca/skills/release/`,
# `plugins/ca-codex/skills/ca-release/`, and
# `plugins/ca-pi/skills/ca-release/` PLUS `plugins/ca-pi/routines/release/`
# — four locations. The review additionally found `ca-pi/routines/release/
# SKILL.md` outside the fixture's reach; generalizing that fix (scanning
# EVERY host's routed-to skill, not just the one the review named) surfaces
# a FIFTH location neither the spec nor the review names at all:
# `plugins/ca-codex/routines/release/SKILL.md` carries an IDENTICAL,
# 7-reference-deep copy of the exact contamination. Scanning only the
# payload the review happened to name would have left this one shipping
# uncaught even after this remediation.
_RELEASE_SKILL_PAYLOADS = (
    ("ca", "claude", "skills/release/SKILL.md",
     "includes/anti-slop-design/core.md"),
    ("ca-codex (stub)", "codex", "skills/ca-release/SKILL.md",
     "routines/release/SKILL.md"),
    ("ca-codex (routines)", "codex", "routines/release/SKILL.md",
     "includes/anti-slop-design/core.md"),
    ("ca-pi (stub)", "pi", "skills/ca-release/SKILL.md",
     "routines/release/SKILL.md"),
    ("ca-pi (routines)", "pi", "routines/release/SKILL.md",
     "includes/anti-slop-design/core.md"),
)

# The two stub payloads are pure routers to the full skill and are expected
# to contribute NO unresolved reference of their own — verified by
# `test_stub_release_skills_contribute_no_unresolved_refs` rather than left
# as a one-time manual claim ("verify and leave alone") in a review comment.
_STUB_PAYLOAD_LABELS = frozenset({"ca-codex (stub)", "ca-pi (stub)"})


def _load_host_tokens():
    """(plugin_token, project_token) per governance host, read from
    `core/hosts.json` — the single source `tools/build-surface.py` itself
    renders each generated skill copy from — rather than re-declaring a
    second, driftable copy of the mapping here. `pi`'s tokens
    (`<plugin-root>`, `<project-root>`) differ in SPELLING from `claude`'s
    (`${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PROJECT_DIR}`); a resolver
    hardcoded to one spelling would misclassify the other host's
    already-portable references as bare, this-repo-relative contamination
    (MEDIUM-3's pi-token finding, adversarial review 2026-07-31)."""
    path = os.path.join(REPO_ROOT, "core", "hosts.json")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return {
        host["name"]: (host["tokens"]["PLUGIN_ROOT"], host["tokens"]["PROJECT_DIR"])
        for host in data["hosts"]
    }


_FENCED_CODE_BLOCK_RE = re.compile(r'```.*?```', re.DOTALL)


def _extract_refs(skill_text):
    """Every backtick-code-span path reference in `skill_text` matching
    `_PATH_REF_RE` or `_GLOB_DIR_REF_RE`. Backtick spans are this
    codebase's near-universal convention for naming an executed or read
    path in skill/command prose.

    Triple-backtick FENCED code blocks are excised first, and must be: a
    naive `` `([^`]+)` `` single-backtick pairing treats the first two
    backticks of an opening ```` ``` ```` fence as an empty span, then pairs
    its third backtick with the FIRST backtick of the closing fence — so
    everything between (the whole fenced block) is swallowed as one giant
    span, and backtick-pair alignment for the ENTIRE REST OF THE FILE after
    it is shifted. Measured against the live release skill (after the
    back-fill lane's Phase-3 marker fences landed, f199962): unpatched, only
    8 of the 14 real references across all five payloads were extracted —
    including losing the `${CLAUDE_PLUGIN_ROOT}/includes/anti-slop-design/
    core.md` and `.codearbiter/CONTEXT.md` references outright, which is
    exactly the "extractor silently drops something" failure class a
    resolution check exists to prevent. The fenced blocks here are raw shell
    (`mkdir`/`touch`/`rm -f` with a `git rev-parse`-derived path), never a
    portability-checkable literal, so excising them loses nothing this
    checker is meant to catch. Substituting a newline (not the empty
    string) keeps line numbers stable for anything that reports them."""
    skill_text = _FENCED_CODE_BLOCK_RE.sub('\n', skill_text)
    refs = set()
    for span in re.findall(r'`([^`]+)`', skill_text):
        refs.update(_PATH_REF_RE.findall(span))
        refs.update(_GLOB_DIR_REF_RE.findall(span))
    return refs


def _within_bounds(rel):
    """True iff a POSIX-style relative path `rel` cannot escape the root it
    would be joined to — no leading `/`, no `..` segment — checked WITHOUT
    touching the filesystem, so a placeholder-rooted reference is rejected
    on shape alone before any existence check runs."""
    if rel.startswith("/") or rel.startswith("\\"):
        return False
    return not any(part == ".." for part in rel.split("/"))


# HIGH-2 (adversarial review 2026-07-31): the ONLY reason a project-dir
# reference skips a physical existence check at all is that a
# consumer-owned `.codearbiter/` path is a session/runtime fact, not a
# packaging fact (see `_resolves`'s docstring). The pre-fix behavior
# exempted the WHOLE project-dir arm unconditionally — measured,
# `${CLAUDE_PROJECT_DIR}/.github/scripts/_releaselib.py` resolved `True` —
# which is a gaming vector: repointing every this-repo helper under that
# placeholder would empty the ratchet while leaving the skill exactly as
# unportable, and nothing else in this campaign discriminates against it
# (`check_skill_portability.py` does not exist yet; AC-6.1 permits the
# prefix wholesale). Only `.codearbiter/` is exempt; every other
# project-dir path falls through to a real existence check against the
# scratch consumer repo.
_PROJECT_DIR_EXEMPT_PREFIX = ".codearbiter/"


def _project_dir_is_exempt(rel):
    return rel == _PROJECT_DIR_EXEMPT_PREFIX.rstrip("/") or \
        rel.startswith(_PROJECT_DIR_EXEMPT_PREFIX)


def _resolves(ref, plugin_root, consumer_root,
              plugin_token="${CLAUDE_PLUGIN_ROOT}",
              project_token="${CLAUDE_PROJECT_DIR}"):
    """Classify one extracted path reference against the two scratch roots.
    `plugin_token`/`project_token` are the placeholder SPELLING the host
    that rendered this skill copy uses (`_load_host_tokens`); they default
    to `claude`'s spelling for direct callers/tests that only ever
    exercise that host.

    - `<plugin_token>/<rel>` — the PORTABLE, correct form for a
      shipped-payload path. Checked for PHYSICAL existence under the
      git-archived plugin tree: this is the one arm that can catch a real
      payload-packaging failure (a file the skill's prose promises but the
      shipped payload does not actually carry) — the "installed result,
      physically" check A-6.6 distinguishes from the lexical A-6.1 guard.

    - `<project_token>/<rel>` — the PORTABLE, correct form for a
      consumer-repo-owned project-state path. Existence is checked for
      every subtree EXCEPT `.codearbiter/` (`_project_dir_is_exempt`,
      HIGH-2 above): whether a consumer has already run `/ca:init` and
      populated `.codearbiter/` is a session/runtime fact, never a
      packaging fact — the skill's own prose already handles absence
      explicitly ("Read these, or STOP and surface the gap — never
      guess"). Treating absence there as a portability defect would pin
      `.codearbiter/CONTEXT.md` into the ratchet list PERMANENTLY, since
      T-73a's fixture deliberately has no `.codearbiter/` (per the spec's
      declared consumer-repo contents) — which would make T-79's "assert
      the list is empty" unreachable. Any OTHER project-dir path is real
      existence-checked against the scratch consumer repo, so the
      exemption cannot be used to launder an arbitrary this-repo path.

    - anything else — a BARE repo-relative path with no placeholder at
      all. The only way such a reference resolves at runtime is if the
      skill's shell commands happen to run with the CONSUMER repo as cwd
      (which they do), so it is checked for existence there, after the
      SAME in-bounds check the placeholder arms get — defensive hardening
      added alongside HIGH-2: an unbounded bare `../../<repo file>`
      reference could otherwise escape the scratch consumer root the same
      way an unbounded project-dir arm could. A bare path naming this
      repository's own layout (`.github/scripts/...`, `plugins/ca/...`,
      `tools/...`) is exactly the contamination class this campaign exists
      to remove, and will not exist in ANY consumer repo."""
    plugin_prefix = plugin_token + "/"
    project_prefix = project_token + "/"
    if ref.startswith(plugin_prefix):
        rel = ref[len(plugin_prefix):]
        if not _within_bounds(rel):
            return False
        return os.path.exists(os.path.join(plugin_root, *rel.split("/")))
    if ref.startswith(project_prefix):
        rel = ref[len(project_prefix):]
        if not _within_bounds(rel):
            return False
        if _project_dir_is_exempt(rel):
            return True
        return os.path.exists(os.path.join(consumer_root, *rel.split("/")))
    if not _within_bounds(ref):
        return False
    return os.path.exists(os.path.join(consumer_root, *ref.split("/")))


class ReferenceResolutionTest(unittest.TestCase):
    """T-73b/T-79 (A-6.6, 'reference resolution'). Physically resolves every
    executed-or-read path reference in EVERY installed copy of the release
    skill (`_RELEASE_SKILL_PAYLOADS`) against the matching scratch plugin
    root and the shared scratch consumer repo, and asserts the UNIONED
    unresolved set is EMPTY.

    T-79 retired the T-73b RATCHET (equality against a committed
    `known-unresolved-refs.txt`, in either direction) into this strict
    zero-form: the skill rewrite (T-41a-d/T-41f) resolved all 24 entries
    the ratchet ever carried, so there is no longer a tolerated-failures
    list to compare against — an empty set is simply asserted outright.

    The ratchet's whole reason to exist was failing in BOTH directions (a
    shrink nobody recorded, and a NEW contaminating reference sneaking in),
    and the strict form must keep both. A shrink has nothing left to catch
    (the list is already empty), so only the second direction still needs a
    live guarantee: a new contaminating reference must still turn this red.
    That is exactly what `self.unresolved == set()` asserts, and
    `test_extraction_is_not_vacuous` below is what keeps this assertion from
    being satisfiable by an extractor that has quietly stopped matching
    anything — the exact failure mode this campaign already found once
    (M4, adversarial review 2026-07-31)."""

    @classmethod
    def setUpClass(cls):
        cls.host_tokens = _load_host_tokens()
        root_by_host = {
            "claude": _FIXTURE.plugin_root,
            "codex": _FIXTURE.codex_plugin_root,
            "pi": _FIXTURE.pi_plugin_root,
        }
        cls.per_payload = {}
        cls.unresolved = set()
        cls.extracted_total = 0
        for label, host, relpath, anchor_suffix in _RELEASE_SKILL_PAYLOADS:
            plugin_root = root_by_host[host]
            plugin_token, project_token = cls.host_tokens[host]
            skill_path = os.path.join(plugin_root, *relpath.split("/"))
            if not os.path.isfile(skill_path):
                raise RuntimeError(
                    f"installed release skill not found at {skill_path!r} "
                    f"(payload {label!r}) — the plugin payload "
                    "materialization itself is broken, not merely this "
                    "reference check")
            with open(skill_path, encoding="utf-8") as fh:
                text = fh.read()
            extracted = _extract_refs(text)
            unresolved = {
                ref for ref in extracted
                if not _resolves(ref, plugin_root, _FIXTURE.consumer_root,
                                  plugin_token, project_token)
            }
            cls.per_payload[label] = {
                "extracted": extracted,
                "unresolved": unresolved,
                "anchor": plugin_token + "/" + anchor_suffix,
            }
            cls.extracted_total += len(extracted)
            cls.unresolved |= unresolved

    def test_extraction_is_not_vacuous(self):
        for label, data in self.per_payload.items():
            self.assertIn(
                data["anchor"], data["extracted"],
                f"payload {label!r}: a reference that should always be "
                "found (unrelated to this campaign's migration) is "
                "missing — the extractor likely regressed, or the "
                "installed skill file resolved to the wrong path")
        self.assertGreaterEqual(
            self.extracted_total, _EXTRACTION_FLOOR,
            f"only {self.extracted_total} path references were extracted "
            f"across all {len(_RELEASE_SKILL_PAYLOADS)} scanned release-"
            f"skill payloads (floor: {_EXTRACTION_FLOOR}). If this is "
            "because T-41a-d legitimately removed hardcoded references, "
            "lower _EXTRACTION_FLOOR in the SAME commit; if not, the "
            "extraction regex itself likely regressed")
        # M4 (adversarial review 2026-07-31): the floor assertion above
        # alone is satisfied by ANY positive floor, so mutating
        # _EXTRACTION_FLOOR down to 1 survives it silently. This second
        # assertion reads the floor's OWN value against the live total, so
        # a floor that has drifted far below reality — whether by mutation
        # or by neglect — goes red here specifically.
        self.assertGreaterEqual(
            _EXTRACTION_FLOOR, self.extracted_total // 2,
            f"_EXTRACTION_FLOOR ({_EXTRACTION_FLOOR}) is far below the "
            f"live extracted total ({self.extracted_total}) — it no "
            "longer distinguishes 'the extractor stopped matching "
            "anything' from 'the skill genuinely has fewer references "
            "now'; raise it toward the live count")

    def test_stub_release_skills_contribute_no_unresolved_refs(self):
        # MEDIUM-3 (adversarial review 2026-07-31): the review found these
        # two payloads are "short stubs with none" and said "verify and
        # leave alone" — proven here directly, on every run, rather than
        # left as a one-time manual claim in a review comment.
        for label in _STUB_PAYLOAD_LABELS:
            self.assertEqual(
                self.per_payload[label]["unresolved"], set(),
                f"stub payload {label!r} now carries an unresolved "
                "reference of its own — it is no longer a pure router to "
                "the full release skill and must be scanned as one")

    def test_reference_resolution_is_empty(self):
        # T-79's strict zero-form: no committed list to compare against —
        # the UNIONED set of unresolved path references across every
        # installed release-skill payload (materialized from live HEAD)
        # must simply be empty.
        self.assertEqual(
            self.unresolved, set(),
            "the release skill (or one of its ca-codex/ca-pi copies) "
            "carries a path reference that does not resolve against the "
            "shipped payload or the scratch consumer repo — a NEW "
            "contaminating this-repo reference, or a payload-packaging "
            "regression:\n"
            f"  unresolved: {sorted(self.unresolved)}\n"
            "Remember: the fixture archives `HEAD`, not the working tree — "
            "commit the fix before re-running this test.")


class ResolverUnitTest(unittest.TestCase):
    """Direct, synthetic-input coverage of `_resolves`'s three arms and the
    extractor's glob support. The live release skill carries exactly ONE
    `${CLAUDE_PLUGIN_ROOT}` reference in its `claude` copy and it happens
    to resolve, so a mutant that made that arm always return True would
    survive `ReferenceResolutionTest` undetected; these exercise each arm
    with both a present and an absent input directly."""

    def test_plugin_root_arm_present(self):
        self.assertTrue(_resolves(
            _STABLE_ANCHOR_REF, _FIXTURE.plugin_root, _FIXTURE.consumer_root))

    def test_plugin_root_arm_absent(self):
        self.assertFalse(_resolves(
            "${CLAUDE_PLUGIN_ROOT}/does/not/exist.md",
            _FIXTURE.plugin_root, _FIXTURE.consumer_root))

    def test_plugin_root_arm_rejects_escape(self):
        # Points at a path that GENUINELY EXISTS just outside plugin_root
        # (the sibling consumer_root's own package.json) rather than an
        # arbitrary absent one — so only `_within_bounds`, never the
        # existence check, can be the reason this returns False. An escape
        # ref that merely happens not to exist would pass this assertion
        # even with the bounds check deleted outright.
        self.assertFalse(_resolves(
            "${CLAUDE_PLUGIN_ROOT}/../consumer-repo/package.json",
            _FIXTURE.plugin_root, _FIXTURE.consumer_root))

    def test_project_dir_arm_is_resolved_by_construction(self):
        self.assertTrue(_resolves(
            "${CLAUDE_PROJECT_DIR}/.codearbiter/CONTEXT.md",
            _FIXTURE.plugin_root, _FIXTURE.consumer_root))

    def test_project_dir_arm_rejects_escape(self):
        self.assertFalse(_resolves(
            "${CLAUDE_PROJECT_DIR}/../outside.md",
            _FIXTURE.plugin_root, _FIXTURE.consumer_root))

    def test_project_dir_arm_gaming_vector_is_rejected(self):
        # HIGH-2 (adversarial review 2026-07-31): pre-fix, ANY path
        # repointed under ${CLAUDE_PROJECT_DIR} resolved unconditionally —
        # this measured True before the fix. A skill could repoint every
        # this-repo helper under this placeholder and empty the ratchet
        # while shipping exactly the same contamination.
        self.assertFalse(_resolves(
            "${CLAUDE_PROJECT_DIR}/.github/scripts/_releaselib.py",
            _FIXTURE.plugin_root, _FIXTURE.consumer_root))

    def test_project_dir_arm_exemption_is_narrow(self):
        # Paired with the two tests above: a NON-.codearbiter project-dir
        # path that genuinely exists in the consumer repo still resolves
        # via a real existence check, and one that does not exist still
        # fails — proving the exemption is scoped to `.codearbiter/`
        # specifically, never widened to "anything under the project dir"
        # as an overcorrection for the gaming vector.
        self.assertTrue(_resolves(
            "${CLAUDE_PROJECT_DIR}/package.json",
            _FIXTURE.plugin_root, _FIXTURE.consumer_root))
        self.assertFalse(_resolves(
            "${CLAUDE_PROJECT_DIR}/does/not/exist.md",
            _FIXTURE.plugin_root, _FIXTURE.consumer_root))

    def test_bare_arm_present(self):
        self.assertTrue(_resolves(
            "src/widget.py", _FIXTURE.plugin_root, _FIXTURE.consumer_root))

    def test_bare_arm_absent(self):
        self.assertFalse(_resolves(
            "docs/missing.md", _FIXTURE.plugin_root, _FIXTURE.consumer_root))

    def test_bare_arm_rejects_escape(self):
        # Defensive hardening added alongside HIGH-2, the same
        # gaming-vector class applied to the THIRD arm: a bare reference is
        # now checked in-bounds before any existence check. Points at a
        # path that GENUINELY EXISTS just outside consumer_root (the
        # sibling plugin_root's own SKILL.md) so only the bounds check,
        # never the existence check, can be the reason this returns False.
        self.assertFalse(_resolves(
            "../plugin-root/skills/release/SKILL.md",
            _FIXTURE.plugin_root, _FIXTURE.consumer_root))

    def test_resolves_with_pi_host_tokens(self):
        # The resolver must work for a host whose placeholder SPELLING is
        # not claude's, not just accept the string by accident.
        plugin_token, project_token = _load_host_tokens()["pi"]
        self.assertTrue(_resolves(
            f"{plugin_token}/routines/release/SKILL.md",
            _FIXTURE.pi_plugin_root, _FIXTURE.consumer_root,
            plugin_token, project_token))
        self.assertFalse(_resolves(
            f"{plugin_token}/does/not/exist.md",
            _FIXTURE.pi_plugin_root, _FIXTURE.consumer_root,
            plugin_token, project_token))

    def test_pi_style_placeholder_is_not_misread_as_bare(self):
        # MEDIUM-3's pi-token finding (adversarial review 2026-07-31): a
        # claude-spelled extractor cannot even MATCH `<plugin-root>/...` at
        # the prefix (no `$` or all-caps env-var shape), so `findall`
        # slides forward and returns only the bare tail — which then fails
        # a real-existence check against consumer_root and becomes a
        # PERMANENT false-contamination entry no T-41x task could ever
        # clear. Proven directly: the whole placeholder-qualified path must
        # be captured, not merely its tail.
        text = "`<plugin-root>/includes/anti-slop-design/core.md`"
        self.assertEqual(
            _extract_refs(text),
            {"<plugin-root>/includes/anti-slop-design/core.md"})

    def test_extractor_sees_executed_globs(self):
        # HIGH-1 (adversarial review 2026-07-31): before the segment
        # charset and `_GLOB_DIR_REF_RE` existed, all three of these
        # EXECUTED globs from the release skill's badge-count sync were
        # invisible to the extractor — `plugins/ca/agents/` has no other
        # representative anywhere in the file, so the ratchet could go
        # empty while all three kept shipping.
        text = (
            "`commands = ls plugins/ca/commands/*.md | grep -v INDEX | wc -l`\n"
            "`skills = ls -d plugins/ca/skills/*/ | wc -l`\n"
            "`agents = ls plugins/ca/agents/*.md | grep -v INDEX | wc -l`\n"
        )
        self.assertEqual(
            _extract_refs(text),
            {"plugins/ca/commands/*.md", "plugins/ca/skills/*/",
             "plugins/ca/agents/*.md"})

    def test_glob_dir_ref_does_not_match_a_plain_scope_directory(self):
        # The discriminator HIGH-1 relies on: a plain trailing-slash SCOPE
        # mention with no glob metacharacter must stay excluded, or the fix
        # would pull the whole `$PAYLOAD` column (`plugins/ca/`,
        # `plugins/ca-pi/tools/`, ...) into the ratchet as a side effect.
        text = "`plugins/ca/` and `plugins/ca-pi/tools/` are payload scopes."
        self.assertEqual(_extract_refs(text), set())

    def test_extractor_still_sees_a_reference_after_a_fenced_code_block(self):
        # Regression pin, independent of the live skill text: introduced by
        # f199962 ("add the back-fill lane"), a fenced ```bash block desyncs
        # a naive `` `([^`]+)` `` single-backtick pairing for everything
        # AFTER it — measured live, this silently dropped 6 of 14 real
        # references across the five shipped payloads, including the very
        # anchor `test_extraction_is_not_vacuous` depends on. This is the
        # exact "an extractor that silently matches nothing [useful]" class
        # of failure the empty-set assertion (`test_reference_resolution_
        # is_empty`) would otherwise be vacuous against. A synthetic fixture
        # here catches a regression even if the live skill text changes
        # shape enough to stop tripping over it by accident.
        text = (
            "Mint the marker:\n\n"
            "   ```bash\n"
            "   mkdir -p \"$(git rev-parse --show-toplevel)/.codearbiter/.markers\"\n"
            "   ```\n\n"
            "Then apply `${CLAUDE_PLUGIN_ROOT}/includes/anti-slop-design/core.md` "
            "before writing.\n"
        )
        self.assertEqual(
            _extract_refs(text),
            {"${CLAUDE_PLUGIN_ROOT}/includes/anti-slop-design/core.md"})


# --------------------------------------------------------------------------- #
# MEDIUM-6 (adversarial review 2026-07-31) — the hermetic git-env guards
# --------------------------------------------------------------------------- #


class HermeticGitEnvTest(unittest.TestCase):
    """`_isolated_git_env`/`_git`'s own docstrings call two controls
    "load-bearing" (issue #556) and cite a concrete threat for each, but
    nothing previously EXECUTED either claim — the assert-the-contract-
    instead-of-the-path shape (memory: dry-run-the-path-not-the-contract).
    Both tests here poison an AMBIENT setting the way a real host could,
    then prove the fixture's own git calls are unaffected; each is
    reproducibly killed by removing the specific override it names."""

    def test_git_config_global_neutralizes_an_ambient_template_dir_poison(self):
        # `core.hooksPath`/`commit.gpgsign`/`tag.gpgsign` are already
        # neutralized on every `_git` call via explicit `-c` flags
        # regardless of GIT_CONFIG_GLOBAL, so poisoning THOSE keys would
        # not discriminate a mutant that renamed GIT_CONFIG_GLOBAL itself.
        # `init.templateDir` is not covered by any per-call `-c` override —
        # it is exactly the class of ambient setting GIT_CONFIG_GLOBAL
        # alone protects. A poisoned templateDir's contents get copied
        # into every `git init`'d repo's `.git/`, so its presence or
        # absence is directly observable.
        with tempfile.TemporaryDirectory() as scratch:
            poison_template = os.path.join(scratch, "poison-template")
            os.makedirs(poison_template, exist_ok=True)
            with open(os.path.join(poison_template, "POISON.txt"), "w") as fh:
                fh.write("poison\n")
            poison_global = os.path.join(scratch, "poison-global.gitconfig")
            with open(poison_global, "w") as fh:
                fh.write("[init]\n\ttemplateDir = %s\n"
                          % poison_template.replace("\\", "/"))

            old = os.environ.get("GIT_CONFIG_GLOBAL")
            os.environ["GIT_CONFIG_GLOBAL"] = poison_global
            try:
                repo = os.path.join(scratch, "repo")
                os.makedirs(repo, exist_ok=True)
                _git(["init", "-q"], repo)
                self.assertFalse(
                    os.path.isfile(os.path.join(repo, ".git", "POISON.txt")),
                    "an ambient GIT_CONFIG_GLOBAL leaked its init.templateDir "
                    "contents into a fixture-initialized repo — "
                    "_isolated_git_env's GIT_CONFIG_GLOBAL override is not "
                    "doing its job")
            finally:
                if old is None:
                    os.environ.pop("GIT_CONFIG_GLOBAL", None)
                else:
                    os.environ["GIT_CONFIG_GLOBAL"] = old

    def test_per_call_hookspath_override_bypasses_a_poisoned_default_hooks_dir(self):
        # A poisoned real `.git/hooks/pre-commit` (issue #556's stale
        # cross-host enforcer cache, or any other blocking hook) sits at
        # the DEFAULT hooks location, which `core.hooksPath` from
        # GIT_CONFIG_GLOBAL alone would not relocate away from (a repo's
        # own local `.git/hooks/` is consulted regardless of the global
        # config file, absent an explicit `core.hooksPath` override on
        # THIS call). `_git` sets that override per call; deleting it
        # would let this exact hook fire and block the commit.
        with tempfile.TemporaryDirectory() as scratch:
            repo = os.path.join(scratch, "repo")
            os.makedirs(repo, exist_ok=True)
            _git(["init", "-q"], repo)
            hooks_dir = os.path.join(repo, ".git", "hooks")
            os.makedirs(hooks_dir, exist_ok=True)
            hook_path = os.path.join(hooks_dir, "pre-commit")
            with open(hook_path, "w", newline="\n") as fh:
                fh.write("#!/bin/sh\nexit 1\n")
            try:
                os.chmod(hook_path, 0o755)
            except OSError:
                pass
            _write_text(os.path.join(repo, "a.txt"), "hi\n")
            _git(["add", "-A"], repo)
            result = _git(["commit", "-q", "-m", "test commit"], repo, check=False)
            self.assertEqual(
                result.returncode, 0,
                "a poisoned default .git/hooks/pre-commit blocked a fixture "
                "commit — _git's per-call `-c core.hooksPath=...` override "
                "is not bypassing it")


# --------------------------------------------------------------------------- #
# T-74/T-75 — the lane driver: invocation strings extracted from the
# INSTALLED release skill, run for real (or classified "accounted", see
# below) against a private, disposable consumer repo. (issue #563, AC-6.6
# "Lane driver" and
# "Assertions are on derived outputs"; .codearbiter/plans/portable-release-
# and-protected-state.md T-74, T-75.)
#
# Why this is not a direct-import test of core/pysrc/_releaselib.py: the
# release skill (`plugins/ca/skills/release/SKILL.md`, pre-T-41x) tells its
# reader to run SPECIFIC shell command lines — `TAG_PREFIX=$(python3
# .github/scripts/_releaselib.py tag-prefix $TARGET)`, `git log
# LAST_TAG..HEAD -- $PAYLOAD`, `git tag -a ... -F <message-file>`, and so
# on. A test that imports `_releaselib.py`'s functions directly and calls
# them in Python can pass while the PROSE instructs the reader to invoke a
# CLI shape that script no longer accepts (an added required argument, a
# renamed subcommand, a flag that moved) — direct import cannot see that
# drift because it never goes through the CLI surface the prose actually
# names. This module instead locates the literal backtick-delimited command
# line following a stable prose ANCHOR in the installed skill text, and
# either subprocess-executes it for real (after substituting the variables
# the skill's own prose defines: `$TARGET`, `$TAG_PREFIX`, `$PAYLOAD`,
# `LAST_TAG`, `${TAG_PREFIX}MAJOR.MINOR.PATCH`, `<message-file>`) or, when
# the invocation names a this-repo path with no `__main__` to run (this
# module's own historical example was `.github/scripts/_releaselib.py`, a
# CI-only shim that never shipped in the plugin payload), classifies it
# "accounted" rather than running it. T-41b's repointing plus giving the
# portable mechanism a CLI were BOTH prerequisites before this class of
# invocation could ever move from accounted to run; the live skill no
# longer produces one (see `test_no_invocations_remain_accounted` below).
# T-79 additionally retired the `known-unresolved-refs.txt` file this
# accounting used to be cross-checked against — "accounted" is now a
# synthetic/unit-test-only concept (`ReferenceResolutionTest`'s empty-set
# assertion is the live guarantee), kept as general machinery in case a
# future invocation reintroduces an unresolvable this-repo path.
#
# Honest scope limit, stated once here rather than left implicit: this
# driver only extracts from `## Targets` through the end of `## Phase 2` —
# never `## Phase 3 — Publish`, which requires explicit user authorization
# and names `git push`, `gh release create`, and `gh release view`. Those
# are gated write/publish actions this fixture must never perform even
# against a disposable repo (no network, no auth, and out of AC-6.6's named
# "target resolution, window derivation, bump classification, changelog
# rolling, tag-message composition" scope). `RELEASE_DATE=$(date +%F)` is
# ALSO out of this driver's extracted set for a narrower reason: `date` is
# not a stdlib-guaranteed executable on every platform this suite runs on
# (the same class of problem T-42's python3->interpreter-fallback exists
# to fix, but nothing yet fixes it for `date`), so this module derives the
# release date with Python's own `datetime.date.today()` instead of
# shelling out — labelled here as test-authored plumbing, never claimed as
# an "extracted invocation".

RELEASE_TARGETS_BLOCK = (
    "<!-- release-targets -->\n"
    "[app]\n"
    "prefix: v\n"
    "manifest: package.json\n"
    "changelog: CHANGELOG.md\n"
    "payload: .\n"
    "<!-- /release-targets -->\n"
)

# A candidate backtick span "looks like an invocation" iff it starts with a
# shell assignment (`VAR=$(`), or a bare `git `/`python3 `/`node ` command —
# the shapes every invocation this driver cares about actually takes. This
# excludes non-invocation backtick spans that sit near an anchor in the same
# sentence (a dotted function reference like `_releaselib.classify_publish_
# state`, or a bare variable mention like `$PAYLOAD`), so the capture walks
# past those to the real command rather than mis-extracting the first
# backtick span it meets.
_INVOCATION_SHAPE_RE = re.compile(r'^(?:[A-Za-z_][A-Za-z0-9_]*=\$\(|git |python3 |node )')

# label -> (stable prose anchor, expected classification). Each anchor
# string is verified unique in the installed skill text (ConsumerFixtureTest-
# style hard-fail on drift, not a silent widen); the expected classification
# is asserted directly in LaneDriverTest.test_lane_driver_classification_map
# so a mutant flipping run<->accounted is caught without comparing the
# driver to itself.
_LANE_INVOCATION_ANCHORS = (
    ("target_resolution_tag_prefix", "never typed from memory:", "run"),
    ("window_last_tag", "never a hand-rolled grep:", "run"),
    ("window_scope_bare", "the commit set is", "run"),
    ("window_scope_full_log", "Read every commit in the", "run"),
    # Anchored on "Peel it through" rather than the former "Tag with":
    # Phase 2 step 1 was reordered so `git tag` runs only inside the
    # `publish_fresh` branch, AFTER classification (MEDIUM, run-3
    # adversarial review — a literal reading of the old order wrote the ref
    # before computing whether writing it was safe). The captured
    # invocation is unchanged (`peel-tag`); only the prose landmark ahead
    # of it moved. Verified unique in all three installed renderings by
    # test_lane_anchors_are_unique_in_every_rendering below.
    ("tag_sha_peel", "Peel it through", "run"),
    ("publish_state_classify", "do not flatly abort", "run"),
)

# T-41b/T-41f (issue #563): all six anchored invocations now resolve under
# the vendored plugin's OWN CLI (`${CLAUDE_PLUGIN_ROOT}/hooks/_releaselib.py`,
# core/pysrc/_releaselib.py's `__main__` entry point) and run for real —
# before this rewrite, three of the six named `.github/scripts/_releaselib.py`
# (a CI-only shim with no `__main__`) and were merely ACCOUNTED for on the
# T-73b ratchet (since retired by T-79), since nothing could actually invoke
# that path from inside a consumer. `_classify_invocation`/`_LANE_SHIM_MARKER` remain as
# general machinery — `LaneDriverUnitTest` still exercises the accounted arm
# directly against synthetic text — in case a future invocation reintroduces
# an unresolvable this-repo path; the LIVE skill no longer produces one.
_LANE_SHIM_MARKER = ".github/scripts/_releaselib.py"


def _capture_invocation_after_anchor(skill_text, anchor, window=500):
    """Find `anchor` (a stable, unique prose substring) in `skill_text`, then
    return the content of the FIRST invocation-shaped backtick span within
    `window` characters after it — skipping any non-invocation backtick span
    (a dotted name, a bare variable mention) that appears first in the same
    sentence. Hard-fails with a named cause, rather than returning an empty
    or partial result, if the anchor is missing (the skill's prose shape
    changed) or no invocation-shaped span follows it (the skill stopped
    naming a command where it used to) — this IS the drift detector; a
    silent skip here would defeat the entire point of extracting from the
    installed text instead of importing the library directly."""
    idx = skill_text.find(anchor)
    if idx == -1:
        raise RuntimeError(
            f"lane-driver anchor not found in the installed release skill: "
            f"{anchor!r} — the skill's prose has changed shape; this "
            "driver's anchors need updating in the SAME commit")
    scanned = skill_text[idx + len(anchor): idx + len(anchor) + window]
    for m in re.finditer(r'`([^`]+)`', scanned):
        candidate = m.group(1)
        if _INVOCATION_SHAPE_RE.match(candidate):
            return candidate
    raise RuntimeError(
        f"no invocation-shaped backtick span found within {window} chars "
        f"after anchor {anchor!r} — the skill stopped naming a runnable "
        "command here")


def _classify_invocation(invocation):
    """"accounted" iff the invocation names the one currently-unresolvable
    this-repo path; "run" otherwise. Post-T-79, there is no committed
    ratchet file to cross-check the accounted case against — the live
    guarantee is `test_no_invocations_remain_accounted`, which asserts the
    accounted case never actually occurs against the shipped skill. This
    function alone does not read any file, so a unit test can exercise it
    against synthetic text with no fixture dependency."""
    return "accounted" if _LANE_SHIM_MARKER in invocation else "run"


def _substitute_argv(argv, mapping):
    """Token-by-token substitution over an ALREADY-`shlex.split` argv list —
    never a substring replace over the raw command STRING before splitting.
    This matters concretely on Windows: the composed tag-message temp path
    substituted for `<message-file>` contains backslashes, and `shlex.split`
    (POSIX mode) treats an unquoted backslash as an escape character that
    would corrupt such a path if it were substituted into the string BEFORE
    tokenization and the result were re-split. Splitting the original,
    backslash-free skill text FIRST and substituting whole or partial tokens
    AFTER avoids ever feeding a Windows path through `shlex`. A single
    substring-replace pass per token covers both a WHOLE-token match
    (`$PAYLOAD`, `<message-file>`) and a token that only CONTAINS the
    variable (`LAST_TAG..HEAD`) — a separate `tok in mapping` short-circuit
    would be dead code, since `str.replace` on an exact match already
    returns the same result."""
    out = []
    for tok in argv:
        replaced = tok
        for old, new in mapping.items():
            if old in replaced:
                replaced = replaced.replace(old, new)
        out.append(replaced)
    return out


def _prepare_argv(argv, cwd):
    """Apply this module's two standing per-invocation transforms to one
    already-tokenized argv list, returning the adjusted list (never mutates
    the input): a leading bare `python3` becomes `sys.executable`, since
    `python3` is not guaranteed present, especially on Windows (the same
    substitution T-42 tracks for the skill itself); a leading `git` gets the
    SAME hermetic isolation `_git` gives every other git call in this module
    (a lane-driver-composed `git tag -a` is exactly as reachable by an
    ambient core.hooksPath/gpgsign poison as any other git invocation here)."""
    if argv and argv[0] == "python3":
        argv = [sys.executable] + argv[1:]
    if argv and argv[0] == "git":
        no_hooks = os.path.join(cwd, ".ca-fixture-no-hooks-dir")
        argv = ["git",
                "-c", f"core.hooksPath={no_hooks}",
                "-c", "commit.gpgsign=false",
                "-c", "tag.gpgsign=false",
                "-c", "user.name=codeArbiter consumer-smoke fixture",
                "-c", "user.email=fixture@example.invalid",
                *argv[1:]]
    return argv


def _run_argv(argv, cwd, input_text=None):
    """Execute one substituted, already-tokenized invocation. No
    `shell=True` anywhere in this module — every invocation this driver runs
    is a plain argv list; a pipe-bearing invocation is staged as SEPARATE
    subprocess calls chained by stdin (`_run_command_substitution`), never a
    literal `|` handed to a real shell. `input_text`, when given, is piped to
    the process's stdin (the pipeline-staging case).

    T-41f (issue #563): a python invocation's environment is built EXPLICITLY
    rather than inherited. `core/pysrc/_releaselib.py`'s `tag-prefix`
    subcommand resolves its declared file via `CLAUDE_PROJECT_DIR` first
    (`default_targets_path`), and an ambient value leaking in from whatever
    session happens to be running this SUITE (this file is itself typically
    run from inside a governed session) would silently repoint resolution
    away from this fixture's own scratch consumer — exactly the class of
    dev-tree-state leak this whole module exists to keep out (memory:
    dev-repo-state-masks-consumer-bugs). `CLAUDE_PROJECT_DIR` is therefore
    always pinned to `cwd`, mirroring what a real host harness does, and
    `CLAUDE_PLUGIN_ROOT` is stripped since no invocation this driver runs
    reads it as an env var — the plugin root is already substituted directly
    into the argv string before this function ever sees it."""
    argv = _prepare_argv(argv, cwd)
    if argv[0] == "git":
        env = _isolated_git_env()
    else:
        env = dict(os.environ)
        env.pop("CLAUDE_PLUGIN_ROOT", None)
        env["CLAUDE_PROJECT_DIR"] = cwd
    return subprocess.run(argv, cwd=cwd, capture_output=True, encoding="utf-8",
                           timeout=GIT_TIMEOUT, input=input_text, env=env)


_VAR_SUBSHELL_RE = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)=\$\((.*)\)$')


def _run_command_substitution(invocation, cwd, mapping):
    """Run a `VAR=$(command)` shaped invocation — possibly containing an
    internal `|` pipeline — for real. Each pipeline stage is a SEPARATE
    `_run_argv` call chained by stdin, never a literal `$(...)` or `|`
    handed to an actual shell (no `shell=True` anywhere in this module).
    Returns `(var_name, stdout.strip(), last_process)` so a caller can both
    use the resolved value and assert on the process that produced it.
    T-41b/T-41f (issue #563): before the release skill's helper invocations
    were repointed under `${CLAUDE_PLUGIN_ROOT}` and the portable mechanism
    gained a CLI, both of this driver's `VAR=$(...)` invocations named a
    this-repo-only shim with no `__main__` and could only be ACCOUNTED for;
    this function is what makes them genuinely RUNNABLE post-rewrite."""
    m = _VAR_SUBSHELL_RE.match(invocation)
    if not m:
        raise ValueError(f"not a VAR=$(...) invocation: {invocation!r}")
    var_name, inner = m.group(1), m.group(2)
    stdin_text = None
    proc = None
    for stage in (s.strip() for s in inner.split("|")):
        argv = _substitute_argv(shlex.split(stage), mapping)
        proc = _run_argv(argv, cwd, input_text=stdin_text)
        stdin_text = proc.stdout
    return var_name, (proc.stdout or "").strip(), proc


def _independent_last_tag(tags, prefix):
    """A LAST_TAG oracle sharing no code with `core/pysrc/_releaselib.py`'s
    `last_tag_select` — mirrors `test_release_trace.py`'s
    `_independent_last_tag` so agreement between the two is genuine
    cross-validation, not two lookups through the same helper."""
    rx = re.compile(r"^" + re.escape(prefix) + r"(\d+)\.(\d+)\.(\d+)$")
    best = None
    for tag in tags:
        m = rx.match(tag)
        if not m:
            continue
        version = tuple(int(g) for g in m.groups())
        if best is None or version > best[0]:
            best = (version, tag)
    return best[1] if best else None


def _parse_window_log(stdout):
    """Parse `git log --pretty=format:%H%n%s%n%b%n----`'s output into a list
    of `{"sha", "subject", "body"}` dicts, oldest-last (git's own order).
    Entries are delimited by a line that is EXACTLY `----`, matching the
    skill's own format string byte for byte."""
    entries = []
    for chunk in stdout.split("\n----\n"):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        lines = chunk.split("\n")
        entries.append({
            "sha": lines[0],
            "subject": lines[1] if len(lines) > 1 else "",
            "body": "\n".join(lines[2:]).strip("\n"),
        })
    return entries


_COMMIT_TYPE_RE = re.compile(r"^(\w+)(\([^)]*\))?(!)?:")
_CHANGELOG_FOOTER_RE = re.compile(r"CHANGELOG:\s*(.+)")
_GROUP_BY_TYPE = {"feat": "Added", "fix": "Fixed", "perf": "Performance"}


def _commit_type(subject):
    m = _COMMIT_TYPE_RE.match(subject)
    if not m:
        return None, False
    return m.group(1), bool(m.group(3))


def _footer_text(body):
    m = _CHANGELOG_FOOTER_RE.search(body)
    return m.group(1).strip() if m else None


def _classify_bump(entries):
    """Transcription of `release/SKILL.md` Phase 1 step 2's classification
    rule. No CLI exists for this in the pre-T-41x skill — there is no
    invocation string to extract, so this is test-authored, mirroring the
    numbered prose directly rather than importing a mechanism function
    (none exists to import). Returns None for a non-bumping window (the
    skill's own STOP case), never a silent default bump."""
    major = minor = patch = False
    for e in entries:
        ctype, bang = _commit_type(e["subject"])
        if bang or "BREAKING CHANGE:" in e["body"]:
            major = True
        elif ctype == "feat":
            minor = True
        elif ctype in ("fix", "perf", "refactor"):
            patch = True
    if major:
        return "major"
    if minor:
        return "minor"
    if patch:
        return "patch"
    return None


def _bump_version(bare, bump):
    major, minor, patch = (int(x) for x in bare.split("."))
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    return None


def _roll_changelog(existing_text, next_version, entries, release_date):
    """Transcription of Phase 1 step 4's rolling rule: a new bracket-heading
    section grouped Added/Fixed/Performance from each commit's `CHANGELOG:`
    footer, with prior sections left intact. Test-authored for the same
    reason `_classify_bump` is — no CLI exists for this step either."""
    groups = {}
    for e in entries:
        ctype, _ = _commit_type(e["subject"])
        group = _GROUP_BY_TYPE.get(ctype)
        if group is None:
            continue
        footer = _footer_text(e["body"])
        if footer is None:
            continue
        groups.setdefault(group, []).append(footer)
    lines = [f"## [{next_version}] - {release_date}", ""]
    for group in ("Added", "Fixed", "Performance"):
        if group in groups:
            lines.append(f"### {group}")
            for item in groups[group]:
                lines.append(f"- {item}")
            lines.append("")
    section_text = "\n".join(lines).rstrip("\n") + "\n"
    if existing_text.startswith("# Changelog"):
        head, _, rest = existing_text.partition("\n")
        full_text = head + "\n\n" + section_text + "\n" + rest.lstrip("\n")
    else:
        full_text = section_text + "\n" + existing_text
    return section_text, full_text


def _git_strip_cleanup(text):
    """Reproduce `git tag`/`git commit`'s DEFAULT `--cleanup=strip` transform
    on a `-F`-supplied message: drop every line starting with `#` (git's
    default comment character), squeeze runs of blank lines down to one, and
    drop leading/trailing blank lines. Implemented independently of git
    itself (never by shelling out and comparing git to itself) so this
    module's expectation of what a REAL `git tag -a -F` call produces is a
    checkable, mutation-sensitive claim rather than "whatever git happened
    to output that day"."""
    lines = [ln for ln in text.split("\n") if not ln.startswith("#")]
    squeezed = []
    blank_run = False
    for ln in lines:
        if ln.strip() == "":
            if blank_run:
                continue
            blank_run = True
        else:
            blank_run = False
        squeezed.append(ln)
    while squeezed and squeezed[0].strip() == "":
        squeezed.pop(0)
    while squeezed and squeezed[-1].strip() == "":
        squeezed.pop()
    return "\n".join(squeezed) + "\n"


def _load_mechanism(path, private_name):
    """Load one `_releaselib.py` copy under a private module name — mirrors
    `test_release_trace.py`'s `_load_core_lane`. Loaded from the MATERIALIZED
    plugin root's `hooks/_releaselib.py` (the vendored, shipped copy) rather
    than `core/pysrc/_releaselib.py` directly, in keeping with this whole
    fixture's point: prove against the installed artifact."""
    spec = importlib.util.spec_from_file_location(private_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[private_name] = module
    spec.loader.exec_module(module)
    return module


class _LaneFixture:
    """A fresh, disposable single-package consumer repo carrying a declared
    `.codearbiter/release-targets.md`, PRIVATE to one mutating test class.
    Never the shared module-level `_FIXTURE.consumer_root`: `ConsumerFixtureTest`
    asserts an EXACT tracked-file set and an exact one-tag list against that
    shared repo, and this class's own sequence rolls a CHANGELOG and creates
    a real annotated tag, either of which would break those assertions (and,
    with unittest's alphabetical class ordering inside a module, silently
    depend on run order to avoid it)."""

    def __init__(self, label):
        self.scratch = tempfile.mkdtemp(prefix=f"ca-lane-driver-{label}-")
        try:
            self.consumer_root = os.path.join(self.scratch, "consumer")
            build_consumer_repo(self.consumer_root)
            targets_path = os.path.join(
                self.consumer_root, ".codearbiter", "release-targets.md")
            _write_text(targets_path, RELEASE_TARGETS_BLOCK)
            _git(["add", "-A"], self.consumer_root)
            _git(["commit", "-q", "-m", "chore: declare release-targets.md"], self.consumer_root)
        except Exception:
            # Mirrors `_Fixture.__init__`'s own pattern: `self.scratch` is
            # allocated before anything that can fail, so a failure here
            # (build_consumer_repo, either git call) must still remove it
            # rather than leak — a caller catching a raised exception out of
            # `__init__` never gets a `self` to call `cleanup()` on.
            self.cleanup()
            raise

    def cleanup(self):
        _force_rmtree(self.scratch)


def _execute_lane_sequence(skill_text, core_lane, consumer_root,
                            target="app", payload="."):
    """Extract, classify, and execute the lane driver's six anchored
    invocations against `consumer_root`, returning a dict of every
    intermediate and derived value both T-74 and T-75 assert against.
    Shared by both test classes so the extraction/substitution/execution
    PLUMBING is written once; each class still asserts directly against
    literals or independent oracles, never against each other's computed
    results, so sharing this function does not make either class's
    assertions mutation-dead.

    Post-T-41b/T-41f, all six anchored invocations are RUN, including the
    two `VAR=$(...)` command-substitution forms (`target_resolution_tag_
    prefix`, `window_last_tag`) that this driver previously could only
    account for — `_run_command_substitution` stages each (the second is an
    internal `|` pipeline) as separate subprocess calls chained by stdin,
    exactly the sequence a shell would run, never a literal shell itself."""
    result = {"invocations": {}, "classification": {}, "processes": {}}

    for label, anchor, expected in _LANE_INVOCATION_ANCHORS:
        invocation = _capture_invocation_after_anchor(skill_text, anchor)
        classification = _classify_invocation(invocation)
        result["invocations"][label] = invocation
        result["classification"][label] = classification

    # The vendored plugin root the loaded `core_lane` module was read from
    # (`_load_mechanism` sets `__file__` to `<plugin_root>/hooks/
    # _releaselib.py`) — substituted for `${CLAUDE_PLUGIN_ROOT}` in every
    # invocation this driver runs, mirroring how a real host resolves that
    # placeholder at prompt-render time.
    plugin_root = os.path.dirname(os.path.dirname(core_lane.__file__))
    root_mapping = {"${CLAUDE_PLUGIN_ROOT}": plugin_root}

    _, tag_prefix, proc = _run_command_substitution(
        result["invocations"]["target_resolution_tag_prefix"], consumer_root,
        {**root_mapping, "$TARGET": target})
    result["processes"]["target_resolution_tag_prefix"] = proc
    result["tag_prefix"] = tag_prefix

    tags = [t.strip() for t in
            _git(["tag", "-l"], consumer_root).stdout.splitlines() if t.strip()]
    result["tags"] = tags

    _, last_tag, proc = _run_command_substitution(
        result["invocations"]["window_last_tag"], consumer_root,
        {**root_mapping, "$TAG_PREFIX": tag_prefix})
    result["processes"]["window_last_tag"] = proc
    result["last_tag_lib"] = last_tag
    result["last_tag_oracle"] = _independent_last_tag(tags, tag_prefix)

    for label in ("window_scope_bare", "window_scope_full_log"):
        argv = _substitute_argv(
            shlex.split(result["invocations"][label]),
            {"LAST_TAG": last_tag, "$PAYLOAD": payload})
        result["processes"][label] = _run_argv(argv, consumer_root)

    result["window_entries"] = _parse_window_log(
        result["processes"]["window_scope_full_log"].stdout)
    result["bump"] = _classify_bump(result["window_entries"])
    bare_last_tag = core_lane._bare_version(last_tag)
    result["next_version"] = _bump_version(bare_last_tag, result["bump"])

    with open(os.path.join(consumer_root, "CHANGELOG.md"), encoding="utf-8") as fh:
        existing_changelog = fh.read()
    release_date = datetime.date.today().isoformat()
    result["release_date"] = release_date
    section_text, full_text = _roll_changelog(
        existing_changelog, result["next_version"], result["window_entries"], release_date)
    result["rolled_section"] = section_text
    result["rolled_full_text"] = full_text
    result["message"] = section_text.rstrip("\n") + f"\nReleased-at: {release_date}\n"
    result["tag_name"] = tag_prefix + result["next_version"]

    fd, message_path = tempfile.mkstemp(prefix="lane-driver-msg-", suffix=".txt")
    os.close(fd)
    try:
        with open(message_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(result["message"])
        argv = _substitute_argv(
            shlex.split(result["invocations"]["tag_sha_peel"]),
            {"${TAG_PREFIX}MAJOR.MINOR.PATCH": result["tag_name"],
             "<message-file>": message_path})
        result["processes"]["tag_sha_peel"] = _run_argv(argv, consumer_root)
    finally:
        os.remove(message_path)

    # publish_state_classify: a bare, 6-positional-argument CLI call — no
    # pipe, no command substitution. Substituted with the state that holds
    # at THIS point in the sequence (the tag composed above exists only
    # in-memory as a message file; no ref has been created), matching
    # exactly what Phase 2 step 1 checks BEFORE tagging: tag_exists=false,
    # so `classify_publish_state` short-circuits to "publish_fresh"
    # regardless of the other five values — the well-defined, meaningful
    # case this fixture can exercise without first creating a real tag.
    head_sha = _git(["rev-parse", "HEAD"], consumer_root).stdout.strip()
    argv = _substitute_argv(
        shlex.split(result["invocations"]["publish_state_classify"]),
        {**root_mapping,
         "<tag_exists>": "false", "<tag_sha>": "", "<head_sha>": head_sha,
         "<tag_version>": result["next_version"],
         "<manifest_version>": result["next_version"],
         "<release_nondraft>": "false"})
    proc = _run_argv(argv, consumer_root)
    result["processes"]["publish_state_classify"] = proc
    result["publish_state"] = (proc.stdout or "").strip()

    return result


class LaneDriverTest(unittest.TestCase):
    """T-74 (AC-6.6 'Lane driver'): the mechanical sequence runs AS THE
    PROSE SPELLS IT — invocation strings extracted from the installed
    `SKILL.md`, never a direct import — through target resolution, window
    derivation, and tag-message composition.

    Post-T-41b/T-41f (issue #563): all six anchored invocations now RUN —
    before that rewrite landed, three of them named a this-repo-only shim
    with no `__main__` and could only be ACCOUNTED for (T-79 later retired
    the `known-unresolved-refs.txt` ratchet this used to be cross-checked
    against). `test_no_invocations_remain_accounted` documents that
    transition directly rather than silently deleting the accounting
    machinery this class used to depend on."""

    @classmethod
    def setUpClass(cls):
        # unittest does NOT call tearDownClass if setUpClass itself raises,
        # so a failure anywhere in this body (a mutant breaking
        # `_execute_lane_sequence`, an anchor going missing) would otherwise
        # leak `cls.lane`'s scratch directory — caught and cleaned up here
        # rather than relying on tearDownClass to run.
        cls.lane = _LaneFixture("t74")
        try:
            skill_path = os.path.join(_FIXTURE.plugin_root, "skills", "release", "SKILL.md")
            with open(skill_path, encoding="utf-8") as fh:
                cls.skill_text = fh.read()
            cls.core_lane = _load_mechanism(
                os.path.join(_FIXTURE.plugin_root, "hooks", "_releaselib.py"),
                "_lane_driver_core_t74")
            cls.result = _execute_lane_sequence(
                cls.skill_text, cls.core_lane, cls.lane.consumer_root)
        except Exception:
            cls.lane.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.lane.cleanup()

    def test_lane_driver_classification_map(self):
        # A literal, hand-declared expectation per label — direct against
        # the anchors table, not derived from anything the driver itself
        # computed, so a mutant flipping run<->accounted in `_classify_invocation`
        # is caught here directly rather than by an equality between two
        # things sharing that same function.
        expected = {label: exp for label, _, exp in _LANE_INVOCATION_ANCHORS}
        self.assertEqual(self.result["classification"], expected)

    def test_no_invocations_remain_accounted(self):
        # T-41b/T-41f landed: every anchored invocation now resolves under
        # the vendored plugin's own CLI and runs for real. This replaces
        # `test_accounted_invocations_are_on_the_committed_ratchet` (which
        # asserted the PRE-rewrite accounted set was non-empty and named on
        # the ratchet) — that assertion would now fail vacuously, since
        # there is nothing left to account for; a green run here is the
        # positive statement that the migration completed, not a weakened
        # substitute for it.
        accounted_labels = [label for label, cls_ in self.result["classification"].items()
                             if cls_ == "accounted"]
        self.assertEqual(
            accounted_labels, [],
            "an invocation is classified accounted again — either a new "
            "this-repo-only reference crept back into the skill, or "
            "_classify_invocation regressed")

    def test_publish_state_classify_ran_and_resolved_publish_fresh(self):
        # The one anchored invocation `_execute_lane_sequence` substitutes
        # with synthetic (not skill-derived) placeholder values, so its
        # correctness is asserted directly here rather than folded into
        # `test_run_invocations_all_exited_zero`'s exit-code-only check
        # (AC-6.6: "never on exit codes alone").
        proc = self.result["processes"]["publish_state_classify"]
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(self.result["publish_state"], "publish_fresh")

    def test_target_resolution_and_last_tag_ran_via_the_vendored_cli(self):
        # Cross-validates the two command-substitution invocations this
        # class now RUNS (previously accounted) against values this driver
        # already trusts from elsewhere: the resolved prefix must match
        # what the consumer's own declared row names, and the resolved
        # LAST_TAG must agree with the independent oracle.
        self.assertEqual(self.result["tag_prefix"], "v")
        self.assertEqual(self.result["last_tag_lib"], self.result["last_tag_oracle"])

    def test_run_invocations_all_exited_zero(self):
        run_labels = [label for label, cls_ in self.result["classification"].items()
                      if cls_ == "run"]
        self.assertTrue(run_labels, "no invocation classified run — the "
                         "actually-runs arm of this test is untested")
        for label in run_labels:
            with self.subTest(label=label):
                proc = self.result["processes"][label]
                self.assertEqual(
                    proc.returncode, 0,
                    f"extracted invocation {label!r} "
                    f"({self.result['invocations'][label]!r}) failed: {proc.stderr}")

    def test_window_derivation_finds_every_commit_git_itself_reports(self):
        # Cross-validated against a SEPARATE git subcommand (rev-list
        # --count), not the same `log` output compared to itself. THREE, not
        # two: `_LaneFixture` declares release-targets.md as its own commit
        # AFTER the v1.2.3 tag (a `chore:` commit contributing no bump and no
        # CHANGELOG: footer), on top of `build_consumer_repo`'s feat and fix.
        last_tag = self.result["last_tag_lib"]
        independent_count = int(_git(
            ["rev-list", "--count", f"{last_tag}..HEAD"], self.lane.consumer_root).stdout.strip())
        self.assertEqual(len(self.result["window_entries"]), independent_count)
        self.assertEqual(len(self.result["window_entries"]), 3)

    def test_window_scope_bare_reports_the_same_commit_count(self):
        # AC-6.6: "never on exit codes alone." `window_scope_bare` (`git log
        # LAST_TAG..HEAD -- $PAYLOAD`, default pretty format) is a RUN
        # invocation whose only other test coverage is its exit code — a
        # mutant substituting a bogus-but-still-zero-exit revision range
        # into it would survive undetected without this. Its stdout is
        # git's own default format, one `commit <sha>` line per entry.
        last_tag = self.result["last_tag_lib"]
        independent_count = int(_git(
            ["rev-list", "--count", f"{last_tag}..HEAD"], self.lane.consumer_root).stdout.strip())
        stdout = self.result["processes"]["window_scope_bare"].stdout
        commit_lines = [ln for ln in stdout.splitlines() if ln.startswith("commit ")]
        self.assertEqual(len(commit_lines), independent_count)
        self.assertEqual(len(commit_lines), 3)

    def test_full_release_skill_payloads_extract_byte_identical_invocations(self):
        # MEDIUM-3's exact defect class (adversarial review 2026-07-31,
        # documented in this same file's ReferenceResolutionTest):
        # the release skill ships as THREE full copies (`ca`,
        # `ca-codex`/`ca-pi` routines), and a driver reading only `ca`'s copy
        # is blind to a drift introduced into a sibling -- including one
        # `tools/build-surface.py` itself renders differently.
        #
        # Post-T-41b (issue #563): three of the six anchored invocations NOW
        # carry the `{{PLUGIN_ROOT}}` placeholder, rendered per-host
        # (`${CLAUDE_PLUGIN_ROOT}` for claude/codex, `<plugin-root>` for pi —
        # `core/hosts.json`), so byte-identity across all three payloads no
        # longer holds literally. Each payload's own plugin-root token is
        # normalized to a fixed canonical string before comparing, so this
        # test still catches a genuine wording/structure drift between
        # copies while tolerating the ONE expected, per-host spelling
        # difference `tools/build-surface.py` itself introduces.
        root_by_host = {
            "claude": _FIXTURE.plugin_root,
            "codex": _FIXTURE.codex_plugin_root,
            "pi": _FIXTURE.pi_plugin_root,
        }
        host_tokens = _load_host_tokens()
        full_payloads = [
            (label, host, relpath) for label, host, relpath, _ in _RELEASE_SKILL_PAYLOADS
            if label not in _STUB_PAYLOAD_LABELS
        ]
        self.assertEqual(len(full_payloads), 3)
        per_payload_invocations = {}
        for label, host, relpath in full_payloads:
            skill_path = os.path.join(root_by_host[host], *relpath.split("/"))
            with open(skill_path, encoding="utf-8") as fh:
                text = fh.read()
            plugin_token, _project_token = host_tokens[host]
            per_payload_invocations[label] = {
                inv_label: _capture_invocation_after_anchor(text, anchor)
                    .replace(plugin_token, "\0PLUGIN_ROOT\0")
                for inv_label, anchor, _ in _LANE_INVOCATION_ANCHORS
            }
        baseline_label, baseline = next(iter(per_payload_invocations.items()))
        for label, invocations in per_payload_invocations.items():
            with self.subTest(payload=label):
                self.assertEqual(
                    invocations, baseline,
                    f"payload {label!r} extracted different invocation strings "
                    f"than {baseline_label!r} (after normalizing each payload's "
                    "own plugin-root token) — the release skill's copies have "
                    "drifted apart")

    def test_tag_sha_peel_created_a_real_annotated_tag(self):
        proc = self.result["processes"]["tag_sha_peel"]
        self.assertEqual(proc.returncode, 0, proc.stderr)
        obj_type = _git(
            ["cat-file", "-t", self.result["tag_name"]], self.lane.consumer_root).stdout.strip()
        self.assertEqual(obj_type, "tag")


class ConsumerEndToEndTest(unittest.TestCase):
    """T-75 (AC-6.6 'consumer_end_to_end'): assertions on DERIVED OUTPUTS —
    the resolved row, LAST_TAG, the computed bump, and the rolled changelog
    text — never on exit codes alone."""

    @classmethod
    def setUpClass(cls):
        # See LaneDriverTest.setUpClass's comment: unittest skips
        # tearDownClass entirely if setUpClass raises, so cleanup on failure
        # is handled explicitly here rather than left to tearDownClass.
        cls.lane = _LaneFixture("t75")
        try:
            skill_path = os.path.join(_FIXTURE.plugin_root, "skills", "release", "SKILL.md")
            with open(skill_path, encoding="utf-8") as fh:
                cls.skill_text = fh.read()
            cls.core_lane = _load_mechanism(
                os.path.join(_FIXTURE.plugin_root, "hooks", "_releaselib.py"),
                "_lane_driver_core_t75")
            cls.result = _execute_lane_sequence(
                cls.skill_text, cls.core_lane, cls.lane.consumer_root)
        except Exception:
            cls.lane.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.lane.cleanup()

    def test_resolved_row(self):
        rows = self.core_lane.load_targets(
            os.path.join(self.lane.consumer_root, ".codearbiter", "release-targets.md"))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["target"], "app")
        self.assertEqual(row["prefix"], "v")
        self.assertEqual(row["manifest"], ["package.json"])
        self.assertEqual(row["changelog"], "CHANGELOG.md")
        self.assertEqual(row["payload"], ".")

    def test_last_tag(self):
        self.assertEqual(self.result["tags"], ["v1.2.3"])
        self.assertEqual(self.result["last_tag_lib"], "v1.2.3")
        self.assertEqual(self.result["last_tag_oracle"], "v1.2.3")
        self.assertEqual(self.result["last_tag_lib"], self.result["last_tag_oracle"])

    def test_computed_bump(self):
        # Direct literal, not a comparison against the classifier's own
        # helper output: a feat + a fix in the window must classify minor
        # (feat outranks fix), and the derived next version must be the
        # strict SemVer advance the manifest/tag gate itself requires.
        self.assertEqual(self.result["bump"], "minor")
        self.assertEqual(self.result["next_version"], "1.3.0")
        self.assertTrue(
            self.core_lane.semver_greater(self.result["next_version"], "1.2.3"))

    def test_bump_classification_negative_case_is_discriminating(self):
        # A docs/chore-only window must NOT bump — proven directly against
        # `_classify_bump`, independent of what the live fixture's own
        # commits happen to be, so a mutant that always returns "minor"
        # cannot survive.
        self.assertIsNone(_classify_bump([
            {"sha": "a", "subject": "docs: fix typo", "body": ""},
            {"sha": "b", "subject": "chore: bump lockfile", "body": ""},
        ]))

    def test_rolled_changelog_text(self):
        text = self.result["rolled_full_text"]
        self.assertIn(f"## [1.3.0] - {self.result['release_date']}", text)
        self.assertIn("### Added", text)
        self.assertIn("- Added a widget export helper.", text)
        self.assertIn("### Fixed", text)
        self.assertIn("- Fixed an off-by-one when counting widgets.", text)
        # Prior section stays intact.
        self.assertIn("## [1.2.3] - 2026-01-01", text)
        self.assertIn("- Initial release.", text)
        # The new section sits ABOVE the prior one.
        self.assertLess(text.index("## [1.3.0]"), text.index("## [1.2.3]"))

    def test_tag_sha_peel_passes_the_same_guards_phase3_applies(self):
        message = self.result["message"]
        tag = self.result["tag_name"]
        self.assertTrue(self.core_lane.notes_heading_matches(message, tag))
        self.assertTrue(self.core_lane.release_dates_consistent(
            self.result["rolled_section"], message))

    def test_the_real_annotated_tag_carries_the_composed_message(self):
        # [NEEDS-TRIAGE] genuine finding, surfaced ONLY because this class
        # actually runs `git tag -a ... -F <message-file>` for real rather
        # than asserting on exit codes or a direct import: git's DEFAULT
        # `--cleanup=strip` (the same behavior `git commit` applies to a
        # hand-typed message) treats every line starting with `#` as a
        # comment and drops it from a `-F`-supplied message. The Phase-1
        # changelog section this skill composes into the tag message is
        # Keep-a-Changelog Markdown, whose OWN heading lines are `## [X.Y.Z]
        # ...` / `### Added` -- exactly `#`-prefixed. The skill's literal
        # instruction (`git tag -a ... -F <message-file>`, no
        # `--cleanup=verbatim`) therefore silently strips the composed
        # message's own version/date heading and every section heading from
        # the CREATED TAG OBJECT, even though the pre-tag composition and
        # its `notes_heading_matches`/`release_dates_consistent` checks (run
        # against the Phase-1 section TEXT and the GitHub Release notes
        # FILE, never against the tag object actually created) never
        # observe it. `RealHistoryTagStrippingEvidenceTest` below confirms
        # this has ALREADY happened to this repo's own real, published
        # `v2.8.13` tag. This is not fixed here -- fixing the skill's `git
        # tag` invocation is out of this test's scope and belongs to
        # whichever task takes up T-41x or a new issue; this assertion
        # documents the ACTUAL, currently-shipping behavior rather than
        # silently "fixing" the extracted invocation to make the test pass.
        tag = self.result["tag_name"]
        obj_type = _git(["cat-file", "-t", tag], self.lane.consumer_root).stdout.strip()
        self.assertEqual(obj_type, "tag")
        raw = _git(["cat-file", "-p", tag], self.lane.consumer_root).stdout
        # The tag object's own header lines (object/type/tag/tagger) precede
        # a blank line, after which the message body begins verbatim.
        _, _, body = raw.partition("\n\n")
        stripped_expectation = _git_strip_cleanup(self.result["message"])
        self.assertEqual(body.rstrip("\n"), stripped_expectation.rstrip("\n"))
        # The composed message's OWN heading survives in-memory (the
        # pre-tag guards run against it) but is genuinely gone from what
        # got tagged -- the concrete gap between "checked" and "shipped".
        self.assertIn(f"## [{self.result['next_version']}]", self.result["message"])
        self.assertNotIn(
            "## [", body,
            "if this now FAILS because the tag body DOES contain its "
            "heading, that means the skill's `git tag -a` invocation picked "
            "up `--cleanup=verbatim` (or equivalent) and the stripping "
            "defect this test documents was FIXED -- re-triage the "
            "[NEEDS-TRIAGE] finding above and relax this assertion "
            "deliberately, rather than treating a red run here as a "
            "regression to chase")


class LaneDriverUnitTest(unittest.TestCase):
    """Direct, synthetic-input coverage of the three arms `_execute_lane_
    sequence` depends on, independent of whatever the LIVE skill currently
    contains — mirrors the role `ResolverUnitTest` plays for T-73b. Without
    this, a mutant in `_classify_invocation` or `_run_argv` that happens to
    behave correctly on the skill's OWN one example of each arm would
    survive undetected."""

    def test_well_formed_invocation_is_extracted_and_runs(self):
        text = "before text. Run this: `git rev-parse HEAD` after text."
        invocation = _capture_invocation_after_anchor(text, "Run this:")
        self.assertEqual(invocation, "git rev-parse HEAD")
        self.assertEqual(_classify_invocation(invocation), "run")
        with tempfile.TemporaryDirectory() as scratch:
            _git(["init", "-q"], scratch)
            _write_text(os.path.join(scratch, "f.txt"), "x\n")
            _git(["add", "-A"], scratch)
            _git(["commit", "-q", "-m", "c"], scratch)
            proc = _run_argv(shlex.split(invocation), scratch)
            self.assertEqual(proc.returncode, 0)

    def test_extraction_fails_loud_when_anchor_missing(self):
        with self.assertRaises(RuntimeError):
            _capture_invocation_after_anchor("no anchor here at all", "MISSING ANCHOR")

    def test_extraction_fails_loud_when_no_invocation_shaped_span_follows(self):
        text = "Anchor here: `_bare.module.reference` and nothing runnable near it."
        with self.assertRaises(RuntimeError):
            _capture_invocation_after_anchor(text, "Anchor here:")

    def test_invocation_naming_this_repo_shim_is_accounted(self):
        invocation = "python3 .github/scripts/_releaselib.py tag-prefix app"
        self.assertEqual(_classify_invocation(invocation), "accounted")

    def test_invocation_with_nonexistent_git_subcommand_fails_rather_than_silently_passing(self):
        # Proves the driver actually surfaces a failing exit code rather
        # than treating "it ran" as "it succeeded" — the malformed-CLI arm
        # AC-6.6 exists to catch, demonstrated with a synthetic invocation
        # rather than depending on the live skill ever naming a broken one.
        with tempfile.TemporaryDirectory() as scratch:
            _git(["init", "-q"], scratch)
            proc = _run_argv(["git", "this-subcommand-does-not-exist"], scratch)
            self.assertNotEqual(proc.returncode, 0)

    def test_substitute_argv_never_reparses_a_backslash_bearing_path_through_shlex(self):
        # The concrete Windows hazard the module docstring names: a
        # `<message-file>` token substituted with a backslash-bearing path
        # must survive as ONE argv element, never re-split.
        argv = shlex.split("git tag -a ${TAG_PREFIX}MAJOR.MINOR.PATCH -F <message-file>")
        windows_path = r"C:\Users\example\AppData\Local\Temp\msg.txt"
        substituted = _substitute_argv(
            argv, {"${TAG_PREFIX}MAJOR.MINOR.PATCH": "v1.3.0", "<message-file>": windows_path})
        self.assertEqual(substituted, ["git", "tag", "-a", "v1.3.0", "-F", windows_path])


class RealHistoryTagStrippingEvidenceTest(unittest.TestCase):
    """[NEEDS-TRIAGE] Corroborates `ConsumerEndToEndTest`'s discovery with
    REAL evidence rather than only the scratch fixture's synthetic proof:
    `git tag -a -F`'s default comment-stripping cleanup has ALREADY silently
    corrupted this repo's own real, previously published release tag
    message. `v2.8.13` is a real, PUBLISHED tag; the project's own release
    skill ("Recovering from a bad release": no break-glass, a published tag
    is never moved or deleted) makes it a permanent historical fact rather
    than transient repo state, so pinning it here does not go stale the way
    pinning "the current HEAD" or "the latest tag" would. Entirely
    read-only against REPO_ROOT (`git cat-file -p`, never `git tag`) --
    creates no ref, mutates nothing.

    **Not mutation-killable by construction** (the same phrasing the sprint
    plan uses for T-12's circularity proof): this asserts a HISTORICAL FACT
    about a commit already in this repository's object database, not the
    behavior of any function this module defines. There is no production
    code path here for a mutant to corrupt; its value is corroborating
    `ConsumerEndToEndTest`'s synthetic finding against real, already-shipped
    evidence, not discriminating a mutation."""

    def test_the_live_v2_8_13_tag_message_is_missing_its_own_changelog_heading(self):
        result = subprocess.run(
            ["git", "cat-file", "-p", "v2.8.13"],
            cwd=REPO_ROOT, capture_output=True, encoding="utf-8", timeout=GIT_TIMEOUT)
        self.assertEqual(
            result.returncode, 0,
            f"v2.8.13 is expected to be a real, permanently published tag in "
            f"this repository's history: {result.stderr}")
        _, _, body = result.stdout.partition("\n\n")
        self.assertNotIn(
            "## [2.8.13]", body,
            "if this now PASSES, this repo's tagging process (or git's own "
            "default cleanup behavior) changed -- re-triage the "
            "[NEEDS-TRIAGE] finding in ConsumerEndToEndTest rather than "
            "deleting this test")


# --------------------------------------------------------------------------- #
# T-76 — consumer back-fill, the real two-arm proof (issue #563, T-49/T-50).
# Replaces the 2026-07-31 canary (`BackfillNotYetImplementedTest`), which
# asserted the ABSENCE of back-fill prose and was written to fail the moment
# it closed, with the instruction to replace the whole class rather than
# loosen the assertion. T-49/T-50 landed in this same commit, so this is
# that replacement: both required arms (refuse without confirmation, persist
# on confirmation) plus the "second run reads, does not re-detect" property,
# run against the scratch consumer fixture (never this repo's dev tree),
# with the `backfill-detect` invocation extracted from the INSTALLED skill
# text and subprocess-executed — mirroring LaneDriverTest's own "prose, not
# import" discipline (AC-6.6's "Lane driver" layer).
# --------------------------------------------------------------------------- #

_BACKFILL_DETECT_ANCHOR = "From the project root, run"


class _BackfillFixture:
    """A fresh, disposable single-package consumer repo carrying NO declared
    `release-targets.md` — the exact precondition the back-fill lane needs.
    Private to this test class for the same reason `_LaneFixture` is private
    to `LaneDriverTest`/`ConsumerEndToEndTest`: a mutating test must never
    touch the shared module-level `_FIXTURE.consumer_root`, which
    `ConsumerFixtureTest` asserts an exact tracked-file set against."""

    def __init__(self, label):
        self.scratch = tempfile.mkdtemp(prefix=f"ca-backfill-{label}-")
        try:
            self.consumer_root = os.path.join(self.scratch, "consumer")
            build_consumer_repo(self.consumer_root)
        except Exception:
            # Mirrors `_Fixture.__init__`/`_LaneFixture.__init__`'s own
            # pattern: allocate `self.scratch` before anything that can
            # fail, so a failure here still removes it rather than leaks.
            self.cleanup()
            raise

    def cleanup(self):
        _force_rmtree(self.scratch)


class BackfillTwoArmProofTest(unittest.TestCase):
    """T-76 (AC-6.6 'backfill_detects'): with no declared file, the detected
    shape is presented and does not proceed unconfirmed. `build_consumer_repo`
    seeds exactly one `package.json` and one `CHANGELOG.md` at its root — the
    single unambiguous candidate of each kind the back-fill lane's own
    never-guess posture requires before it can propose anything at all."""

    @classmethod
    def setUpClass(cls):
        # See LaneDriverTest.setUpClass's comment: unittest skips
        # tearDownClass entirely if setUpClass raises, so cleanup on failure
        # is handled explicitly here rather than left to tearDownClass.
        cls.lane = _BackfillFixture("t76")
        try:
            skill_path = os.path.join(_FIXTURE.plugin_root, "skills", "release", "SKILL.md")
            with open(skill_path, encoding="utf-8") as fh:
                cls.skill_text = fh.read()
            cls.core_lane = _load_mechanism(
                os.path.join(_FIXTURE.plugin_root, "hooks", "_releaselib.py"),
                "_backfill_two_arm_core")
            cls.targets_path = os.path.join(
                cls.lane.consumer_root, ".codearbiter", "release-targets.md")
            cls.invocation = _capture_invocation_after_anchor(
                cls.skill_text, _BACKFILL_DETECT_ANCHOR)
        except Exception:
            cls.lane.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.lane.cleanup()

    def _run_detect(self):
        plugin_root = os.path.dirname(os.path.dirname(self.core_lane.__file__))
        argv = _substitute_argv(
            shlex.split(self.invocation), {"${CLAUDE_PLUGIN_ROOT}": plugin_root})
        return _run_argv(argv, self.lane.consumer_root)

    def test_no_declared_file_and_the_parser_still_refuses_to_default(self):
        # The property `AbsentBlockError` is CORRECT and MUST stay (the task
        # brief's own instruction): the back-fill lane HANDLES this error,
        # it is never a silent default inside the parser itself.
        #
        # This owns its own pristine consumer rather than reading the shared
        # class fixture. It previously asserted absence against `self.
        # targets_path`, which `test_arm_2_persist_...` legitimately CREATES —
        # and unittest orders methods alphabetically, so `arm_2` runs first and
        # the absence assertion failed. It only ever passed while the class's
        # setUpClass was erroring and none of these methods ran at all. A test
        # asserting "no declared file exists" must not depend on no other test
        # having made one.
        pristine = _BackfillFixture("t76-pristine")
        try:
            path = os.path.join(
                pristine.consumer_root, ".codearbiter", "release-targets.md")
            self.assertFalse(
                os.path.isfile(path),
                "a freshly built consumer must carry no declared file")
            with self.assertRaises(self.core_lane.AbsentBlockError):
                self.core_lane.load_targets(path)
        finally:
            pristine.cleanup()

    def test_detection_extracted_from_the_installed_skill_finds_the_candidate(self):
        proc = self._run_detect()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("[app]", proc.stdout)
        self.assertIn("prefix: v", proc.stdout)
        self.assertIn("manifest: package.json", proc.stdout)
        self.assertIn("changelog: CHANGELOG.md", proc.stdout)
        self.assertIn("payload: .", proc.stdout)

    def test_lane_anchors_are_unique_in_every_rendering(self):
        # The header comment above _LANE_INVOCATION_ANCHORS has always
        # CLAIMED each anchor is "verified unique in the installed skill
        # text". Nothing enforced it until now: the claim was prose, and a
        # prose claim about a test is exactly the kind of thing that goes
        # stale silently.
        #
        # Two distinct failure modes, both real:
        #   - MISSING (count 0) — a prose edit moves or deletes the
        #     landmark. This fires loudly at setUpClass, so it is already
        #     hard to miss; the run-3 reorder of Phase 2 step 1 removed
        #     "Tag with" and did exactly this.
        #   - AMBIGUOUS (count > 1) — a prose edit introduces a SECOND
        #     occurrence earlier in the file. `str.find()` takes the first
        #     match, so the driver silently captures a different
        #     invocation and every downstream assertion still passes,
        #     against the wrong command. That is the one worth a test.
        #
        # Checked across all three full-prose renderings, not just `ca`: a
        # check reading one copy is blind to drift in a sibling.
        root_by_host = {
            "claude": _FIXTURE.plugin_root,
            "codex": _FIXTURE.codex_plugin_root,
            "pi": _FIXTURE.pi_plugin_root,
        }
        full_payloads = [
            (label, host, relpath) for label, host, relpath, _ in _RELEASE_SKILL_PAYLOADS
            if label not in _STUB_PAYLOAD_LABELS
        ]
        self.assertEqual(len(full_payloads), 3)
        for label, host, relpath in full_payloads:
            skill_path = os.path.join(root_by_host[host], *relpath.split("/"))
            with open(skill_path, encoding="utf-8") as fh:
                text = fh.read()
            for name, anchor, _classification in _LANE_INVOCATION_ANCHORS:
                self.assertEqual(
                    text.count(anchor), 1,
                    f"payload {label!r}: lane anchor {name!r} = {anchor!r} "
                    f"occurs {text.count(anchor)} time(s); it must occur "
                    "exactly once. Zero means a prose edit moved the "
                    "landmark (update the anchor in the SAME commit). More "
                    "than one means find()'s first-match rule now silently "
                    "captures the wrong invocation while every assertion "
                    "downstream keeps passing.")

    def test_full_release_skill_payloads_extract_the_same_backfill_invocation(self):
        # MEDIUM-3's exact defect class (mirrors LaneDriverTest's own
        # cross-payload check): a driver reading only the `ca` copy is
        # blind to a drift introduced into a sibling. Scope to the THREE
        # full payloads (the two `ca-release` stubs never carry this
        # section at all), normalize each host's own plugin-root token
        # spelling, and assert the extracted invocation is identical
        # across all three -- and that the anchor is unambiguous (occurs
        # exactly once) in each.
        root_by_host = {
            "claude": _FIXTURE.plugin_root,
            "codex": _FIXTURE.codex_plugin_root,
            "pi": _FIXTURE.pi_plugin_root,
        }
        host_tokens = _load_host_tokens()
        full_payloads = [
            (label, host, relpath) for label, host, relpath, _ in _RELEASE_SKILL_PAYLOADS
            if label not in _STUB_PAYLOAD_LABELS
        ]
        self.assertEqual(len(full_payloads), 3)
        per_payload_invocation = {}
        for label, host, relpath in full_payloads:
            skill_path = os.path.join(root_by_host[host], *relpath.split("/"))
            with open(skill_path, encoding="utf-8") as fh:
                text = fh.read()
            self.assertEqual(
                text.count(_BACKFILL_DETECT_ANCHOR), 1,
                f"payload {label!r}: anchor {_BACKFILL_DETECT_ANCHOR!r} must "
                "occur exactly once (an ambiguous anchor would silently "
                "extract the WRONG invocation via find()'s first-match rule)")
            plugin_token, _project_token = host_tokens[host]
            invocation = _capture_invocation_after_anchor(text, _BACKFILL_DETECT_ANCHOR)
            per_payload_invocation[label] = invocation.replace(
                plugin_token, "\0PLUGIN_ROOT\0")
        baseline_label, baseline = next(iter(per_payload_invocation.items()))
        for label, invocation in per_payload_invocation.items():
            with self.subTest(payload=label):
                self.assertEqual(
                    invocation, baseline,
                    f"payload {label!r} extracted a different backfill-detect "
                    f"invocation than {baseline_label!r} (after normalizing "
                    "each payload's own plugin-root token) -- the release "
                    "skill's copies have drifted apart")

    def test_arm_1_refuse_without_confirmation_writes_nothing(self):
        # Detection alone is the mechanical half of "does not proceed
        # without explicit confirmation": running it — even twice, as if a
        # user has not yet answered — must never touch disk on its own.
        self._run_detect()
        self._run_detect()
        self.assertFalse(
            os.path.isfile(self.targets_path),
            "backfill-detect must only PRINT the candidate block; it must "
            "never write release-targets.md on its own")

    def test_arm_2_persist_on_confirmation_and_a_second_run_reads_not_redetects(self):
        proc = self._run_detect()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        confirmed_block = proc.stdout

        # Confirmation: the lane's own persist step (Back-fill step 3) --
        # write the confirmed block verbatim, exactly as the skill prose
        # instructs.
        os.makedirs(os.path.dirname(self.targets_path), exist_ok=True)
        with open(self.targets_path, "w", encoding="utf-8", newline="") as fh:
            fh.write(confirmed_block)

        rows = self.core_lane.load_targets(self.targets_path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["target"], "app")
        self.assertEqual(rows[0]["prefix"], "v")
        self.assertEqual(rows[0]["manifest"], ["package.json"])
        self.assertEqual(rows[0]["changelog"], "CHANGELOG.md")
        self.assertEqual(rows[0]["payload"], ".")

        # T-50: "a second run reads it rather than re-detecting" -- proven
        # by NOT invoking detection again here at all (no `_run_detect`
        # call below) and still getting the identical row back from the
        # normal load path alone.
        second_read = self.core_lane.load_targets(self.targets_path)
        self.assertEqual(second_read, rows)

    def test_ambiguous_candidates_still_refuse_rather_than_guess(self):
        # A DIFFERENT scratch repo, not the shared happy-path lane: a second
        # candidate manifest makes the scan genuinely ambiguous, and the
        # command must refuse (non-zero exit, nothing printed) rather than
        # pick one silently.
        ambiguous = _BackfillFixture("t76-ambiguous")
        try:
            with open(os.path.join(ambiguous.consumer_root, "pyproject.toml"),
                      "w", encoding="utf-8") as fh:
                fh.write("")
            plugin_root = os.path.dirname(os.path.dirname(self.core_lane.__file__))
            argv = _substitute_argv(
                shlex.split(self.invocation), {"${CLAUDE_PLUGIN_ROOT}": plugin_root})
            proc = _run_argv(argv, ambiguous.consumer_root)
            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout, "")
            ambiguous_targets_path = os.path.join(
                ambiguous.consumer_root, ".codearbiter", "release-targets.md")
            self.assertFalse(os.path.isfile(ambiguous_targets_path))
        finally:
            ambiguous.cleanup()


if __name__ == "__main__":
    unittest.main()
