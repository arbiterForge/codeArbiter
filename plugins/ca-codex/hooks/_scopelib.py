#!/usr/bin/env python3
# codeArbiter - path SCOPE detection: which repo paths are database migrations
# (H-14), CI/CD workflow files (H-15), and deployment / IaC manifests (H-16),
# including the project's own overrides declared in security-controls.md.
#
# Extracted from _hooklib (issue #321, architecture-002) as slice 3. The
# cleanest seam of the four, measured the same way as the others: this cluster
# references NOTHING from the rest of _hooklib, and NOTHING in the rest of
# _hooklib references it. Its only dependency is norm_path, already on the
# _pathnorm floor. Zero edges in either direction.
#
# WHY THESE BELONG TOGETHER: they are one mechanism wearing three labels. All
# three predicates are `path_in_globs(rel, root, <DEFAULTS>, <DECL_RE>)` over the
# same glob compiler, the same security-controls.md reader, and the same two
# caches - so a change to how a project DECLARES a scope (the `<scope>-paths`
# lines) lands in one place instead of three. The defaults differ; the machinery
# does not.
#
# The caches are deliberate and mtime-keyed: every Write/Edit hook calls these,
# and re-reading plus re-compiling security-controls.md per call showed up as
# real latency on a large repo.
#
# _hooklib re-exports every public name below, so no consumer changed and the
# pre-existing hook suites prove parity without moving.

from __future__ import annotations

import os
import re

from _pathnorm import norm_path


# Migration-path detection (H-14). Shared by migration-pass.py (the producer)
# and pre-bash.py (the backstop) so the two never drift on what counts as a
# migration. Default globs cover the common ORM/migration ecosystems; a project
# extends or narrows the set via a `migration-paths` block in
# security-controls.md. `**` matches any run of path segments (including none);
# `*`/`?` stay within one segment.
MIGRATION_DEFAULT_GLOBS = (
    "**/migrations/**",
    "**/migrate/**",
    "**/db/migrate/**",
    "**/alembic/versions/*.py",
    "**/prisma/migrations/**",
)
_MIG_DECL_RE = re.compile(
    r"<!--\s*migration-paths\s*-->(.*?)<!--\s*/migration-paths\s*-->", re.S | re.I)

# CI/CD workflow detection (H-15, #73). Advisory only — no commit gate; the
# defaults cover the common CI ecosystems and a project extends/narrows them via
# a `ci-paths` block in security-controls.md (same `+`/`-` grammar as migrations).
CI_DEFAULT_GLOBS = (
    ".github/workflows/**",
    ".circleci/**",
    "**/.gitlab-ci.yml",
    "**/Jenkinsfile",
    "**/azure-pipelines.yml",
    "**/bitbucket-pipelines.yml",
)
_CI_DECL_RE = re.compile(
    r"<!--\s*ci-paths\s*-->(.*?)<!--\s*/ci-paths\s*-->", re.S | re.I)

# Deployment / IaC detection (H-16, #73). Advisory only. Defaults cover the
# common container/orchestration/IaC manifests; extend/narrow via a
# `deploy-paths` block in security-controls.md.
DEPLOY_DEFAULT_GLOBS = (
    "**/Dockerfile",
    "**/Dockerfile.*",
    "**/docker-compose*.yml",
    "**/docker-compose*.yaml",
    "**/*.tf",
    "**/*.tfvars",
    "**/k8s/**",
    "**/helm/**",
    "**/kustomization.yaml",
    "**/kustomization.yml",
    "**/Procfile",
)
_DEPLOY_DECL_RE = re.compile(
    r"<!--\s*deploy-paths\s*-->(.*?)<!--\s*/deploy-paths\s*-->", re.S | re.I)


def _glob_to_re(glob):
    """Compile a forward-slash glob into a full-path regex. `**/` is an optional
    run of leading segments, `**` is any chars, `*`/`?` stay within a segment."""
    g = norm_path(glob)
    out, i = ["^"], 0
    while i < len(g):
        if g[i:i + 3] == "**/":
            out.append("(?:.*/)?")
            i += 3
        elif g[i:i + 2] == "**":
            out.append(".*")
            i += 2
        elif g[i] == "*":
            out.append("[^/]*")
            i += 1
        elif g[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(g[i]))
            i += 1
    out.append("$")
    return re.compile("".join(out))


# performance-002: the DEFAULT glob tuples are module constants, so compile each
# to a regex ONCE at module load instead of per glob per path_in_globs() call.
# A single post-write-edit.py invocation otherwise recompiled up to 44 regexes
# (5 migration + 6 CI + 11 deploy x the calls that hit them). These compiled
# tuples line up 1:1 with their string tuples; the matcher uses them directly
# for the defaults and only compiles the per-controls custom globs on demand.
_MIGRATION_DEFAULT_RES = tuple(_glob_to_re(g) for g in MIGRATION_DEFAULT_GLOBS)
_CI_DEFAULT_RES = tuple(_glob_to_re(g) for g in CI_DEFAULT_GLOBS)
_DEPLOY_DEFAULT_RES = tuple(_glob_to_re(g) for g in DEPLOY_DEFAULT_GLOBS)

# Map each default string tuple to its precompiled regex tuple, so the matcher
# can look up the right precompiled set from the `defaults` argument alone
# (preserving the existing public signatures of scope_globs/path_in_globs).
_DEFAULT_RES_BY_GLOBS = {
    MIGRATION_DEFAULT_GLOBS: _MIGRATION_DEFAULT_RES,
    CI_DEFAULT_GLOBS: _CI_DEFAULT_RES,
    DEPLOY_DEFAULT_GLOBS: _DEPLOY_DEFAULT_RES,
}


