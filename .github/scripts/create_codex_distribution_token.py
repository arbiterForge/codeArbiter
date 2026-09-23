#!/usr/bin/env python3
"""Mint the short-lived token for the dedicated Codex distribution GitHub App."""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

API_URL = "https://api.github.com"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def mint(app_id: int, installation_id: int, private_key: Path) -> str:
    if app_id <= 0 or app_id == 15368 or installation_id <= 0:
        raise ValueError("a dedicated GitHub App and installation are required")
    now = int(time.time())
    header = _b64(b'{"alg":"RS256","typ":"JWT"}')
    payload = _b64(json.dumps(
        {"iat": now - 60, "exp": now + 540, "iss": str(app_id)},
        sort_keys=True, separators=(",", ":"),
    ).encode("ascii"))
    unsigned = f"{header}.{payload}".encode("ascii")
    signed = subprocess.run(
        ["openssl", "dgst", "-sha256", "-sign", str(private_key)],
        input=unsigned, check=True, capture_output=True,
    ).stdout
    jwt = f"{header}.{payload}.{_b64(signed)}"
    request = urllib.request.Request(
        f"{API_URL}/app/installations/{installation_id}/access_tokens",
        data=b"{}", method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {jwt}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "codeArbiter-codex-distribution",
        },
    )
    opener = urllib.request.build_opener(_NoRedirect())
    with opener.open(request, timeout=30) as response:
        value = json.load(response)
    token = value.get("token") if isinstance(value, dict) else None
    if not isinstance(token, str) or not token:
        raise ValueError("GitHub App installation token response was malformed")
    return token


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-id", type=int, required=True)
    parser.add_argument("--installation-id", type=int, required=True)
    parser.add_argument("--private-key", type=Path, required=True)
    args = parser.parse_args()
    token = mint(args.app_id, args.installation_id, args.private_key)
    print(f"::add-mask::{token}")
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        raise ValueError("GITHUB_OUTPUT is unavailable")
    with open(output, "a", encoding="utf-8", newline="\n") as stream:
        stream.write(f"token={token}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
