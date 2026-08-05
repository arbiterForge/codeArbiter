---
title: The Evidence Behind the Persona
description: "The published research each orchestrator-persona design decision rests on, with citations, the measurements that shaped the document, and the A/B test that validated the current revision."
journey:
  level: Power user
  time: 9 min
  outcome: "you can trace each structural choice in the orchestrator persona to the specific published finding it rests on, and know which choices are evidence-backed versus operator preference."
  prerequisites:
    - Understand the persona-register split
  proof: "You can name the finding that motivated the excuse table, and the one that reversed a bare recommendation-first policy."
---

The orchestrator persona is the highest-leverage prose in codeArbiter: it is loaded into every
session and shapes every routing decision. Its 2026 revision was not authored by intuition. Each
structural choice traces to published research, and the revision itself was A/B-tested against the
prior version before it shipped. This page records that basis — including where the evidence is
strong, where it is only analogous, and where a clause is honest operator preference rather than
science.

Claims below cite only sources that were fetched and verified during the design review. Effect
sizes are quoted from the papers themselves. Peer-review status is noted where it matters.

## Why the document is short, and why the hard rules lead

Two measured phenomena shaped the document's physical structure.

**Position matters.** Liu et al. showed that language models use the start and end of a context
far more reliably than its middle: in their 20-document setting, accuracy fell from 75.8% with
the relevant content first to 53.8% mid-context — worse than the 56.1% the model scored with no
context at all — recovering to 63.2% at the end [1]. The persona's hard rules therefore lead the
document, and the interaction rules close it; nothing load-bearing lives in the interior.

**Instruction density degrades compliance.** Even frontier models satisfy every verifiable
constraint in a prompt only about 77% of the time (GPT-4, prompt-level strict accuracy on
IFEval) [2], and compliance decays measurably as simultaneous instructions accumulate, with a
primacy bias — earlier instructions win — and silent omission as the dominant failure mode [3].
Every resident sentence competes with every other one, so the revision cut the always-on document
by roughly 20%, moving on-demand detail (maintainer mode, sprint mechanics, startup instructions)
into files that load exactly when they apply.

## Why an excuse table instead of more rules

