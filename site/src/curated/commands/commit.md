---
entity: commands/commit
related: [sprint, skills/tdd]
gates:
  - gate: verification
    when: every invocation
    effect: test, lint, and secret-scan results must all come back clean before anything else runs
  - gate: behavioral proof + diff review
    when: after verification passes
    effect: the change must demonstrate the behavior it claims, and the diff is reviewed line by line before staging
---

## What it does

This is the single entry point for turning staged work into a commit — nothing in codeArbiter
calls `git commit` any other way. Invoking it hands control to a multi-phase check that reads the
repository's current state itself (what's staged, what changed, whether the test suite is green)
rather than taking your word for it, then walks through verification, a behavioral check, and a
diff review before anything is written to history.

## Usage

```
/ca:commit
```

Takes no arguments — everything it needs comes from the current git state.