# performance-001: hooks are EPHEMERAL single-shot processes (one invocation
# then exit), so a module-level cache lives for exactly one invocation — there
# is NO cross-invocation persistence. Within that one process, scope_globs reads
# security-controls.md on every is_migration_path/is_ci_path/is_deploy_path call
# (2-3 reads per hook). Cache the controls text keyed by (root, mtime) so a hit
# skips the read; the mtime key keeps it correct even on an intra-process change
# (the file is re-read when its mtime moves), and keys the absent-file state too.
_CONTROLS_CACHE = {}


def _controls_mtime(root):
    """mtime of `root`'s security-controls.md, or None when absent/unreadable.
    The cache key — distinct mtimes (and the None absent-state) bust the cache."""
    try:
        return os.path.getmtime(
            os.path.join(root, ".codearbiter", "security-controls.md"))
    except Exception:  # noqa: BLE001 — no controls file -> None (defaults only)
        return None


def _read_controls(root):
    """The repo's security-controls.md text, or "" when absent/unreadable.

    Process-cached keyed by (root, mtime): a cache hit skips the file read, and
    the mtime component invalidates the entry whenever the file changes (or is
    created/removed), so verdicts are unchanged. Single-shot hook process only —
    no cross-invocation persistence."""
    mtime = _controls_mtime(root)
    key = (root, mtime)
    cached = _CONTROLS_CACHE.get(key)
    if cached is not None:
        return cached[0]
    try:
        with open(os.path.join(root, ".codearbiter", "security-controls.md"),
                  encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:  # noqa: BLE001 — no controls file -> defaults only
        text = ""
    # Cache the text AND the compiled custom globs per scope (filled lazily by
    # scope_globs) under the same mtime key, so a custom-glob set compiles at
    # most once per (root, mtime) instead of once per path_in_globs() call.
    _CONTROLS_CACHE[key] = (text, {})
    return text


def _custom_re_cache(root):
    """The per-(root, mtime) dict that caches compiled custom-glob regexes for
    this controls revision. Populated lazily by scope_globs. Returns a throwaway
    dict only if the controls entry is somehow missing (defensive; the read
    above always seeds it first)."""
    entry = _CONTROLS_CACHE.get((root, _controls_mtime(root)))
    return entry[1] if entry is not None else {}


def scope_globs(root, defaults, decl_re):
    """(includes, excludes) for one scope category: the built-in `defaults` plus
    any declaration block matched by `decl_re` in security-controls.md
    (`+ glob` extends, `- glob` excludes). Shared by every path-glob scope
    detector (migration/CI/deploy) so they never drift on the grammar."""
    includes, excludes = list(defaults), []
    m = decl_re.search(_read_controls(root))
    if not m:
        return includes, excludes
    for ln in m.group(1).splitlines():
        ln = ln.strip()
        if ln.startswith("+ "):
            includes.append(ln[2:].strip())
        elif ln.startswith("- "):
            excludes.append(ln[2:].strip())
    return includes, excludes


def _scope_res(root, defaults, decl_re):
    """(include_res, exclude_res) as compiled regexes for one scope category.
    Default globs use the module-precompiled regexes (zero per-call compilation);
    any per-controls custom globs are compiled at most once per (root, mtime) and
    cached. Equivalent to compiling each string from scope_globs() — verdicts are
    identical; only the regex work is amortised."""
    includes, excludes = scope_globs(root, defaults, decl_re)
    default_res = _DEFAULT_RES_BY_GLOBS.get(defaults)
    if default_res is None:
        # Unknown defaults set (no precompiled tuple) — compile everything.
        return ([_glob_to_re(g) for g in includes],
                [_glob_to_re(g) for g in excludes])
    # Defaults occupy the head of `includes` (scope_globs builds list(defaults)
    # then appends customs); reuse the precompiled regexes for that head and
    # compile only the trailing customs. Excludes are all custom.
    custom_cache = _custom_re_cache(root)

    def _compile(g):
        r = custom_cache.get(g)
        if r is None:
            r = _glob_to_re(g)
            custom_cache[g] = r
        return r

    n = len(defaults)
    include_res = list(default_res) + [_compile(g) for g in includes[n:]]
    exclude_res = [_compile(g) for g in excludes]
    return include_res, exclude_res


def path_in_globs(rel, root, defaults, decl_re):
    """True iff `rel` (a repo-relative path) matches an include glob and no
    exclude glob for the given scope category. Excludes win — the false-positive
    escape hatch. The one matcher behind is_migration_path/is_ci_path/
    is_deploy_path."""
    rel = norm_path(rel).lstrip("/")
    include_res, exclude_res = _scope_res(root, defaults, decl_re)
    if any(r.match(rel) for r in exclude_res):
        return False
    return any(r.match(rel) for r in include_res)


def migration_globs(root):
    """(includes, excludes) for migration detection: defaults plus any
    `migration-paths` declaration in security-controls.md."""
    return scope_globs(root, MIGRATION_DEFAULT_GLOBS, _MIG_DECL_RE)


def is_migration_path(rel, root):
    """True iff `rel` is a database migration (H-14). Excludes win — the
    escape hatch for a project whose `migrations/` dir holds non-DB files."""
    return path_in_globs(rel, root, MIGRATION_DEFAULT_GLOBS, _MIG_DECL_RE)


def is_ci_path(rel, root):
    """True iff `rel` is a CI/CD workflow file (H-15, advisory)."""
    return path_in_globs(rel, root, CI_DEFAULT_GLOBS, _CI_DECL_RE)


def is_deploy_path(rel, root):
    """True iff `rel` is a deployment / IaC manifest (H-16, advisory)."""
    return path_in_globs(rel, root, DEPLOY_DEFAULT_GLOBS, _DEPLOY_DECL_RE)
