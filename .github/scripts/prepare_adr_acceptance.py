#!/usr/bin/env python3
"""Create a content-bound local packet for ADR acceptance commit leg one."""

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "core", "pysrc"))

import adr_lifecycle as al
from _gitexec import root_bound_git_env


SCHEMA = "adr-acceptance-pending/v1"
MAX_LIFETIME = dt.timedelta(hours=4)
ADR_PREFIX = ".codearbiter/decisions/"
LOG_REL = ADR_PREFIX + "decision-log.md"


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _git(root, *args):
    return subprocess.run(
        ["git", "--no-replace-objects", "-C", root, *args],
        capture_output=True, check=False,
        env=root_bound_git_env(),
    )


def _git_text(root, *args):
    result = _git(root, *args)
    if result.returncode != 0:
        raise ValueError("git %s failed" % " ".join(args))
    return result.stdout.decode("utf-8").strip()


def _index_blob(root, path):
    result = _git(root, "show", ":%s" % path)
    if result.returncode != 0:
        raise ValueError("staged path is unavailable: %s" % path)
    return result.stdout


def _head_blob(root, path):
    result = _git(root, "show", "HEAD:%s" % path)
    return result.stdout if result.returncode == 0 else None


def transition_body(blob):
    """Bind every ADR byte except its two recognized status-value tokens."""
    return al.immutable_body(blob)


def packet_path(root):
    git_dir = os.path.normcase(os.path.realpath(
        _git_text(root, "rev-parse", "--absolute-git-dir")))
    admin_dir = os.path.abspath(os.path.join(git_dir, "codearbiter"))
    if os.path.commonpath((git_dir, admin_dir)) != git_dir:
        raise ValueError("packet directory escapes the worktree Git administration directory")
    if os.path.lexists(admin_dir):
        if (not os.path.isdir(admin_dir) or os.path.islink(admin_dir) or
                os.path.normcase(os.path.realpath(admin_dir)) != os.path.normcase(admin_dir)):
            raise ValueError("packet directory is redirected")
    return os.path.join(admin_dir, "adr-acceptance-pending.json")


def repository_identity(root):
    return {
        "root": os.path.normcase(os.path.realpath(root)),
        "git_dir": os.path.normcase(os.path.realpath(_git_text(
            root, "rev-parse", "--absolute-git-dir"))),
        "common_dir": os.path.normcase(os.path.realpath(_git_text(
            root, "rev-parse", "--path-format=absolute", "--git-common-dir"))),
    }


def _install_packet(destination, packet):
    """Atomically install packet without replacing any concurrent writer."""
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    if (os.path.islink(os.path.dirname(destination)) or
            os.path.normcase(os.path.realpath(os.path.dirname(destination))) !=
            os.path.normcase(os.path.dirname(destination))):
        raise ValueError("packet directory is redirected")
    descriptor, temporary = tempfile.mkstemp(
        prefix="adr-acceptance-", suffix=".json", dir=os.path.dirname(destination))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(packet, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError as exc:
            raise FileExistsError(
                "pending acceptance packet already exists; clear it explicitly") from exc
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_packet(root, adr, obligations, reviewed_by, reviewed_at, valid_until):
    """Validate inputs and atomically write one ephemeral acceptance packet."""
    if not al.ADR_RE.fullmatch(adr + ".md"):
        raise ValueError("invalid ADR stem")
    if (not isinstance(reviewed_by, list) or not reviewed_by or
            any(not isinstance(item, str) or not item.strip() for item in reviewed_by)):
        raise ValueError("independent reviewer evidence is required")
    reviewed_moment = al._parse_time(reviewed_at)
    expiry = al._parse_time(valid_until)
    if reviewed_moment >= expiry or expiry - reviewed_moment > MAX_LIFETIME:
        raise ValueError("packet lifetime must be positive and no more than four hours")

    adr_rel = ADR_PREFIX + adr + ".md"
    adr_blob = _index_blob(root, adr_rel)
    if al.parse_adr(adr_blob)["status"] != "accepted":
        raise ValueError("staged ADR is not accepted")
    log_blob = _index_blob(root, LOG_REL)
    base_log = _head_blob(root, LOG_REL)
    if base_log is None:
        raise ValueError("HEAD decision log is unavailable")

    synthetic = {
        "schema": "adr-lifecycle/v1", "event": "acceptance", "adr": adr,
        "recorded_at": reviewed_at, "source_commit": "0" * 40,
        "blob_sha256": _sha(adr_blob),
        "body_sha256": _sha(al.immutable_body(adr_blob)),
        "obligations": obligations,
        "obligations_sha256": al.obligation_set_digest(obligations),
        "obligations_sealed": True,
    }
    errors = al.validate_events([synthetic], {adr: adr_blob})
    if errors:
        raise ValueError("invalid sealed obligations: %s" % "; ".join(errors))

    packet = {
        "schema": SCHEMA,
        "repository": repository_identity(root),
        "head": _git_text(root, "rev-parse", "HEAD"),
        "index_tree": _git_text(root, "write-tree"),
        "adr": adr,
        "adr_blob_sha256": _sha(adr_blob),
        "transition_body_sha256": _sha(transition_body(adr_blob)),
        "decision_log_base_sha256": _sha(base_log),
        "decision_log_index_sha256": _sha(log_blob),
        "obligations": obligations,
        "obligations_sha256": synthetic["obligations_sha256"],
        "reviewed_by": reviewed_by,
        "reviewed_at": reviewed_at,
        "valid_until": valid_until,
    }
    destination = packet_path(root)
    _install_packet(destination, packet)
    return destination


def read_packet(root):
    try:
        path = packet_path(root)
        if os.path.islink(path) or not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as handle:
            packet = json.load(handle)
    except (OSError, UnicodeError, ValueError):
        return None
    return packet if isinstance(packet, dict) else None


def clear_packet(root):
    """Remove only this worktree's ephemeral packet, when present."""
    path = packet_path(root)
    if os.path.lexists(path) and (os.path.islink(path) or not os.path.isfile(path)):
        raise ValueError("pending acceptance packet is not a regular file")
    try:
        os.unlink(path)
    except FileNotFoundError:
        return False
    return True


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=REPO)
    parser.add_argument("--clear", action="store_true")
    parser.add_argument("--adr")
    parser.add_argument("--obligations-json")
    parser.add_argument("--reviewed-by", action="append")
    parser.add_argument("--reviewed-at")
    parser.add_argument("--valid-until")
    args = parser.parse_args(argv)
    if args.clear:
        print("cleared" if clear_packet(args.root) else "already absent")
        return 0
    for field in ("adr", "obligations_json", "reviewed_by", "reviewed_at", "valid_until"):
        if not getattr(args, field):
            parser.error("--%s is required unless --clear is used" % field.replace("_", "-"))
    with open(args.obligations_json, encoding="utf-8") as handle:
        obligations = json.load(handle)
    print(write_packet(
        args.root, args.adr, obligations, args.reviewed_by,
        args.reviewed_at, args.valid_until))
    return 0


if __name__ == "__main__":
    sys.exit(main())
