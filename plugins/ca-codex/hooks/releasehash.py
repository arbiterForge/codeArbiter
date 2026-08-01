#!/usr/bin/env python3
# codeArbiter — pre-tag content-hash confirmation (A-2.10).
#
# A row's `pre-tag` commands are operator-authored shell that `/ca:release`
# EXECUTES before composing a tag. `.codearbiter/release-targets.md` is
# marker-gated under H-22, so changing those commands already costs a fresh
# authoring marker — but that gate is about WRITING the file. Nothing made the
# release lane notice that the commands it is about to run are not the ones
# anybody last looked at.
#
# This closes that: the lane records a hash of a row's pre-tag content when an
# operator confirms it, and refuses to run silently once that hash changes. A
# changed hash is not a block — it is a re-confirmation prompt. Per ADR-0010
# this is COOPERATIVE-grade: an agent that skips the check is not stopped by
# the operating system, only by the lane's own discipline. Stated plainly here
# rather than implied, because a reader who mistakes it for enforcement would
# over-trust it.
#
# WHY A PYTHON PRODUCER, not a shell redirect. H-19 (`pre-write.py`) blocks
# Write-tool writes to `.codearbiter/.markers/*` outright, and
# `_bashguardlib`'s companion rule blocks shell redirects and interpreter
# invocations that name a gate marker. Both exist because a hand-forged marker
# is a forged gate pass. The confirmation record therefore needs a sanctioned
# producer, which is this module.
#
# Ships to every governance plugin byte-identically via tools/sync-core.py, so
# it carries NO fact about any particular repository: the target name, the
# commands, and the project root all arrive as arguments or from the declared
# file.
#
# Public API:
#   pre_tag_digest(commands) -> str
#   confirmation_path(root, target) -> str
#   read_confirmation(root, target) -> str | None
#   record_confirmation(root, target, digest) -> str
#   confirmation_state(root, target, commands) -> str
#   main(argv) -> int
#
# CLI:
#   releasehash.py digest <target>    print the current pre-tag digest
#   releasehash.py check <target>     exit 0 confirmed, 1 changed, 2 never
#                                     confirmed, 3/4 declared-file states
#   releasehash.py record <target>    mint the confirmation (the sanctioned
#                                     producer; run only after an operator has
#                                     actually READ the commands)

from __future__ import annotations

import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _releaselib  # noqa: E402 — sibling module, flat hooks/ layout

DIGEST_VERSION = "1"
MARKER_DIRNAME = ".markers"
CONFIRMED_PREFIX = "pre-tag-confirmed-"

CONFIRMED = "confirmed"
CHANGED = "changed"
NEVER = "never-confirmed"
NO_COMMANDS = "no-commands"


def pre_tag_digest(commands):
    """A stable digest of a row's `pre-tag` command list.

    ORDER-SENSITIVE on purpose. The commands run in declared order and a
    reordering can change what a release checks — a check that ran after a
    rebuild is not the same check as one that ran before it — so swapping
    two entries must invalidate the confirmation, not preserve it.

    Each command is length-prefixed before joining, so `["ab", "c"]` and
    `["a", "bc"]` cannot collide into one digest. Versioned, so a future
    change to this construction cannot be mistaken for a content change
    by an old recorded value.

    Pure and non-raising: a non-list, or a list with non-string members,
    degrades to the digest of an empty list rather than raising inside a
    release lane.
    """
    if not isinstance(commands, (list, tuple)):
        commands = []
    parts = [DIGEST_VERSION]
    for command in commands:
        if not isinstance(command, str):
            continue
        parts.append(f"{len(command)}:{command}")
    joined = "\n".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def confirmation_path(root, target):
    """Where `target`'s confirmation is recorded.

    One marker PER TARGET, never a shared one: a multi-target repository
    confirming `ca`'s commands must not thereby confirm `ca-pi`'s.
    """
    safe = "".join(ch if (ch.isalnum() or ch in "-_") else "_" for ch in str(target))
    return os.path.join(root, ".codearbiter", MARKER_DIRNAME,
                        CONFIRMED_PREFIX + safe)


def read_confirmation(root, target):
    """The recorded digest for `target`, or None when never confirmed.

    Never raises: an unreadable or empty marker reads as "never confirmed",
    which is the conservative answer — it prompts rather than admits.
    """
    try:
        with open(confirmation_path(root, target), encoding="utf-8") as handle:
            value = handle.read().strip()
    except (OSError, UnicodeError):
        return None
    return value or None


def record_confirmation(root, target, digest):
    """Mint the confirmation marker. Returns the path written.

    THE SANCTIONED PRODUCER. Call this only after an operator has actually
    read the commands — recording a digest nobody looked at converts this
    from a confirmation into a rubber stamp, which is worse than not
    having it, because the lane then reports "confirmed" about content no
    human has seen.
    """
    path = confirmation_path(root, target)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(str(digest).strip() + "\n")
    return path


def confirmation_state(root, target, commands):
    """One of `confirmed` / `changed` / `never-confirmed` / `no-commands`.

    `no-commands` is deliberately distinct from `confirmed`: a row that
    declares no pre-tag commands has nothing to confirm, and reporting it
    as confirmed would claim an operator approved something that does not
    exist. The lane treats both as "proceed", but only one of them is a
    statement about human review.
    """
    if not commands:
        return NO_COMMANDS
    recorded = read_confirmation(root, target)
    if recorded is None:
        return NEVER
    return CONFIRMED if recorded == pre_tag_digest(commands) else CHANGED


def _row_commands(target, targets_path=None):
    path = targets_path or _releaselib.default_targets_path()
    rows = _releaselib.load_targets(path)
    row = next((r for r in rows if r["target"] == target), None)
    if row is None:
        return None
    return row.get("pre_tag") or []


def main(argv=None):
    """CLI. See the module header for subcommands and exit codes."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2 or argv[0] not in ("digest", "check", "record"):
        sys.stderr.write("usage: releasehash.py {digest|check|record} <target>\n")
        return 2
    command, target = argv
    root = os.path.dirname(os.path.dirname(_releaselib.default_targets_path()))

    try:
        commands = _row_commands(target)
    except _releaselib.ReleaseTargetsError as error:
        sys.stderr.write(f"{type(error).__name__}: {error}\n")
        return _releaselib._targets_error_exit_code(error)
    if commands is None:
        sys.stderr.write(f"unknown release target: {target}\n")
        return 2

    if command == "digest":
        print(pre_tag_digest(commands))
        return 0

    if command == "record":
        path = record_confirmation(root, target, pre_tag_digest(commands))
        print(f"recorded pre-tag confirmation for {target}: {path}")
        return 0

    state = confirmation_state(root, target, commands)
    print(state)
    if state in (CONFIRMED, NO_COMMANDS):
        return 0
    if state == CHANGED:
        sys.stderr.write(
            f"releasehash: {target}'s pre-tag commands have CHANGED since they "
            "were last confirmed. Read them, and re-confirm with "
            f"`releasehash.py record {target}` before releasing. These commands "
            "are executed by the release lane, so a change nobody has read is "
            "the case this check exists for.\n")
        return 1
    sys.stderr.write(
        f"releasehash: {target}'s pre-tag commands have never been confirmed. "
        f"Read them, then run `releasehash.py record {target}`.\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
