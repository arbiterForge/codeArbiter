# PR #1030 release-owner exercise

An independent agent read the exact Claude release skill at
`plugins/ca/skills/release/SKILL.md` without an expected-outcome briefing.
Its raw-byte SHA-256 was
`945fc4ff8f1248766001f50aa314e9fb123a769dc5caffabdaf6811a833d0ffd`.
The agent used a disposable local Git clone and ran selected shipped helpers.

| Path | Observed result |
| --- | --- |
| Unknown target | `show-row no-such-target` exited 2 with `unknown release target`. |
| Unreachable tag | `list-targets`, `show-row ca`, and `clean-tree-status ca` exited 0; the clean-tree output was empty. `last-tag-for-policy` selected `v3.3.0` and exited 0. `verify-tag-ancestor v3.3.0 <fixture>` exited 1, so the procedure stopped before classification or version derivation. |
| Manifest ahead | On clean branch `codex/release-blind-success` at `c2759b228a07712331c64dfef1cd09319cb9a6da`, the `ca` target, tree and tag-ancestry checks exited 0. Manifest `3.4.0` was ahead of reachable `v3.3.0`; `version-greater` exited 0 and the procedure stopped (overall exit 1). |
| Unfootered window | On the same branch, `ca-sandbox` target, tree, tag and ancestry checks exited 0. Manifest and tag were both `0.1.9`. The two-commit window produced a patch bump, but `classify-window` reported `[NEEDS-TRIAGE]` for an unfootered `perf(ci)` commit and exited 1; the procedure stopped (overall exit 1). |

The final clone state was HEAD `c2759b228a07712331c64dfef1cd09319cb9a6da`,
tree `6c392b1824203df3724b83a6ac0e63f3341b3ac6`, branch
`codex/release-blind-success`, with empty porcelain status and worktree and
index diff checks both exiting 0. No source or release-skill defect was found
in these traversed paths.

The exercise did not complete a successful release preview: ten other
matching-version `ca-sandbox` branch windows also classified with exit 1 or
2. Environment PreToolUse H-01 denied disposable fixture setup commands that
mentioned Git commit creation; H-22 denied a read-only hash command naming
`release-targets.md`. No fetch, build, pre-tag command, commit, tag, release,
publication or Back-fill path was exercised. The prior successful-preview
exercise remains historical evidence for its earlier skill hash, and this
record does not renew it.
