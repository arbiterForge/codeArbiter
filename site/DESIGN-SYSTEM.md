# Documentation design system

This is the contract for codeArbiter's public documentation. It exists so the landing page,
hand-authored guidance, and generated reference feel like one product without turning every page
into a custom layout.

## Product principles

1. **Proof before promise.** A claim about enforcement is paired with a mechanism, transcript,
   dated verification record, or source link.
2. **One page, one reader outcome.** A reader should know why the page matters, how to act on it,
   what success looks like, and where to go next.
3. **Source-visible reference.** Generated pages add reader orientation but retain the exact shipped
   source in a collapsed block. Curated prose never replaces the implementation contract.
4. **Local-first delivery.** Fonts and production assets ship with the static build. The site makes
   no runtime request to a font or analytics service.
5. **Quiet confidence.** Gold identifies decisions, gates, and primary actions. It is not a general
   highlight color. Motion explains sequence and is removed under `prefers-reduced-motion`.

## SMARTS decisions

### Landing shell

| Option | Scalable | Maintainable | Available | Reliable | Testable | Securable |
|---|---|---|---|---|---|---|
| Keep the home page inside the documentation sidebar | Adequate | Strong | Strong | Strong | Strong | Strong |
| Use a full-width Starlight splash and keep the docs shell for inner pages | Strong | Strong | Strong | Strong | Strong | Strong |
| Build a separate marketing application | Strong | Weak | Adequate | Weak | Weak | Adequate |

**Decision:** use Starlight's splash shell. It creates a first-class product entrance while keeping
one build, one navigation system, and one link/search index.

### Typography

| Option | Scalable | Maintainable | Available | Reliable | Testable | Securable |
|---|---|---|---|---|---|---|
| System fonts only | Adequate | Strong | Strong | Strong | Strong | Strong |
| Vendor reviewed variable-font subsets with their licenses | Strong | Strong | Strong | Strong | Strong | Strong |
| Runtime Google Fonts request | Adequate | Adequate | Weak | Weak | Adequate | Weak |

**Decision:** bundle the Latin subsets of Manrope Variable and JetBrains Mono Variable as static
assets, with their complete OFL-1.1 license texts beside them. They add no package or production
network dependency and give product and technical surfaces distinct voices.

### Reference orientation

| Option | Scalable | Maintainable | Available | Reliable | Testable | Securable |
|---|---|---|---|---|---|---|
| Hand-edit generated pages | Weak | Weak | Strong | Weak | Weak | Adequate |
| Keep source embeds only | Adequate | Strong | Strong | Strong | Strong | Strong |
| Add collection-specific orientation in the generator and keep source embeds | Strong | Strong | Strong | Strong | Strong | Strong |

**Decision:** commands state how to invoke them in Claude Code and Codex; skills state that the
orchestrator routes to them; agents state that an owning skill dispatches them. The generator owns
that distinction across the full collection.

## Tokens and primitives

Shared tokens and primitives live in `src/styles/design-system.css`.

- **Typography:** `--ca-font-sans`, `--ca-font-mono`, and the `--ca-text-*` scale.
- **Spacing:** `--ca-space-1` through `--ca-space-9`.
- **Surfaces:** `--ca-bg`, `--ca-bg-raised`, `--ca-bg-panel`, `--ca-line`.
- **Meaning:** `--ca-brand` for gates/actions, `--ca-positive` for verified state,
  `--ca-danger` for blocks, and `--ca-preview` for Feature Forge status.
- **Components:** `.ca-button`, `.ca-panel`, `.ca-pill`, `.ca-eyebrow`, and
  `.ca-reference-lead`.

Page-specific selectors belong in `src/styles/landing.css` or a named component. Do not add
one-off colors, font stacks, or spacing values to content files.

## Page completeness contract

### Getting Started

Answer: what must be installed, what command to run, what the reader should observe, how to verify
enforcement, and where host behavior differs.

### Guides

State the outcome and prerequisites, give an ordered procedure, show observable success, cover the
likely block or recovery path, and link the exact command reference.

### Concepts

Explain the problem, the mental model, one concrete example, how the concept changes real use, its
limits, and the next practical page. A definition alone is incomplete.

### Generated reference

- **Command:** invocation, purpose, example, gates, alternatives, exact source.
- **Skill:** routing context, phases or behavior, exits, gates, related commands, exact source.
- **Agent:** dispatch context, tool/model boundary, output or findings contract, related routes,
  exact source.
- **Hook gate:** tag, condition, effect, exact emitted message, source location.

### Trust and lifecycle

Compatibility, enforcement, privacy/network behavior, uninstall, troubleshooting, changelog, and
license must be findable without reading the landing page top to bottom.

## Required verification

Before documentation changes ship:

1. Generate the reference and build the static site.
2. Run unit tests, typecheck, and the post-build link audit.
3. Crawl every sitemap route for HTTP success, one H1, a description, and image alt text.
4. Inspect the landing, one page from each hand-authored category, and one page from each generated
   collection at desktop and mobile widths.
5. Test keyboard focus, search, reduced motion, and horizontal overflow.
