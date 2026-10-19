#!/usr/bin/env python3
# codeArbiter — reject stray control bytes in tracked text files.
"""Fail when a tracked text file contains an ASCII control byte.

Tooling that writes files can turn an escape such as `\\b`, `\\x01` or `\\n`
inside a string literal into the raw byte. The result still parses, so tests
and review miss it: a regex holding a literal backspace matches nothing, and a
"\\x01" placeholder becomes an invisible character. Tab, line feed and carriage
return are allowed. A file with a NUL byte in its first 8 KiB is treated as
binary and skipped. Write an intended control character as an escape.

Usage: check_control_bytes.py [ROOT] [--paths PATH ...]
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

ALLOWED = {0x09, 0x0A, 0x0D}
CONTROL = frozenset(set(range(0x20)) - ALLOWED | {0x7F})
BINARY_PROBE = 8192


def tracked_files(root: Path) -> list[str]:
    """Regular tracked files. Gitlinks (160000) and symlinks (120000) carry
    no text of their own here."""
    out = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--stage"],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    paths = set()
    # Git emits pathnames verbatim with -z, and they need not be UTF-8.
    # surrogateescape round-trips any bytes back to the POSIX filesystem name.
    for record in out.stdout.split(b"\0"):
        meta, _, rel = record.partition(b"\t")
        if rel and meta.split()[0] in (b"100644", b"100755"):
            paths.add(rel.decode("utf-8", "surrogateescape"))
    return sorted(paths)


def findings(root: Path, rel: str) -> list[str]:
    path = root / rel
    try:
        data = path.read_bytes()
    except (FileNotFoundError, UnicodeEncodeError):
        return []  # deleted in the work tree, or a name this OS cannot hold
    if b"\0" in data[:BINARY_PROBE]:
        return []
    found = []
    line, col = 1, 1
    for byte in data:
        if byte in CONTROL:
            found.append(f"{rel}:{line}:{col}: control byte 0x{byte:02x}")
        if byte == 0x0A:
            line, col = line + 1, 1
        else:
            col += 1
    return found


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--paths", nargs="*", help="check these paths instead of git ls-files")
    args = parser.parse_args(argv)
    root = Path(args.root)
    paths = args.paths if args.paths is not None else tracked_files(root)
    problems = [f for rel in paths for f in findings(root, rel)]
    if problems:
        sys.stderr.write("control-byte check FAILED (write the character as an escape):\n")
        for problem in problems[:200]:
            sys.stderr.write(f"  {problem}\n")
        if len(problems) > 200:
            sys.stderr.write(f"  ... and {len(problems) - 200} more\n")
        return 1
    print(f"control-byte check passed ({len(paths)} file(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
