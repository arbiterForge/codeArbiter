#!/usr/bin/env python3
# codeArbiter — canonical-core sync tool (ADR-0011, codex-support M1).
#
# core/pysrc/ holds the CANONICAL copy of every host-neutral hook python file
# (all shared _*lib.py modules, hostapi.py, and every entry script). Each
# plugin vendors byte-identical copies in its own hooks/ directory — plugins
# must stay self-contained installable payloads, so they cannot import out of
# tree — and this tool is what keeps the vendored copies from drifting.
#
# Deliberately NOT synced: each plugin's _host.py (the per-plugin host
# definition — the one file that is SUPPOSED to differ between plugins) and
# anything that exists only in the plugin (hooks.json, tests/, __pycache__).
#
# Modes:
#   python tools/sync-core.py            # write: core/pysrc/*.py -> each plugin
#   python tools/sync-core.py --check    # verify: exit 1 listing any vendored
#                                        # copy that differs (CI parity gate)
#
# Comparison and copy are BYTE-level (files are read/written in binary), so
# LF endings in core are preserved exactly in the vendored copies and a CRLF
# drift is a reported difference, never silently normalized. Stdlib only
# (ADR-0004).

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(REPO, "core", "pysrc")

# Every plugin hooks dir that vendors the core.
PLUGINS = (
    os.path.join("plugins", "ca", "hooks"),
    os.path.join("plugins", "ca-codex", "hooks"),
)

# Per-plugin files that must never be synced from core even if a same-named
# file appears there by mistake.
EXCLUDE = frozenset({"_host.py"})


def core_files():
    """Sorted basenames of the canonical .py files under core/pysrc/."""
    try:
        names = os.listdir(CORE)
    except OSError as e:
        sys.stderr.write(f"sync-core: cannot list {CORE}: {e}\n")
        sys.exit(2)
    return sorted(n for n in names
                  if n.endswith(".py") and n not in EXCLUDE
                  and os.path.isfile(os.path.join(CORE, n)))


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    check = "--check" in argv
    unknown = [a for a in argv if a != "--check"]
    if unknown:
        sys.stderr.write(f"sync-core: unknown argument(s): {' '.join(unknown)}\n"
                         "usage: python tools/sync-core.py [--check]\n")
        return 2

    names = core_files()
    if not names:
        sys.stderr.write(f"sync-core: no .py files found under {CORE}\n")
        return 2

    drifted = []   # (plugin-relative path) whose vendored bytes differ / are absent
    written = 0
    for rel_hooks in PLUGINS:
        hooks_dir = os.path.join(REPO, rel_hooks)
        for name in names:
            src = os.path.join(CORE, name)
            dst = os.path.join(hooks_dir, name)
            try:
                src_bytes = read_bytes(src)
            except OSError as e:
                sys.stderr.write(f"sync-core: cannot read canonical source {src}: {e}\n")
                return 1
            try:
                same = read_bytes(dst) == src_bytes
            except OSError:
                same = False  # absent vendored copy counts as drift
            if same:
                continue
            if check:
                drifted.append(os.path.join(rel_hooks, name).replace(os.sep, "/"))
                continue
            try:
                with open(dst, "wb") as f:  # binary: byte-exact, LF preserved
                    f.write(src_bytes)
            except OSError as e:
                sys.stderr.write(f"sync-core: cannot write vendored copy {dst}: {e}\n")
                return 1
            written += 1

    if check:
        if drifted:
            print("sync-core --check: vendored copies differ from core/pysrc/:")
            for p in drifted:
                print(f"  {p}")
            print("run `python tools/sync-core.py` to re-vendor from core.")
            return 1
        print(f"sync-core --check: OK ({len(names)} core file(s) x "
              f"{len(PLUGINS)} plugin(s), all byte-identical)")
        return 0

    print(f"sync-core: {written} file(s) written, "
          f"{len(names) * len(PLUGINS) - written} already current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
