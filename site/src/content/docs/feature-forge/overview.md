---
title: What Is the Feature Forge
description: "The two-axis model that governs per-feature maturity independently of the version payload: SemVer for the whole plugin, the Feature Forge for each feature's preview or stable status."
---

SemVer answers one question: did the plugin payload change? A version bump means every user
gets the new payload. It says nothing about whether a given feature inside that payload is
ready to trust by default.

The **Feature Forge** answers the second question, per feature. A feature can ship in
**preview**: opt-in, dormant, off by default. It rides along in a release without changing
anyone's behavior until they turn it on. Once real-world evidence shows it holds up, it gets
promoted to **stable** and becomes on by default. The version says the whole payload moved;
the forge says which individual features have earned trust.

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

## Next

- [What's in the Forge](/feature-forge/whats-in-the-forge/): the live list of features currently in preview.
- [Using features still in the Forge](/feature-forge/using-preview-features/): how to turn a preview feature on.
