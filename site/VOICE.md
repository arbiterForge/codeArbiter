# Voice guide

A working checklist for anyone writing or editing pages under `site/src/content/docs/`.

## The principle

In docs, **"you" is always the reader** — the developer using codeArbiter — never the
model or the orchestrator persona. codeArbiter (or "the plugin") is the thing being
described; the reader is the one being addressed.

The plugin ships an orchestrator persona (`plugins/ca/ORCHESTRATOR.md`) written in a
different register: it addresses the *model*, in second person, as an operating
instruction ("You orchestrate; you do not freelance. You hold the gates; the user holds
the decisions."). That persona-register text is source material, not doc prose. It may
appear in docs only as clearly quoted or embedded source (fenced, attributed, or inside a
source-embed block per the spec's curated-content model) — never rewritten as if it were
addressing the reader, and never left to stand as unmarked page prose.

If a passage reads naturally with "the model" substituted for "you," it is in the wrong
register for a docs page. Rewrite it so "you" resolves only to the reader.

## Register table

| Register | Where | Rules |
|---|---|---|
| **Landing** | `index`, section intros | Punchy allowed. Show, don't claim — back an assertion with a concrete mechanism, example, or link, not adjectives. Max **one** aphorism or negation-triad per page. |
| **Instructional** | Getting Started, Guides | Second person to the reader, imperative mood ("run", "open", "check"). Every step is verifiable — state what the reader should see or get back. No aphorisms. |
| **Explanatory** | Concepts, Enforcement | Plain declarative. Define each term on first use, or link the glossary. Examples are mandatory, not optional color. |
| **Reference** | Generated pages + curated framing | Neutral, front-loaded (lead with the fact, not the setup), template-conformant across all entries in a collection. No personality, no aphorisms. |

## Aphorism budget

Repeated parallel negation triads ("It does not X. It does not Y. It stops; it does not
Z.") are a persona-register cadence. They are budgeted to **landing page and section
intros only, once per page, maximum**. Everywhere else, say the positive rule plainly:
what the gate does, not a list of what it refuses to do.

## Punctuation

Em-dashes are not used as sentence separators in site prose. Restructure with a period, a
comma, a colon, or parentheses instead.

## Terminology anchors

One meaning each, locked to `plugins/ca/ORCHESTRATOR.md` §0.1. Do not drift or invent a
synonym:

- **gate** — a phase exit condition (STOP/BLOCK). Not "checkpoint," not "guardrail."
- **lane** — a sanctioned path through the system (implementation, commit & ship,
  decisions, project & meta). Not "workflow," not "track."
- **STOP / BLOCK** — gate actions. STOP surfaces a decision and waits; BLOCK refuses to
  proceed until fixed.
- **override** — the sanctioned, logged bypass (`/override`). Never "workaround" or
  "skip."
- **Feature Forge** — the two-axis preview-features system. In navigation and
  reader-facing copy it is labeled "Preview Features"; "Feature Forge" is the internal
  name and may appear in explanatory prose once introduced.
- **tribunal** — the deep, rarely-convened whole-codebase audit (`/ca:tribunal`). Not a
  synonym for the routine `/ca:checkpoint` sweep.

## Self-review checklist

Before shipping a page, confirm:

- [ ] Every "you" resolves to the reader, never to the model.
- [ ] No persona-register passage stands as unmarked page prose.
- [ ] At most one aphorism/negation-triad, and only if this is a landing page or section
      intro.
- [ ] Register matches the table above for this page's Diátaxis category.
- [ ] Terminology matches the anchors list — no synonyms substituted.
- [ ] Every instructional step states what the reader should observe.
