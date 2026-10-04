#!/usr/bin/env python3
# codeArbiter — collect and union native Go statement profiles without relabelling metrics.
"""Offline, stdlib-only tooling for core/artifacts, not a qualification receipt.

collect --module-root ROOT --output NEW_DIR [--expect-platform OS/ARCH]
        [--extra-profile TEXT_PROFILE ...]
summarize --module-root ROOT --input DIR ... [--expect-platform OS/ARCH ...]
          [--minimum-statements PERCENT] [--require-integration]

The default expected union is all six supported platforms. A caller may name a
smaller local set; the report always names it. Missing expected hosts fail.
Go reports statements, not lines or branches. No policy minimum is built in.

source_identity(root) -> dict hashes every module input (including test and
embedded bytes), excluding only .git. Keep all generated output outside root.
integration_metadata(root, profile, expected_source) -> dict compares the
identity captured BEFORE an instrumented CLI build with the current inputs.
The integration producer writes that result to str(profile) + '.json', then
passes --extra-profile to collect. Build with -covermode=atomic; convert genuine
GOCOVERDIR data with `go tool covdata textfmt`. The producer owns real binary
execution; these unkeyed hashes detect mistakes/substitution, not forged runs.
No production bridge environment or installed authority is changed here.
"""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys


PLATFORMS = frozenset({
    "linux/amd64", "linux/arm64", "windows/amd64", "windows/arm64",
    "darwin/amd64", "darwin/arm64",
})
FORMAT = "codearbiter.go-statement-coverage/1"
EXTRA_FORMAT = "codearbiter.go-statement-integration/1"
MAX_BYTES = 32 * 1024 * 1024
UNIT_COMMAND = [
    "go", "test", "-buildvcs=false", "-count=1", "-coverpkg=./...",
    "-covermode=atomic", "-coverprofile={profile}", "./...",
]
PROFILE_ROW = re.compile(r"([^\s]+\.go):([1-9][0-9]*)\.([1-9][0-9]*),([1-9][0-9]*)\.([1-9][0-9]*) ([0-9]+) ([0-9]+)")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def _read(path: Path) -> bytes:
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or path.is_symlink()
            or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
            or info.st_size > MAX_BYTES):
        raise ValueError(f"not a bounded regular file: {path}")
    data = path.read_bytes()
    if len(data) > MAX_BYTES:
        raise ValueError(f"file exceeds size limit: {path}")
    return data


