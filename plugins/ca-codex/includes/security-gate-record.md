# Recording the security-gate pass

The shared mechanism by which `crypto-compliance` and `secret-handling` unblock a commit. Referenced
by both skills' "On pass" step; the only difference between them is which commit hook the marker
satisfies (H-09b for crypto/TLS, H-10b for secrets).

**On a genuine independent-review PASS only**, run the producer as one standalone command from
the exact checkout whose staged diff was reviewed. This is the sanctioned PASS-recording route,
not an override:

```bash
python "${PLUGIN_ROOT}/hooks/security-pass.py"
```

Use the host's known Python 3 launcher in place of `python` when it has a different literal name;
do not combine launcher discovery and the producer in one chained shell expression. The producer
ignores an inherited `CLAUDE_PROJECT_DIR`: its current working directory is the reviewed source
identity. Do not run it from a launch-time main checkout when the review covered a linked worktree. It writes the
shared `.codearbiter/.markers/security-gate-passed` containing that worktree binding plus a digest
of the complete staged diff and diagnostic digests for its sensitive rows. Unstaged and untracked
rows are not absorbed. The
PreToolUse commit hook (**H-09b** for crypto/TLS, **H-10b**
for secrets) blocks any commit whose staged diff touches a guarded pattern until this marker exists
AND matches the exact staged candidate being committed. There is no time window: a pass stays
valid only while that complete staged diff remains byte-for-byte the independently reviewed
candidate. Any added, removed, moved, or changed row blocks, so a pass recorded for one diff cannot
launder a later, different change. That includes an unrelated staged edit to a non-sensitive file:
the binding is the whole staged candidate, not only its sensitive lines. A commit form that can
absorb unstaged content (for example `git commit -a`) is blocked only when the candidate touches a
guarded pattern; stage the reviewed candidate explicitly and commit that. The producer's success
records the outcome of the review you performed; it does not itself prove a semantic reviewer PASS,
and a binary override, an attributed `/override`, and a reviewer PASS stay distinct records.

On any BLOCK, self-review, unreadable candidate, stale result, or wrong-worktree result, do **not**
record the pass — the commit stays blocked until the finding is resolved and the independent gate
genuinely passes. A premature or unconditional recording defeats the gate. `/override` is only the
explicit exception for skipping the review; ordinary PASS recording does not use it.
