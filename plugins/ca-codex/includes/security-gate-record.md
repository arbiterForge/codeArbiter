# Recording the security-gate pass

The shared mechanism by which `crypto-compliance` and `secret-handling` unblock a commit. Referenced
by both skills' "On pass" step; the only difference between them is which commit hook the marker
satisfies (H-09b for crypto/TLS, H-10b for secrets).

**On a genuine independent-review PASS only**, run the producer as one standalone command from
the exact checkout whose staged diff was reviewed. This is the sanctioned PASS-recording route,
not an override:

```bash
python "${PLUGIN_ROOT}/hooks/security-pass.py" --root "<project-root>"
```

Use the host's known Python 3 launcher in place of `python` when it has a different literal name;
do not combine launcher discovery and the producer in one chained shell expression. The producer
ignores an inherited `CLAUDE_PROJECT_DIR`: `--root` is the reviewed source identity. It writes the
shared `.codearbiter/.markers/security-gate-passed` containing that worktree binding plus a digest
of the complete staged diff and diagnostic digests for its sensitive rows. Unstaged and untracked
rows are not absorbed. The
PreToolUse commit hook (**H-09b** for crypto/TLS, **H-10b**
for secrets) blocks any commit whose staged diff touches a guarded pattern until this marker exists
AND matches the exact staged candidate being committed. There is no time window: a pass stays
valid only while that complete staged diff remains byte-for-byte the independently reviewed
candidate. Any added, removed, moved, or changed row blocks, so a pass recorded for one diff cannot
launder a later, different change.

On any BLOCK, self-review, unreadable candidate, stale result, or wrong-worktree result, do **not**
record the pass — the commit stays blocked until the finding is resolved and the independent gate
genuinely passes. A premature or unconditional recording defeats the gate. `/override` is only the
explicit exception for skipping the review; ordinary PASS recording does not use it.
