---
entity: commands/refactor
related: [feature, fix, skills/refactor]
use_when: "Behavior stays the same and only the shape of the code changes: a rename, extract, inline, move or dedup."
avoid_when: "The current behavior is wrong, which is `/ca:fix`, or the change adds behavior, which is `/ca:feature`."
asks: "The exact surface being restructured and why it is worth doing. It shows the scope table and continues; only a material expansion needs another decision."
produces: "The restructured code, passing characterization tests that show behavior is unchanged, and lint, type and coverage results for the touched surface."
---

## What it does

This is the lane for moving or reshaping code without changing what it does — a rename, an extract,
an inline, a dedup, or swapping an internal implementation for another one that behaves identically.
The proof comes from a measured post-backfill baseline established before restructuring. Add
passing characterization tests where coverage is missing, then preserve their behavioral assertions.
Necessary import or symbol-reference updates may adapt tests to the new structure while retaining
the same oracle. A changed expected result belongs to feature or fix work. Required direct tests,
coverage metrics and critical-path evidence still apply.

The existing request authorizes the named refactor. Present its inspected scope table and
continue; only a material expansion or changed outcome needs another decision.

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
Running the post-backfill parity tests: 37 passed, 0 failed; behavioral assertions preserved.
Exhaustive exact-head GitHub Actions checks remain required before merge.
Coverage on the named surface: unchanged. Parity proven.
```
