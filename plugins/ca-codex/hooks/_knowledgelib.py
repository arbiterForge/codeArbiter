"""Locate repository knowledge without reading or parsing it.

A repository keeps its narrative context either as the five legacy Markdown
documents or, once converted, as native HTML knowledge under
`.codearbiter/context/`. `CONTEXT.md` selects the format with one
frontmatter line, `context-format: html`, and stays the activation owner
either way. This module only reads that small frontmatter: hooks may call it
on every tool use, so it never starts the artifact engine or opens HTML.
"""
from __future__ import annotations

import os

DOCUMENTS = ("project", "tech-stack", "coding-standards", "security-controls", "code-map")
FORMAT_LINE = "context-format: html"
CONTEXT_FILE = "CONTEXT.md"

LEGACY_PATHS = {
    "project": ".codearbiter/" + CONTEXT_FILE,
    "tech-stack": ".codearbiter/tech-stack.md",
    "coding-standards": ".codearbiter/coding-standards.md",
    "security-controls": ".codearbiter/security-controls.md",
    "code-map": ".codearbiter/code-map.md",
}
HTML_PATHS = {doc: f".codearbiter/context/{doc}.html" for doc in DOCUMENTS}
DECOMPOSITION_PATH = ".codearbiter/decomposition/project.html"

# The frontmatter of an activation file is a few lines; a larger read is not
# needed to find one key and keeps a hostile file from costing a hook time.
_FRONTMATTER_LIMIT = 16 * 1024


def artifact_id(doc: str) -> str:
    """The stable knowledge ID for one of the five documents."""
    if doc not in DOCUMENTS:
        raise ValueError(f"unknown knowledge document: {doc}")
    return "CTX-" + doc.upper()


def frontmatter_selects_html(text: str) -> bool:
    """True when a properly closed leading frontmatter holds the format line."""
    lines = text.lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != "---":
        return False
    found = False
    for line in lines[1:]:
        if line.strip() == "---":
            return found
        if line.strip() == FORMAT_LINE:
            found = True
    return False


def context_format(root: str) -> str:
    """'html' for a converted repository, otherwise 'markdown'.

    An unreadable or malformed CONTEXT.md is reported as markdown: the
    activation readers own that failure, and the legacy layout is the one an
    unconverted or broken repository actually has.
    """
    try:
        with open(os.path.join(root, ".codearbiter", CONTEXT_FILE), encoding="utf-8", errors="replace") as handle:
            text = handle.read(_FRONTMATTER_LIMIT)
    except OSError:
        return "markdown"
    return "html" if frontmatter_selects_html(text) else "markdown"


def narrative_path(root: str, doc: str) -> str:
    """Repository-relative path of one narrative document in the active format."""
    if doc not in DOCUMENTS:
        raise ValueError(f"unknown knowledge document: {doc}")
    return HTML_PATHS[doc] if context_format(root) == "html" else LEGACY_PATHS[doc]


def narrative_paths(root: str) -> dict[str, str]:
    """All five narrative paths in the active format."""
    paths = HTML_PATHS if context_format(root) == "html" else LEGACY_PATHS
    return dict(paths)
