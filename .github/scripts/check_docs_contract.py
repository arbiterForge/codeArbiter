#!/usr/bin/env python3
"""Repository-wide, read-only documentation contract checker."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable


REPO = Path(__file__).resolve().parents[2]
INLINE_LINK = re.compile(r"(?<!!)\[[^]]*\]\((?P<target>[^)\s]+)(?:\s+[^)]*)?\)")
URL_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
GITHUB_RELATIVE = re.compile(r"^(?:\.\./)+(?:pull|issues|commit|compare|releases)/.+")
ALLOWED_GENERATOR_CHECKS = frozenset({("python", "tools/build-surface.py", "--check")})


class ContractError(ValueError):
    """The CI-owned documentation contract is malformed."""


@dataclass(frozen=True)
class Rule:
    name: str
    includes: tuple[str, ...]
    excludes: tuple[str, ...]


@dataclass(frozen=True)
class Binding:
    path: PurePosixPath
    template: str


@dataclass(frozen=True)
class DocsContract:
    rules: tuple[Rule, ...]
    bindings: tuple[Binding, ...]
    generator_checks: tuple[tuple[str, ...], ...]


@dataclass(frozen=True, order=True)
class Finding:
    code: str
    path: str
    detail: str = ""


def load_contract(path: Path) -> DocsContract:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ContractError(f"cannot load documentation contract: {error}") from error
    if not isinstance(document, dict) or document.get("schema") != 1:
        raise ContractError("documentation contract must use schema 1")
    raw_classes = document.get("classes")
    if not isinstance(raw_classes, list):
        raise ContractError("documentation contract requires a classes list")
    rules = []
    names = set()
    for item in raw_classes:
        if not isinstance(item, dict):
            raise ContractError("every documentation class must be an object")
        name, includes, excludes = item.get("name"), item.get("include"), item.get("exclude", [])
        if name not in {"generated", "current", "historical"} or name in names:
            raise ContractError("documentation classes must use unique generated/current/historical names")
        if not isinstance(includes, list) or not includes or not all(isinstance(pattern, str) and pattern for pattern in includes):
            raise ContractError(f"{name}: include must contain non-empty glob patterns")
        if not isinstance(excludes, list) or not all(isinstance(pattern, str) and pattern for pattern in excludes):
            raise ContractError(f"{name}: exclude must contain only non-empty glob patterns")
        names.add(name)
        rules.append(Rule(name, tuple(includes), tuple(excludes)))
    raw_bindings = document.get("bindings", [])
    if not isinstance(raw_bindings, list):
        raise ContractError("documentation bindings must be a list")
    bindings = []
    bound_paths = set()
    for item in raw_bindings:
        if not isinstance(item, dict):
            raise ContractError("every documentation binding must be an object")
        raw_path, template = item.get("path"), item.get("template")
        if not isinstance(raw_path, str) or not raw_path or not isinstance(template, str) or not template:
            raise ContractError("documentation binding requires path and template")
        path_value = PurePosixPath(raw_path)
        if path_value.is_absolute() or ".." in path_value.parts or path_value in bound_paths:
            raise ContractError("documentation binding path must be unique and repository-relative")
        bound_paths.add(path_value)
        bindings.append(Binding(path_value, template))
    raw_checks = document.get("generator_checks", [])
    if not isinstance(raw_checks, list) or not all(
        isinstance(command, list) and command and all(isinstance(part, str) and part for part in command)
        for command in raw_checks
    ):
        raise ContractError("generator_checks must contain non-empty command arrays")
    generator_checks = tuple(tuple(command) for command in raw_checks)
    if any(command not in ALLOWED_GENERATOR_CHECKS for command in generator_checks):
        raise ContractError("generator_checks contains an unapproved command")
    return DocsContract(tuple(rules), tuple(bindings), generator_checks)


def tracked_markdown(repo: Path) -> tuple[Path, ...]:
    completed = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "*.md"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
    )
    if completed.returncode != 0:
        raise ContractError("cannot list tracked Markdown documents")
    return tuple(Path(line) for line in completed.stdout.splitlines() if line)


def classify(path: PurePosixPath, contract: DocsContract) -> tuple[str, ...]:
    rendered = path.as_posix()
    return tuple(
        rule.name for rule in contract.rules
        if any(_glob_matches(rendered, pattern) for pattern in rule.includes)
        and not any(_glob_matches(rendered, pattern) for pattern in rule.excludes)
    )


def _glob_matches(path: str, pattern: str) -> bool:
    """Match a path glob where `*` never crosses a directory boundary."""
    pieces = []
    index = 0
    while index < len(pattern):
        character = pattern[index]
        if character == "*" and index + 1 < len(pattern) and pattern[index + 1] == "*":
            index += 2
            if index < len(pattern) and pattern[index] == "/":
                pieces.append("(?:.*/)?")
                index += 1
            else:
                pieces.append(".*")
            continue
        if character == "*":
            pieces.append("[^/]*")
        elif character == "?":
            pieces.append("[^/]")
        else:
            pieces.append(re.escape(character))
        index += 1
    return re.fullmatch("".join(pieces), path) is not None


def _relative_targets(text: str) -> Iterable[str]:
    for match in INLINE_LINK.finditer(_without_fenced_code(text)):
        target = match.group("target").strip().strip("<>")
        target = target.split("#", 1)[0]
        if target and not target.startswith("/") and not URL_SCHEME.match(target):
            yield target


def _without_fenced_code(text: str) -> str:
    retained = []
    fence = None
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        marker = stripped[:3]
        if fence is None and marker in {"```", "~~~"}:
            fence = marker
            continue
        if fence is not None:
            if marker == fence:
                fence = None
            continue
        retained.append(line)
    return "".join(retained)


def _link_finding(repo: Path, source: Path, target: str) -> Finding | None:
    if GITHUB_RELATIVE.fullmatch(target):
        return None
    root = repo.resolve()
    site_root = root / "site" / "src" / "content" / "docs"
    if source.as_posix().startswith("site/src/content/docs/") and target.endswith("/"):
        route = target
        while route.startswith("../"):
            route = route[3:]
        route = route.removeprefix("./")
        # Routes produced by `npm run gen` are gitignored (see .gitignore), so
        # they are absent from a fresh checkout; accept them structurally.
        if route == "changelog/" or route.startswith("reference/"):
            return None
        candidate = (site_root / route).resolve()
        if candidate.is_relative_to(site_root.resolve()) and candidate.is_dir():
            return None
    resolved = (root / source.parent / target).resolve()
    if not resolved.is_relative_to(root) or not resolved.exists():
        return Finding("DOC-LINK-MISSING", source.as_posix(), target)
    return None


def _expected(template: str, policy: object) -> str:
    try:
        return template.format(
            minimum=policy.minimum,
            last_verified=policy.last_verified,
        )
    except (AttributeError, KeyError, ValueError) as error:
        raise ContractError(f"invalid documentation fact template: {error}") from error


def check_documentation(
    repo: Path,
    contract: DocsContract,
    policy: object,
    paths: Iterable[Path] | None = None,
) -> list[Finding]:
    selected = tuple(paths) if paths is not None else tracked_markdown(repo)
    bindings = {binding.path: binding for binding in contract.bindings}
    findings = []
    for path in selected:
        relative = PurePosixPath(path.as_posix())
        classes = classify(relative, contract)
        if not classes:
            findings.append(Finding("DOC-UNCLASSIFIED", relative.as_posix()))
            continue
        if len(classes) != 1:
            findings.append(Finding("DOC-AMBIGUOUS", relative.as_posix(), ",".join(classes)))
            continue
        full_path = repo / path
        try:
            text = full_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            findings.append(Finding("DOC-UNREADABLE", relative.as_posix(), str(error)))
            continue
        for target in _relative_targets(text):
            finding = _link_finding(repo, Path(relative), target)
            if finding is not None:
                findings.append(finding)
        binding = bindings.get(relative)
        if binding is not None and classes[0] != "current":
            findings.append(Finding("DOC-BINDING-NONCURRENT", relative.as_posix()))
        elif binding is not None and _expected(binding.template, policy) not in text:
            findings.append(Finding("DOC-FACT-STALE", relative.as_posix(), _expected(binding.template, policy)))
    for command in contract.generator_checks:
        try:
            completed = subprocess.run(
                command,
                cwd=repo,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired):
            findings.append(Finding("DOC-GENERATOR-FAILED", command[0], "unavailable or timed out"))
            continue
        if completed.returncode != 0:
            findings.append(Finding("DOC-GENERATOR-FAILED", command[0], f"exit {completed.returncode}"))
    return sorted(findings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=REPO / ".github" / "docs-contract.json")
    parser.add_argument("--targets", type=Path, default=REPO / ".github" / "pi-promotion-targets.json")
    args = parser.parse_args(argv)
    from pi_promotion import load_targets, read_policy

    try:
        findings = check_documentation(REPO, load_contract(args.contract), read_policy(REPO, load_targets(args.targets)))
    except ContractError as error:
        sys.stderr.write(f"documentation contract: {error}\n")
        return 2
    for finding in findings:
        suffix = "" if not finding.detail else f": {finding.detail}"
        print(f"{finding.code} {finding.path}{suffix}")
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
