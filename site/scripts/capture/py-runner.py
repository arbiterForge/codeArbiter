#!/usr/bin/env python3
"""Run one repository script as `python <script> <args>` and record what it loaded.

    py-runner.py <side-file> <repo-root> <entry-script> [args...]

The capture harness runs every captured tool through this file so it can report
the repository modules the interpreter actually imported, not just the entry
script. The entry runs under the same conditions as a direct invocation:
`__main__`, its own directory first on `sys.path`, `sys.argv[0]` as its path, and
the interpreter's own exit-status rules for `SystemExit`. After the run, the
repository files in `sys.modules` (plus the entry) are written to <side-file> as
a JSON list of repository-relative POSIX paths.

Limit: modules a tool loads in a child process, or loads by file path without
registering them in `sys.modules`, are not seen. The harness hashes only what
this reports, so a capture of such a tool must name those files itself.
"""

import json
import os
import runpy
import sys
import traceback


def _inside(path, root):
    path_norm = os.path.normcase(path)
    root_norm = os.path.normcase(root)
    return path_norm.startswith(root_norm.rstrip(os.sep) + os.sep)


def _loaded_repository_files(repo_root, entry, runner):
    found = {entry}
    for module in list(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if not filename or not str(filename).endswith(".py"):
            continue
        real = os.path.realpath(filename)
        if real != runner and _inside(real, repo_root):
            found.add(real)
    return sorted(os.path.relpath(path, repo_root).replace(os.sep, "/") for path in found)


def _exit_status(error):
    """The status the interpreter itself would give `SystemExit`, printing a message as it does."""
    code = error.code
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    print(code, file=sys.stderr)
    return 1


def main():
    side_file, repo_root, entry, *arguments = sys.argv[1:]
    repo_root = os.path.realpath(repo_root)
    entry = os.path.realpath(entry)
    runner = os.path.realpath(__file__)
    sys.argv = [entry, *arguments]
    sys.path[0] = os.path.dirname(entry)  # what `python <entry>` puts first, instead of this file's directory
    status = 0
    try:
        runpy.run_path(entry, run_name="__main__")
    except SystemExit as error:
        status = _exit_status(error)
    except BaseException:  # the tool crashed: show it as the interpreter would, and fail
        traceback.print_exc()
        status = 1
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        with open(side_file, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(_loaded_repository_files(repo_root, entry, runner), handle)
    return status


if __name__ == "__main__":
    sys.exit(main())
