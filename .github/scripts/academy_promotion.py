#!/usr/bin/env python3
"""Resolve and apply exact immutable Arbiter Academy release promotions."""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import NamedTuple


ACADEMY_REPOSITORY = "arbiterForge/arbiter-academy"
API_ROOT = f"https://api.github.com/repos/{ACADEMY_REPOSITORY}"
RELEASE_PATTERN = re.compile(r"^preview-(0|[1-9]\d*)\.(0|[1-9]\d*)$")
GIT_OBJECT_ID_PATTERN = re.compile(r"^[0-9a-f]{40}$")
RELEASE_LITERAL = re.compile(r'^const RELEASE = "(preview-[0-9]+\.[0-9]+)";$', re.MULTILINE)
TEST_RELEASE_LITERAL = re.compile(
    r'^\s*expect\(source\.release\)\.toBe\("(preview-[0-9]+\.[0-9]+)"\);$',
    re.MULTILINE,
)
FIXTURE_RELEASE_LITERAL = re.compile(
    r'^const fixtureRelease = "(preview-[0-9]+\.[0-9]+)";$',
    re.MULTILINE,
)
TEST_COMMIT_LITERAL = re.compile(
    r'^\s*expect\(source\.commit\)\.toBe\("([0-9a-f]{40})"\);$',
    re.MULTILINE,
)
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
RELEASES_PER_PAGE = 100
MAX_RELEASE_PAGES = 10


class PromotionError(ValueError):
    """The candidate cannot cross the Academy consumer boundary."""


class Candidate(NamedTuple):
    release: str
    tag_object: str
    commit: str


def parse_release(value: object) -> tuple[int, int]:
    if not isinstance(value, str):
        raise PromotionError("Academy release must be a string")
    match = RELEASE_PATTERN.fullmatch(value)
    if match is None:
        raise PromotionError("Academy release must be an exact preview-MAJOR.MINOR tag")
    return int(match.group(1)), int(match.group(2))


