#!/usr/bin/env python3
"""codeArbiter — guard-logic regression matrix for pre-bash.py.

The cold-install matrix (test_hooks_cold_install.py) proves the *interpreter
plumbing*: every hook entry runs, blocks survive the fallback, nothing is
silently dormant. This harness proves the *guard logic itself*: every H-01 /
H-02 / H-03 / H-05 / H-11 / H-09b spelling that must BLOCK does block (exit 2,
correct tag), and every legitimate spelling that must ALLOW still exits 0.

Each case pipes Claude-Code-shaped hook JSON into pre-bash.py via the current
interpreter, cwd'd into a throwaway arbiter-enabled git repo. The repo carries
real files/dirs so the path-resolving guards (directory staging, glob args)
exercise their filesystem branch, and a real commit history so the H-09b
diff-binding cases run against genuine staged diffs.

Stdlib only. Exit 0 = all assertions pass; exit 1 = failures.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOOKS = os.path.join(REPO, "plugins", "ca", "hooks")
PRE_BASH = os.path.join(HOOKS, "pre-bash.py")
SECURITY_PASS = os.path.join(HOOKS, "security-pass.py")

# Load pre-bash.py as a module for direct unit tests of its pure parsers
# (the file name has a hyphen, so import via spec). Import is side-effect-free:
# pre-bash.py only reads stdin / acts inside main(), guarded by __main__.
import importlib.util as _ilu  # noqa: E402
_spec = _ilu.spec_from_file_location("pre_bash_mod", PRE_BASH)
pre_bash = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(pre_bash)

failures = []
checks = 0


def sh(args, cwd, **kw):
    # Pin CLAUDE_PROJECT_DIR to the fixture repo: project_root() trusts the
    # harness signal first, and a value leaking in from a live Claude session
    # would silently point every guard at the developer's real repo.
    env = {**os.environ, "CLAUDE_PROJECT_DIR": cwd}
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=60,
                          env=env, **kw)


def git(args, cwd):
    r = sh(["git"] + args, cwd)
    if r.returncode != 0:
        sys.exit(f"FATAL: git {' '.join(args)} failed in fixture: {r.stderr}")
    return r


def run_hook(fixture, command):
    """pre-bash.py exactly as the hook layer sees it: hook JSON on stdin."""
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    return sh([sys.executable, PRE_BASH], fixture, input=payload)


def check(cond, label, detail):
    global checks
    checks += 1
    if cond:
        return
    failures.append(f"FAIL [{label}] {detail}")
    print(failures[-1])


def expect_block(fixture, command, tag, label):
    r = run_hook(fixture, command)
    check(r.returncode == 2 and f"[{tag}]" in r.stderr, label,
          f"expected BLOCK [{tag}] for: {command!r}\n"
          f"  exit={r.returncode} stderr={r.stderr.strip()[:300]!r}")


def expect_allow(fixture, command, label):
    r = run_hook(fixture, command)
    check(r.returncode == 0 and "BLOCKED" not in r.stderr, label,
          f"expected ALLOW for: {command!r}\n"
          f"  exit={r.returncode} stderr={r.stderr.strip()[:300]!r}")


def make_fixture(base, branch):
    """An arbiter-enabled repo with one commit, on `branch`."""
    root = os.path.join(base, f"fixture-{branch.replace('/', '-')}")
    os.makedirs(root)
    git(["init", "-q", "-b", branch, root], base)
    git(["config", "user.email", "harness@example.com"], root)
    git(["config", "user.name", "harness"], root)
    ca = os.path.join(root, ".codearbiter")
    os.makedirs(os.path.join(ca, "decisions"))
    with open(os.path.join(ca, "CONTEXT.md"), "w", encoding="utf-8") as f:
        f.write("---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\nguard fixture\n")
    with open(os.path.join(ca, "overrides.log"), "w", encoding="utf-8") as f:
        f.write("[2026-01-01T00:00:00Z] | BY: harness | GATE: none | REASON: seed\n")
    with open(os.path.join(ca, "decisions", "0001-seed.md"), "w", encoding="utf-8") as f:
        f.write("# ADR-0001\nseed decision\n")
    os.makedirs(os.path.join(root, "src"))
    for rel in ("src/app.py", "notes.txt"):
        with open(os.path.join(root, rel), "w", encoding="utf-8") as f:
            f.write("print('hello')\n")
    git(["add", "src/app.py", "notes.txt",
         ".codearbiter/CONTEXT.md", ".codearbiter/overrides.log",
         ".codearbiter/decisions/0001-seed.md"], root)
    git(["commit", "-q", "-m", "seed"], root)
    return root


def check_commit_pathspecs():
    """Unit-level: a heredoc BODY (stdin content via `-F -`) must not be parsed as
    pathspecs (the false H-09b/H-14 block), but everything else — including a
    multi-line quoted `-m` message AND a real trailing pathspec — must survive, or
    the worktree-union scan (v2.rev.0015) under-scans. Redirect operators are
    skipped while barewords after them stay over-included."""
    strip = pre_bash._strip_heredoc_bodies
    cp = pre_bash.commit_pathspecs

    # the heredoc operator + body + delimiter is removed; nothing else is cut
    s = strip(" -F - <<'EOF'\nfix: x\nbody ../docs\nEOF")
    check("../docs" not in s and "<<" not in s, "strip-heredoc",
          "the heredoc body+operator must be stripped from the arg string")
    check(cp(strip(" -F - <<'EOF'\nfix: x\nsee ../docs\nEOF")) == [], "cp-heredoc",
          "heredoc body tokens must not be parsed as pathspecs")
    check(cp(" -F - <<'EOF'") == [], "cp-redirect-op",
          "the heredoc operator token must not be a pathspec")
    # a `\\`-newline continuation is joined, not cut
    check("b.py" in strip(" a.py \\\n b.py"), "strip-continuation",
          "a line-continuation must be joined, not truncated")

    # NON-WEAKENING (the v2.rev.0015 regression the first cut introduced): a real
    # pathspec after a MULTI-LINE quoted -m message must still be collected — a
    # literal newline inside quotes must NOT drop the trailing path.
    check(cp(strip(' -m "l1\nl2" secret.py')) == ["secret.py"], "cp-multiline-msg",
          "a pathspec after a multi-line -m message must still be collected")
    check(cp(strip(' -m "l1\n\nbody" -- secret.py')) == ["secret.py"],
          "cp-multiline-dashdash",
          "the canonical `-- path` form after a multi-line message must survive")
    # a pathspec on the OPERATOR line, after `<<WORD`, is a real git pathspec
    # (the shell passes it to git; only the body is stdin) — it must survive the
    # heredoc strip, not be swallowed with the body (errs-open under-scan).
    check(cp(strip(" -F - <<EOF secret.py\nbody\nEOF")) == ["secret.py"],
          "cp-heredoc-opline-pathspec",
          "a pathspec after `<<WORD` on the operator line must be preserved")

    # ordinary pathspecs / flags
    check(cp(" -m 'msg' src/app.py") == ["src/app.py"], "cp-pathspec",
          "a real pathspec must still be collected")
    check(cp(" -m x a.py b.py") == ["a.py", "b.py"], "cp-multi",
          "multiple pathspecs collected")
    check(cp(" -- a.py") == ["a.py"], "cp-dashdash", "explicit -- pathspec collected")
    # a redirect OPERATOR is skipped, but a bareword after it is still over-included
    # (so `git commit > log secret.py` cannot smuggle secret.py past the scan)
    check("secret.py" in cp(" > log secret.py"), "cp-redirect-overinclude",
          "a bareword after a redirect must still be over-included (no under-scan)")


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    base = tempfile.mkdtemp(prefix="ca-guards-")
    try:
        check_commit_pathspecs()                    # pure parser units (no fixture)
        fx = make_fixture(base, "feat/work")        # the normal case: a feature branch
        fx_main = make_fixture(base, "main")        # only for on-main push/commit cases

        # ---- H-03: staging must name explicit files --------------------------
        for cmd in ("git add -A", "git add .", "git add --all", "git add -u",
                    "git add --update", "git add *", "git add '*.py'",
                    "git add src/", "git add src", "git add :/",
                    "git add ':(glob)**/*.js'"):
            expect_block(fx, cmd, "H-03", f"H-03 block: {cmd}")
        for cmd in ("git add notes.txt", "git add src/app.py",
                    "git add notes.txt src/app.py", "git add -- notes.txt",
                    # unresolvable path: git's problem, not the guard's
                    "git add no/such/file.txt"):
            expect_allow(fx, cmd, f"H-03 allow: {cmd}")

        # ---- H-05: audit logs are append-only --------------------------------
        for cmd in ("echo x > .codearbiter/overrides.log",
                    # `>|` force-clobbers even under `set -o noclobber` — it
                    # truncates the audit log exactly as `>` does and must block.
                    "echo x >| .codearbiter/overrides.log",
                    "echo x >|.codearbiter/overrides.log",
                    "truncate -s0 .codearbiter/overrides.log",
                    "tee .codearbiter/overrides.log < /tmp/x",
                    "cp /dev/null .codearbiter/overrides.log",
                    "dd if=/dev/null of=.codearbiter/overrides.log",
                    "sed -i d .codearbiter/triage.log",
                    "rm .codearbiter/triage.log",
                    "Set-Content .codearbiter/overrides.log 'gone'",
                    # sprint-log.md is the /sprint decision record — append-only.
                    "echo x > .codearbiter/sprint-log.md",
                    "echo x >| .codearbiter/sprint-log.md",
                    "rm .codearbiter/sprint-log.md",
                    "Set-Content .codearbiter/sprint-log.md 'gone'",
                    # gate-events.log (observability-001, #186) joins the append-only
                    # set — the durable BLOCK/REMIND/WARN sink gets the same H-05
                    # tool-call protection as the other three audit logs.
                    "echo x > .codearbiter/gate-events.log",
                    "rm .codearbiter/gate-events.log",
                    # #335: Git-native worktree restoration rewrites tracked audit
                    # logs without using any of the filesystem verbs above.
                    "git checkout -- .codearbiter/gate-events.log",
                    "git checkout HEAD -- .codearbiter/sprint-log.md",
                    "git restore .codearbiter/overrides.log",
                    "git restore --source=HEAD -- .codearbiter/triage.log",
                    "git -C . restore -- .codearbiter/overrides.log"):
            expect_block(fx, cmd, "H-05", f"H-05 block: {cmd}")
        for cmd in ("echo entry >> .codearbiter/overrides.log",
                    "echo entry >> .codearbiter/sprint-log.md",
                    "echo entry >> .codearbiter/gate-events.log",
                    "cat .codearbiter/overrides.log",
                    "grep GATE .codearbiter/overrides.log",
                    "cat .codearbiter/sprint-log.md",
                    "tail -5 .codearbiter/triage.log",
                    "cat .codearbiter/gate-events.log",
                    # Git reads of audit history remain legitimate; only checkout
                    # and restore are destructive to the worktree audit trail.
                    "git diff -- .codearbiter/overrides.log",
                    "git show HEAD:.codearbiter/overrides.log",
                    # A later read-only command naming an audit log must not
                    # make an unrelated restore look destructive.
                    "git restore notes.txt; cat .codearbiter/overrides.log"):
            expect_allow(fx, cmd, f"H-05 allow: {cmd}")

        # ---- H-11: no shell writes into .codearbiter/decisions/ --------------
        for cmd in ("echo '# fake ADR' > .codearbiter/decisions/0009-fake.md",
                    "echo '# fake ADR' >| .codearbiter/decisions/0009-fake.md",
                    "echo more >> .codearbiter/decisions/0001-seed.md",
                    "touch .codearbiter/decisions/0010-x.md",
                    "cp /tmp/draft.md .codearbiter/decisions/0011-y.md",
                    "rm .codearbiter/decisions/0001-seed.md",
                    "mv .codearbiter/decisions/0001-seed.md /tmp/",
                    "sed -i 's/accepted/rejected/' .codearbiter/decisions/0001-seed.md",
                    "Set-Content .codearbiter\\decisions\\0001-seed.md 'rewritten'"):
            expect_block(fx, cmd, "H-11", f"H-11 block: {cmd}")
        for cmd in ("cat .codearbiter/decisions/0001-seed.md",
                    "ls .codearbiter/decisions/",
                    "grep -r seed .codearbiter/decisions/"):
            expect_allow(fx, cmd, f"H-11 allow: {cmd}")

        # ---- H-19: interpreter one-liners forging a gate marker (#237) -------
        # The mv/cp/tee/sed/redirect flank (below, exercised via H-05-style
        # verbs elsewhere) misses an arbitrary interpreter invocation entirely —
        # `python -c "..."` can hand-write the marker using the SAME public
        # helpers the sanctioned producer uses, and no verb in the old list
        # ever fires. Each of these must BLOCK exactly like the mv/cp forge.
        for cmd in (
            'python -c "open(\'.codearbiter/.markers/security-gate-passed\', '
            '\'w\').write(\'deadbeef\')"',
            'python3 -c "open(\'.codearbiter/.markers/security-gate-passed\', '
            '\'w\').write(\'deadbeef\')"',
            'node -e "require(\'fs\').writeFileSync('
            '\'.codearbiter/.markers/security-gate-passed\', \'deadbeef\')"',
            'perl -e \'open(my $fh, ">", ".codearbiter/.markers/'
            'security-gate-passed"); print $fh "deadbeef"\'',
            'ruby -e \'File.write(".codearbiter/.markers/'
            'security-gate-passed", "deadbeef")\'',
            'sh -c "echo deadbeef > .codearbiter/.markers/'
            'security-gate-passed"',
            # the segment-bound case: a `;` sits BEFORE the marker path inside
            # the interpreter's own quoted payload. A verb-style regex whose
            # scan stops at the first `;` (as the mv/cp flank's does, by
            # design, to avoid reaching across an unrelated chained command)
            # would never reach the marker here and falsely ALLOW.
            'python -c "import sys; open(\'.codearbiter/.markers/'
            'security-gate-passed\', \'w\').write(\'deadbeef\')"',
            'python3 -c "d=\'deadbeef\'; open(\'.codearbiter/.markers/'
            'migration-gate-passed\', \'w\').write(d)"',
        ):
            expect_block(fx, cmd, "H-19", f"H-19 block: {cmd}")
        # must NOT over-block a benign interpreter call that never names a
        # gate marker anywhere on the line.
        for cmd in ('python -c "print(1)"', 'node -e "console.log(1)"',
                    'sh -c "echo hello"'):
            expect_allow(fx, cmd, f"H-19 allow (benign interpreter): {cmd}")

        # ---- H-19 review finding: newline-crossing + heredoc/prose scoping ----
        # Defect 1: a MULTI-LINE `-c`/`-e` payload is completely ordinary
        # python/node/etc — the interpreter token and the marker path can sit
        # on different physical lines of the SAME invocation. A regex whose
        # scan cannot cross a newline (`[^\n]*`) misses this identical attack.
        multiline_python = (
            "python -c \"\n"
            "open('.codearbiter/.markers/security-gate-passed', 'w')."
            "write('deadbeef')\n\""
        )
        expect_block(fx, multiline_python, "H-19",
                     f"H-19 block: multi-line python -c payload: {multiline_python!r}")

        # Same attack, one level further removed: the heredoc's DIRECT consumer
        # is `cat` (not a shell), but `bash -c` elsewhere in the command
        # EXECUTES the substituted result — a genuine executor route
        # (`_has_shell_executor`), so the body really runs and must still
        # BLOCK, mirroring how commit/push/add already treat this shape.
        bash_c_heredoc = (
            "bash -c \"$(cat <<'EOF'\n"
            "python -c \\\"open('.codearbiter/.markers/security-gate-passed', "
            "'w').write('deadbeef')\\\"\n"
            "EOF\n"
            ")\""
        )
        expect_block(fx, bash_c_heredoc, "H-19",
                     f"H-19 block: heredoc body reaching bash -c executor: {bash_c_heredoc!r}")

        # Defect 2: a heredoc fed to a NON-shell consumer with no executor
        # anywhere in the command is inert PROSE to this guard (D-3, #223) —
        # a PR/issue body merely DESCRIBING the python-c forgery attack must
        # not itself trip H-19, or this very sprint's own PR body would block.
        pr_body_prose = (
            "gh pr create --body \"$(cat <<'EOF'\n"
            "Fixes #237: a `python -c` one-liner could write\n"
            ".codearbiter/.markers/security-gate-passed and the gate accepted it.\n"
            "EOF\n"
            ")\""
        )
        expect_allow(fx, pr_body_prose,
                     f"H-19 allow: PR-body prose describing the forge: {pr_body_prose!r}")
        issue_body_prose = pr_body_prose.replace("gh pr create", "gh issue create")
        expect_allow(fx, issue_body_prose,
                     f"H-19 allow: issue-body prose describing the forge: {issue_body_prose!r}")

        # ---- H-01/H-02: protected-branch pushes ------------------------------
        for cmd in ("git push origin HEAD:main", "git push origin feat/work:main",
                    "git push origin main", "git push origin :main",
                    "git push origin HEAD:refs/heads/master",
                    "git push upstream master"):
            expect_block(fx, cmd, "H-01", f"H-01 block: {cmd}")
        for cmd in ("git push origin feat/work", "git push origin HEAD:feat/work",
                    "git push -u origin feat/work", "git push origin v2.0.0",
                    "git push origin feature-main", "git push",
                    "git push origin"):
            expect_allow(fx, cmd, f"H-01 allow: {cmd}")
        # --all pushes every local branch (incl. main); --mirror pushes every
        # ref and can force-update/delete them. Both write protected refs from
        # any branch and must block regardless of the current branch.
        for cmd in ("git push --all", "git push --all origin",
                    "git push origin --all", "git push --mirror",
                    "git push --mirror origin", "git push origin --mirror"):
            expect_block(fx, cmd, "H-01", f"H-01 block: {cmd}")
        expect_block(fx_main, "git push", "H-01", "H-01 block: bare push on main")
        expect_block(fx_main, "git push origin", "H-01", "H-01 block: push remote-only on main")
        expect_block(fx_main, "git commit -m x", "H-01", "H-01 block: commit on main")
        # Case-insensitive protected name: `Main` is the default branch on a
        # case-folding ref store and must block exactly like `main`. Built in its
        # own sub-base so `fixture-Main` doesn't collide with `fixture-main` on a
        # case-insensitive filesystem.
        case_base = os.path.join(base, "case")
        os.makedirs(case_base)
        fx_Main = make_fixture(case_base, "Main")
        expect_block(fx_Main, "git commit -m x", "H-01", "H-01 block: commit on 'Main'")
        # Detached HEAD sitting on main's tip: current_branch() is "" but a commit
        # still writes onto main's history -> must block.
        git(["checkout", "--detach"], fx_main)
        expect_block(fx_main, "git commit -m x", "H-01",
                     "H-01 block: commit in detached HEAD at main tip")
        # performance-006 parity lock: head_on_protected_tip now resolves HEAD +
        # both protected branches in a SINGLE `git rev-parse HEAD main master`.
        # When `master` is absent that spawn exits nonzero and echoes the
        # unresolved name as a non-SHA line — the detection must read SHA-shaped
        # lines only and still BLOCK a detached HEAD on the `master` tip when
        # master is the default branch (main absent).
        master_base = os.path.join(base, "master-case")
        os.makedirs(master_base)
        fx_master = make_fixture(master_base, "master")
        git(["checkout", "--detach"], fx_master)
        expect_block(fx_master, "git commit -m x", "H-01",
                     "H-01 block: commit in detached HEAD at master tip")
        # And the converse: a detached HEAD on an OLDER commit (main exists but
        # HEAD != its tip) must ALLOW — the single spawn must not misread a
        # resolved-but-different protected SHA as a tip match.
        detach_base = os.path.join(base, "detach-old")
        os.makedirs(detach_base)
        fx_old = make_fixture(detach_base, "main")
        with open(os.path.join(fx_old, "notes.txt"), "a", encoding="utf-8") as f:
            f.write("second commit\n")
        git(["add", "notes.txt"], fx_old)
        git(["commit", "-q", "-m", "second"], fx_old)
        git(["checkout", "--detach", "HEAD~1"], fx_old)
        expect_allow(fx_old, "git commit -m x",
                     "allow: detached HEAD on an older commit is not a protected tip")
        expect_block(fx, "git push --force origin feat/work", "H-02", "H-02 block: force push")

        # ---- H-09b: the diff-bound security gate (TOCTOU closed) -------------
        crypto_file = os.path.join(fx, "src", "auth.js")
        with open(crypto_file, "w", encoding="utf-8") as f:
            f.write("const h = createHash('sha256');\n")
        git(["add", "src/auth.js"], fx)

        # 6a. no marker at all -> freshness block
        expect_block(fx, "git commit -m 'add hashing'", "H-09b",
                     "H-09b block: crypto commit with no recorded pass")

        # 6b. legacy empty marker (the old `touch`) -> binding block.
        # An empty marker proves only that *something* passed recently; it
        # covers no lines, so the diff-bound check must reject it.
        markers = os.path.join(fx, ".codearbiter", ".markers")
        os.makedirs(markers, exist_ok=True)
        with open(os.path.join(markers, "security-gate-passed"), "w") as f:
            pass
        r = run_hook(fx, "git commit -m 'add hashing'")
        check(r.returncode == 2 and "not covered" in r.stderr, "H-09b empty-marker",
              f"empty (legacy touch) marker must not admit a crypto commit\n"
              f"  exit={r.returncode} stderr={r.stderr.strip()[:300]!r}")

        # 6c. a genuine pass recorded by security-pass.py -> allow
        r = sh([sys.executable, SECURITY_PASS], fx)
        check(r.returncode == 0 and "1 sensitive line" in r.stdout, "security-pass",
              f"security-pass.py must record exactly the one sensitive line\n"
              f"  exit={r.returncode} out={r.stdout.strip()[:300]!r} "
              f"err={r.stderr.strip()[:300]!r}")
        expect_allow(fx, "git commit -m 'add hashing'",
                     "H-09b allow: pass covers the staged sensitive line")

        # 6d. THE TOCTOU CASE: inside the freshness window, stage a *different*
        # crypto line the gate never saw -> must block on coverage.
        with open(crypto_file, "a", encoding="utf-8") as f:
            f.write("const weak = createHash('md5');\n")
        git(["add", "src/auth.js"], fx)
        r = run_hook(fx, "git commit -m 'sneak in md5'")
        check(r.returncode == 2 and "not covered" in r.stderr, "H-09b TOCTOU",
              f"a fresh pass for one diff must not admit a different crypto diff\n"
              f"  exit={r.returncode} stderr={r.stderr.strip()[:300]!r}")

        # 6e. benign commit with no sensitive lines: no marker needed
        with open(os.path.join(fx, "notes.txt"), "a", encoding="utf-8") as f:
            f.write("more notes\n")
        git(["add", "notes.txt"], fx)
        shutil.rmtree(markers)
        # the crypto file is still staged from 6d — unstage it so only the
        # benign change remains
        git(["restore", "--staged", "src/auth.js"], fx)
        expect_allow(fx, "git commit -m 'notes only'",
                     "H-09b allow: benign commit needs no pass")

        # ---- #279: gate-events.log self-poisoning exemption -------------------
        # The gate's own audit sink echoes the detector's message text back at
        # itself: the REAL H-09 REMIND text (post-write-edit.py) spells out
        # "no MD5/SHA1/DES/3DES/RC2/RC4/Blowfish", and those bare words match
        # CRYPTO_RE just as well as a genuine algorithm choice would. An
        # uncommitted appended REMIND line in gate-events.log must NOT be
        # treated as a sensitive line — narrowly, only for that one file.
        shutil.rmtree(markers, ignore_errors=True)
        crypto_remind_line = (
            "[2026-07-12T17:12:53Z] REMIND [H-09] host=codex "
            "hook=post-write-edit.py | Crypto/TLS pattern detected. Run the "
            "crypto-compliance check + dispatch auth-crypto-reviewer (no "
            "MD5/SHA1/DES/3DES/RC2/RC4/Blowfish; do not disable TLS "
            "verification). The commit will block until the gate records a "
            "pass.\n"
        )

        # 6e2. gate-events.log dirty with a self-referential REMIND line, diff
        # otherwise innocuous -> ALLOW, no marker needed.
        gate_events = os.path.join(fx, ".codearbiter", "gate-events.log")
        with open(gate_events, "a", encoding="utf-8") as f:
            f.write(crypto_remind_line)
        git(["add", ".codearbiter/gate-events.log"], fx)
        with open(os.path.join(fx, "notes.txt"), "a", encoding="utf-8") as f:
            f.write("another benign note\n")
        git(["add", "notes.txt"], fx)
        expect_allow(fx, "git commit -m 'log churn only'",
                     "#279 allow: dirty gate-events.log alone must not block H-09b")

        # 6e3. still BLOCKS: a real crypto line added to a genuine source file,
        # over-excluding must not weaken the scan for actual source changes.
        git(["restore", "--staged", "--worktree", ".codearbiter/gate-events.log"], fx)
        git(["restore", "--staged", "--worktree", "notes.txt"], fx)
        with open(crypto_file, "a", encoding="utf-8") as f:
            f.write("const h4 = createHash('sha1');\n")
        git(["add", "src/auth.js"], fx)
        expect_block(fx, "git commit -m 'real crypto'", "H-09b",
                     "#279 block: a real crypto line in a source file still blocks")

        # 6e4. still BLOCKS with gate-events.log ALSO dirty — proves the log is
        # excluded, not the whole scan.
        with open(gate_events, "a", encoding="utf-8") as f:
            f.write(crypto_remind_line)
        git(["add", ".codearbiter/gate-events.log"], fx)
        expect_block(fx, "git commit -m 'real crypto plus log churn'", "H-09b",
                     "#279 block: real crypto still blocks even with gate-events.log dirty")
        git(["restore", "--staged", "--worktree", "src/auth.js"], fx)
        git(["restore", "--staged", "--worktree", ".codearbiter/gate-events.log"], fx)

        # 6e5. still BLOCKS: a secret added to overrides.log — the narrow scope
        # proves only gate-events.log is exempt, not every audit log.
        overrides_log = os.path.join(fx, ".codearbiter", "overrides.log")
        with open(overrides_log, "a", encoding="utf-8") as f:
            f.write('[2026-07-12T17:14:00Z] | BY: harness | GATE: none | '
                    'REASON: api_key="abcd1234efgh"\n')
        git(["add", ".codearbiter/overrides.log"], fx)
        expect_block(fx, "git commit -m 'log secret'", "H-10b",
                     "#279 block: a secret in overrides.log still blocks (narrow scope)")
        git(["restore", "--staged", "--worktree", ".codearbiter/overrides.log"], fx)

        # 6e6/6e7. THE EVASION (2026-07 review finding): the attribution used
        # to key off "+++ b/<path>", which a genuine ADDED CONTENT line can
        # FORGE — a source line whose text is "++ b/.codearbiter/gate-events.
        # log" renders in `git diff` as "+++ b/.codearbiter/gate-events.log",
        # byte-identical to the real hunk header, hijacking attribution for
        # every added line after it. A real crypto line placed right after
        # such a forged line must still BLOCK with no marker recorded.
        with open(crypto_file, "a", encoding="utf-8") as f:
            f.write("++ b/.codearbiter/gate-events.log\n"
                    "const h5 = createHash('md5');\n")
        git(["add", "src/auth.js"], fx)
        expect_block(fx, "git commit -m 'forged plusplusplus header (2-plus form)'", "H-09b",
                     "#279 block: a forged '++ b/...' content line must not evade the scan")
        git(["restore", "--staged", "--worktree", "src/auth.js"], fx)

        # Same shape with the 3-plus content form ("+++ b/<path>" as literal
        # SOURCE text, rendering as "++++ b/<path>" once diff-prefixed) —
        # covers the other prefix arithmetic the reviewer called out.
        with open(crypto_file, "a", encoding="utf-8") as f:
            f.write("+++ b/.codearbiter/gate-events.log\n"
                    "const h6 = createHash('md5');\n")
        git(["add", "src/auth.js"], fx)
        expect_block(fx, "git commit -m 'forged plusplusplus header (3-plus form)'", "H-09b",
                     "#279 block: a forged '+++ b/...' content line must not evade the scan")
        git(["restore", "--staged", "--worktree", "src/auth.js"], fx)

        # 6e8. THE AMBIGUOUS-PATH BYPASS (2026-07 security review, round 3,
        # HIGH): a genuine repo file whose path itself contains " b/" renders
        # its `diff --git` header as
        #   diff --git a/x b/.codearbiter/gate-events.log b/x b/.codearbiter/gate-events.log
        # A greedy regex parse of that line (the round-2 fix) resolves the
        # path to ".codearbiter/gate-events.log" (the LAST " b/" split),
        # exempting the WHOLE unrelated source file. A real crypto call and a
        # committed secret in that file must still BLOCK with no marker.
        odd_dir = os.path.join(fx, "x b", ".codearbiter")
        os.makedirs(odd_dir, exist_ok=True)
        odd_file = os.path.join(odd_dir, "gate-events.log")
        with open(odd_file, "w", encoding="utf-8") as f:
            f.write("const h7 = createHash('md5');\n"
                    'const key = api_key="abcd1234efgh";\n')
        git(["add", "x b/.codearbiter/gate-events.log"], fx)
        expect_block(fx, "git commit -m 'ambiguous path exploit'", "H-09b",
                     "#279 block: a real source file named 'x b/...' must not be "
                     "misattributed to the exempt log via a greedy diff --git parse")
        git(["restore", "--staged", "--worktree", "x b/.codearbiter/gate-events.log"], fx)

        # 6e9/6e10. THE DIFF-CONFIG BYPASS (round 3, MEDIUM-1): the REAL
        # gate-events.log, dirty, must stay exempt (commit ALLOWED) even when
        # the repo has `diff.mnemonicPrefix=true` or `diff.noprefix=true` set
        # — either config, left unpinned by the H-09b/H-10b readers, changes
        # the destination-path prefix the fixed `+++ b/` strip depends on,
        # silently un-exempting the log and reopening the exact self-DoS this
        # whole change exists to close.
        for cfg_name, cfg_val in (("mnemonicPrefix", "true"), ("noprefix", "true")):
            git(["config", f"diff.{cfg_name}", cfg_val], fx)
            with open(gate_events, "a", encoding="utf-8") as f:
                f.write(crypto_remind_line)
            git(["add", ".codearbiter/gate-events.log"], fx)
            expect_allow(
                fx, f"git commit -m 'log churn under diff.{cfg_name}={cfg_val}'",
                f"#279 allow: gate-events.log stays exempt under diff.{cfg_name}={cfg_val}")
            git(["restore", "--staged", "--worktree", ".codearbiter/gate-events.log"], fx)
            git(["config", "--unset", f"diff.{cfg_name}"], fx)

        # ---- 6f-6j: deep-review HIGH (v2.rev.0015) — a `git commit <pathspec>`
        # records the WORKTREE content of the named paths, bypassing the index.
        # The gate scanned only --cached (unioning worktree only on -a/add), so an
        # unstaged crypto/secret/migration change named as a pathspec slipped past
        # with no recorded pass. Also: the security scan must fail CLOSED on a
        # git-read error (parity with the H-14 backstop). RED until pre-bash.py is
        # fixed; locked here so the hole can never silently reopen.
        fxp = make_fixture(base, "feat/pathspec")
        os.makedirs(os.path.join(fxp, "migrations"))
        mig_rel = "migrations/001_init.sql"
        with open(os.path.join(fxp, mig_rel), "w", encoding="utf-8") as f:
            f.write("CREATE TABLE t (id int);\n")
        git(["add", mig_rel], fxp)
        git(["commit", "-q", "-m", "seed migration"], fxp)
        appp = os.path.join(fxp, "src", "app.py")  # tracked since make_fixture

        # 6f. H-09b: unstaged crypto in a tracked file, committed by pathspec.
        with open(appp, "a", encoding="utf-8") as f:
            f.write("const h = createHash('sha256');\n")
        expect_block(fxp, "git commit -m 'sneak' src/app.py", "H-09b",
                     "H-09b block: pathspec commit of an unstaged crypto change")
        git(["checkout", "--", "src/app.py"], fxp)

        # 6g. H-10b: same, for a secret literal.
        with open(appp, "a", encoding="utf-8") as f:
            f.write('const api_key = "abcd1234efgh";\n')
        expect_block(fxp, "git commit -m 'sneak' src/app.py", "H-10b",
                     "H-10b block: pathspec commit of an unstaged secret")
        git(["checkout", "--", "src/app.py"], fxp)

        # 6h. H-14: unstaged migration edit committed by pathspec.
        with open(os.path.join(fxp, mig_rel), "a", encoding="utf-8") as f:
            f.write("ALTER TABLE t ADD c int;\n")
        expect_block(fxp, f"git commit -m 'sneak' {mig_rel}", "H-14",
                     "H-14 block: pathspec commit of an unstaged migration")
        git(["checkout", "--", mig_rel], fxp)

        # 6i. coverage lock-in (GREEN already): -am sweeps the worktree -> H-09b.
        with open(appp, "a", encoding="utf-8") as f:
            f.write("const h2 = createHash('sha256');\n")
        expect_block(fxp, "git commit -am 'sweep'", "H-09b",
                     "H-09b block: git commit -am pulls in worktree crypto")
        git(["checkout", "--", "src/app.py"], fxp)

        # 6j. fail-CLOSED: a git-read error during the security scan must BLOCK,
        # not pass. An arbiter-enabled dir that is not a git repo forces the
        # `git diff` nonzero-return path (proxy for a timeout/locked-index error).
        nogit = os.path.join(base, "nogit")
        os.makedirs(os.path.join(nogit, ".codearbiter"))
        with open(os.path.join(nogit, ".codearbiter", "CONTEXT.md"), "w", encoding="utf-8") as f:
            f.write("---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\n")
        with open(os.path.join(nogit, "auth.js"), "w", encoding="utf-8") as f:
            f.write("const h = createHash('sha256');\n")
        r = run_hook(nogit, "git commit -m x auth.js")
        check(r.returncode == 2, "H-09b fail-closed",
              f"a git-diff failure during the security scan must fail CLOSED (block)\n"
              f"  exit={r.returncode} stderr={r.stderr.strip()[:300]!r}")

        # 6k. the worktree union must NOT over-block a benign pathspec commit.
        with open(os.path.join(fxp, "notes.txt"), "a", encoding="utf-8") as f:
            f.write("a benign note\n")
        expect_allow(fxp, "git commit -m 'notes' notes.txt",
                     "allow: benign pathspec commit is not over-blocked")

        # 6l. the recommended `git commit -F - <<EOF` multi-line form must NOT
        # false-block: its heredoc body is the message via stdin, not pathspecs.
        # RED before the fix — body tokens (e.g. `../docs`) were parsed as
        # pathspecs and `git diff HEAD -- ../docs` errored -> fail-closed.
        expect_allow(
            fxp,
            "git commit -F - <<'EOF'\nchore: tidy\n\nSee ../docs for context.\nEOF",
            "H-09b heredoc: benign -F - <<EOF must not false-block on body tokens")

        # 6m. non-weakening lock-in: a heredoc commit that STAGES crypto must
        # still block — the --cached scan catches it regardless of how the
        # message is supplied (proves the fix narrows parsing, not the gate).
        with open(appp, "a", encoding="utf-8") as f:
            f.write("const h = createHash('sha256');\n")
        git(["add", "src/app.py"], fxp)
        expect_block(
            fxp,
            "git commit -F - <<'EOF'\nfeat: hashing\nEOF",
            "H-09b",
            "H-09b heredoc: staged crypto still blocks (fix does not weaken the gate)")
        git(["restore", "--staged", "src/app.py"], fxp)
        git(["checkout", "--", "src/app.py"], fxp)

        # 6n. THE worktree-union non-weakening proof: an UNSTAGED crypto change
        # committed by pathspec, with a MULTI-LINE `-m` message, must still block.
        # A first-line split would truncate at the literal newline inside the
        # quotes and drop the trailing pathspec -> bypass. (RED against that;
        # GREEN once only heredoc bodies are stripped.)
        with open(appp, "a", encoding="utf-8") as f:
            f.write("const h3 = createHash('sha256');\n")
        expect_block(
            fxp,
            'git commit -m "subject\n\nbody line" src/app.py',
            "H-09b",
            "H-09b: worktree crypto via multi-line -m pathspec commit still blocks")
        git(["checkout", "--", "src/app.py"], fxp)

        # 6l. SCOPED, not over-scanned: an unstaged crypto change in app.py must
        # NOT block a pathspec commit that names only the benign notes.txt — the
        # scan is scoped to the named paths, so an unrelated worktree change
        # elsewhere is not dragged in (app.py's crypto isn't being committed).
        with open(appp, "a", encoding="utf-8") as f:
            f.write("const x = createHash('sha256');\n")
        expect_allow(fxp, "git commit -m 'notes' notes.txt",
                     "allow: pathspec scan is scoped to named paths, not whole worktree")
        git(["checkout", "--", "src/app.py"], fxp)
        git(["checkout", "--", "notes.txt"], fxp)
    finally:
        shutil.rmtree(base, ignore_errors=True)

    print(f"\n{checks} assertions, {len(failures)} failed")
    if failures:
        print("\nRELEASE BLOCKER: a guard-logic case failed. Do not weaken the hook.")
        sys.exit(1)
    print("guard-logic matrix: PASS")


if __name__ == "__main__":
    main()
