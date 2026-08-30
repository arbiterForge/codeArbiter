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
SYMBOLIC_SEGMENT = re.compile(r"<[a-z][a-z0-9-]*>")
SYMBOLIC_TARGET_CHARS = re.compile(r"^[A-Za-z0-9_./<>-]+$")
ATX_HEADING = re.compile(r"^[ \t]{0,3}#{1,6}(?:[ \t]+|$)")
LIST_ITEM = re.compile(
    r"^[ \t]{0,3}(?:(?P<bullet>[*+-])|(?P<number>[0-9]{1,9})[.)])"
    r"(?P<spacing>[ \t]+|$)(?P<body>.*)$"
)
INDENTED_LIST_ITEM = re.compile(
    r"^[ \t]+(?:(?P<bullet>[*+-])|(?P<number>[0-9]{1,9})[.)])"
    r"(?P<spacing>[ \t]+|$)(?P<body>.*)$"
)
SETEXT_UNDERLINE = re.compile(r"^[ \t]{0,3}=+[ \t]*$")
THEMATIC_BREAK = re.compile(
    r"^[ \t]{0,3}(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$"
)
HTML_BLOCK_TAGS = frozenset(
    "address article aside base basefont blockquote body caption center col colgroup "
    "dd details dialog dir div dl dt fieldset figcaption figure footer form frame "
    "frameset h1 h2 h3 h4 h5 h6 head header hr html iframe legend li link main menu "
    "menuitem nav noframes ol optgroup option p param search section summary table "
    "tbody td tfoot th thead title tr track ul".split()
)
HTML_TAG_NAME = r"[A-Za-z][A-Za-z0-9-]*"
HTML_ATTR_NAME = r"[A-Za-z_:][A-Za-z0-9_.:-]*"
HTML_ATTR_VALUE = r"(?:[^\s\"'=<>`]+|'[^']*'|\"[^\"]*\")"
TYPE_SEVEN_TAG = re.compile(
    rf"(?:<{HTML_TAG_NAME}(?:\s+{HTML_ATTR_NAME}(?:\s*=\s*{HTML_ATTR_VALUE})?)*"
    rf"\s*/?>|</{HTML_TAG_NAME}\s*>)[ \t]*"
)
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
    version_claim_exempt: tuple[PurePosixPath, ...] = ()


@dataclass(frozen=True, order=True)
class Finding:
    code: str
    path: str
    detail: str = ""


PI_VERSION_CLAIM = re.compile(r"\b0\.80\.\d+\b")


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
    raw_exempt = document.get("version_claim_exempt", [])
    if not isinstance(raw_exempt, list) or not all(isinstance(item, str) and item for item in raw_exempt):
        raise ContractError("version_claim_exempt must contain repository-relative paths")
    exempt = tuple(PurePosixPath(item) for item in raw_exempt)
    if any(item.is_absolute() or ".." in item.parts for item in exempt):
        raise ContractError("version_claim_exempt paths must be repository-relative")
    return DocsContract(tuple(rules), tuple(bindings), generator_checks, exempt)


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
    without_code = _without_inline_code(
        _without_html_blocks(_without_fenced_code(text))
    )
    for match in INLINE_LINK.finditer(without_code):
        target = match.group("target").strip()
        if target.startswith("<") and target.endswith(">"):
            target = target[1:-1]
        target = target.split("#", 1)[0]
        if target and not target.startswith("/") and not URL_SCHEME.match(target):
            yield target


def _without_fenced_code(text: str) -> str:
    retained = []
    fence = None
    for line in text.splitlines(keepends=True):
        quote_depth, content = _strip_block_quotes(line.rstrip("\r\n"))
        if fence is not None and quote_depth < fence[2]:
            fence = None
        if fence is None:
            opener = _fence_opener(content)
        else:
            opener = None
        if opener is not None:
            fence = (*opener, quote_depth)
            retained.append("\n")
            continue
        if fence is not None:
            if quote_depth == fence[2] and _is_fence_closer(content, fence[:2]):
                fence = None
            retained.append("\n")
            continue
        retained.append(line)
    return "".join(retained)


def _fence_opener(content: str) -> tuple[str, int] | None:
    indent = len(content) - len(content.lstrip(" "))
    if indent > 3 or content.startswith("\t"):
        return None
    stripped = content[indent:]
    if not stripped or stripped[0] not in {"`", "~"}:
        return None
    marker = stripped[0]
    width = len(stripped) - len(stripped.lstrip(marker))
    if width < 3:
        return None
    info = stripped[width:]
    if marker == "`" and "`" in info:
        return None
    return marker, width


def _is_fence_closer(content: str, fence: tuple[str, int]) -> bool:
    indent = len(content) - len(content.lstrip(" "))
    if indent > 3 or content.startswith("\t"):
        return False
    stripped = content[indent:]
    marker, opener_width = fence
    width = len(stripped) - len(stripped.lstrip(marker))
    return width >= opener_width and not stripped[width:].strip()


