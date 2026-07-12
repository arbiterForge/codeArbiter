# [Decision] Are Codex MCP file-write tools in scope for the write gate?

> **Codex multi-host support (ADR-0011).** Code under review is on branch `feat/codex-support-m0`, not `main`. ca-codex ships BETA; these are blocking-severity for the affected code but nothing is merged to the default branch yet.

**Type:** decision-required (discussion, not a fix ticket)

**Where:**
- `plugins/ca-codex/hooks/hooks.json:16-55`
- `plugins/ca-codex/hooks/_host.py:163-169`

**Question:**

Codex MCP tools (mcp__*) normalize to OTHER and bypass every write-path guard, so an MCP filesystem/write server can overwrite CONTEXT.md, forge a gate marker, or truncate an audit log with no hook firing. This mirrors an accepted Claude-side gap under the ADR-0010 cooperative-agent trust model, but the dual-host work widens it.

**Options / considerations:**
- State in security-controls.md that MCP-tool writes are out of scope (accept-risk, documented).
- Extend the write-path matchers/normalization to cover mcp__* write tools on Codex.

Decision belongs in security-controls.md / an ADR, not a straight fix.

<!-- dedup_key: appsec:plugins/ca-codex/hooks/hooks.json:mcp-write-bypass · findings: appsec-002 -->
