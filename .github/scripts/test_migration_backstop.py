#!/usr/bin/env python3
"""codeArbiter — H-14 migration commit-time backstop regression suite (issue #77).

Proves the four moving parts of the migration backstop:

  * detection   — `_hooklib.is_migration_path` over the default glob set and the
                  `security-controls.md` extend/exclude declaration (OB-01..03).
  * producer    — `migration-pass.py` writes a complete candidate-bound marker
                  for exactly the staged migrations (OB-04).
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
import shutil
import subprocess
import sys
import tempfile
# Strip the live harness's project signal: project_root() trusts
# CLAUDE_PROJECT_DIR first, and a value leaking in from a Claude session
# would point every spawned hook at the real repo, not the fixture repo.
os.environ.pop("CLAUDE_PROJECT_DIR", None)


HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
HOOKS = os.path.join(REPO, "plugins", "ca", "hooks")
PRE_BASH = os.path.join(HOOKS, "pre-bash.py")
MIGRATION_PASS = os.path.join(HOOKS, "migration-pass.py")
GIT_ENFORCE = os.path.join(HOOKS, "git-enforce.py")
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


def run_pass(fixture, args=None, cwd=None, env=None):
    argv = [sys.executable, MIGRATION_PASS]
    argv.extend(["--root", fixture] if args is None else args)
    return sh(argv, cwd or fixture, env=env)


def run_precommit(fixture, env=None):
    return sh([sys.executable, GIT_ENFORCE, "pre-commit"], fixture, env=env)


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
    write(root, "migrations/0001_init.sql", MIG)
    git(["add", "migrations/0001_init.sql"], root)
    r = run_pass(root)
    check(r.returncode == 0, "OB-04", f"migration-pass.py exit={r.returncode} stderr={r.stderr[:200]!r}")
    mp = marker_path(root)
    recorded = ""
    if os.path.isfile(mp):
        with open(mp, encoding="utf-8") as f:
            recorded = f.read()
    check(content_digest(MIG) in recorded.split(), "OB-04",
          "marker must contain the migration's content digest")
    check(any(row.startswith("root-v1:") for row in recorded.split()), "OB-04",
          "marker must bind the reviewed worktree root")
    check(any(row.startswith("migration-candidate-v2:") for row in recorded.split()),
          "OB-04", "marker must bind the complete staged migration candidate")

    # The emitted explicit-root form works independently of process cwd.
    explicit = run_pass(root, cwd=base)
    check(explicit.returncode == 0, "OB-04",
          f"explicit --root producer must work from another cwd: {explicit.stderr[:200]!r}")

    # Invalid roots/argv fail closed and preserve an existing marker.
    before = recorded
    nested = os.path.join(root, "nested")
    os.makedirs(nested)
    for args in (["--root", nested], ["--root", os.path.join(root, "missing")],
                 ["--wrong", root], ["--root"]):
        refused = run_pass(root, args=args)
        with open(mp, encoding="utf-8") as stream:
            after = stream.read()
        check(refused.returncode == 1 and after == before, "OB-04",
              f"invalid producer argv must preserve marker: {args!r}")

    # #1037 analog: the independent migration review is staged-only. A nearby
    # untracked migration must not silently inherit that PASS.
    untracked = make_repo(base, "producer-untracked")
    write(untracked, "migrations/0002_hidden.sql", MIG2)
    result = run_pass(untracked)
    hidden_marker = ""
    if os.path.isfile(marker_path(untracked)):
        with open(marker_path(untracked), encoding="utf-8") as stream:
            hidden_marker = stream.read()
    check(result.returncode == 0 and content_digest(MIG2) not in hidden_marker.split(),
          "OB-04", "unreviewed untracked migration must not enter the marker")

    # The producer and both consumers must bind to the index, not to a newer
    # unstaged worktree edit. Otherwise a review of staged A can mint a marker
    # for unreviewed B, which later staging B could replay.
    divergent = make_repo(base, "producer-index-worktree-divergence")
    write(divergent, "migrations/0003_divergent.sql", MIG)
    git(["add", "migrations/0003_divergent.sql"], divergent)
    write(divergent, "migrations/0003_divergent.sql", MIG2)
    result = run_pass(divergent)
    divergent_marker = ""
    if os.path.isfile(marker_path(divergent)):
        with open(marker_path(divergent), encoding="utf-8") as stream:
            divergent_marker = stream.read()
    check(result.returncode == 0 and content_digest(MIG) in divergent_marker.split()
          and content_digest(MIG2) not in divergent_marker.split(), "OB-04",
          "producer must record staged migration bytes, not unstaged worktree bytes")
    staged_a = run_hook(divergent, "git commit -m wip")
    check(staged_a.returncode == 0 and "BLOCKED" not in staged_a.stderr, "OB-04",
          f"plain commit must compare the reviewed index candidate: {staged_a.stderr[:300]!r}")
    staged_a_backstop = run_precommit(divergent)
    check(staged_a_backstop.returncode == 0
          and "BLOCKED" not in staged_a_backstop.stderr, "OB-04",
          f"pre-commit must compare the reviewed index candidate: "
          f"{staged_a_backstop.stderr[:300]!r}")
    git(["add", "migrations/0003_divergent.sql"], divergent)
    staged_b = run_hook(divergent, "git commit -m wip")
    check(staged_b.returncode == 2 and "[H-14]" in staged_b.stderr, "OB-04",
          f"later staging unreviewed worktree bytes must re-block: {staged_b.stderr[:300]!r}")
    staged_b_backstop = run_precommit(divergent)
    check(staged_b_backstop.returncode == 1 and "[H-14]" in staged_b_backstop.stderr,
          "OB-04", f"pre-commit must re-block later staged bytes: "
          f"{staged_b_backstop.stderr[:300]!r}")

    unicode_path = make_repo(base, "producer-unicode-path")
    write(unicode_path, "migrations/é.sql", MIG)
    git(["add", "migrations/é.sql"], unicode_path)
    result = run_pass(unicode_path)
    unicode_marker = ""
    if os.path.isfile(marker_path(unicode_path)):
        with open(marker_path(unicode_path), encoding="utf-8") as stream:
            unicode_marker = stream.read()
    check(result.returncode == 0 and content_digest(MIG) in unicode_marker.split(),
          "OB-04", "C-quoted non-ASCII migration paths must stay in the candidate")
    unicode_guard = run_hook(unicode_path, "git commit -m wip")
    check(unicode_guard.returncode == 0 and "BLOCKED" not in unicode_guard.stderr,
          "OB-04", f"reviewed non-ASCII migration must be admitted: "
          f"{unicode_guard.stderr[:300]!r}")
    unicode_backstop = run_precommit(unicode_path)
    check(unicode_backstop.returncode == 0 and "BLOCKED" not in unicode_backstop.stderr,
          "OB-04", f"pre-commit must admit reviewed non-ASCII migration: "
          f"{unicode_backstop.stderr[:300]!r}")

    renamed = make_repo(base, "producer-migration-removal")
    write(renamed, "migrations/0004_remove.sql", MIG)
    git(["add", "migrations/0004_remove.sql"], renamed)
    git(["commit", "-q", "-m", "seed migration"], renamed)
    os.makedirs(os.path.join(renamed, "archive"))
    git(["mv", "migrations/0004_remove.sql", "archive/0004_remove.sql"], renamed)
    before = run_hook(renamed, "git commit -m wip")
    before_backstop = run_precommit(renamed)
    check(before.returncode == 2 and "[H-14]" in before.stderr, "OB-04",
          f"moving a migration out of scope must require review: {before.stderr[:300]!r}")
    check(before_backstop.returncode == 1 and "[H-14]" in before_backstop.stderr,
          "OB-04", f"pre-commit must require review for migration removal: "
          f"{before_backstop.stderr[:300]!r}")
    result = run_pass(renamed)
    after = run_hook(renamed, "git commit -m wip")
    after_backstop = run_precommit(renamed)
    check(result.returncode == 0 and after.returncode == 0
          and after_backstop.returncode == 0, "OB-04",
          "reviewed migration removal must bind its deletion and pass both consumers")

    # A deletion review must bind the deleted preimage, not merely the path and
    # a null final value. Otherwise a marker minted for deleting bytes A can be
    # replayed after HEAD moves to different bytes B at the same path.
    stale_delete = make_repo(base, "producer-stale-deletion-preimage")
    stale_rel = "migrations/0004_stale.sql"
    write(stale_delete, stale_rel, MIG)
    git(["add", stale_rel], stale_delete)
    git(["commit", "-q", "-m", "seed reviewed deletion"], stale_delete)
    git(["rm", "-q", stale_rel], stale_delete)
    reviewed = run_pass(stale_delete)
    alternate_index = os.path.join(stale_delete, ".git", "stale-head-index")
    stale_env = {**os.environ, "GIT_INDEX_FILE": alternate_index}
    read_tree = sh(["git", "read-tree", "HEAD"], stale_delete, env=stale_env)
    write(stale_delete, stale_rel, MIG2)
    stage_new_head = sh(["git", "add", "--", stale_rel], stale_delete,
                        env=stale_env)
    tree = sh(["git", "write-tree"], stale_delete, env=stale_env)
    parent = git(["rev-parse", "HEAD"], stale_delete).stdout.strip()
    replacement = sh(["git", "commit-tree", tree.stdout.strip(), "-p", parent,
                      "-m", "replace deleted preimage"], stale_delete,
                     env=stale_env)
    update = git(["update-ref", "HEAD", replacement.stdout.strip()], stale_delete)
    stale_backstop = run_precommit(stale_delete)
    check(all(part.returncode == 0 for part in (
              reviewed, read_tree, stage_new_head, tree, replacement, update))
          and stale_backstop.returncode == 1 and "[H-14]" in stale_backstop.stderr,
          "OB-04", "a reviewed deletion must re-block after its HEAD preimage changes: "
          f"{stale_backstop.stderr[:300]!r}")

    literal = make_repo(base, "producer-literal-pathspec")
    write(literal, "migrations/a1.sql", MIG2)
    git(["add", "migrations/a1.sql"], literal)
    git(["commit", "-q", "-m", "seed pathspec decoy"], literal)
    write(literal, "migrations/a[1].sql", MIG)
    git(["add", "migrations/a[1].sql"], literal)
    result = run_pass(literal)
    literal_marker = ""
    if os.path.isfile(marker_path(literal)):
        with open(marker_path(literal), encoding="utf-8") as stream:
            literal_marker = stream.read()
    check(result.returncode == 0 and content_digest(MIG) in literal_marker.split()
          and content_digest(MIG2) not in literal_marker.split(), "OB-04",
          "index reads must treat migration names as literal paths, not pathspecs")
    literal_guard = run_precommit(literal)
    check(literal_guard.returncode == 0 and "BLOCKED" not in literal_guard.stderr,
          "OB-04", f"literal metacharacter path must retain exact blob identity: "
          f"{literal_guard.stderr[:300]!r}")

    alternate = make_repo(base, "producer-alternate-index")
    write(alternate, "seed.txt", "seed\n")
    git(["add", "seed.txt"], alternate)
    git(["commit", "-q", "-m", "seed alternate index"], alternate)
    alternate_index = os.path.join(alternate, ".git", "alternate-index")
    shutil.copyfile(os.path.join(alternate, ".git", "index"), alternate_index)
    write(alternate, "migrations/0005_alt.sql", MIG)
    alternate_env = {**os.environ, "GIT_INDEX_FILE": alternate_index}
    staged = sh(["git", "add", "migrations/0005_alt.sql"], alternate,
                env=alternate_env)
    check(staged.returncode == 0, "OB-04", staged.stderr[:300])
    before = run_precommit(alternate, env=alternate_env)
    check(before.returncode == 1 and "[H-14]" in before.stderr, "OB-04",
          f"alternate-index migration must not bypass pre-commit: {before.stderr[:300]!r}")
    result = run_pass(alternate, env=alternate_env)
    after = run_precommit(alternate, env=alternate_env)
    check(result.returncode == 0 and after.returncode == 0, "OB-04",
          "producer and pre-commit must bind the same active alternate index")

    unreadable = make_repo(base, "producer-non-utf8")
    invalid_path = os.path.join(unreadable, "migrations", "invalid.sql")
    os.makedirs(os.path.dirname(invalid_path), exist_ok=True)
    with open(invalid_path, "wb") as stream:
        stream.write(b"CREATE TABLE bad_\xff (id int);\n")
    git(["add", "migrations/invalid.sql"], unreadable)
    refused = run_pass(unreadable)
    check(refused.returncode == 1 and not os.path.exists(marker_path(unreadable)),
          "OB-04", "non-UTF-8 staged migration must remain unreadable and unrecorded")

    # A symlink's index blob is only its target path, not the effective SQL.
    # Producer and both consumers must refuse added and typechanged symlinks.
    for label, typechange in (("added", False), ("typechanged", True)):
        linked = make_repo(base, f"producer-{label}-migration-symlink")
        rel = f"migrations/{label}.sql"
        if typechange:
            write(linked, rel, MIG)
            git(["add", rel], linked)
            git(["commit", "-q", "-m", "seed regular migration"], linked)
        target_blob = sh(["git", "hash-object", "-w", "--stdin"], linked,
                         input="../payload.sql\n")
        staged_link = sh([
            "git", "update-index", "--add", "--cacheinfo",
            f"120000,{target_blob.stdout.strip()},{rel}",
        ], linked)
        refused = run_pass(linked)
        hook_block = run_hook(linked, "git commit -m wip")
        backstop_block = run_precommit(linked)
        check(target_blob.returncode == 0 and staged_link.returncode == 0
              and refused.returncode == 1
              and hook_block.returncode == 2 and "[H-14]" in hook_block.stderr
              and backstop_block.returncode == 1 and "[H-14]" in backstop_block.stderr,
              "OB-04", f"{label} migration symlink must fail closed in producer and "
              f"both consumers: producer={refused.stderr[:160]!r} "
              f"hook={hook_block.stderr[:160]!r} backstop={backstop_block.stderr[:160]!r}")


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

    # OB-07b: the complete candidate binding is exact even where the legacy
    # per-file compatibility digest intentionally strips trailing whitespace.
    r3b = make_repo(base, "bs-whitespace-edit")
    write(r3b, "migrations/0001.sql", MIG)
    git(["add", "migrations/0001.sql"], r3b)
    run_pass(r3b)
    write(r3b, "migrations/0001.sql", MIG.rstrip("\n") + "  \n")
    git(["add", "migrations/0001.sql"], r3b)
    res = run_hook(r3b, "git commit -m wip")
    check(res.returncode == 2 and "complete candidate" in res.stderr, "OB-07b",
          f"trailing-whitespace edit must change exact candidate: {res.stderr[:300]!r}")

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

    # OB-C2: one of two migration digests is not a complete candidate PASS.
    r9 = make_repo(base, "bs-partial")
    write(r9, "migrations/0001.sql", MIG)
    write(r9, "migrations/0002.sql", MIG2)
    git(["add", "migrations/0001.sql", "migrations/0002.sql"], r9)
    from _hooklib import content_digest, worktree_marker_binding  # noqa: E402
    os.makedirs(os.path.dirname(marker_path(r9)), exist_ok=True)
    with open(marker_path(r9), "w", encoding="utf-8") as stream:
        stream.write(worktree_marker_binding(r9) + "\n" + content_digest(MIG) + "\n")
    res = run_hook(r9, "git commit -m wip")
    check(res.returncode == 2 and "migrations/0002.sql" in res.stderr, "OB-C2",
          f"partial marker must name and block the omitted migration: {res.stderr[:300]!r}")

    # OB-C3: `git -C <subdir>` uses the repository root for marker binding.
    r10 = make_repo(base, "bs-subdir")
    subdir = os.path.join(r10, "src")
    os.makedirs(subdir)
    write(r10, "migrations/0001.sql", MIG)
    git(["add", "migrations/0001.sql"], r10)
    run_pass(r10, cwd=subdir)
    command = f'git -C "{subdir}" commit -m wip'
    res = run_hook(r10, command)
    check(res.returncode == 0 and "BLOCKED" not in res.stderr, "OB-C3",
          f"subdir commit must accept root-bound PASS: {res.stderr[:300]!r}")

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
    # migration-pass.py must import only stdlib + shared dependency-free helpers.
    if os.path.isfile(MIGRATION_PASS):
        with open(MIGRATION_PASS, encoding="utf-8") as f:
            src = f.read()
        third_party = [ln for ln in src.splitlines()
                       if ln.startswith(("import ", "from "))
                       and "_hooklib" not in ln
                       and "_gitexec" not in ln
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
