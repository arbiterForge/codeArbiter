#!/usr/bin/env python3
"""codeArbiter — H-14 migration commit-time backstop regression suite (issue #77).

Proves the four moving parts of the migration backstop:

  * detection   — `_hooklib.is_migration_path` over the default glob set and the
                  `security-controls.md` extend/exclude declaration (OB-01..03).
  * producer    — `migration-pass.py` writes a content-digest marker for every
                  staged/worktree/untracked migration (OB-04).
  * backstop    — `pre-bash.py` H-14 BLOCKs a `git commit` of a migration not
                  covered by the marker, admits a covered one, re-blocks an
                  edited one, leaves non-migration commits alone, is dormant
                  outside an arbiter repo, and covers `-a` (OB-05..10, OB-C1).
  * wiring      — commit-gate prose dispatches the reviewer + records the pass
                  (OB-11), and the new hook code is byte-compilable stdlib (OB-S1).

Same harness shape as test_hook_guards.py: hook JSON on stdin, throwaway
arbiter-enabled git repos, stdlib only. Exit 0 = pass; exit 1 = failures.
"""

import json
import os
import py_compile
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOOKS = os.path.join(REPO, "plugins", "ca", "hooks")
PRE_BASH = os.path.join(HOOKS, "pre-bash.py")
MIGRATION_PASS = os.path.join(HOOKS, "migration-pass.py")
COMMIT_GATE = os.path.join(REPO, "plugins", "ca", "skills", "commit-gate", "SKILL.md")

sys.path.insert(0, HOOKS)

failures = []
checks = 0


def check(cond, label, detail=""):
    global checks
    checks += 1
    if cond:
        return
    failures.append(f"FAIL [{label}] {detail}")
    print(failures[-1])


def sh(args, cwd, **kw):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=60, **kw)


def git(args, cwd):
    r = sh(["git"] + args, cwd)
    if r.returncode != 0:
        sys.exit(f"FATAL: git {' '.join(args)} failed in fixture: {r.stderr}")
    return r


def run_hook(fixture, command):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    return sh([sys.executable, PRE_BASH], fixture, input=payload)


def run_pass(fixture):
    return sh([sys.executable, MIGRATION_PASS], fixture)


def make_repo(base, name, arbiter=True, controls=None):
    """A git repo on a feature branch (so H-01 never fires), arbiter-enabled
    unless arbiter=False. `controls` is optional security-controls.md text."""
    root = os.path.join(base, name)
    os.makedirs(root)
    git(["init", "-q", "-b", "feat/work", root], base)
    git(["config", "user.email", "h@example.com"], root)
    git(["config", "user.name", "h"], root)
    if arbiter:
        ca = os.path.join(root, ".codearbiter")
        os.makedirs(ca, exist_ok=True)
        with open(os.path.join(ca, "CONTEXT.md"), "w", encoding="utf-8") as f:
            f.write("---\narbiter: enabled\nstage: 2\n---\n<!--INITIALIZED-->\nfixture\n")
        if controls is not None:
            with open(os.path.join(ca, "security-controls.md"), "w", encoding="utf-8") as f:
                f.write(controls)
    return root


