#!/usr/bin/env python3
# codeArbiter — off-hot-path update-check refresh (AC-3/AC-4).
#
# Thin entry point. session-start.py spawns this DETACHED so the GitHub
# Releases fetch never blocks SessionStart's stdout injection (issue #194's
# constraint): the parent hook returns immediately without ever awaiting this
# process. This script may be launched once per session, but the network call
# inside _updatelib.refresh_if_stale() is itself gated to AT MOST once per day
# by the cached `checked_at` — a same-day re-launch is a single cheap file
# read, not a fetch.
#
# Fail-silent by construction (mirrors _updatelib.refresh_if_stale): any error
# here — missing plugin dir, filesystem, network — degrades to "cache
# unchanged", never a traceback. The spawner also discards this process's
# stdout/stderr, so even an unswallowed print would go nowhere; the try/except
# below exists so the process still exits 0 either way.

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hostapi  # noqa: E402 — host seam (ADR-0011)


def main():
    try:
        import _updatelib
        _updatelib.refresh_if_stale()
    except Exception:  # noqa: BLE001 — detached refresh must never surface an error
        pass


def run(host, argv=None):
    """Host-seam entry point (ADR-0011): the __main__ guard calls this with the
    plugin's loaded Host. Wraps main() unchanged — the refresh stays fail-silent
    and the process still exits 0 either way, exactly as the prior module-level
    try/except did."""
    main()
    return 0


if __name__ == "__main__":
    sys.exit(run(hostapi.load_host()) or 0)
