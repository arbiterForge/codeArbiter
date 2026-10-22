#!/usr/bin/env python3
"""CI20 direct executable smoke: unqualified test input, never an installation.

Runs only on a native CI test consumer after validating the exact source, run,
toolchain and binary bytes. No release.json, installed ArtifactClient, receipt,
package assembly, or native_tested assertion is involved.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from ci20_candidate import ci_identity, verify

PROTOCOL = "codearbiter.artifact-api/0.1.0"
MAX_STDOUT = 65_536


def direct_smoke(binary: Path) -> None:
    """Exercise the actual native executable, not the installed host bridge."""
    with tempfile.TemporaryDirectory(prefix="ci20-direct-") as temporary:
        root = Path(temporary).resolve(strict=True)
        # The capabilities endpoint is read-only and must not create a store.
        invocation = [str(binary), "capabilities", "--root", str(root)]
        env = {name: os.environ[name] for name in ("SystemRoot", "WINDIR") if name in os.environ}
        result = subprocess.run(invocation, cwd=root, env=env,
                                capture_output=True, timeout=30, check=False)
        if (result.returncode != 0 or len(result.stdout) > MAX_STDOUT
                or len(result.stdout.splitlines()) != 1):
            raise ValueError("direct native capabilities smoke failed")
        def unique(pairs):
            output = {}
            for key, value in pairs:
                if key in output:
                    raise ValueError("duplicate native response key")
                output[key] = value
            return output
        response = json.loads(result.stdout, object_pairs_hook=unique,
                              parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        if (not isinstance(response, dict)
                or response.get("protocol") != PROTOCOL
                or response.get("operation") != "capabilities"
                or response.get("ok") is not True
                or not isinstance(response.get("result"), dict)
                or response.get("error") is not None):
            raise ValueError("direct native capabilities protocol mismatch")
        if list(root.iterdir()):
            raise ValueError("read-only direct native capabilities mutated fixture")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    args = parser.parse_args()
    try:
        identity = ci_identity("verify")
        binary = verify(args.candidate, identity)
        direct_smoke(binary)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as error:
        raise SystemExit("unqualified direct smoke refused: " + str(error)) from error
    print("Direct native CI test input passed; still UNQUALIFIED")


if __name__ == "__main__":
    main()
