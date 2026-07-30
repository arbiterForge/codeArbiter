#!/usr/bin/env python3
# codeArbiter - repo-relative path primitives. The dependency FLOOR of the
# guard-classifier modules (issue #321).
#
# Two lines of code in its own module on purpose. Every path classifier -
# the H-05/H-11 protected-path set, the H-09b/H-10b sensitive scan, the
# H-14/H-15/H-16 scope globs - normalizes separators before matching, so
# whichever of them is extracted from _hooklib first would otherwise have to
# either import from _hooklib (a cycle, since _hooklib re-exports it) or carry
# its own copy (the drift _hooklib exists to prevent).
#
# So it goes BELOW all of them. Nothing here may import from a sibling core
# module; that is what makes it a floor rather than another god module.
#
# `repo_rel` joined in slice 2 on the same test: it references no other module
# symbol, and both the protected-path classifiers and the activation helpers
# need it. Its docstring is the canonical statement of why a LEXICAL relpath is
# wrong here - the 8.3 / symlink divergence that also produced #539 and #541.


import os


def norm_path(p):
    """Normalize separators so guard regexes match Windows backslash paths."""
    return (p or "").replace("\\", "/")


def repo_rel(fpath, root):
    """Repo-relative POSIX path for `fpath`, or "" when it lies outside `root`.

    realpath BOTH sides before relpath: `git rev-parse --show-toplevel`
    (project_root) canonicalizes symlinks and 8.3 short names, but the
    `file_path` in a hook payload may not — so on macOS (TMPDIR `/var` ->
    `/private/var`) and Windows (`RUNNER~1` -> `runneradmin`) the two name the
    same repo via divergent forms. A purely lexical relpath on those forms
    yields a bogus `..`-prefixed path, which silently suppressed every
    path-scoped reminder (#125 CI: H-12/H-15/H-16/H-13 dropped on macOS +
    Windows runners while ubuntu passed)."""
    if not fpath:
        return ""
    rel = os.path.relpath(os.path.realpath(fpath), os.path.realpath(root))
    rel = rel.replace(os.sep, "/")
    return "" if rel == ".." or rel.startswith("../") else rel
