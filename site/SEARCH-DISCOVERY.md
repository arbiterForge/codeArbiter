# codeArbiter search discovery

This file owns the search-discovery contract for codeArbiter. It is not a promise of ranking and it
must not become a keyword-stuffing checklist. Product accuracy, source-backed claims, and a useful
reader journey remain higher priority than search wording.

## Baseline — 2026-09-27

The public site is crawlable and indexed at `https://codearbiter.dev/`. The legacy GitHub Pages
URLs under `https://arbiterforge.github.io/codeArbiter/` currently redirect to the custom domain.
The remaining first-pass problem is authority and identity clarity:

- the GitHub repository is already competitive for branded queries;
- the repository README still linked throughout to the legacy GitHub Pages hostname;
- the homepage title and H1 described the category without naming codeArbiter prominently;
- there was no explicit `WebSite` site-name structured data or `og:site_name`;
- Starlight sitemap generation was enabled through Astro's `site` setting, but no public
  `robots.txt` advertised the sitemap;
- the documentation is technically deep, but common search vocabulary such as "AI coding agent
  guardrails", "agentic coding governance", and "audit trail" was not consistently present on the
  pages that already own those concepts.

This change addresses those signals without manufacturing new claims or publishing thin landing
pages.

## Sector language and search intent

Research on 2026-09-27 found the strongest adjacent material framed around concrete operator
problems rather than product-internal vocabulary:

- OpenAI, "Running Codex safely at OpenAI":
  https://openai.com/index/running-codex-safely/
  — controls, technical boundaries, approvals, and telemetry.
- Anthropic, "Steering Claude Code: when to use CLAUDE.md, skills, hooks, and subagents":
  https://claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more
  — deterministic hooks and permissions as guardrails.
- Anthropic, "How to configure hooks":
  https://claude.com/blog/how-to-configure-hooks
  — enforcing project rules and blocking actions before execution.
- Google Cloud, "What is agentic coding?":
  https://cloud.google.com/discover/what-is-agentic-coding
  — governance, scope control, guardrails, audit trails, and human checks.
- AI Governance Institute, "How do we govern agentic coding assistants and AI developer tools?":
  https://aigovernance.com/playbook/governing-agentic-developer-tools
  — governance of developer agents as a distinct operational risk category.

These sources do not define codeArbiter's claims. They establish the language people use when
searching for the class of problem codeArbiter addresses.

## Query map

Use query families to decide which existing page should answer a search. Do not create one page per
keyword.

| Intent | Representative queries | Canonical codeArbiter page |
|---|---|---|
| Brand/entity | codeArbiter, code arbiter | `/` |
| Definition | what is codeArbiter, what is code arbiter | `/overview/` |
| Category | agentic coding governance, AI coding agent governance | `/`, then `/overview/` |
| Guardrails | AI coding agent guardrails, Claude Code guardrails | `/enforcement/` |
| Audit/evidence | coding agent audit trail, AI coding agent audit trail | `/concepts/auditability/` |
| Host evaluation | Claude Code governance, Codex governance | host-specific getting-started and evidence pages |
| Exact operation | codeArbiter command/skill/hook names | generated reference pages |

When Search Console shows a materially different intent, expand the page that already owns the
concept before creating a new route. A new route needs a distinct reader job, not merely a different
keyword.

## Technical contract

The site must preserve all of the following:

1. Astro `site` remains `https://codearbiter.dev` so Starlight emits canonical URLs and its
   built-in sitemap for the custom domain.
2. `public/robots.txt` allows normal crawling and advertises
   `https://codearbiter.dev/sitemap-index.xml`.
3. The homepage emits one `WebSite` entity whose preferred name is `codeArbiter`, with
   `Code Arbiter` and `codearbiter.dev` as alternatives.
4. The homepage emits a bounded software entity that identifies the project as a free,
   AGPL-3.0-only developer application and links its GitHub repository.
5. `og:site_name` is `codeArbiter`.
6. Public repository and generated documentation links use `https://codearbiter.dev` directly.
   The legacy GitHub Pages host is a redirect compatibility surface, not a link target.
7. The homepage and definition page say plainly what codeArbiter is before relying on internal terms
   such as lanes, gates, SMARTS, or the Feature Forge.

## Search Console runbook

Search Console configuration is intentionally not automated in the repository because Domain
property verification belongs to the domain owner.

1. Create or confirm a **Domain property** for `codearbiter.dev` and verify it with DNS.
2. Submit `https://codearbiter.dev/sitemap-index.xml`.
3. Use URL Inspection for:
   - `https://codearbiter.dev/`
   - `https://codearbiter.dev/overview/`
   - `https://codearbiter.dev/enforcement/`
   - `https://codearbiter.dev/concepts/auditability/`
4. Confirm Google's selected canonical is the `codearbiter.dev` URL for each page.
5. After a material metadata/entity change, request recrawl for the homepage and the directly
   affected high-value page. Do not repeatedly request indexing for unchanged URLs.
6. Track query impressions, clicks, CTR, position, indexed-page count, and canonicalization warnings.
   Separate branded and non-branded queries so brand growth does not hide category-discovery issues.

Initial branded watch list:

- `codearbiter`
- `code arbiter`
- `what is codearbiter`
- `what is code arbiter`

Initial category watch list:

- `agentic coding governance`
- `AI coding agent governance`
- `AI coding agent guardrails`
- `Claude Code guardrails`
- `Claude Code governance`
- `Codex governance`
- `coding agent audit trail`

## External authority hygiene

The GitHub repository currently points its Homepage field at `https://codeArbiter.dev`, which is
correct. Its About description is much less descriptive than the README and homepage; updating that
repository metadata to a concise product definition is a manual repository-setting task, not a
versioned website change.

For npm packages, plugin catalogs, ecosystem directories, conference material, articles, and future
community posts:

- use `https://codearbiter.dev/` as the product/homepage URL;
- use `https://github.com/arbiterForge/codeArbiter` when the destination is specifically source,
  issues, releases, or contribution;
- avoid deliberately creating low-quality backlinks or duplicating the same article across many
  sites.

## Content expansion rule

Do not start with six SEO landing pages. Start with the existing technically authoritative pages.
Use Search Console to identify queries where codeArbiter already receives impressions but the
current page does not satisfy the intent well enough.

A content expansion is justified when all are true:

1. the query represents a real user job relevant to codeArbiter;
2. the existing owning page cannot answer it cleanly without becoming incoherent;
3. the new page can provide substantial original technical value, examples, evidence, or comparison;
4. the page has a clear internal-link path from the owning concept and back to exact source-backed
   documentation.

Likely future investigations, not pre-approved pages:

- how deterministic Claude Code guardrails differ from prompt instructions;
- governing the same repository across Claude Code and Codex;
- what an auditable coding-agent workflow actually records;
- approvals versus hard technical boundaries for coding agents;
- safely operating autonomous coding agents without disabling all permissions.

## Review cadence

Revisit the query map after meaningful Search Console data accumulates and after major host/platform
changes. Search language changes quickly; claims and page ownership must remain grounded in the
current product rather than frozen around today's terminology.
