#!/usr/bin/env python3
# codeArbiter — shared hook helpers (issues #24, #25).
#
# Replaces the bash+jq hook layer with a cross-platform, fail-LOUD Python
# implementation. The bash hooks began with `which jq > /dev/null || exit 0`,
# so on any machine without jq (e.g. a stock Windows install) EVERY safety gate
# silently evaporated with no signal — the plugin appeared installed but was
# inert. Python is already a plugin dependency (statusline, scaffolder), needs
# no jq, and lets a hook fail loud instead of fail open.
#
# Blocking contract: a PreToolUse hook BLOCKS the tool call by exiting 2 (its
# stderr is fed back to Claude). Exit 0 allows. The prior bash hooks used
# exit 1 — a NON-blocking error under Claude Code's hook contract — so their
# "BLOCKED" gates may not have been stopping the tool at all; this port closes
# that latent gap.
#
# Interpreter launch: hooks.json registers every hook TWICE — `python3 <script>`
# plus a fallback `python3 -c "" || python <script>`. Stock Windows often has no
# real python3 (the Microsoft Store stub exits 9009), which would make every
# gate fail OPEN; the fallback entry probes for python3 and runs `python` only
# when it is absent. A single `python3 x || python x` entry would be wrong: when
# python3 exists and the script BLOCKS (exit 2), `||` would re-run it against a
# drained stdin and the rerun's exit 0 would swallow the block. Separate hook
# entries each receive their own stdin, so the block survives.

import hashlib
import json
import os
import re
import subprocess
import sys
import time

# Crypto/TLS and secret patterns — shared by the post-write reminder (H-09/H-10)
# and the blocking pre-commit gate (H-09b/H-10b) so the two never drift.
# Deliberately NOT matched: crypto.randomUUID / crypto.getRandomValues (benign
# ID generation tripped the gate on routine commits) — the bare `crypto\.`
# catch-all is narrowed to the members that actually sign, encrypt, derive
# keys, or produce security-relevant randomness. bcrypt stays: approved or
# not, a password-hashing change is exactly what crypto-compliance reviews.
CRYPTO_RE = re.compile(
    r"(createHash|createCipher|createHmac|\bmd5\b|\bsha1\b|\brc4\b|\bdes\b|3des"
    r"|\bRSA\b|x509|bcrypt"
    r"|crypto\.(subtle|sign|verify|createSign|createVerify|generateKey"
    r"|publicEncrypt|privateDecrypt|pbkdf2|scrypt|randomBytes|createDiffieHellman)"
    r"|InsecureSkipVerify|verify=False)",
    re.I,
)
SECRET_RE = re.compile(
    r"\b(password|secret|token|api_key|apikey|private_key|passphrase|credential)"
    r"""\s*=\s*["'][^"']{4,}""",
    re.I,
)


ARBITER_RE = re.compile(r"^\s*arbiter:\s*enabled\s*$", re.I)


def utf8_stdio():
    """Force UTF-8 on stdout/stderr. Windows pipes default to the locale code
    page (cp1252), and ORCHESTRATOR.md contains non-cp1252 glyphs — without this
    the SessionStart injection dies with UnicodeEncodeError."""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass


def norm_path(p):
    """Normalize separators so guard regexes match Windows backslash paths."""
    return (p or "").replace("\\", "/")


def frontmatter_enabled(ctx_path):
    """Return (enabled, malformed). `enabled` iff `arbiter: enabled` appears in a
    properly-closed leading YAML frontmatter block. `malformed` iff a block opens
    (`---` on line 1) but never closes — the fail-loud case. A file with no
    frontmatter at all is simply dormant (not malformed)."""
    try:
        with open(ctx_path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:  # noqa: BLE001
        return (False, False)
    lines = text.split("\n")
    if not lines:
        return (False, False)
    first = lines[0].lstrip("﻿")  # tolerate a leading UTF-8 BOM
    if first.strip() != "---":
        return (False, False)  # no opening delimiter — dormant, not malformed
    found = False
    for ln in lines[1:]:
        if ln.strip() == "---":
            return (found, False)  # closing delimiter — decision is final
        if ARBITER_RE.match(ln):
            found = True
    return (False, True)  # opened but never closed — malformed


def arbiter_active(root):
    """True iff this repo opted in (`arbiter: enabled` in CONTEXT.md frontmatter).
    Every enforcement hook gates on this so the plugin is genuinely dormant in
    repos that never opted in — the plugin.json activation contract."""
    enabled, _ = frontmatter_enabled(os.path.join(root, ".codearbiter", "CONTEXT.md"))
    return enabled


def read_input():
    """Parse the hook JSON from stdin. Fail loud (warn) but not closed on error —
    a parse failure must not brick the session by blocking every tool call."""
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception as e:  # noqa: BLE001 — any malformed input
        warn(f"hook input unparseable ({e}); proceeding without enforcement")
        return {}


def tool_input(data):
    return (data or {}).get("tool_input", {}) or {}


def project_root():
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    return os.getcwd()


def line_digest(line):
    """Digest of one added diff line, for the security-gate binding
    (H-09b/H-10b). The gate-pass marker stores these digests instead of being
    an empty `touch`d file, so a recorded pass admits only the exact sensitive
    lines it reviewed — not whatever lands in the next 30 minutes. Trailing
    whitespace is stripped so CRLF translation between worktree and index
    never breaks the match."""
    return hashlib.sha256(line.rstrip().encode("utf-8", "replace")).hexdigest()


def marker_fresh(path, minutes):
    """True if the marker file exists and was touched within `minutes`."""
    try:
        return os.path.isfile(path) and (time.time() - os.path.getmtime(path)) < minutes * 60
    except Exception:  # noqa: BLE001
        return False


def block(tag, msg):
    """BLOCK the tool call: stderr is surfaced to Claude, exit 2."""
    print(f"BLOCKED [{tag}]: {msg}", file=sys.stderr)
    sys.exit(2)


def remind(tag, msg):
    """Non-blocking nudge to stderr."""
    print(f"REMINDER [{tag}]: {msg}", file=sys.stderr)


def warn(msg):
    """Loud degradation/diagnostic breadcrumb — never silent."""
    print(f"codeArbiter hook: {msg}", file=sys.stderr)
