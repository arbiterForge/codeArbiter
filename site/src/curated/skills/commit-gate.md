---
entity: skills/commit-gate
related: [commands/commit, tdd]
gates:
  - gate: permission
    when: every invocation
    effect: an explicit instruction to commit must be on record; "looks good" does not count
  - gate: verification
    when: after classification
    effect: tests, lint, and a secrets scan must all come back clean, plus crypto/secret/migration/CI review where the diff touches those areas, before anything else runs
  - gate: behavioral proof
    when: after verification passes
    effect: a freshly run command must demonstrate the change does what the spec claims — a self-report is not accepted
  - gate: diff review
    when: before staging
    effect: the full staged diff is read for stray files, secrets, incomplete work, and scope creep; any finding unstages the offending files and stops
---

## What it does

This is the only door into version control — nothing else in the project runs `git commit`.
Invoking it (via the commit command) hands control to a sequence of checks that read the
repository's actual state rather than taking your word for it: what's staged, what changed,
whether the suite is green. It walks from confirming you actually asked for a commit through
classification, verification, a behavioral proof, and a full diff review before anything lands.

## Phases

1. Confirm explicit authorization to commit.
2. Confirm the branch is not a protected one.
3. Classify the staged change into a single commit type and flag any database migration.
4. Run tests, lint, and a secrets scan; route through the crypto, secret, migration, or CI/deploy
   review gates when the diff touches those areas.
5. Prove the change's claimed behavior with a fresh command run, not a self-report.
5.5. When a tracked source file drifted, re-scout just that slice and either silently
   re-baseline or route a changed claim into diff review.
6. Read the complete staged diff for stray files, secrets, unfinished work, or scope creep.
7. Run the follow-up harvest, then stage exactly the intended files by explicit path.
8. Compose a Conventional Commits message with a body explaining why.
9. Commit, capturing the resulting SHA, and confirm the tree is clean afterward.

## Exits

A clean run ends in a commit SHA, a clean working tree, and a report of what each gate found. A
BLOCK at any gate halts the commit entirely and surfaces exactly what needs fixing before the
sequence can be re-run.
