severity: low

page: getting-started/install.md, overview.md

user_goal: Understand "single-plugin marketplace" framing.

gap: install.md states "codeArbiter self-hosts a single-plugin marketplace from its GitHub repo" — this phrasing is stale per ADR-0007, which explicitly changed marketplace.json's framing from "Single-plugin marketplace" to a two-plugin (now four-plugin) one. This is the install-page-specific instance of finding 01's broader host-count problem.

remediation: Remove or update "single-plugin marketplace" language to reflect the current multi-plugin marketplace.
