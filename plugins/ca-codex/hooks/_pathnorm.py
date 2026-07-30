#!/usr/bin/env python3
# codeArbiter - repo-relative path normalization. The dependency FLOOR of the
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


def norm_path(p):
    """Normalize separators so guard regexes match Windows backslash paths."""
    return (p or "").replace("\\", "/")
