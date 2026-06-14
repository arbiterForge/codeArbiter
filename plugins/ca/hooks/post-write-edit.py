#!/usr/bin/env python3
# codeArbiter v2 — PostToolUse(Write|Edit) reminders. Scope-touch nudges.
# Python port of post-write-edit.sh (#25): no jq, fails loud.
#
# These are advisory (non-blocking) nudges fired right after a write. The
# load-bearing crypto/secret ENFORCEMENT is the blocking pre-commit gate in
# pre-bash.py (H-09b/H-10b); these reminders surface the touch early so the gate
# isn't a surprise at commit time. Kept: H-07 (dependency review), H-09 (crypto),
# H-10 (secret). Added: H-12 (file governed by an ADR with a `governs:` field).

import fnmatch
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hooklib import (  # noqa: E402
    CRYPTO_RE, SECRET_RE, arbiter_active, project_root, read_input, remind,
    tool_input, utf8_stdio,
)
from _sloplib import find_prose_separator_dashes, in_antislop_doc_scope  # noqa: E402

DEP_MANIFEST_RE = re.compile(
    r"(package\.json|package-lock\.json|yarn\.lock|pnpm-lock\.yaml|requirements\.txt"
    r"|pyproject\.toml|go\.mod|Cargo\.toml)$"
)

GOVERNS_RE = re.compile(r"^governs:\s*(.+)$", re.I)
TITLE_RE = re.compile(r"^title:\s*(.+)$", re.I)
STATUS_RE = re.compile(r"^status:\s*(.+)$", re.I)


def governs_index(root):
    """path-glob → ADR map from decisions/ frontmatter, cached against the
    directory's latest mtime so the scan doesn't repeat on every write."""
    ddir = os.path.join(root, ".codearbiter", "decisions")
    if not os.path.isdir(ddir):
        return []
    files = [f for f in os.listdir(ddir) if re.match(r"[0-9]+-.+\.md$", f)]
    if not files:
        return []
    stamp = max(os.path.getmtime(os.path.join(ddir, f)) for f in files)
    cache_path = os.path.join(root, ".codearbiter", ".markers", "governs-cache.json")
    try:
        with open(cache_path, encoding="utf-8") as f:
            cache = json.load(f)
        if cache.get("stamp") == stamp:
            return cache.get("index", [])
    except Exception:  # noqa: BLE001 — absent/corrupt cache just rebuilds
        pass

    index = []
    for fn in files:
        title, status, globs = fn, "", []
        try:
            with open(os.path.join(ddir, fn), encoding="utf-8", errors="replace") as f:
                for i, ln in enumerate(f):
                    if i > 25:
                        break
                    if m := GOVERNS_RE.match(ln.strip()):
                        globs = [g.strip() for g in m.group(1).split(",") if g.strip()]
                    elif m := TITLE_RE.match(ln.strip()):
                        title = m.group(1).strip()
                    elif m := STATUS_RE.match(ln.strip()):
                        status = m.group(1).strip().lower()
        except Exception:  # noqa: BLE001
            continue
        if globs and status not in ("superseded", "rejected"):
            adr = fn.split("-")[0]
            index.append({"adr": adr, "title": title, "globs": globs})
    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({"stamp": stamp, "index": index}, f)
    except Exception:  # noqa: BLE001 — cache is an optimization, never required
        pass
    return index


def main():
    utf8_stdio()
    root = project_root()
    if not arbiter_active(root):
        sys.exit(0)
    ti = tool_input(read_input())
    fpath = ti.get("file_path", "") or ""
    content = ti.get("content") or ti.get("new_string") or ""

    # H-12: the touched file is governed by an accepted ADR — surface it so the
    # recorded decision pushes back at edit time, not at the next checkpoint.
    rel = os.path.relpath(fpath, root).replace(os.sep, "/") if fpath else ""
    if rel and not rel.startswith(".."):
        for entry in governs_index(root):
            if any(fnmatch.fnmatch(rel, g) for g in entry["globs"]):
                remind("H-12", f"{rel} is governed by ADR-{entry['adr']} ({entry['title']}). "
                               f"If this change contradicts it, route to /ca:reconcile or "
                               f"/ca:adr — do not drift silently.")
                break

    # H-07: dependency manifest changed — review before committing.
    if DEP_MANIFEST_RE.search(fpath):
        remind("H-07", "Dependency manifest changed. Dispatch dependency-reviewer before "
                       "committing (ORCHESTRATOR §5).")

    # H-09: crypto/TLS pattern — the pre-commit gate will BLOCK until the
    # crypto-compliance gate records a pass; run it now to avoid a commit-time stop.
    if CRYPTO_RE.search(content):
        remind("H-09", "Crypto/TLS pattern detected. Run the crypto-compliance check + dispatch "
                       "auth-crypto-reviewer (no MD5/SHA1/DES/RC4; do not disable TLS "
                       "verification). The commit will block until the gate records a pass.")

    # H-10: possible hardcoded secret.
    if SECRET_RE.search(content):
        remind("H-10", "Possible hardcoded secret. Run the secret-handling check before "
                       "committing. The commit will block until the gate records a pass.")

    # H-13: a user-facing doc was written with an em/en dash used as a prose
    # separator (anti-slop-design core §3.A, the single highest-signal AI tell).
    # Advisory nudge to run the copy self-audit before it ships. Scope is community
    # docs + docs/**, never codeArbiter's own framework bodies (see _sloplib).
    if rel and not rel.startswith("..") and in_antislop_doc_scope(rel):
        hits = find_prose_separator_dashes(content)
        if hits:
            shown = ", ".join(str(h["line"]) for h in hits[:5])
            more = "" if len(hits) <= 5 else f" (+{len(hits) - 5} more)"
            remind("H-13", f"{rel}: em/en dash used as a prose separator on line(s) "
                           f"{shown}{more} (anti-slop-design §3.A). Restructure the prose "
                           f"and run the §3.A/§3.B copy self-audit before committing.")

    sys.exit(0)


if __name__ == "__main__":
    main()
