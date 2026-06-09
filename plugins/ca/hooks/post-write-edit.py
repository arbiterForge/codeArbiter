#!/usr/bin/env python3
# codeArbiter v2 — PostToolUse(Write|Edit) reminders. Scope-touch nudges.
# Python port of post-write-edit.sh (#25): no jq, fails loud.
#
# These are advisory (non-blocking) nudges fired right after a write. The
# load-bearing crypto/secret ENFORCEMENT is the blocking pre-commit gate in
# pre-bash.py (H-09b/H-10b); these reminders surface the touch early so the gate
# isn't a surprise at commit time. Kept: H-07 (dependency review), H-09 (crypto),
# H-10 (secret).

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _hooklib import CRYPTO_RE, SECRET_RE, read_input, remind, tool_input  # noqa: E402

DEP_MANIFEST_RE = re.compile(
    r"(package\.json|package-lock\.json|yarn\.lock|pnpm-lock\.yaml|requirements\.txt"
    r"|pyproject\.toml|go\.mod|Cargo\.toml)$"
)


def main():
    ti = tool_input(read_input())
    fpath = ti.get("file_path", "") or ""
    content = ti.get("content") or ti.get("new_string") or ""

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

    sys.exit(0)


if __name__ == "__main__":
    main()
