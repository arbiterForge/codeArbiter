---
title: What Is the Feature Forge
description: "The two-axis model that governs per-feature maturity independently of the version payload: SemVer for the whole plugin, the Feature Forge for each feature's preview or stable status."
journey:
  level: Labs
  time: 5 min
  outcome: "the ability to read version and feature-maturity labels together and decide whether preview risk fits your repository."
  prerequisites:
    - Know the plugin and host version you are running
  proof: "You can name the preview's opt-in, off switch, evidence gap, and stable-promotion bar."
---

SemVer answers one question: did the plugin payload change? A version bump means every user
gets the new payload. It says nothing about whether a given feature inside that payload is
ready to trust by default.

The **Feature Forge** answers the second question, per feature. A feature can ship in
**preview**: opt-in, dormant, off by default. It rides along in a release without changing
anyone's behavior until they turn it on. Once real-world evidence shows it holds up, it gets
promoted to **stable** and becomes on by default. The version says the whole payload moved;
the forge says which individual features have earned trust.

<figure class="ca-art-banner ca-art-banner--forge">
  <img src="/codeArbiter/art/feature-forge.webp" alt="" loading="lazy" />
  <figcaption>Preview is not unfinished. It is shipped work still earning the right to become the default.</figcaption>
</figure>

That is the two-axis model. Read them together and a release is legible: SemVer governs the
whole payload, the Feature Forge governs each feature's maturity.

<figure class="ca-diagram">
  <img src="/codeArbiter/diagrams/two-axis-model.svg" alt="Two-axis labeling model. SemVer governs the whole plugin payload; the Feature Forge governs each feature as preview (opt-in, dormant) or stable (on by default, evidence-promoted)." loading="lazy" />
  <figcaption>Two axes: SemVer for the whole payload, the Feature Forge for per-feature maturity.</figcaption>
</figure>

Promotion is driven by evidence, not by a calendar. A preview feature graduates when its
real-world use shows it is safe to default on, and that judgment is recorded as a tracked
decision rather than assumed. The forge keeps the cost of trying something new low and the
cost of trusting it honest.

## What preview means for you

A preview feature must stay dormant until you opt in. Before enabling one, read its live entry,
identify the environment variable or command that arms it, and note how to turn it off. Start with
the least consequential mode when one exists, such as transcript pruning's `dry` mode. A preview
label is not permission to weaken a hard gate or to accept undocumented spending.

If behavior changes while its opt-in is absent, treat that as a defect. Disable the feature, record
the observed version and host, and follow [Troubleshooting](/guides/troubleshooting/).

After enabling a preview, verify the inverse as well: remove its flag or environment variable, start
a fresh session when startup state is involved, and prove the feature is dormant again. A preview
whose off switch cannot be demonstrated is not safe to evaluate in consequential work.

## Related

- [What's in the Forge](/feature-forge/whats-in-the-forge/): the live list of features currently in preview.
- [Using features still in the Forge](/feature-forge/using-preview-features/): how to turn a preview feature on.
