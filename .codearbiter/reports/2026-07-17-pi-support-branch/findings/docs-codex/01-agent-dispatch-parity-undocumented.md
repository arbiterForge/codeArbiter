# Gap 01: Agent-dispatch behavior gap is buried in one table cell, not documented on the pages a Codex user actually visits

**Severity:** high (user-blockage view)

**Page(s):** `site/src/content/docs/reference/index.md`, `site/src/content/docs/reference/agents/*.md` (27 pages), `site/src/content/docs/reference/commands/review.md`, `site/src/content/docs/reference/commands/checkpoint.md`, `site/src/content/docs/reference/commands/tribunal.md`

## What the user was trying to do

A Codex user runs `$ca-review` or `$ca-checkpoint` and, wanting to understand what will happen, opens the Reference section — the Agents catalog lists 27 dispatchable reviewer/author agents (`security-reviewer`, `finding-triage`, `tribunal-appsec-reviewer`, etc.), each with its own page implying it runs as an isolated, tool-scoped subagent.

## What's missing

Nothing on the Reference index, the individual agent pages, or the command pages for `review`/`checkpoint`/`tribunal`/`pr` tells the reader this catalog describes Claude Code's `Task`-tool agent dispatch and does not work the same way on Codex. The only place this is stated at all is one row in one table on `getting-started/claude-code-and-codex.md`:

> "Reviewer roles | Plugin agents can be dispatched | Roles execute inline until Codex agent packaging reaches its later milestone"

That page is not linked from the Reference section, and nothing on `/reference/`, `/reference/agents/*`, or the affected command pages links back to it. A Codex user reading the Agents catalog (which is the canonical, generated, "can never drift" reference per its own description) has no signal that model-tier isolation, the `inherit`/`Haiku`/`Sonnet` tool restrictions, and separate-context dispatch don't apply to their host — they'll assume `$ca-review` spins up the same 27 isolated subagents Claude Code does.

## One-line remediation shape

Add a host-scope callout at the top of `reference/index.md`'s Agents section (and ideally a per-page badge or note on `reference/agents/*.md`) stating the Agents catalog describes Claude Code `Task` dispatch, with a link to the Codex host-differences table, and note that Codex executes the same reviewer roles inline within the current thread.