def _without_html_blocks(text: str) -> str:
    retained = []
    block = None
    paragraph_open = False
    paragraph_quote_depth = 0
    for line in text.splitlines(keepends=True):
        quote_depth, content = _strip_block_quotes(line.rstrip("\r\n"))
        if paragraph_open and quote_depth != paragraph_quote_depth:
            paragraph_open = False
        if block is not None:
            list_indent = block[2]
            leaves_quote = quote_depth < block[1]
            leaves_list = (
                list_indent is not None
                and bool(content.strip())
                and _leading_columns(content) < list_indent
            )
            if leaves_quote or leaves_list:
                block = None
        if block is None:
            html_type, html_content, list_indent = _html_block_start(
                content, allow_type_seven=not paragraph_open
            )
            if html_type is None:
                retained.append(line)
                if not line.strip():
                    paragraph_open = False
                elif _markdown_block_kind(line, None, False) == "standalone":
                    paragraph_open = False
                else:
                    paragraph_open = True
                    paragraph_quote_depth = quote_depth
                continue
            terminator = _html_block_terminator(html_type)
            if terminator is None or not terminator.search(html_content):
                block = (html_type, quote_depth, list_indent)
            retained.append("\n")
            paragraph_open = False
            continue
        terminator = _html_block_terminator(block[0])
        retained.append("\n")
        if block[0] in {"block-tag", "type-seven"} and not content.strip():
            block = None
            paragraph_open = False
        elif terminator is not None and quote_depth == block[1] and terminator.search(content):
            block = None
    return "".join(retained)


def _html_block_start(
    content: str, *, allow_type_seven: bool
) -> tuple[str | None, str, int | None]:
    html_type = _html_block_type(content, allow_type_seven=allow_type_seven)
    if html_type is not None:
        return html_type, content, None
    body = content
    continuation_indent = 0
    first_prefix = True
    while True:
        list_match = LIST_ITEM.match(body)
        if list_match is None:
            return None, content, None
        if first_prefix and not allow_type_seven and not _list_item_interrupts(
            body, list_match, continuation_indent
        ):
            return None, content, None
        list_body, body_start = _list_item_body(body, list_match, continuation_indent)
        continuation_indent = _display_columns(
            body[:body_start], continuation_indent
        )
        body = list_body
        html_type = _html_block_type(body, allow_type_seven=True)
        if html_type is not None:
            return html_type, body, continuation_indent
        first_prefix = False


def _html_block_type(content: str, *, allow_type_seven: bool = False) -> str | None:
    stripped = content.lstrip(" ")
    if len(content) - len(stripped) > 3 or content.startswith("\t"):
        return None
    tag = re.match(r"(?i)<(script|pre|style|textarea)(?:[ \t>]|$)", stripped)
    if tag:
        return tag.group(1).lower()
    if stripped.startswith("<!--"):
        return "comment"
    if stripped.startswith("<?"):
        return "processing"
    if stripped.startswith("<![CDATA["):
        return "cdata"
    if re.match(r"<![A-Z]", stripped):
        return "declaration"
    block_tag = re.match(r"(?i)</?([a-z][a-z0-9-]*)(?:[ \t>/]|$)", stripped)
    if block_tag and block_tag.group(1).lower() in HTML_BLOCK_TAGS:
        return "block-tag"
    if allow_type_seven and TYPE_SEVEN_TAG.fullmatch(stripped):
        return "type-seven"
    return None


def _html_block_terminator(html_type: str) -> re.Pattern[str] | None:
    if html_type in {"script", "pre", "style", "textarea"}:
        return re.compile(rf"(?i)</{html_type}[ \t]*>")
    return {
        "comment": re.compile(r"--!?>"),
        "processing": re.compile(r"\?>"),
        "cdata": re.compile(r"\]\]>"),
        "declaration": re.compile(r">"),
        "block-tag": None,
        "type-seven": None,
    }[html_type]


def _leading_columns(content: str) -> int:
    prefix = content[: len(content) - len(content.lstrip(" \t"))]
    return _display_columns(prefix)


def _display_columns(text: str, column: int = 0) -> int:
    for character in text:
        if character == "\t":
            column += 4 - (column % 4)
        else:
            column += 1
    return column


def _without_inline_code(text: str) -> str:
    """Mask bounded code spans without pairing separate Markdown blocks."""
    retained = []
    block = []
    block_kind = None

    def flush() -> None:
        nonlocal block, block_kind
        if block:
            retained.append(_without_inline_code_block("".join(block)))
        block = []
        block_kind = None

    for line in text.splitlines(keepends=True):
        if not line.strip():
            flush()
            retained.append(line)
            continue
        kind = _markdown_block_kind(line, block_kind, bool(block))
        if kind == "standalone":
            flush()
            retained.append(_without_inline_code_block(line))
            continue
        if kind is not None and kind != block_kind:
            if not (_is_list_kind(block_kind) and kind == _list_container(block_kind)):
                flush()
                block_kind = kind
        elif _is_list_kind(kind):
            flush()
            block_kind = kind
        block.append(line)
    flush()
    return "".join(retained)


