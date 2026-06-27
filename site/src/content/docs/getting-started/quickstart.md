---
title: Quickstart
description: "Opt a repository into codeArbiter enforcement, run a first command through a gated lane, and watch the commit gate block a real crypto mistake."
---

This tutorial walks three steps in order: opt a repository into enforcement, run a first command through a gated lane, and watch a gate catch a mistake before it reaches version control.

Before starting, complete the plugin install from the [Install](/getting-started/install/) page. Python 3 must be on your `PATH` and `git config user.email` must be set.

## 1. Opt the repo in

Open the target repository in Claude Code and run:

```text
/ca:init
```

`/ca:init` scaffolds `.codearbiter/` at the repo root and routes to the right context populator for your situation:

| You have | Routed to | What it produces |
|---|---|---|
| An existing codebase | `/ca:create-context` | Fills `.codearbiter/` from the source already there |
| A new project, no code yet | `/ca:decompose` | A layered interview that builds `.codearbiter/` from scratch |

When it finishes, confirm the activation flag:

```text
# .codearbiter/CONTEXT.md — first three lines
---
arbiter: enabled
---
```

With `arbiter: enabled` in a properly closed frontmatter block, the next session opens with the orchestrator active and every gate armed. A file missing that flag loads nothing and blocks nothing.

## 2. Run a first command

Send the first real work through a gated lane:

```text
/ca:fix "password reset endpoint throws 500 when token is expired"
```

The `fix` lane routes to the test-first skill. An author agent reads the relevant source, writes a failing test, then writes the minimum implementation to pass it.

As the author writes `auth/reset.py`, the advisory hook fires immediately after the `Write` call:

```text
[H-09] crypto pattern touched in auth/reset.py — run the crypto-compliance gate before commit; the commit will block until a pass is recorded.
```

The author wrote `hashlib.md5(token.encode()).hexdigest()` to hash the reset token. MD5 is in codeArbiter's banned-primitive list. The advisory does not stop the write. It tells you the commit will.

## 3. Observe the gate catch

The tests pass. The author proposes to commit the work. Run it:

```text
/ca:commit
```

The commit gate runs `pre-bash.py` before the `git commit` shell call fires. It reads the staged diff, finds the MD5 line, and exits 2:

```text
BLOCKED [H-09b]: staged diff introduces crypto primitives not covered by a recorded gate pass.
  auth/reset.py +47: token_hash = hashlib.md5(token.encode()).hexdigest()
  Run the crypto-compliance gate or remove the flagged lines before retrying.
```

The `git commit` did not run. The mistake did not reach version control.

To clear the gate, the crypto-compliance skill reviews the flagged lines. MD5 as a token-hashing primitive is a banned pattern. The skill proposes replacing it with `secrets.token_urlsafe()`, which requires no gate pass at all. Once the flagged line is gone and the tests still pass, `/ca:commit` succeeds.

That is the commit gate working as designed: the advisory surfaces the problem at write time, and the hard gate closes before the mistake ships.

For the full catalog of blocking gates, see [Enforcement & Security](/enforcement/). For the ideas behind lanes and gate strengths, see [Concepts](/concepts/).
