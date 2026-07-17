# Gap 02: Command/skill reference pages never show the `$ca-<name>` Codex form

**Severity:** medium

**Page(s):** `site/src/content/docs/reference/index.md`, all 38 pages under `site/src/content/docs/reference/commands/*.md`

## What the user was trying to do

A Codex user who has already learned (from Install/Quickstart) that Codex commands use `$ca-<name>` instead of `/ca:<name>` goes to the Reference catalog to look up a specific command's usage, e.g. `$ca-fix` or `$ca-commit`, to check its arguments/gates.

## What's missing

Every command reference page's "Usage" section is written exclusively in `/ca:<name>` form (e.g. `/ca:init | --stage N | --check`), and the "Source" footer cites only `plugins/ca/commands/<name>.md` — never `plugins/ca-codex/commands/<name>.md`. There is no note anywhere in `/reference/` that these pages are generated from the `ca` (Claude Code) plugin payload and that Codex's `ca-codex` payload uses the `$ca-<name>` entry form with the same behavior. A Codex user has to infer the mapping themselves from the Install page (which shows only `init` and `doctor` as `$ca-` examples) — none of the other 36 commands' Codex spelling is confirmed anywhere in the docs.

## One-line remediation shape

Add one sentence near the top of `reference/index.md` ("commands below are generated from the `ca` plugin; Codex uses the same name with `$ca-` in place of `/ca:`") and, if straightforward, have the generator emit both forms in each command page's Usage block.