def write(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


def marker_path(root):
    return os.path.join(root, ".codearbiter", ".markers", "migration-gate-passed")


MIG = "CREATE TABLE t (id int);\n"
MIG2 = "CREATE TABLE t (id int, name text);\n"


# ── A. detection (OB-01..03) ────────────────────────────────────────────────
def section_detection(base):
    try:
        from _hooklib import is_migration_path  # noqa: E402
    except Exception as e:  # noqa: BLE001
        check(False, "OB-01..03", f"_hooklib.is_migration_path missing: {e}")
        return
    root = make_repo(base, "detect")
    yes = ["db/migrate/20240101_x.rb", "migrations/0001_init.py",
           "alembic/versions/abc_x.py", "prisma/migrations/2024_x/migration.sql"]
    no = ["src/app.py", "docs/migrations-guide.md"]
    for p in yes:
        check(is_migration_path(p, root), "OB-01", f"default glob should match {p!r}")
    for p in no:
        check(not is_migration_path(p, root), "OB-01", f"should NOT match {p!r}")

    ext = make_repo(base, "detect-ext",
                    controls="# sc\n<!-- migration-paths -->\n+ schema/changesets/**\n<!-- /migration-paths -->\n")
    check(is_migration_path("schema/changesets/v5.sql", ext), "OB-02",
          "project-added glob should detect schema/changesets/v5.sql")

    exc = make_repo(base, "detect-exc",
                    controls="# sc\n<!-- migration-paths -->\n- migrations/seed/**\n<!-- /migration-paths -->\n")
    check(not is_migration_path("migrations/seed/data.sql", exc), "OB-03",
          "exclusion should drop migrations/seed/data.sql")
    check(is_migration_path("migrations/0001_init.py", exc), "OB-03",
          "exclusion must not over-suppress a normal migration")

    # glob translator: bare `**` (any chars incl. /) and `?` (one non-/ char).
    g = make_repo(base, "detect-glob",
                  controls="# sc\n<!-- migration-paths -->\n+ legacy**\n+ rev?.sql\n<!-- /migration-paths -->\n")
    check(is_migration_path("legacy/x/y.sql", g), "OB-02", "bare ** should span segments")
    check(is_migration_path("rev5.sql", g), "OB-02", "? should match one char")
    check(not is_migration_path("rev55.sql", g), "OB-02", "? must match exactly one char")


# ── B. producer (OB-04) ─────────────────────────────────────────────────────
def section_producer(base):
    try:
        from _hooklib import content_digest  # noqa: E402
    except Exception as e:  # noqa: BLE001
        check(False, "OB-04", f"_hooklib.content_digest missing: {e}")
        return
    root = make_repo(base, "producer")
    write(root, "migrations/0001_init.sql", MIG)  # untracked, as commit-gate would stage
    r = run_pass(root)
    check(r.returncode == 0, "OB-04", f"migration-pass.py exit={r.returncode} stderr={r.stderr[:200]!r}")
    mp = marker_path(root)
    recorded = ""
    if os.path.isfile(mp):
        with open(mp, encoding="utf-8") as f:
            recorded = f.read()
    check(content_digest(MIG) in recorded.split(), "OB-04",
          "marker must contain the migration's content digest")


# ── C. backstop (OB-05..10, OB-C1) ──────────────────────────────────────────
def section_backstop(base):
    # OB-05: unreviewed migration blocks (no marker).
    r1 = make_repo(base, "bs-block")
    write(r1, "migrations/0001.sql", MIG)
    git(["add", "migrations/0001.sql"], r1)
    res = run_hook(r1, "git commit -m wip")
    check(res.returncode == 2 and "[H-14]" in res.stderr, "OB-05",
          f"unreviewed migration must BLOCK; exit={res.returncode} stderr={res.stderr[:200]!r}")

    # OB-06: covered migration admits.
    r2 = make_repo(base, "bs-allow")
    write(r2, "migrations/0001.sql", MIG)
    git(["add", "migrations/0001.sql"], r2)
    run_pass(r2)
    res = run_hook(r2, "git commit -m wip")
    check(res.returncode == 0 and "BLOCKED" not in res.stderr, "OB-06",
          f"reviewed migration must ALLOW; exit={res.returncode} stderr={res.stderr[:200]!r}")

    # OB-07: edited-after-review re-blocks (digest mismatch).
    r3 = make_repo(base, "bs-edit")
    write(r3, "migrations/0001.sql", MIG)
    git(["add", "migrations/0001.sql"], r3)
    run_pass(r3)                       # marker bound to MIG
    write(r3, "migrations/0001.sql", MIG2)  # content changes after review
    git(["add", "migrations/0001.sql"], r3)
    res = run_hook(r3, "git commit -m wip")
    check(res.returncode == 2 and "[H-14]" in res.stderr, "OB-07",
          f"edited migration must re-BLOCK; exit={res.returncode} stderr={res.stderr[:200]!r}")

    # OB-08: non-migration commit unaffected (no marker required).
    r4 = make_repo(base, "bs-nonmig")
    write(r4, "src/app.py", "x = 1\n")
    git(["add", "src/app.py"], r4)
    res = run_hook(r4, "git commit -m wip")
    check(res.returncode == 0 and "BLOCKED" not in res.stderr, "OB-08",
          f"non-migration commit must ALLOW; exit={res.returncode} stderr={res.stderr[:200]!r}")

    # OB-09: dormant outside an arbiter repo.
    r5 = make_repo(base, "bs-dormant", arbiter=False)
    write(r5, "migrations/0001.sql", MIG)
    git(["add", "migrations/0001.sql"], r5)
    res = run_hook(r5, "git commit -m wip")
    check(res.returncode == 0 and "BLOCKED" not in res.stderr, "OB-09",
          f"no .codearbiter -> backstop dormant; exit={res.returncode} stderr={res.stderr[:200]!r}")

    # OB-10: `-a` coverage — a tracked migration modified in the worktree.
    r6 = make_repo(base, "bs-all")
    write(r6, "migrations/0001.sql", MIG)
    git(["add", "migrations/0001.sql"], r6)
    git(["commit", "-q", "-m", "seed migration"], r6)  # now tracked + committed
    write(r6, "migrations/0001.sql", MIG2)             # worktree edit, NOT staged
    res = run_hook(r6, "git commit -am wip")
    check(res.returncode == 2 and "[H-14]" in res.stderr, "OB-10",
          f"`git commit -a` of a migration must BLOCK; exit={res.returncode} stderr={res.stderr[:200]!r}")

    # OB-C1: a marker present but not covering this file is no coverage -> BLOCK,
    # and the hook does not crash (fail-closed, not fail-open).
    r7 = make_repo(base, "bs-corrupt")
    write(r7, "migrations/0001.sql", MIG)
    git(["add", "migrations/0001.sql"], r7)
    os.makedirs(os.path.dirname(marker_path(r7)), exist_ok=True)
    with open(marker_path(r7), "w", encoding="utf-8") as f:
        f.write("deadbeef\n")  # an unrelated digest
    res = run_hook(r7, "git commit -m wip")
    check(res.returncode == 2 and "[H-14]" in res.stderr, "OB-C1",
          f"marker missing this digest must BLOCK (fail-closed); exit={res.returncode} stderr={res.stderr[:200]!r}")

    # OB-C1 (oversize): a migration too large to digest (>1MB) can never be
    # covered by a marker, so it stays fail-closed -> BLOCK. Both producer and
    # backstop skip the read; the backstop treats an unreadable file as
    # uncovered. Guards against the size limit drifting between the two.
    r8 = make_repo(base, "bs-oversize")
    big = MIG + ("-- padding\n" * 100000)  # ~1.3 MB
    p = write(r8, "migrations/large.sql", big)
    check(os.path.getsize(p) > 1_000_000, "OB-C1", "oversize fixture must exceed 1MB")
    git(["add", "migrations/large.sql"], r8)
    run_pass(r8)  # producer skips it -> marker has no digest for it
    res = run_hook(r8, "git commit -m wip")
    check(res.returncode == 2 and "[H-14]" in res.stderr, "OB-C1",
          f"oversize migration must BLOCK (too large to digest); exit={res.returncode} stderr={res.stderr[:200]!r}")


# ── D. prose wiring (OB-11) ─────────────────────────────────────────────────
def section_wiring():
    try:
        with open(COMMIT_GATE, encoding="utf-8") as f:
            text = f.read()
    except Exception as e:  # noqa: BLE001
        check(False, "OB-11", f"cannot read commit-gate SKILL.md: {e}")
        return
    for tok in ("migration-reviewer", "migration-pass.py", "H-14", "migration-gate-passed"):
        check(tok in text, "OB-11", f"commit-gate prose must reference {tok!r}")


# ── E. stdlib + compile (OB-S1) ─────────────────────────────────────────────
def section_stdlib():
    for path in (MIGRATION_PASS, PRE_BASH, os.path.join(HOOKS, "_hooklib.py")):
        try:
            py_compile.compile(path, doraise=True)
            ok = True
        except Exception as e:  # noqa: BLE001
            ok = False
            check(False, "OB-S1", f"py_compile failed for {os.path.basename(path)}: {e}")
        if ok:
            check(True, "OB-S1", "")
    # migration-pass.py must import only stdlib + the shared _hooklib.
    if os.path.isfile(MIGRATION_PASS):
        with open(MIGRATION_PASS, encoding="utf-8") as f:
            src = f.read()
        third_party = [ln for ln in src.splitlines()
                       if ln.startswith(("import ", "from "))
                       and "_hooklib" not in ln
                       and not any(m in ln for m in (
                           "import os", "import sys", "import subprocess",
                           "import hashlib", "import json", "import re"))]
        check(not third_party, "OB-S1", f"non-stdlib import in migration-pass.py: {third_party}")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        section_detection(tmp)
        section_producer(tmp)
        section_backstop(tmp)
    section_wiring()
    section_stdlib()
    print(f"\n{checks} checks, {len(failures)} failures")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