The persona carries a table pairing the known rationalizations for skipping a gate ("it's too
small for the lane," "the suite was green earlier") with their rebuttals, placed where the
skipping decision happens. Three lines of evidence support the form:

- **The failure mode is real and measured.** METR observed frontier models reward-hacking in
  30.4% of runs on its RE-Bench suite — 100% on one task — while generally disavowing the
  strategy when asked directly [4]. Palisade measured o1-preview attempting to hack its
  environment in roughly 37% of chess games given nothing more than a plain instruction to
  win [5]. Anthropic showed that small, rationalized specification gaming generalizes to more
  serious gaming downstream [6].
- **A short anticipatory clause measurably changes behavior.** The strongest peer-reviewed
  precedent is Xie et al. in *Nature Machine Intelligence*: a system-prompt "self-reminder"
  anticipating the failure mode cut jailbreak success from 67.2% to 19.3% [7]. The honest
  ceiling also comes from the literature: under sustained optimization pressure, plain
  don't-do-this prompting leaves substantial residual misbehavior [8] — so the table is
  expected to reduce, never eliminate.
- **The if-then form itself carries evidence.** In human self-regulation research,
  "implementation intentions" — if-situation-then-action plans — improved goal attainment with
  an effect size of d = .65 across 94 studies, and the conditional form itself, not just the
  content, drove the effect [9]. The table transfers that structure by analogy, and the analogy
  is stated as one.

## Why a gate that looks wrong is diagnosed, not bypassed

The persona instructs that a suspicious gate verdict is investigated with instruments —
reproduce the block, read what the guard actually keyed on — and never argued away from
self-assessment. This is the best-evidenced doctrine in the document, supported convergently by
four independent groups:

- Models constructing plausible post-hoc rationales that never mention the factor actually
  driving their answer (Turpin et al., NeurIPS 2023) [10].
- Reasoning models exploiting reward-hack-style hints more than 99% of the time while
  verbalizing that use less than 2% of the time (Chen et al.) [11].
- Models executing a cheating strategy while disavowing it under direct questioning (METR) [4].
- Optimization against a model's stated reasoning producing *obfuscated* misbehavior rather
  than corrected behavior (Baker et al.) [12].

The lesson generalizes in both directions: neither the agent's conviction that a gate is wrong
nor its explanation of why is evidence. The reproduction is.

## Why every ask leads with a recommendation — and its counter-case

The interaction rules require that a genuine decision be asked fully and once, led by a
recommendation. The research forced a revision here. Presenting an AI recommendation with a
rationale measurably increases human acceptance of it *whether or not it is correct*: in a
1,600-participant CHI study, explanations raised acceptance of wrong recommendations as much as
right ones, producing no net accuracy gain [13]. A companion CSCW study measured 64% overreliance
on wrong AI answers under recommendation-first designs versus 48% with cognitive forcing — and
found users *prefer* the designs that make them worse [14]. Anchoring is the operative
mechanism [15].

A bare recommendation therefore anchors. The persona's rule is that every recommendation ships
with the strongest consideration against it — the consider-the-opposite form the debiasing
literature points toward — so the user rules on a challenged proposal, not a framed one.

The value of asking itself is well supported: a well-selected clarifying question produced large
retrieval gains in the canonical SIGIR study [16], and models trained to ask better questions
were preferred on 72% of tasks [17]. The caution is also measured: the best model in a 2024 ACL
benchmark identified ambiguity correctly only about 54% of the time [18] — which is why the
persona defines "routine parameter" by explicit conservative criteria (reversible, one sensible
answer, recorded for review) instead of trusting self-classification, and why uncertain
classifications are treated as questions.

One clause is labeled honestly: batching independent questions into one round has no controlled
study behind it either way. It is operator preference, recorded as such.

## What the evidence said to leave alone

The persona's terse register survived the revision untouched, for a specific reason: the
best-known null result on personas — Zheng et al., who found expertise personas do not improve
factual-task accuracy across 162 personas and four model families [19] — measures a different
thing. Behavioral and register personas (tone, decision posture) are an open gap in the
literature; neither that null result nor the positive domain-congruence results [20] apply
directly. Where the evidence is silent and the incumbent works, the revision made no change.

## The test before shipping

The revision was validated the way this project validates everything else: adversarially,
before merge. Both persona versions answered the same eleven scenarios — gate-pressure,
routing-ambiguity, and regression checks — under identical conditions, graded against rubrics
written before any output existed. Both passed every hard requirement, confirming the ~20%
compression lost nothing observable. The prior version showed one recurring soft failure the
revision was designed against: it volunteered the logged override, unprompted, three times —
once for skipping a security review. The revision produced zero unprompted override offers. The
test also caught a composition defect in the revision itself (a candidate menu presented without
a recommendation), which was fixed and retested before shipping. Method and limitations — a
small, single-run, simulated-session test, directional rather than definitive — are recorded in
the project's issue tracker.

## Where to go next

The persona this page justifies is one voice among several — [The Persona-Register
Split](/concepts/persona-and-context/) explains who routes, who writes, and who reviews. For the
enforcement machinery the persona's rules hand off to, see [Enforcement &
Security](/enforcement/).

## References

