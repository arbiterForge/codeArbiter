#!/usr/bin/env python3
# codeArbiter — shared entry-point dispatch helper (jscpd dedup, #320/#334 item 2).
#
# Every hook/tool entry file (doctor.py, pre-edit.py, pre-write.py, pre-read.py,
# git-enforce.py, post-write-edit.py, migration-pass.py, security-pass.py,
# statusline.py, boardsync.py, metrics.py, preview.py, taskwrite.py, babysit.py,
# init-codearbiter.py, ...) carries the identically-shaped `run(host, argv=None)`
# body: wire the process-cached Host live (#257, ADR-0011) via a `set_host`
# callable BEFORE `main` runs, invoke `main` (with or without `argv`), and either
# discard its return (always `return 0`) or propagate it as the exit code —
# jscpd flags this near-duplicate boilerplate across ~15 files. This module
# hoists the shared BODY only; each caller keeps its own `run(host, argv=None)`
# signature/docstring and passes its own `main`/`set_host` callables plus the
# two booleans that capture its file's variant behavior (verbatim-equivalent —
# behavior is unchanged, not "improved").
#
# Zero import-time side effects; pure function; no filesystem/git access.
#
# Public API:
#   dispatch(host, argv, main_fn, set_host_fn, pass_argv, propagate_result) -> int
#       Wire `host` via set_host_fn(host), call main_fn() or main_fn(argv)
#       (per pass_argv), then return that result or 0 (per propagate_result).

def dispatch(host, argv, main_fn, set_host_fn, pass_argv, propagate_result):
    """Shared body of an entry file's `run(host, argv=None)`.

    set_host_fn(host)     -- primes the process-cached Host (#257) BEFORE
                              main_fn runs, so any get_host() call downstream
                              resolves to the SAME instance the caller passed
                              here (no second hostapi.load_host()).
    main_fn()/main_fn(argv) -- per `pass_argv`: some entry files' main() takes
                              no arguments, others take `argv=None`.
    return result or 0    -- per `propagate_result`: some callers discard
                              main_fn's return value (always exit 0, matching
                              the old bare `main()` guard); others propagate
                              main_fn's return value as the exit code
                              (matching the old `sys.exit(main())` guard).
    """
    set_host_fn(host)
    result = main_fn(argv) if pass_argv else main_fn()
    return result if propagate_result else 0
