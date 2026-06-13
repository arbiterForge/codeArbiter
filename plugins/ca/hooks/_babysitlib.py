"""pr-babysitter config resolution (Feature 2).

A pure config-resolution unit for the pr-babysitter command. This module holds
NO command behavior — only the env-driven resolver that decides whether the
babysitter is enabled and how it reacts to a red gate. The command behavior is
authored as prose in a later task.

Environment variables
---------------------
CODEARBITER_BABYSIT
    Master switch. Accepted "on" spellings (case-insensitive): ``on``, ``true``,
    ``1``. Anything else — including absent, empty, or an unknown value —
    resolves to OFF. Default: OFF (PB-8). Even when set on, the babysitter is
    two-layer gated on arbiter dormancy: it stays OFF unless ``arbiter_active``
    reports the repo opted in (PB-10). It is NEVER auto-enabled.

CODEARBITER_BABYSIT_ONRED
    What to do when the gate goes red. Normalized lowercase; one of ``propose``
    or ``branch``. Any unknown, empty, or absent value resolves to ``propose``.
    Default: ``propose`` (PB-5).
"""

_ON_VALUES = ("on", "true", "1")
_ONRED_VALUES = ("propose", "branch")
_ONRED_DEFAULT = "propose"


def babysit_config(env, root, arbiter_active=None):
    """Resolve the pr-babysitter config from ``env`` (a dict) for ``root``.

    ``env`` and ``root`` are explicit parameters — this resolver never reads or
    mutates ``os.environ``. ``arbiter_active`` is injected (defaulting to
    ``_hooklib.arbiter_active``) so tests can pass a stub for the dormancy gate.

    Returns a dict with at least ``enabled`` (bool) and ``on_red`` (str).
    """
    if arbiter_active is None:
        import _hooklib
        arbiter_active = _hooklib.arbiter_active

    raw = (env.get("CODEARBITER_BABYSIT", "off") or "off").lower()
    switched_on = raw in _ON_VALUES
    # PB-10: two-layer gate — the env switch never overrides arbiter dormancy.
    enabled = switched_on and bool(arbiter_active(root))

    on_red = (env.get("CODEARBITER_BABYSIT_ONRED", "") or "").lower()
    if on_red not in _ONRED_VALUES:
        on_red = _ONRED_DEFAULT  # PB-5

    return {"enabled": enabled, "on_red": on_red}


def main(argv=None):
    """CLI shim: resolve the babysitter config against the live environment and
    print it as one JSON line, so /ca:pr and /ca:watch invoke this single
    resolver instead of re-implementing the flag check in prose (no drift from
    the accepted on|true|1 spellings or the PB-10 dormancy gate). Fail-safe:
    any error degrades to the OFF default and still exits 0 — a broken resolver
    must never become a reason to auto-attach a watcher."""
    import argparse
    import json
    import os

    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--root", default=os.getcwd())
    args = parser.parse_args(argv)
    try:
        cfg = babysit_config(os.environ, args.root)
    except Exception:  # noqa: BLE001
        cfg = {"enabled": False, "on_red": _ONRED_DEFAULT}
    print(json.dumps(cfg))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
