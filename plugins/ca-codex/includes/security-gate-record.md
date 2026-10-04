# Recording the security-gate pass

The shared mechanism by which `crypto-compliance` and `secret-handling` unblock a commit. Referenced
by both skills' "On pass" step; the only difference between them is which commit hook the marker
satisfies (H-09b for crypto/TLS, H-10b for secrets).

**On a genuine PASS only**, resolve the interpreter once by presence — `PY=python3; { command -v python3 >/dev/null 2>&1 && python3 --version >/dev/null 2>&1; } || PY=python`
— never `python3 X || python X`, which reruns X on any nonzero exit and reports the second run's
code instead of the first's (#577) — then run:

```bash
"$PY" "${PLUGIN_ROOT}/hooks/security-pass.py"
```

It writes `<project-root>/.codearbiter/.markers/security-gate-passed` containing a digest of
every sensitive added line it approved. The PreToolUse commit hook (**H-09b** for crypto/TLS, **H-10b**
for secrets) blocks any commit whose staged diff touches a guarded pattern until this marker exists
AND covers every sensitive line being committed. There is no time window: a pass stays valid for
exactly the lines it reviewed, and any new or changed sensitive line is uncovered and blocks, so a
pass recorded for one diff cannot launder a later, different change.

On any BLOCK, do **not** record the pass — the commit stays blocked until the finding is resolved and
the gate genuinely passes. A premature or unconditional recording defeats the gate.
