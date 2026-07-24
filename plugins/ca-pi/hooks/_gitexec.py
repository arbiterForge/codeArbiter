#!/usr/bin/env python3
# codeArbiter — optional absolute executable identities for shared Git helpers.
#
# Claude and Codex retain their historical bare-executable behavior when the
# variables are absent. The Pi bridge supplies validated absolute identities;
# every shared Git subprocess then consumes the same identity, and the managed
# Git hook carries it into the later hook process.
#
# Public API:
#   trusted_git_executable() -> str|None     validated CODEARBITER_GIT_EXECUTABLE, or
#                                             None if unset
#   trusted_python_executable() -> str|None  validated CODEARBITER_PYTHON_EXECUTABLE, or
#                                             None if unset
#   git_executable() -> str                  trusted_git_executable() or the bare "git"
#                                             fallback

import os


GIT_ENV = "CODEARBITER_GIT_EXECUTABLE"
PYTHON_ENV = "CODEARBITER_PYTHON_EXECUTABLE"


def _trusted_environment_path(name):
    value = os.environ.get(name)
    if not value:
        return None
    if not os.path.isabs(value):
        raise RuntimeError(f"{name} must be absolute")
    canonical = os.path.realpath(value)
    if not os.path.isfile(canonical):
        raise RuntimeError(f"{name} is unavailable")
    return canonical


def trusted_git_executable():
    return _trusted_environment_path(GIT_ENV)


def trusted_python_executable():
    return _trusted_environment_path(PYTHON_ENV)


def git_executable():
    return trusted_git_executable() or "git"