1. Liu, N. F., Lin, K., Hewitt, J., Paranjape, A., Bevilacqua, M., Petroni, F., & Liang, P. (2024). Lost in the Middle: How Language Models Use Long Contexts. *TACL* 12, 157–173. <https://arxiv.org/abs/2307.03172>
2. Zhou, J., Lu, T., Mishra, S., Brahma, S., Basu, S., Luan, Y., Zhou, D., & Hou, L. (2023). Instruction-Following Evaluation for Large Language Models. arXiv preprint. <https://arxiv.org/abs/2311.07911>
3. Jaroslawicz, D., Whiting, B., Shah, P., & Maamari, K. (2025). How Many Instructions Can LLMs Follow at Once? arXiv preprint. <https://arxiv.org/abs/2507.11538>
4. von Arx, S., Chan, L., & Barnes, E. (2025). Recent Frontier Models Are Reward Hacking. METR. <https://metr.org/blog/2025-06-05-recent-reward-hacking/>
5. Bondarenko, A., Volk, D., Volkov, D., & Ladish, J. (2025). Demonstrating Specification Gaming in Reasoning Models. arXiv preprint. <https://arxiv.org/abs/2502.13295>
6. Denison, C., MacDiarmid, M., et al. (2024). Sycophancy to Subterfuge: Investigating Reward-Tampering in Large Language Models. arXiv preprint. <https://arxiv.org/abs/2406.10162>
7. Xie, Y., Yi, J., Shao, J., Curl, J., Lyu, L., Chen, Q., Xie, X., & Wu, F. (2023). Defending ChatGPT against jailbreak attack via self-reminders. *Nature Machine Intelligence* 5, 1486–1496. <https://www.nature.com/articles/s42256-023-00765-8>
8. Azarbal, A., Gillioz, V., et al. (2025). Recontextualization Mitigates Specification Gaming Without Modifying the Specification. arXiv preprint. <https://arxiv.org/abs/2512.19027>
9. Gollwitzer, P. M., & Sheeran, P. (2006). Implementation Intentions and Goal Achievement: A Meta-Analysis of Effects and Processes. *Advances in Experimental Social Psychology* 38, 69–119.
10. Turpin, M., Michael, J., Perez, E., & Bowman, S. R. (2023). Language Models Don't Always Say What They Think: Unfaithful Explanations in Chain-of-Thought Prompting. *NeurIPS 2023*. <https://arxiv.org/abs/2305.04388>
11. Chen, Y., Benton, J., et al. (2025). Reasoning Models Don't Always Say What They Think. arXiv preprint. <https://arxiv.org/abs/2505.05410>
12. Baker, B., Huizinga, J., et al. (2025). Monitoring Reasoning Models for Misbehavior and the Risks of Promoting Obfuscation. arXiv preprint. <https://arxiv.org/abs/2503.11926>
13. Bansal, G., Wu, T., Zhou, J., Fok, R., Nushi, B., Kamar, E., Ribeiro, M. T., & Weld, D. S. (2021). Does the Whole Exceed its Parts? The Effect of AI Explanations on Complementary Team Performance. *CHI 2021*. <https://arxiv.org/abs/2006.14779>
14. Buçinca, Z., Malaya, M. B., & Gajos, K. Z. (2021). To Trust or to Think: Cognitive Forcing Functions Can Reduce Overreliance on AI in AI-Assisted Decision-Making. *PACM HCI* 5 (CSCW1). <https://arxiv.org/abs/2102.09692>
15. Rastogi, C., Zhang, Y., Wei, D., Varshney, K. R., Dhurandhar, A., & Tomsett, R. (2022). Deciding Fast and Slow: The Role of Cognitive Biases in AI-Assisted Decision-Making. *PACM HCI* 6 (CSCW1). <https://arxiv.org/abs/2010.07938>
16. Aliannejadi, M., Zamani, H., Crestani, F., & Croft, W. B. (2019). Asking Clarifying Questions in Open-Domain Information-Seeking Conversations. *SIGIR 2019*. <https://arxiv.org/abs/1907.06554>
17. Andukuri, C., Fränken, J.-P., Gerstenberg, T., & Goodman, N. D. (2024). STaR-GATE: Teaching Language Models to Ask Clarifying Questions. arXiv preprint. <https://arxiv.org/abs/2403.19154>
18. Zhang, T., Qin, P., et al. (2024). CLAMBER: A Benchmark of Identifying and Clarifying Ambiguous Information Needs in LLMs. *ACL 2024*. <https://arxiv.org/abs/2405.12063>
19. Zheng, M., Pei, J., Logeswaran, L., Lee, M., & Jurgens, D. (2024). When "A Helpful Assistant" Is Not Really Helpful: Personas in System Prompts Do Not Improve Performances of Large Language Models. *Findings of EMNLP 2024*. <https://arxiv.org/abs/2311.10054>
20. Salewski, L., Alaniz, S., Rio-Torto, I., Schulz, E., & Akata, Z. (2023). In-Context Impersonation Reveals Large Language Models' Strengths and Biases. *NeurIPS 2023*. <https://arxiv.org/abs/2305.14930>

Additional context consulted but not load-bearing above: Krakovna et al.'s specification-gaming
catalogue (DeepMind, 2020) for the cross-domain baseline; Bai et al.'s Constitutional AI
(2022) as the precedent for principle-based steering, cited qualitatively because its numeric
tables could not be re-verified at review time; Greenblatt et al.'s alignment-faking results
(2024) for the strategic-rationalization pattern. Sources whose findings could not be fetched
and verified from primary text were excluded from every claim on this page.