def _markdown_block_kind(
    line: str, active_kind: str | None, has_active_block: bool
) -> str | None:
    content = line.rstrip("\r\n")
    quote_depth, content = _strip_block_quotes(content)
    if (
        ATX_HEADING.match(content)
        or THEMATIC_BREAK.fullmatch(content)
        or SETEXT_UNDERLINE.fullmatch(content)
        or (quote_depth and not content.strip())
    ):
        return "standalone"
    nested_match = (
        _is_list_kind(active_kind)
        and _list_quote_depth(active_kind) == quote_depth
        and INDENTED_LIST_ITEM.match(content)
    )
    list_match = LIST_ITEM.match(content) or nested_match
    interrupts_paragraph = has_active_block and (
        active_kind is None or active_kind == f"quote:{quote_depth}"
    )
    if list_match and interrupts_paragraph:
        if not _list_item_interrupts(content, list_match):
            list_match = None
    if list_match:
        return f"quote:{quote_depth}:list" if quote_depth else "list"
    if quote_depth:
        return f"quote:{quote_depth}"
    return None


def _strip_block_quotes(content: str) -> tuple[int, str]:
    depth = 0
    while True:
        match = re.match(r"^[ \t]{0,3}>[ \t]?", content)
        if match is None:
            return depth, content
        depth += 1
        content = content[match.end() :]


def _is_list_kind(kind: str | None) -> bool:
    return kind == "list" or bool(kind and kind.endswith(":list"))


def _list_container(kind: str | None) -> str | None:
    if kind == "list":
        return None
    if kind and kind.endswith(":list"):
        return kind[: -len(":list")]
    return kind


def _list_quote_depth(kind: str | None) -> int:
    if kind == "list":
        return 0
    if kind and kind.startswith("quote:") and kind.endswith(":list"):
        return int(kind.split(":", 2)[1])
    return -1


def _list_item_body(
    content: str, match: re.Match[str], start_column: int = 0
) -> tuple[str, int]:
    spacing = match.group("spacing")
    if not spacing:
        body_start = match.end("spacing")
        return content[body_start:], body_start
    marker_end = match.start("spacing")
    marker_column = _display_columns(content[:marker_end], start_column)
    spacing_width = _display_columns(spacing, marker_column) - marker_column
    consumed = len(spacing) if 1 <= spacing_width <= 4 else 1
    body_start = marker_end + consumed
    return content[body_start:], body_start


def _list_item_interrupts(
    content: str, match: re.Match[str], start_column: int = 0
) -> bool:
    body, _ = _list_item_body(content, match, start_column)
    number = match.group("number")
    return (number is None or int(number) == 1) and bool(body.strip())


def _without_inline_code_block(text: str) -> str:
    """Mask bounded Markdown code spans within one paragraph-like block."""
    masked = list(text)
    index = 0
    while index < len(text):
        if text[index] != "`" or _is_escaped(text, index):
            index += 1
            continue
        opener_end = index
        while opener_end < len(text) and text[opener_end] == "`":
            opener_end += 1
        width = opener_end - index
        search = opener_end
        closer_end = None
        while search < len(text):
            closer = text.find("`", search)
            if closer < 0:
                break
            candidate_end = closer
            while candidate_end < len(text) and text[candidate_end] == "`":
                candidate_end += 1
            if candidate_end - closer == width:
                closer_end = candidate_end
                break
            search = candidate_end
        if closer_end is None:
            index = opener_end
            continue
        for position in range(index, closer_end):
            if masked[position] != "\n":
                masked[position] = " "
        index = closer_end
    return "".join(masked)


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    index -= 1
    while index >= 0 and text[index] == "\\":
        backslashes += 1
        index -= 1
    return backslashes % 2 == 1


def _link_finding(repo: Path, source: Path, target: str) -> Finding | None:
    if GITHUB_RELATIVE.fullmatch(target):
        return None
    root = repo.resolve()
    symbolic = SYMBOLIC_SEGMENT.sub("symbol", target)
    if (symbolic != target and SYMBOLIC_TARGET_CHARS.fullmatch(target)
            and "<" not in symbolic and ">" not in symbolic):
        candidate = (root / source.parent / symbolic).resolve()
        if candidate.is_relative_to(root):
            return None
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
        if classes[0] == "current" and relative not in contract.version_claim_exempt:
            allowed_versions = {policy.minimum, policy.last_verified}
            for stale in sorted(set(PI_VERSION_CLAIM.findall(text)) - allowed_versions):
                findings.append(Finding("DOC-VERSION-STALE", relative.as_posix(), stale))
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
