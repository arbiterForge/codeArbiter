#!/usr/bin/env python3
"""Per-target release planner: observe what is already published, then say
what is left to do.

Every plugin (ca, ca-codex, ca-pi, ca-sandbox) releases independently. A
release job never carries state between runs; it re-observes the remote tag
and the draft-inclusive Release list and acts only on what is missing. That
makes a re-run the recovery path for any half-finished publication.

One completion model (`observe`) owns what "published" means for a target:
the version's tag names the release commit, its Release is public, and every
required asset (the exact package, then the final publication receipt) is
fully uploaded with the expected digest where one is known. `eligible` and
`plan` are projections of that one observation, so the preflight, the
per-job recheck and the composite's plan cannot disagree about whether work
remains. A public Release that is missing only its receipt is incomplete:
it stays eligible and its plan schedules only the receipt.

The only hard refusals here protect consumers and history:
  * an existing tag that names a different commit (the version is spent);
  * more than one Release claiming the same tag (ambiguous state);
  * a present asset whose digest or upload state conflicts (never replaced);
  * malformed observation input (never read as "absent").

Subcommands:
  eligible  --version V --prefix P --releases FILE (--tags FILE | --tag-refs FILE)
            [--target T] [--source SHA]
            -> prints true|false. True when the manifest is a strict SemVer
               advance over the series' last tag, or when its own tag exists
               at this source but its publication is not complete. A tag at a
               different commit whose publication is complete is false (that
               source owns the version); one that is incomplete is an error
               naming the owning commit.
  plan      --tag T --source SHA --remote-tag FILE --releases FILE
            (--target T --version V [--package-file F --package-sha256 D] | --asset N ...)
            [--output FILE]
            -> key=value lines: tag=create|present, release=create|draft|published,
               release-id=<id or empty>, missing-assets=<space separated>,
               complete=true|false, effects=<ordered remaining effects>.
  required-assets --target T --version V
            -> the asset names a complete publication of T carries.
  receipt   --target --host --tag --version --source --package-file --package-sha256
            --channel --channel-ref --release-state --output
            -> writes the per-target receipt describing what was observed.
  verify-receipt --receipt FILE --target --host --tag --version --source
            --package-file --package-sha256 --channel [--channel-ref REF]
            -> exit 0 only when an already-attached receipt names exactly this
               publication; any other content is refused, never accepted by name.
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
SHA256 = re.compile(r"[0-9a-f]{64}")
RECEIPT_ASSET = "codearbiter-publication.json"
RECEIPT_FORMAT = "codearbiter.target-publication/0.1.0"
# target -> package host. The package file name mirrors the CI package owner
# (tools/build-host-packages.py `filenames`); a test pins the two together and
# the composite refuses a cohort file that differs from this name.
TARGET_HOSTS = {"ca": "claude", "ca-codex": "codex", "ca-pi": "pi", "ca-sandbox": None}
PACKAGE_ASSET = {
    "claude": "codearbiter-ca-{version}.tar.gz",
    "codex": "codearbiter-ca-codex-{version}.tar.gz",
    "pi": "arbiterforge-ca-pi-{version}.tgz",
}
CHANNELS = {"claude": "ca-marketplace", "codex": "ca-codex-marketplace"}
# Remaining publication effects, in the composite's execution order.
EFFECT_ORDER = ("tag", "draft", "asset", "channel", "publish", "receipt")


class Conflict(ValueError):
    """Observed remote state that no automatic retry may resolve."""


def package_asset_name(host: str, version: str) -> str:
    if host not in PACKAGE_ASSET:
        raise ValueError(f"unknown package host {host!r}")
    return PACKAGE_ASSET[host].format(version=version)


def required_assets(target: str, version: str) -> list[str]:
    if target not in TARGET_HOSTS:
        raise ValueError(f"unknown release target {target!r}")
    host = TARGET_HOSTS[target]
    return ([package_asset_name(host, version)] if host else []) + [RECEIPT_ASSET]


def channel_name(host: str, version: str) -> str:
    if host == "pi":
        return f"npm:@arbiterforge/ca-pi@{version}"
    return CHANNELS.get(host, "none")


def tag_refs(remote_text: str) -> dict[str, str]:
    """Map each tag in an ls-remote/for-each-ref listing to the commit it names."""
    direct: dict[str, str] = {}
    peeled: dict[str, str] = {}
    for line in remote_text.splitlines():
        fields = line.split()
        if len(fields) != 2:
            continue
        sha, ref = fields
        if not ref.startswith("refs/tags/"):
            continue
        if SHA.fullmatch(sha) is None:
            raise ValueError(f"tag listing names {ref} with a malformed object id")
        name = ref[len("refs/tags/"):]
        if name.endswith("^{}"):
            peeled[name[:-3]] = sha
        else:
            direct[name] = sha
    return {name: peeled.get(name, sha) for name, sha in direct.items()}


def peel_remote_tag(remote_text: str, tag: str) -> str:
    """Return the commit an `ls-remote` listing says `tag` names, or ''."""
    return tag_refs(remote_text).get(tag, "")


def _flatten(pages) -> list:
    if not isinstance(pages, list):
        raise ValueError("Release listing must be a JSON array of pages")
    flat = []
    for page in pages:
        flat.extend(page if isinstance(page, list) else [page])
    return flat


def releases_for(pages: list, tag: str) -> list[dict]:
    return [release for release in _flatten(pages)
            if isinstance(release, dict) and release.get("tag_name") == tag]


def release_state(pages: list, tag: str) -> tuple[str, dict | None]:
    found = releases_for(pages, tag)
    if len(found) > 1:
        raise Conflict(f"{len(found)} Releases claim {tag}; delete the duplicates, then re-run")
    if not found:
        return "create", None
    draft = found[0].get("draft")
    if not isinstance(draft, bool):
        raise ValueError(f"Release for {tag} has no boolean draft state")
    return ("draft" if draft else "published"), found[0]


def _asset_observations(release: dict | None, tag: str, assets: list[str],
                        digests: dict[str, str]) -> list[str]:
    """Return the required asset names still missing; refuse conflicting ones."""
    present: dict[str, dict] = {}
    for asset in (release or {}).get("assets") or []:
        if not isinstance(asset, dict) or not isinstance(asset.get("name"), str):
            raise ValueError(f"Release for {tag} lists a malformed asset")
        if asset["name"] in present:
            raise Conflict(f"Release for {tag} carries {asset['name']} twice")
        present[asset["name"]] = asset
    missing = []
    for name in assets:
        asset = present.get(name)
        if asset is None:
            missing.append(name)
            continue
        state = asset.get("state", "uploaded")
        if state != "uploaded":
            raise Conflict(
                f"{name} on {tag} is in upload state {state!r}; an interrupted upload is "
                "never overwritten automatically. Inspect it, remove only that incomplete "
                "asset, then re-run")
        expected = digests.get(name)
        observed = asset.get("digest")
        if expected and observed and observed != f"sha256:{expected}":
            raise Conflict(
                f"{name} on {tag} reads back {observed}, not sha256:{expected}; a "
                "conflicting published asset is never replaced. Publish a new version")
    return missing


def observe(*, tag: str, source: str | None, tagged: str, pages: list,
            assets: list[str], digests: dict[str, str] | None = None) -> dict[str, object]:
    """The one per-target completion model.

    `tagged` is the commit the version tag names ('' when absent). A tag at
    another commit is reported as `foreign`; callers decide whether that is a
    refusal (plan) or another source's finished release (eligible).
    """
    if source is not None and SHA.fullmatch(source) is None:
        raise ValueError("source must be a full lowercase commit id")
    digests = dict(digests or {})
    for name, value in digests.items():
        if SHA256.fullmatch(value) is None:
            raise ValueError(f"expected digest for {name} must be a lowercase sha256")
    state, release = release_state(pages, tag)
    missing = _asset_observations(release, tag, assets, digests)
    if not tagged:
        tag_state = "absent"
    elif source is None or tagged == source:
        tag_state = "exact"
    else:
        tag_state = "foreign"
    if tag_state == "absent" and state == "published":
        # GitHub cannot hold a public Release without its tag; a listing that
        # says otherwise is stale or partial, so it is not evidence of absence.
        raise Conflict(f"Release for {tag} is public but the tag listing lacks {tag}; "
                       "re-observe before any retry")
    complete = tag_state != "absent" and state == "published" and not missing
    packaged = any(name != RECEIPT_ASSET for name in assets)
    effects: list[str] = []
    if tag_state == "absent":
        effects.append("tag")
    if state == "create":
        effects.append("draft")
    package_missing = any(name != RECEIPT_ASSET for name in missing)
    if state != "published":
        # A draft (or absent) Release has not finished: the asset upload,
        # channel promotion and public transition are each observe-then-act.
        # A packaged host always has a channel (marketplace branch or npm).
        effects += (["asset", "channel"] if packaged else []) + ["publish"]
    elif package_missing:
        # Public already, so its channel was promoted first (the composite
        # orders channel before the public transition); restore only the
        # exact verified bytes and never repeat the channel effect.
        effects.append("asset")
    if RECEIPT_ASSET in missing:
        effects.append("receipt")
    return {
        "tag": tag_state, "tagged": tagged, "release": state,
        "release-id": str(release["id"]) if release else "",
        "missing-assets": missing, "complete": complete,
        "effects": [effect for effect in EFFECT_ORDER if effect in effects],
    }


def describe(observation: dict[str, object], tag: str) -> str:
    missing = " ".join(observation["missing-assets"]) or "none"
    effects = " ".join(observation["effects"]) or "none"
    tagged = observation["tagged"] or "absent"
    return (f"{tag}: tag={observation['tag']} ({tagged}) release={observation['release']} "
            f"missing-assets={missing} complete={str(observation['complete']).lower()} "
            f"remaining-effects={effects}")


def eligible(version: str, prefix: str, tags: list[str], pages: list, *,
             refs: dict[str, str] | None = None, source: str | None = None,
             assets: list[str] | None = None, log=None) -> bool:
    tag = prefix + version
    if refs is not None:
        tags = sorted(refs)
    if tag not in tags:
        last = _releaselib.last_tag_select(tags, prefix)
        return (last == _releaselib.NONE_SENTINEL
                or _releaselib.semver_greater(version, _releaselib._bare_version(last)))
    if refs is None:
        # A bare name list cannot say which commit the tag names; the
        # composite's plan still refuses a spent tag before any effect.
        tagged, source = "unpeeled", None
    else:
        tagged = refs[tag]
    observation = observe(tag=tag, source=source, tagged=tagged, pages=pages,
                          assets=assets if assets is not None else [RECEIPT_ASSET])
    if log:
        log(describe(observation, tag))
    if observation["tag"] == "foreign":
        if observation["complete"]:
            return False  # another source owns and finished this version
        raise Conflict(
            f"{tag} names {tagged}, not {source}, and its publication is incomplete "
            f"(remaining: {' '.join(observation['effects'])}). Recover it by re-running the "
            f"original release run for {tagged} while its CI artifacts are retained; this "
            "source cannot complete another commit's publication")
    return not observation["complete"]


def plan(*, tag: str, source: str, remote_tag: str, pages: list,
         assets: list[str], digests: dict[str, str] | None = None) -> dict[str, str]:
    if SHA.fullmatch(source) is None:
        raise ValueError("source must be a full lowercase commit id")
    tagged = peel_remote_tag(remote_tag, tag)
    if tagged and tagged != source:
        raise Conflict(
            f"{tag} already names {tagged}, not {source}: this version is spent. "
            "Bump the plugin version and merge again.")
    observation = observe(tag=tag, source=source, tagged=tagged, pages=pages,
                          assets=assets, digests=digests)
    return {
        "tag": "present" if tagged else "create",
        "release": str(observation["release"]),
        "release-id": str(observation["release-id"]),
        "missing-assets": " ".join(observation["missing-assets"]),
        "complete": "true" if observation["complete"] else "false",
        "effects": " ".join(observation["effects"]),
    }


def verify_receipt(receipt: dict, expected: dict[str, str]) -> None:
    if not isinstance(receipt, dict) or receipt.get("format") != RECEIPT_FORMAT:
        raise Conflict("attached publication receipt has an unknown format")
    for key, value in expected.items():
        if receipt.get(key) != value:
            raise Conflict(
                f"attached publication receipt says {key}={receipt.get(key)!r}, but this "
                f"publication is {value!r}; a conflicting receipt is never replaced")
    if receipt.get("release_state") != "published":
        raise Conflict("attached publication receipt does not record a published Release")


def _load(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _digest_args(values: list[str]) -> dict[str, str]:
    digests = {}
    for value in values:
        name, sep, digest = value.partition("=")
        if not sep or not name:
            raise ValueError(f"--asset-digest needs NAME=SHA256, got {value!r}")
        digests[name] = digest
    return digests


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    e = sub.add_parser("eligible")
    e.add_argument("--version", required=True); e.add_argument("--prefix", required=True)
    e.add_argument("--releases", required=True)
    listing = e.add_mutually_exclusive_group(required=True)
    listing.add_argument("--tags"); listing.add_argument("--tag-refs")
    e.add_argument("--target"); e.add_argument("--source")
    p = sub.add_parser("plan")
    p.add_argument("--tag", required=True); p.add_argument("--source", required=True)
    p.add_argument("--remote-tag", required=True); p.add_argument("--releases", required=True)
    p.add_argument("--target"); p.add_argument("--version")
    p.add_argument("--package-file"); p.add_argument("--package-sha256")
    p.add_argument("--asset", action="append", default=[])
    p.add_argument("--asset-digest", action="append", default=[])
    p.add_argument("--output")
    a = sub.add_parser("required-assets")
    a.add_argument("--target", required=True); a.add_argument("--version", required=True)
    r = sub.add_parser("receipt")
    for name in ("target", "host", "tag", "version", "source", "package-file",
                 "package-sha256", "channel", "channel-ref", "release-state", "output"):
        r.add_argument("--" + name, required=True)
    v = sub.add_parser("verify-receipt")
    for name in ("receipt", "target", "host", "tag", "version", "source", "package-file",
                 "package-sha256", "channel"):
        v.add_argument("--" + name, required=True)
    v.add_argument("--channel-ref")
    args = parser.parse_args(argv)
    try:
        if args.command == "eligible":
            pages = _load(args.releases)
            assets = (required_assets(args.target, args.version) if args.target
                      else [RECEIPT_ASSET])
            if args.tag_refs is not None:
                refs = tag_refs(Path(args.tag_refs).read_text(encoding="utf-8"))
                go = eligible(args.version, args.prefix, [], pages, refs=refs,
                              source=args.source, assets=assets,
                              log=lambda line: print(line, file=sys.stderr))
            else:
                tags = Path(args.tags).read_text(encoding="utf-8").split()
                go = eligible(args.version, args.prefix, tags, pages, source=args.source,
                              assets=assets, log=lambda line: print(line, file=sys.stderr))
            print("true" if go else "false")
            return 0
        if args.command == "plan":
            digests = _digest_args(args.asset_digest)
            if args.target:
                if not args.version:
                    raise ValueError("plan --target needs --version")
                assets = required_assets(args.target, args.version) + args.asset
                host = TARGET_HOSTS[args.target]
                if host:
                    expected = package_asset_name(host, args.version)
                    if args.package_file != expected:
                        raise Conflict(
                            f"verified package file {args.package_file!r} is not the "
                            f"declared {args.target} asset {expected!r}")
                    if args.package_sha256:
                        digests[expected] = args.package_sha256
            else:
                assets = args.asset
            result = plan(tag=args.tag, source=args.source,
                          remote_tag=Path(args.remote_tag).read_text(encoding="utf-8"),
                          pages=_load(args.releases), assets=assets, digests=digests)
            lines = "".join(f"{key}={value}\n" for key, value in result.items())
            if args.output:
                with open(args.output, "a", encoding="utf-8", newline="\n") as stream:
                    stream.write(lines)
            sys.stdout.write(lines)
            return 0
        if args.command == "required-assets":
            print(" ".join(required_assets(args.target, args.version)))
            return 0
        if args.command == "verify-receipt":
            expected = {
                "target": args.target, "host": args.host, "tag": args.tag,
                "version": args.version, "source_commit": args.source,
                "package_file": args.package_file, "package_sha256": args.package_sha256,
                "channel": args.channel,
            }
            if args.channel_ref is not None:
                expected["channel_ref"] = args.channel_ref
            verify_receipt(_load(args.receipt), expected)
            print(f"attached receipt names {args.tag} at {args.source}")
            return 0
        receipt = {
            "format": RECEIPT_FORMAT,
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
