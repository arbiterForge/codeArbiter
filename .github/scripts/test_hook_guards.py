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

failures = []
checks = 0


def sh(args, cwd, **kw):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=60, **kw)


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


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass

    base = tempfile.mkdtemp(prefix="ca-guards-")
    try:
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
                    "truncate -s0 .codearbiter/overrides.log",
                    "tee .codearbiter/overrides.log < /tmp/x",
                    "cp /dev/null .codearbiter/overrides.log",
                    "dd if=/dev/null of=.codearbiter/overrides.log",
                    "sed -i d .codearbiter/triage.log",
                    "rm .codearbiter/triage.log",
                    "Set-Content .codearbiter/overrides.log 'gone'"):
            expect_block(fx, cmd, "H-05", f"H-05 block: {cmd}")
        for cmd in ("echo entry >> .codearbiter/overrides.log",
                    "cat .codearbiter/overrides.log",
                    "grep GATE .codearbiter/overrides.log",
                    "tail -5 .codearbiter/triage.log"):
            expect_allow(fx, cmd, f"H-05 allow: {cmd}")

        # ---- H-11: no shell writes into .codearbiter/decisions/ --------------
        for cmd in ("echo '# fake ADR' > .codearbiter/decisions/0009-fake.md",
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
        expect_block(fx_main, "git push", "H-01", "H-01 block: bare push on main")
        expect_block(fx_main, "git push origin", "H-01", "H-01 block: push remote-only on main")
        expect_block(fx_main, "git commit -m x", "H-01", "H-01 block: commit on main")
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
    finally:
        shutil.rmtree(base, ignore_errors=True)

    print(f"\n{checks} assertions, {len(failures)} failed")
    if failures:
        print("\nRELEASE BLOCKER: a guard-logic case failed. Do not weaken the hook.")
        sys.exit(1)
    print("guard-logic matrix: PASS")


if __name__ == "__main__":
    main()
