---
entity: commands/commands
related: [btw]
---

## What it does

Prints the public command catalog straight from `COMMANDS.md` — the plugin's own single source
of truth for what each `/ca:*` command takes and where it routes. There is no second, hand-copied
table maintained anywhere else in the prompt set, so this command can't drift out of sync with
the real routing table: it renders the file itself, not a memory of it.

Reach for it when you know you want *something* codeArbiter does but not the exact command name
or argument shape.

## Usage

```
/ca:commands
```

Takes no arguments — it always renders the full catalog.

## Example

```text
> /ca:commands

Implementation
  /ca:feature   "description"         Spec-driven feature: brainstorm -> plan -> build -> commit -> finish
  /ca:sprint    ["goal"] [--farm]     Autonomous sprint; every auto-decision SMARTS-scored and logged
  /ca:fix       "bug description"    Fix a defect via tdd, regression-test-first
  ...

Commit & ship
  /ca:commit    (none)                The only path to a commit
  /ca:pr        ["title"]             Finish a branch: open-PR / merge-via-PR / discard
  /ca:watch     <PR number|url|branch> Babysit a PR's CI; never auto-merges
  ...
```
