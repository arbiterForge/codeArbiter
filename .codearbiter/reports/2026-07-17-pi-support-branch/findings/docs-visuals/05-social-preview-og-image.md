# 05 — No social-preview (og:image) card configured for the docs site

**Value:** High

**Page(s):** `site/astro.config.mjs` (Starlight config — no `head` og:image tags, no `social` preview image), effectively affects every page's link-unfurl in Slack/Discord/Twitter/GitHub.

## What to depict

`astro.config.mjs`'s Starlight block sets `title`, `description`, `logo`, and `favicon`,
but there is no configured Open Graph / Twitter Card image. When someone shares a docs
link (landing page or any deep page) in Slack, Discord, or X, the unfurl will show no
image or a generic fallback. This is a real, high-traffic gap: it's the first visual
impression for every shared link, and codeArbiter's landing page already invests
heavily in a polished hero (`GateCatchTerminal`, `InstallTerminal`, `TrustRow`,
lane-flow and statusline figures) that never gets seen by someone who only sees the
unfurl card.

## Recommended form

A single static social-preview card (1200×630, the standard OG size): logo + wordmark +
tagline ("Shared enforcement and project-context parity across Claude Code and Codex"),
built from the same visual language as the existing landing hero — dark background,
violet accent, monospace terminal-style framing element (echoing `GateCatchTerminal`).
Not a diagram; this is branded static art, closer to a title card than a technical
figure.

## GPT image vs. hand-drawn

Hand-built (SVG exported to PNG, or directly composed in HTML/CSS and screenshotted) —
**not** GPT image generation. This card carries the project's actual logo, wordmark, and
brand palette; those need to be precise and consistent with the existing site assets
(`src/assets/logo.svg`, `theme.css` violet palette), not regenerated/approximated by an
image model. This is squarely the kind of asset the project's anti-slop-design doctrine
warns about if outsourced to a generator — a logo/wordmark card is exactly where a GPT
image would introduce subtle typography, color, or logo-fidelity drift that reads as
unpolished the moment it's compared to the real site.
