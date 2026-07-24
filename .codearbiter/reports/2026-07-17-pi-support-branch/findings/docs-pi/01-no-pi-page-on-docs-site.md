# 01 — No Pi install/quickstart page anywhere on the published docs site

**Severity:** high (user-blockage view)

**Page path:** missing page (site-wide). Checked and confirmed zero mentions of
"Pi" in: `site/src/content/docs/getting-started/install.md`,
`getting-started/compatibility.md`, `getting-started/quickstart.md`,
`guides/uninstalling.md`, `guides/troubleshooting.md`, `guides/the-statusline.md`,
`index.mdx`, `faq.md`, `enforcement.md`. The Starlight sidebar in
`site/astro.config.mjs` (lines 114–182) lists a "Claude Code + Codex" page but
has no Pi entry in any section (Getting Started, Guides, Preview Features,
Concepts, Reference). The Starlight site `description` itself still reads
"Shared enforcement and project-context parity across Claude Code and Codex"
(line 77) — Pi isn't in the site's self-description.

**What the user was trying to do:** A new user who wants to install and use
codeArbiter with Pi opens the docs site (the thing search engines and the
GitHub README link to) and looks for a Pi install path from the landing page
or left nav, as they would for Claude Code or Codex.

**What's missing:** There is no findable path at all. The install instructions,
supported-version list (Pi 0.80.5/0.80.6), trust-flow explanation, and the
`pi install git:arbiterForge/codeArbiter@ca-pi-v<version>` command exist only
in the **repository root** `README.md` (lines 113–130) and
`docs/pi-parity-testing.md` — neither of which is part of the published
Starlight site (`site/src/content/docs/`). A user who only knows the docs site
URL has no way to discover Pi support exists, let alone install it.

**Remediation shape:** Add a Pi install page under
`site/src/content/docs/getting-started/` (e.g. `install-pi.md` or fold into a
tri-host `install.md`), register it in the sidebar in `astro.config.mjs`, and
port the pinned Git-install command, supported-version list, and trust-flow
summary from `README.md` §Pi / `docs/pi-parity-testing.md`.