def _json(path: Path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def constant(value):
        raise ValueError(f"non-finite JSON value: {value}")

    return json.loads(_read(path), object_pairs_hook=pairs, parse_constant=constant)


def _keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError("missing or unknown metadata fields")


def _environment(target=None):
    env = {**os.environ, "GOTOOLCHAIN": "local", "GOWORK": "off", "GOENV": "off",
           "GOFLAGS": "", "GOPROXY": "off", "GOSUMDB": "off", "CGO_ENABLED": "0"}
    env.pop("GOCOVERDIR", None)
    if target is not None:
        env["GOOS"], env["GOARCH"] = target.split("/")
    return env


def _go(root: Path, *args, target=None) -> str:
    result = subprocess.run(["go", *args], cwd=root, env=_environment(target),
                            capture_output=True, text=True, encoding="utf-8", timeout=900)
    if result.returncode:
        raise ValueError(f"go {args[0]} failed: {result.stderr[-2000:]}")
    return result.stdout.strip()


def _native(root: Path):
    env = json.loads(_go(root, "env", "-json", "GOOS", "GOARCH", "GOHOSTOS", "GOHOSTARCH", "GOVERSION"))
    platform = env["GOOS"] + "/" + env["GOARCH"]
    if platform not in PLATFORMS or platform != env["GOHOSTOS"] + "/" + env["GOHOSTARCH"]:
        raise ValueError("collection requires a supported native Go host, not a cross target")
    return platform, env["GOVERSION"]


def source_identity(module_root: Path) -> dict:
    """Bind all module bytes, including embedded assets and tests; no output in root."""
    root = Path(module_root).resolve(strict=True)
    _read(root / "go.mod")
    files = {}
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(name for name in dirs if name != ".git")
        for name in dirs:
            path = Path(directory) / name
            info = path.lstat()
            if path.is_symlink() or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ValueError(f"linked module input directory: {path}")
        for name in sorted(names):
            if name != ".git":
                path = Path(directory) / name
                files[path.relative_to(root).as_posix()] = _digest(_read(path))
    module = _go(root, "list", "-m")
    if not module or len(module.split()) != 1:
        raise ValueError("expected one module path")
    identity = {"module": module, "files": files}
    return {**identity, "sha256": _digest(_canonical(identity))}


def _packages(root, target=None):
    return dict(line.split() for line in _go(root, "list", "-f", "{{.ImportPath}} {{.Name}}", "./...", target=target).splitlines())


def _profile(raw: bytes, source: dict, root: Path):
    rows = raw.decode("utf-8").splitlines()
    if not rows or rows[0] != "mode: atomic":
        raise ValueError("expected an atomic Go text statement profile")
    blocks = {}
    source_lines = {}
    prefix = source["module"] + "/"
    for row in rows[1:]:
        match = PROFILE_ROW.fullmatch(row)
        if match is None:
            raise ValueError("malformed Go coverage row")
        name = match[1]
        relative = name.removeprefix(prefix)
        if (not name.startswith(prefix) or relative not in source["files"]
                or relative.endswith("_test.go") or "\\" in relative):
            raise ValueError("profile contains a foreign or non-production source")
        start_line, start_col, end_line, end_col, statements, hits = map(int, match.groups()[1:])
        if relative not in source_lines:
            source_lines[relative] = _read(root / relative).splitlines()
        lines = source_lines[relative]
        if ((end_line, end_col) < (start_line, start_col) or end_line > len(lines)
                or start_col > len(lines[start_line - 1]) + 1
                or end_col > len(lines[end_line - 1]) + 1
                or statements > 2**32 - 1 or hits > 2**64 - 1):
            raise ValueError("profile block is outside its exact source")
        key = (name, start_line, start_col, end_line, end_col)
        if key in blocks and blocks[key][0] != statements:
            raise ValueError("conflicting statement counts for a source block")
        blocks[key] = (statements, bool(hits) or blocks.get(key, (0, False))[1])
    if not blocks or not sum(value[0] for value in blocks.values()):
        raise ValueError("profile has no instrumentable statements")
    return blocks


def _block_digest(blocks):
    return _digest(_canonical([list(key) + [value[0]] for key, value in sorted(blocks.items())]))


def integration_metadata(module_root, profile, expected_source):
    """Call after a genuine CLI exercise, passing source_identity taken before build."""
    root = Path(module_root).resolve(strict=True)
    current = source_identity(root)
    if current != expected_source:
        raise ValueError("module inputs changed during the integration build/exercise")
    platform, version = _native(root)
    raw = _read(Path(profile))
    _profile(raw, current, root)
    return {"format": EXTRA_FORMAT, "source_sha256": current["sha256"],
            "platform": platform, "go_version": version, "profile_sha256": _digest(raw)}


def collect(root, output, expected_platform=None, extra_profiles=()):
    root = root.resolve(strict=True)
    output = output.absolute()
    if output.resolve().is_relative_to(root):
        raise ValueError("coverage output must be outside the module inputs")
    platform, version = _native(root)
    if expected_platform is not None and platform != expected_platform:
        raise ValueError("native platform does not match the expected platform")
    before = source_identity(root)
    packages = _packages(root)
    output.mkdir(parents=True, exist_ok=False)
    unit = output / "unit.coverage.out"
    command = [arg.replace("{profile}", str(unit)) for arg in UNIT_COMMAND]
    result = subprocess.run(command, cwd=root, env=_environment(), capture_output=True, timeout=900)
    (output / "unit.log").write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise ValueError(f"native go test failed with exit {result.returncode}; see {output / 'unit.log'}")
    profiles = []
    for index, path in enumerate([unit, *extra_profiles]):
        raw = _read(path)
        if index:
            sidecar = _json(Path(str(path) + ".json"))
            expected = {"format": EXTRA_FORMAT, "source_sha256": before["sha256"],
                        "platform": platform, "go_version": version, "profile_sha256": _digest(raw)}
            if sidecar != expected:
                raise ValueError("integration profile identity does not match this native collection")
        blocks = _profile(raw, before, root)
        name = "unit.coverage.out" if not index else f"integration-{index}.coverage.out"
        if index:
            (output / name).write_bytes(raw)
        profiles.append({"file": name, "kind": "unit" if not index else "integration",
                         "sha256": _digest(raw), "blocks_sha256": _block_digest(blocks)})
    if source_identity(root) != before:
        raise ValueError("module inputs changed during native collection")
    metadata = {"format": FORMAT, "platform": platform, "go_version": version,
                "source": before, "packages": packages, "unit_command": UNIT_COMMAND,
                "profiles": profiles}
    # Publication is last. A failed/partial run has no usable metadata.
    with (output / "metadata.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(metadata, stream, sort_keys=True, indent=2)
        stream.write("\n")
    return {"status": "COLLECTED", "metric": "statements", "platform": platform,
            "source_sha256": before["sha256"], "output": str(output),
            "integration_profiles": len(extra_profiles)}


def _merge(destination, source):
    for key, value in source.items():
        if key in destination and destination[key][0] != value[0]:
            raise ValueError("source block statement count mismatch")
        destination[key] = (value[0], value[1] or destination.get(key, (0, False))[1])


def summarize(root, inputs, expected_platforms, minimum=None, require_integration=False):
    expected = set(expected_platforms)
    if not expected or len(expected) != len(expected_platforms) or not expected <= PLATFORMS:
        raise ValueError("expected platforms must be distinct supported platform names")
    if minimum is not None and (not minimum.is_finite() or not 0 <= minimum <= 100):
        raise ValueError("statement minimum must be finite and between 0 and 100")
    root = root.resolve(strict=True)
    current = source_identity(root)
    _, version = _native(root)
    seen = set()
    union = {}
    layouts = {}
    missing_integration = []
    for folder in inputs:
        meta = _json(folder / "metadata.json")
        _keys(meta, ("format", "platform", "go_version", "source", "packages", "unit_command", "profiles"))
        platform = meta["platform"]
        if not isinstance(platform, str) or platform not in expected or platform in seen:
            raise ValueError("duplicate or unexpected platform collection")
        if (meta["format"] != FORMAT or meta["source"] != current or meta["go_version"] != version
                or meta["unit_command"] != UNIT_COMMAND or meta["packages"] != _packages(root, platform)):
            raise ValueError("stale or mismatched source, toolchain, package or command identity")
        if not isinstance(meta["profiles"], list) or not meta["profiles"]:
            raise ValueError("native unit profile is missing")
        seen.add(platform)
        unit = {}
        integration = {}
        for index, entry in enumerate(meta["profiles"]):
            _keys(entry, ("file", "kind", "sha256", "blocks_sha256"))
            name = "unit.coverage.out" if not index else f"integration-{index}.coverage.out"
            if entry["file"] != name or entry["kind"] != ("unit" if not index else "integration"):
                raise ValueError("invalid native profile inventory")
            raw = _read(folder / name)
            if _digest(raw) != entry["sha256"]:
                raise ValueError("profile byte digest mismatch")
            blocks = _profile(raw, current, root)
            if _block_digest(blocks) != entry["blocks_sha256"]:
                raise ValueError("profile block inventory mismatch")
            if not index:
                unit = blocks
            else:
                if any(key not in unit or unit[key][0] != value[0] for key, value in blocks.items()):
                    raise ValueError("integration profile does not match native unit instrumentation")
                _merge(integration, blocks)
        local_layouts = {}
        for key, value in unit.items():
            package = key[0].rsplit("/", 1)[0]
            if package not in meta["packages"]:
                raise ValueError("profile package is outside the native package inventory")
            local_layouts.setdefault(key[0], {})[key[1:]] = value[0]
        for name, layout in local_layouts.items():
            if name in layouts and layout != layouts[name]:
                raise ValueError("shared source instrumentation differs across native hosts")
            layouts[name] = layout
        executables = [name for name, kind in meta["packages"].items() if kind == "main"]
        if not executables or any(not any(key[0].rsplit("/", 1)[0] == name and value[1]
                                        for key, value in integration.items()) for name in executables):
            missing_integration.append(platform)
        _merge(union, unit)
        _merge(union, integration)
    if source_identity(root) != current:
        raise ValueError("module inputs changed during summarization")
    total = sum(value[0] for value in union.values())
    covered = sum(value[0] for value in union.values() if value[1])
    if not total:
        raise ValueError("no statement coverage inputs")
    missing = sorted(expected - seen)
    meets = None if minimum is None else Decimal(100 * covered) >= minimum * total
    status = ("PARTIAL" if missing else "MISSING_INTEGRATION" if require_integration and missing_integration
              else "BELOW_MINIMUM" if meets is False else "COMPLETE")
    return {"status": status, "metric": "statements", "not_measured": ["lines", "branches"],
            "source_sha256": current["sha256"], "go_version": version,
            "expected_platforms": sorted(expected), "platforms": sorted(seen), "missing_platforms": missing,
            "statements": {"total": total, "covered": covered, "percent": round(100 * covered / total, 4)},
            "minimum_statements": None if minimum is None else float(minimum), "minimum_met": meets,
            "integration": {"required": require_integration,
                            "missing_platforms": sorted(set(missing_integration) | set(missing))}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    collector = commands.add_parser("collect")
    collector.add_argument("--module-root", type=Path, required=True)
    collector.add_argument("--output", type=Path, required=True)
    collector.add_argument("--expect-platform")
    collector.add_argument("--extra-profile", type=Path, action="append", default=[])
    merger = commands.add_parser("summarize")
    merger.add_argument("--module-root", type=Path, required=True)
    merger.add_argument("--input", type=Path, action="append", required=True)
    merger.add_argument("--expect-platform", action="append")
    merger.add_argument("--minimum-statements")
    merger.add_argument("--require-integration", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "collect":
            report = collect(args.module_root, args.output, args.expect_platform, args.extra_profile)
        else:
            minimum = None if args.minimum_statements is None else Decimal(args.minimum_statements)
            report = summarize(args.module_root, args.input, args.expect_platform or sorted(PLATFORMS),
                               minimum, args.require_integration)
    except (OSError, ValueError, InvalidOperation, subprocess.TimeoutExpired) as exc:
        report = {"status": "INVALID", "error": str(exc)}
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0 if report["status"] in {"COLLECTED", "COMPLETE"} else 1


if __name__ == "__main__":
    sys.exit(main())