def _record(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise PromotionError(f"Academy {label} response must be an object")
    return value


def _string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise PromotionError(f"Academy manifest {field} must be a string array")
    return value


def validate_candidate(
    release_document: object,
    ref_document: object,
    tag_document: object,
    manifest_document: object,
    *,
    current_release: str,
    allow_current: bool = False,
) -> Candidate:
    """Bind the Release, annotated tag, peeled commit, and publication manifest."""
    release = _record(release_document, "Release")
    ref = _record(ref_document, "tag ref")
    tag = _record(tag_document, "annotated tag")
    manifest = _record(manifest_document, "publication manifest")
    candidate_release = release.get("tag_name")
    candidate_version = parse_release(candidate_release)
    current_version = parse_release(current_release)
    if candidate_version < current_version or (candidate_version == current_version and not allow_current):
        raise PromotionError("Academy candidate must advance the current release")
    if release.get("draft") is not False or release.get("prerelease") is not False:
        raise PromotionError("Academy candidate must be a published stable Release")
    if release.get("immutable") is not True:
        raise PromotionError("Academy candidate Release must be immutable")

    ref_object = _record(ref.get("object"), "tag ref object")
    if ref.get("ref") != f"refs/tags/{candidate_release}" or ref_object.get("type") != "tag":
        raise PromotionError("Academy candidate must resolve through an annotated tag ref")
    tag_object = ref_object.get("sha")
    if not isinstance(tag_object, str) or GIT_OBJECT_ID_PATTERN.fullmatch(tag_object) is None:
        raise PromotionError("Academy annotated tag object must be an exact Git object ID")

    peeled = _record(tag.get("object"), "peeled tag object")
    if tag.get("tag") != candidate_release or peeled.get("type") != "commit":
        raise PromotionError("Academy annotated tag must peel to the matching commit")
    commit = peeled.get("sha")
    if not isinstance(commit, str) or GIT_OBJECT_ID_PATTERN.fullmatch(commit) is None:
        raise PromotionError("Academy peeled commit must be an exact Git object ID")

    available = _string_list(manifest.get("available_labs"), "available_labs")
    runnable = _string_list(manifest.get("runnable_labs"), "runnable_labs")
    guided = _string_list(manifest.get("guided_labs"), "guided_labs")
    if manifest.get("release") != candidate_release or not available:
        raise PromotionError("Academy publication manifest must identify the non-empty candidate release")
    if available != runnable or available != guided or len(available) != len(set(available)):
        raise PromotionError("Academy publication inventories must be identical, ordered, and unique")
    return Candidate(candidate_release, tag_object, commit)


def _read_json(url: str) -> object:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "codeArbiter-Academy-promotion/1",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.geturl() != url:
                raise PromotionError("Academy API request redirected unexpectedly")
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except (OSError, urllib.error.URLError) as error:
        raise PromotionError(f"Academy API request failed: {error}") from error
    if len(payload) > MAX_RESPONSE_BYTES:
        raise PromotionError("Academy API response exceeded the bounded size")
    try:
        return json.loads(payload)
    except (UnicodeError, ValueError) as error:
        raise PromotionError("Academy API response was not valid JSON") from error


def _api_path(path: str, *, query: dict[str, str] | None = None) -> str:
    url = f"{API_ROOT}/{path}"
    return f"{url}?{urllib.parse.urlencode(query)}" if query else url


def _latest_preview_release() -> dict:
    candidate: tuple[tuple[int, int], dict] | None = None
    for page in range(1, MAX_RELEASE_PAGES + 1):
        value = _read_json(
            _api_path(
                "releases",
                query={"per_page": str(RELEASES_PER_PAGE), "page": str(page)},
            )
        )
        if not isinstance(value, list):
            raise PromotionError("Academy Releases response must be an array")
        for item in value:
            release = _record(item, "Release list item")
            if release.get("draft") is not False or release.get("prerelease") is not False:
                continue
            try:
                version = parse_release(release.get("tag_name"))
            except PromotionError:
                continue
            if candidate is None or version > candidate[0]:
                candidate = version, release
        if len(value) < RELEASES_PER_PAGE:
            break
    else:
        raise PromotionError("Academy Release inventory exceeded the bounded page limit")
    if candidate is None:
        raise PromotionError("Academy repository has no published Preview Release")
    return candidate[1]


def resolve_candidate(
    requested: str | None,
    current_release: str,
    *,
    allow_current: bool = False,
) -> Candidate:
    """Resolve one candidate exclusively from bounded public GitHub API reads."""
    if requested:
        parse_release(requested)
        release_url = _api_path(f"releases/tags/{urllib.parse.quote(requested, safe='')}")
        release = _record(_read_json(release_url), "Release")
    else:
        release = _latest_preview_release()
    candidate_release = release.get("tag_name")
    parse_release(candidate_release)
    encoded = urllib.parse.quote(candidate_release, safe="")
    ref = _record(_read_json(_api_path(f"git/ref/tags/{encoded}")), "tag ref")
    ref_object = _record(ref.get("object"), "tag ref object")
    tag_object = ref_object.get("sha")
    if not isinstance(tag_object, str) or GIT_OBJECT_ID_PATTERN.fullmatch(tag_object) is None:
        raise PromotionError("Academy tag ref returned no exact object identity")
    tag = _read_json(_api_path(f"git/tags/{tag_object}"))
    tag_record = _record(tag, "annotated tag")
    peeled = _record(tag_record.get("object"), "peeled tag object")
    commit = peeled.get("sha")
    if not isinstance(commit, str) or GIT_OBJECT_ID_PATTERN.fullmatch(commit) is None:
        raise PromotionError("Academy tag returned no exact peeled commit")
    content = _record(
        _read_json(
            _api_path(
                f"contents/academy/publication/{encoded}.json",
                query={"ref": commit},
            )
        ),
        "manifest content",
    )
    if content.get("encoding") != "base64" or not isinstance(content.get("content"), str):
        raise PromotionError("Academy manifest content must be base64 encoded")
    try:
        encoded_content = "".join(content["content"].split())
        manifest = json.loads(base64.b64decode(encoded_content, validate=True))
    except (ValueError, UnicodeError) as error:
        raise PromotionError("Academy publication manifest content is invalid") from error
    return validate_candidate(
        release,
        ref,
        tag,
        manifest,
        current_release=current_release,
        allow_current=allow_current,
    )


def current_release(root: Path) -> str:
    source = root / "site" / "scripts" / "academy-source.ts"
    matches = RELEASE_LITERAL.findall(source.read_text(encoding="utf-8"))
    if len(matches) != 1:
        raise PromotionError("Academy consumer must contain one canonical release literal")
    parse_release(matches[0])
    return matches[0]


def apply_candidate(root: Path, candidate: Candidate, *, expected_current: str) -> list[Path]:
    """Apply only the single declared consumer release literal."""
    source = root / "site" / "scripts" / "academy-source.ts"
    text = source.read_text(encoding="utf-8")
    matches = list(RELEASE_LITERAL.finditer(text))
    if len(matches) != 1:
        raise PromotionError("Academy consumer must contain one canonical release literal")
    previous = matches[0].group(1)
    if previous != expected_current or parse_release(previous) >= parse_release(candidate.release):
        raise PromotionError("Academy promotion baseline changed or does not advance")
    updated = text[: matches[0].start(1)] + candidate.release + text[matches[0].end(1) :]

    contract = root / "site" / "scripts" / "academy-source.test.ts"
    contract_text = contract.read_text(encoding="utf-8")
    release_matches = list(TEST_RELEASE_LITERAL.finditer(contract_text))
    fixture_matches = list(FIXTURE_RELEASE_LITERAL.finditer(contract_text))
    commit_matches = list(TEST_COMMIT_LITERAL.finditer(contract_text))
    if len(release_matches) != 1 or release_matches[0].group(1) != expected_current:
        raise PromotionError("Academy exact-pin test must contain the expected release once")
    if len(fixture_matches) != 1 or fixture_matches[0].group(1) != expected_current:
        raise PromotionError("Academy source fixture must contain the expected release once")
    if len(commit_matches) != 1:
        raise PromotionError("Academy exact-pin test must contain one source commit")
    replacements = [
        (release_matches[0].start(1), release_matches[0].end(1), candidate.release),
        (fixture_matches[0].start(1), fixture_matches[0].end(1), candidate.release),
        (commit_matches[0].start(1), commit_matches[0].end(1), candidate.commit),
    ]
    for start, end, replacement in sorted(replacements, reverse=True):
        contract_text = contract_text[:start] + replacement + contract_text[end:]
    source.write_text(updated, encoding="utf-8", newline="")
    contract.write_text(contract_text, encoding="utf-8", newline="")
    return [Path("site/scripts/academy-source.ts"), Path("site/scripts/academy-source.test.ts")]


def _verify_submodule(root: Path, expected: str) -> None:
    try:
        actual = subprocess.check_output(
            ["git", "-C", str(root / "academy-source"), "rev-parse", "HEAD"],
            text=True,
            encoding="utf-8",
        ).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise PromotionError("Academy submodule commit is unavailable") from error
    if actual != expected:
        raise PromotionError(f"Academy submodule must be checked out at {expected}")


def _verify_current_source(root: Path, candidate: Candidate) -> None:
    _verify_submodule(root, candidate.commit)
    contract = root / "site" / "scripts" / "academy-source.test.ts"
    matches = TEST_COMMIT_LITERAL.findall(contract.read_text(encoding="utf-8"))
    if matches != [candidate.commit]:
        raise PromotionError("Academy exact-pin contract must match the current peeled commit")


def _write_outputs(path: Path, candidate: Candidate, baseline: str, *, up_to_date: bool) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as output:
        output.write(f"release={candidate.release}\n")
        output.write(f"tag_object={candidate.tag_object}\n")
        output.write(f"commit={candidate.commit}\n")
        output.write(f"current_release={baseline}\n")
        output.write(f"up_to_date={str(up_to_date).lower()}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    resolve = subparsers.add_parser("resolve")
    resolve.add_argument("--candidate")
    resolve.add_argument("--current-release")
    resolve.add_argument("--output", type=Path)
    apply = subparsers.add_parser("apply")
    apply.add_argument("--release", required=True)
    apply.add_argument("--tag-object", required=True)
    apply.add_argument("--commit", required=True)
    apply.add_argument("--expected-current", required=True)
    apply.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        if args.command == "resolve":
            baseline = args.current_release or current_release(Path.cwd())
            candidate = resolve_candidate(args.candidate, baseline, allow_current=True)
            up_to_date = candidate.release == baseline
            if up_to_date:
                _verify_current_source(Path.cwd(), candidate)
            if args.output:
                _write_outputs(args.output, candidate, baseline, up_to_date=up_to_date)
            print(json.dumps(candidate._asdict(), sort_keys=True))
        else:
            candidate = Candidate(args.release, args.tag_object, args.commit)
            parse_release(candidate.release)
            if (GIT_OBJECT_ID_PATTERN.fullmatch(candidate.tag_object) is None or
                    GIT_OBJECT_ID_PATTERN.fullmatch(candidate.commit) is None):
                raise PromotionError("Academy apply identities must be exact Git object IDs")
            _verify_submodule(args.root, candidate.commit)
            for changed in apply_candidate(args.root, candidate, expected_current=args.expected_current):
                print(changed.as_posix())
    except (OSError, PromotionError) as error:
        print(f"academy promotion refused: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
