#!/usr/bin/env python3
"""Per-target release planner: observe what is already published, then say
what is left to do.

Every plugin (ca, ca-codex, ca-pi, ca-sandbox) releases independently. A
release job never carries state between runs; it re-observes the remote tag
and the draft-inclusive Release list and acts only on what is missing. That
makes a re-run the recovery path for any half-finished publication.

The only hard refusals here protect consumers and history:
  * an existing tag that names a different commit (the version is spent);
  * more than one Release claiming the same tag (ambiguous state).

Subcommands:
  eligible  --version V --prefix P --tags FILE --releases FILE
            -> prints true|false. True when the manifest is a strict SemVer
               advance over the series' last tag, or when its own tag exists
               but its Release is not yet published (finish a partial run).
  plan      --tag T --source SHA --remote-tag FILE --releases FILE [--asset N ...]
            [--output FILE]
            -> key=value lines: tag=create|present, release=create|draft|published,
               release-id=<id or empty>, missing-assets=<space separated>.
  receipt   --target --host --tag --version --source --package-file --package-sha256
            --channel --channel-ref --release-state --output
            -> writes the per-target receipt describing what was observed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _releaselib  # noqa: E402

SHA = re.compile(r"[0-9a-f]{40}")


def peel_remote_tag(remote_text: str, tag: str) -> str:
    """Return the commit an `ls-remote` listing says `tag` names, or ''."""
    direct = peeled = ""
    for line in remote_text.splitlines():
        fields = line.split()
        if len(fields) != 2:
            continue
        sha, ref = fields
        if ref == f"refs/tags/{tag}^{{}}":
            peeled = sha
        elif ref == f"refs/tags/{tag}":
            direct = sha
    return peeled or direct


def releases_for(pages: list, tag: str) -> list[dict]:
    flat = [release for page in pages for release in (page if isinstance(page, list) else [page])]
    return [release for release in flat if isinstance(release, dict) and release.get("tag_name") == tag]


def release_state(pages: list, tag: str) -> tuple[str, dict | None]:
    found = releases_for(pages, tag)
    if len(found) > 1:
        raise ValueError(f"{len(found)} Releases claim {tag}; delete the duplicates, then re-run")
    if not found:
        return "create", None
    return ("draft" if found[0].get("draft") else "published"), found[0]


def eligible(version: str, prefix: str, tags: list[str], pages: list) -> bool:
    last = _releaselib.last_tag_select(tags, prefix)
    if last == _releaselib.NONE_SENTINEL:
        return True
    if _releaselib.semver_greater(version, _releaselib._bare_version(last)):
        return True
    tag = prefix + version
    return tag in tags and release_state(pages, tag)[0] != "published"


def plan(*, tag: str, source: str, remote_tag: str, pages: list,
         assets: list[str]) -> dict[str, str]:
    if SHA.fullmatch(source) is None:
        raise ValueError("source must be a full lowercase commit id")
    tagged = peel_remote_tag(remote_tag, tag)
    if tagged and tagged != source:
        raise ValueError(
            f"{tag} already names {tagged}, not {source}: this version is spent. "
            "Bump the plugin version and merge again.")
    state, release = release_state(pages, tag)
    present = {asset.get("name") for asset in (release or {}).get("assets") or []
               if isinstance(asset, dict)}
    return {
        "tag": "present" if tagged else "create",
        "release": state,
        "release-id": str(release["id"]) if release else "",
        "missing-assets": " ".join(name for name in assets if name not in present),
    }


def _load(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    e = sub.add_parser("eligible")
    e.add_argument("--version", required=True); e.add_argument("--prefix", required=True)
    e.add_argument("--tags", required=True); e.add_argument("--releases", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--tag", required=True); p.add_argument("--source", required=True)
    p.add_argument("--remote-tag", required=True); p.add_argument("--releases", required=True)
    p.add_argument("--asset", action="append", default=[]); p.add_argument("--output")
    r = sub.add_parser("receipt")
    for name in ("target", "host", "tag", "version", "source", "package-file",
                 "package-sha256", "channel", "channel-ref", "release-state", "output"):
        r.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "eligible":
            tags = Path(args.tags).read_text(encoding="utf-8").split()
            print("true" if eligible(args.version, args.prefix, tags, _load(args.releases)) else "false")
            return 0
        if args.command == "plan":
            result = plan(tag=args.tag, source=args.source,
                          remote_tag=Path(args.remote_tag).read_text(encoding="utf-8"),
                          pages=_load(args.releases), assets=args.asset)
            lines = "".join(f"{key}={value}\n" for key, value in result.items())
            if args.output:
                with open(args.output, "a", encoding="utf-8", newline="\n") as stream:
                    stream.write(lines)
            sys.stdout.write(lines)
            return 0
        receipt = {
            "format": "codearbiter.target-publication/0.1.0",
            "target": args.target, "host": args.host, "tag": args.tag,
            "version": args.version, "source_commit": args.source,
            "package_file": args.package_file, "package_sha256": args.package_sha256,
            "channel": args.channel, "channel_ref": args.channel_ref,
            "release_state": args.release_state,
        }
        with open(args.output, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(receipt, stream, indent=2, sort_keys=True); stream.write("\n")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
