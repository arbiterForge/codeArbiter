#!/usr/bin/env python3
"""codeArbiter — T-73a/T-73b: the scratch consumer fixture and the
reference-resolution ratchet (issue #563, AC-6.6,
.codearbiter/specs/release-portable-fixture.md,
.codearbiter/plans/portable-release-and-protected-state.md).

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
  ReferenceResolutionRatchetTest   T-73b — extracts every executed-or-read
                                    path reference from EVERY INSTALLED copy
                                    of the release skill (the spec's own
                                    "Source of truth" list, plus
                                    `ca-codex/routines/release/SKILL.md`,
                                    which ships an identically-contaminated
                                    copy the spec's enumeration omits — see
                                    the adversarial-review remediation on
                                    2026-07-31) and compares the UNIONED
                                    unresolved set against a committed
                                    ratchet file.
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

import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
KNOWN_UNRESOLVED_PATH = os.path.join(HERE, "known-unresolved-refs.txt")

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
# T-73b — reference-resolution ratchet
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
_EXTRACTION_FLOOR = 45
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


def _extract_refs(skill_text):
    """Every backtick-code-span path reference in `skill_text` matching
    `_PATH_REF_RE` or `_GLOB_DIR_REF_RE`. Backtick spans are this
    codebase's near-universal convention for naming an executed or read
    path in skill/command prose."""
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


def _load_known_unresolved():
    if not os.path.isfile(KNOWN_UNRESOLVED_PATH):
        raise RuntimeError(f"missing ratchet file: {KNOWN_UNRESOLVED_PATH!r}")
    entries = set()
    with open(KNOWN_UNRESOLVED_PATH, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            entries.add(line)
    return entries


class ReferenceResolutionRatchetTest(unittest.TestCase):
    """T-73b (A-6.6, 'reference resolution'). Physically resolves every
    executed-or-read path reference in EVERY installed copy of the release
    skill (`_RELEASE_SKILL_PAYLOADS`) against the matching scratch plugin
    root and the shared scratch consumer repo, and compares the UNIONED
    unresolved set to the committed ratchet file — green and required from
    day one, failing on a change in EITHER direction that is not
    accompanied by the same edit to `known-unresolved-refs.txt`."""

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

    def test_reference_resolution_ratchet(self):
        known = _load_known_unresolved()
        added = sorted(self.unresolved - known)
        removed = sorted(known - self.unresolved)
        self.assertEqual(
            self.unresolved, known,
            "the UNIONED set of unresolved path references across every "
            "installed release-skill payload (materialized from live HEAD) "
            f"no longer matches {KNOWN_UNRESOLVED_PATH!r}.\n"
            f"  newly UNRESOLVED (not yet on the list — likely a NEW "
            f"contaminating reference): {added or '(none)'}\n"
            f"  newly RESOLVED (should be REMOVED from the list in this "
            f"SAME commit): {removed or '(none)'}\n"
            "Remember: the fixture archives `HEAD`, not the working tree — "
            "commit both the SKILL.md edit and the known-unresolved-refs.txt "
            "edit before re-running this test.")


class ResolverUnitTest(unittest.TestCase):
    """Direct, synthetic-input coverage of `_resolves`'s three arms and the
    extractor's glob support. The live release skill carries exactly ONE
    `${CLAUDE_PLUGIN_ROOT}` reference in its `claude` copy and it happens
    to resolve, so a mutant that made that arm always return True would
    survive `ReferenceResolutionRatchetTest` undetected; these exercise
    each arm with both a present and an absent input directly."""

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


if __name__ == "__main__":
    unittest.main()
