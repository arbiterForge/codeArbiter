# Recording the security-gate pass

The shared mechanism by which `crypto-compliance` and `secret-handling` unblock a commit. Referenced
by both skills' "On pass" step; the only difference between them is which commit hook the marker
satisfies (H-09b for crypto/TLS, H-10b for secrets).

**On a genuine PASS only**, run:

```bash
python3 "<plugin-root>/hooks/security-pass.py" || python "<plugin-root>/hooks/security-pass.py"
```

It writes `<project-root>/.codearbiter/.markers/security-gate-passed` containing a digest of
every sensitive added line it approved. The PreToolUse commit hook (**H-09b** for crypto/TLS, **H-10b**
for secrets) blocks any commit whose staged diff touches a guarded pattern until this marker is fresh
(< 30 min) AND covers every sensitive line being committed — a pass recorded for one diff cannot
launder a later, different change through the freshness window.

On any BLOCK, do **not** record the pass — the commit stays blocked until the finding is resolved and
the gate genuinely passes. A premature or unconditional recording defeats the gate.
