severity: high

page: overview.md, index.mdx (landing), getting-started/install.md

user_goal: Understand what codeArbiter is and which hosts it supports before installing.

gap: Docs describe exactly two hosts — "codeArbiter ships as `ca` for Claude Code and `ca-codex` for Codex" (overview.md) and "Two sibling plugins" (index.mdx hero copy). The repo actually ships four sibling plugins today: `ca`, `ca-codex`, `ca-pi` (Pi host), and `ca-sandbox` (infrastructure plugin) — confirmed in README.md: "four sibling plugins: the three governance hosts (`ca`, `ca-codex`, and `ca-pi`) plus the `ca-sandbox` infrastructure plugin," with generated command counts `ca: 39, ca-codex: 37, ca-pi: 38`. This matches ADR-0007 (ca-sandbox) and ADR-0014 (Pi host support), both accepted. Zero mentions of "pi" or "ca-pi" anywhere in site/src/content/docs/.

remediation: Update overview.md, index.mdx hero/why-gates copy, and install.md to name all current hosts (or explicitly scope the docs site to Claude Code + Codex only, with a clear pointer to README for Pi/sandbox until pages exist).
