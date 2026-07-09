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
import hostapi  # noqa: E402 — host seam (ADR-0011)
from _hooklib import (  # noqa: E402
    CRYPTO_RE, SECRET_RE, arbiter_active, get_host, is_ci_path, is_deploy_path,
    project_root, read_input, remind, repo_rel, set_host, utf8_stdio,
)
from _sloplib import find_prose_separator_dashes, in_antislop_doc_scope  # noqa: E402

DEP_MANIFEST_RE = re.compile(
    r"(package\.json|package-lock\.json|yarn\.lock|pnpm-lock\.yaml|requirements\.txt"
    r"|pyproject\.toml|go\.mod|Cargo\.toml)$"
)

# Narrow, high-signal auth patterns for the H-17 advisory (#73). Deliberately
# tight — auth has no clean deterministic trigger, so this nudges on the
# unmistakable markers (passport, jwt verify/sign, framework guards/decorators,
# common auth middleware names) rather than every mention of "login"/"session",
# which would be noise. Advisory only: there is no auth commit gate.
AUTH_RE = re.compile(
    r"(passport\.(?:authenticate|use)"
    r"|\bjsonwebtoken\b|jwt\.(?:verify|sign)"
    r"|@(?:UseGuards|CanActivate|Authorize|RequireAuth)\b"
    r"|\b(?:AuthGuard|requireAuth|isAuthenticated|authenticateUser|withAuth)\b"
    r"|@login_required\b)",
    re.I,
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


def _remind_op(root, op):
    """Run every advisory nudge against ONE canonical file op
    (hostapi.Host.iter_file_ops, ADR-0011 M2). Under Claude Code this receives
    exactly the one op its Write/Edit payload maps to — op["added_text"] is
    content-or-new_string, precisely the pre-seam `ti.get("content") or
    ti.get("new_string")` read — so the Claude reminder path is unchanged. A
    Codex apply_patch envelope fans out to one op per touched file, each
    getting the same per-file nudges over its added lines."""
    fpath = op.get("file_path", "") or ""
    content = op.get("added_text") or ""

    # H-12: the touched file is governed by an accepted ADR — surface it so the
    # recorded decision pushes back at edit time, not at the next checkpoint.
    rel = repo_rel(fpath, root)
    if rel:
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

    # H-15: CI/CD workflow touched — advisory (#73). A bad workflow only runs
    # once merged, so this is a nudge, not a commit gate; dispatch security-reviewer
    # before the PR merges.
    if rel and is_ci_path(rel, root):
        remind("H-15", "CI/CD workflow changed. Dispatch security-reviewer before merging "
                       "(it reviews workflow/secrets/permissions exposure). Advisory — "
                       "not a commit block.")

    # H-16: deployment / IaC manifest touched — advisory (#73). IaC bites only on
    # apply, so this nudges; security-reviewer is the enforcement point at PR.
    if rel and is_deploy_path(rel, root):
        remind("H-16", "Deployment/IaC manifest changed. Dispatch security-reviewer before "
                       "merging (it reviews exposed ports, public ACLs, disabled "
                       "encryption, privilege). Advisory — not a commit block.")

    # H-17: authentication/authorization logic touched — advisory (#73). Narrow,
    # high-signal patterns only; the dangerous crypto/secret primitives are still
    # hard-blocked by H-09b/H-10b at commit time.
    if AUTH_RE.search(content):
        remind("H-17", "Auth/authorization logic detected. Dispatch security-reviewer "
                       "before merging (authn on every protected route; authz at the "
                       "right layer). Advisory — not a commit block.")

    # H-09: crypto/TLS pattern — the pre-commit gate will BLOCK until the
    # crypto-compliance gate records a pass; run it now to avoid a commit-time stop.
    if CRYPTO_RE.search(content):
        remind("H-09", "Crypto/TLS pattern detected. Run the crypto-compliance check + dispatch "
                       "auth-crypto-reviewer (no MD5/SHA1/DES/3DES/RC2/RC4/Blowfish; do not disable "
                       "TLS verification). The commit will block until the gate records a pass.")

    # H-10: possible hardcoded secret.
    if SECRET_RE.search(content):
        remind("H-10", "Possible hardcoded secret. Run the secret-handling check before "
                       "committing. The commit will block until the gate records a pass.")

    # H-13: a user-facing doc was written with an em/en dash used as a prose
    # separator (anti-slop-design core §3.A, the single highest-signal AI tell).
    # Advisory nudge to run the copy self-audit before it ships. Scope is community
    # docs + docs/**, never codeArbiter's own framework bodies (see _sloplib).
    if rel and in_antislop_doc_scope(rel):
        hits = find_prose_separator_dashes(content)
        if hits:
            shown = ", ".join(str(h["line"]) for h in hits[:5])
            more = "" if len(hits) <= 5 else f" (+{len(hits) - 5} more)"
            remind("H-13", f"{rel}: em/en dash used as a prose separator on line(s) "
                           f"{shown}{more} (anti-slop-design §3.A). Restructure the prose "
                           f"and run the §3.A/§3.B copy self-audit before committing.")


def main():
    utf8_stdio()
    root = project_root()
    if not arbiter_active(root):
        sys.exit(0)
    # Host seam (ADR-0011, M2): one canonical op per touched file — exactly one
    # under Claude Code (verdict-identical to the pre-seam single-payload body),
    # one per patched file under Codex.
    for op in get_host().iter_file_ops(read_input()):
        _remind_op(root, op)
    sys.exit(0)


def run(host, argv=None):
    """Host-seam entry point (ADR-0011): the __main__ guard calls this with the
    plugin's loaded Host. Wraps main() unchanged — main() still communicates
    via sys.exit/stdout/stderr, and its return value stays discarded exactly
    as the old bare `main()` guard discarded it (so the process still exits 0
    on a normal fall-through).

    Wires `host` live (#257): primes `_hooklib`'s process-cached Host via
    `set_host()` BEFORE main() runs, so main()'s `get_host()` call resolves
    to the SAME instance the caller passed here — no second
    `hostapi.load_host()`, and `run(fake_host)` genuinely exercises
    `fake_host`."""
    set_host(host)
    main()
    return 0


if __name__ == "__main__":
    sys.exit(run(hostapi.load_host()) or 0)
