---
title: Quickstart
description: "Opt a repository into codeArbiter enforcement, run a first command through a gated lane, and watch the commit gate block a real crypto mistake."
---

This tutorial walks three steps in order: opt a repository into enforcement, run a first command through a gated lane, and watch a gate catch a mistake before it reaches version control.

Before starting, complete the plugin install from the [Install](/getting-started/install/) page. Python 3 must be on your `PATH` and `git config user.email` must be set.

## 1. Opt the Repo In

Open the target repository in Claude Code and run:

```text
/ca:init
```

`/ca:init` scaffolds `.codearbiter/` at the repo root and routes to a context populator for your situation. See [Opt a Repository In](/guides/opt-in-a-repo/) for the two routing paths and how to confirm the `arbiter: enabled` activation flag. With that flag set in a properly closed frontmatter block, the next session opens with the orchestrator active and every gate armed.

## 2. Run a First Command

Send the first real work through a gated [lane](/glossary/#lane):

```text
/ca:fix "webhook retries create duplicate payment records"
```

The `fix` lane routes to the test-first skill. An author agent reads the relevant source, writes a failing test, then writes the minimum implementation to pass it.

As the author writes `payment.ts`, the advisory hook fires immediately after the `Write` call. You should see it in the tool-call output before the write is even done:

```text
REMINDER [H-09]: Crypto/TLS pattern detected. Run the crypto-compliance check + dispatch auth-crypto-reviewer (no MD5/SHA1/DES/3DES/RC2/RC4/Blowfish; do not disable TLS verification). The commit will block until the gate records a pass.
```

The author wrote `createHash("md5")` to derive an idempotency key from the payment payload. MD5 is in codeArbiter's banned-primitive list. The advisory does not stop the write — it tells you the commit will. (The scan behind this gate is language-agnostic: a Python `hashlib.md5` call trips the identical H-09/H-09b pair.)

## 3. Observe the Gate Catch

The tests pass. The author proposes to commit the work. Run it:

```text
/ca:commit
```

The commit gate runs `pre-bash.py` before the `git commit` shell call fires. It reads the staged diff, finds the MD5 line, and exits 2. You should see the commit rejected:

```text
BLOCKED [H-09b]: This commit introduces crypto/TLS changes, but no security-gate pass is recorded (.codearbiter/.markers/security-gate-passed). Run the crypto-compliance gate (it records the pass), then commit.
```

The `git commit` did not run. The mistake did not reach version control.

To clear the gate, the crypto-compliance skill reviews the flagged line. MD5 as a hashing primitive is a banned pattern; the skill proposes replacing it with `createHash("sha256")`, which is on the approved list. Once the fix lands and the tests still pass, run `/ca:commit` again — you should see it succeed, with a line confirming the security-gate pass was recorded and bound to the changed line.

That is the commit gate working as designed: the advisory surfaces the problem at write time, and the hard gate closes before the mistake ships.

For the full catalog of blocking gates, see [Enforcement & Security](/enforcement/). For the ideas behind lanes and gate strengths, see [Concepts](/concepts/).
