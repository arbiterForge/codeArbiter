#!/usr/bin/env python3
"""Check the distinct Codex GitHub App identities before minting either token.

This step receives only public numeric IDs. Each private key stays in its own
token-mint process environment and is validated by that required mint step.
"""

from __future__ import annotations

import os
import re
import sys


def _positive_id(value: str | None, label: str) -> int:
    if not isinstance(value, str) or re.fullmatch(r"[1-9][0-9]{0,18}", value) is None:
        raise ValueError(f"{label} must be a canonical positive integer")
    return int(value)


def validate(values: dict[str, str]) -> None:
    publisher = _positive_id(values.get("PUBLISHER_APP_ID"), "publisher App ID")
    _positive_id(values.get("PUBLISHER_INSTALLATION_ID"), "publisher installation ID")
    verifier = _positive_id(values.get("VERIFIER_APP_ID"), "verifier App ID")
    _positive_id(values.get("VERIFIER_INSTALLATION_ID"), "verifier installation ID")
    if publisher == 15368 or verifier == 15368:
        raise ValueError("dedicated Codex Apps are required")
    if publisher == verifier:
        raise ValueError("publisher and verifier App IDs must be distinct")


def main() -> int:
    try:
        validate(os.environ)
    except ValueError as exc:
        print(f"Codex distribution identity check failed: {exc}", file=sys.stderr)
        return 1
    print("Codex distribution App identities are distinct and configured")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
