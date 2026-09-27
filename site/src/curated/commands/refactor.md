---
entity: commands/refactor
related: [feature, fix, skills/refactor]
gates:
  - gate: named surface
    when: before the restructure starts
    effect: the exact files, functions, or methods in scope must be stated; a vague target like "the auth module" is rejected
  - gate: parity coverage
    when: before any code moves
    effect: pre-existing tests must already cover the named surface, with at least one direct test per public method — an under-covered surface halts and backfills first
  - gate: parity verification
    when: after the restructure
    effect: impact-bounded pre-existing parity tests pass locally without edits; exhaustive exact-head proof runs in hosted CI before merge
---

## What it does

This is the lane for moving or reshaping code without changing what it does — a rename, an extract,
an inline, a dedup, or swapping an internal implementation for another one that behaves identically.
The proof that nothing changed comes from tests that already existed before the restructure started;
editing one of those tests to make it pass again is treated as a behavior change in disguise, not
valid proof. If the surface isn't covered well enough to prove parity, the work pauses to add tests
first. And if what comes out the other end would actually classify as new behavior, the whole thing
reroutes to feature work instead of finishing as a refactor.

## Usage

A plain-language request for behavior-preserving restructure selects the same owning
skill. `/ca:refactor` remains an explicit entry generated from that skill, not a
second independently maintained procedure. The gates below still apply.

```
/ca:refactor <surface and motivation>
```

State the exact surface being restructured and why it's worth doing — both parts are required.

## Example

```text
> /ca:refactor extract the retry logic in OrderClient.submit() into a shared withRetry() helper — three other clients duplicate it

Surface locked: OrderClient.submit(), PaymentClient.submit(), InventoryClient.reserve().
Parity coverage: each has a direct test; PaymentClient's covers only the success path — backfilling
a failure-path test before continuing.
[backfill test added, suite green]
Applying the extraction... no new branches, no new error paths.
Running affected parity tests unmodified: 37 passed, 0 failed; no pre-existing parity test files modified.
Exhaustive exact-head GitHub Actions checks remain required before merge.
Coverage on the named surface: unchanged. Parity proven.
```

## When to reach for it

Reach for `/ca:refactor` when the behavior is staying the same and only the shape of the code is
changing. If the motivation is "the current behavior is wrong," that's `/ca:fix`; if it adds new
behavior, that's `/ca:feature`.
