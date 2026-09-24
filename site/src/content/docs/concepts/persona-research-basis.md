---
title: The Evidence Behind the Persona
description: "Read the historical research rationale without treating old benchmarks, design analogies or a bounded prompt comparison as current codeArbiter performance evidence."
journey:
  level: Reference
  time: "10 minutes"
  outcome: "Distinguish published research, a historical product experiment, an implementation choice and evidence about today's installed workflow."
  prerequisites:
    - The Persona-Register Split
  proof: "You can state the evidence category and scope of a rationale without promoting it into a current efficacy guarantee."
---

This page preserves the attribution behind an earlier persona revision. **It is a historical
research rationale, not a live benchmark or certification of today's models, adapters or prompts.**
The previous narrative is retained at
[the exact source snapshot](https://github.com/arbiterForge/codeArbiter/blob/aebee1bb753d29e34030ee22c98c9eb8fabb1752/site/src/content/docs/concepts/persona-research-basis.md).
Its effect sizes, model versions and project-test report belong to that historical claim set.
They were not rerun or independently revalidated in this documentation overhaul.

The reference list below preserves the original authors, titles and links. A citation identifies
where a rationale came from; it does not establish that a particular intervention improves
codeArbiter in its current environment. Use [role separation](/concepts/persona-and-context/)
for current source-defined behavior and [Enforcement & Security](/enforcement/) for the control
boundaries that a prompt alone cannot establish.

## Why the document is short, and why the hard rules lead

The earlier rationale connected prompt placement to long-context retrieval research, particularly
Liu and colleagues [1], and instruction load to instruction-following evaluations [2, 3]. Its
design response was to keep standing instructions focused and move situational detail to the
point of use. That is the provenance of the design choice, not proof of a fixed safe prompt size.

A retrieval benchmark, an instruction benchmark and a governed coding task do not ask identical
questions. Do not import an old percentage into a claim that a present coding model will follow
all instructions or notice every middle-of-context rule. The operational check is whether the
actual required context reached the worker and the relevant evidence came back.

## Why an excuse table instead of more rules

The original narrative used specification-gaming and self-reminder work [4–8] to motivate brief
reminders at a likely failure point. It also drew an explicit analogy from human implementation
intentions [9]. These are different evidence categories: a model intervention in one study,
an observed failure in another environment, and a human-behavior analogy.

They can inform a prompt design. They cannot establish immunity to rationalization or replace a
blocking control. Nor does a human effect size become a predicted model improvement. Keep the
analogy labelled and test the actual candidate before changing a product claim.

## Why a gate that looks wrong is diagnosed, not bypassed

The historical rationale cited work on unfaithful explanations, hidden use of hints and obfuscated
misbehavior [4, 10–12]. The product lesson it drew was to inspect an observable reproduction rather
than accepting the model's confidence about why a gate fired.

That distinction remains useful as an inspection method: capture the condition, input, source and
result, then diagnose the matching control. A gate can have a defect, and the model can describe a
plausible cause, without either statement establishing that bypass is authorized. See
[Override a gate safely](/guides/overriding-a-gate/) for the actual boundary.

## Why every ask leads with a recommendation, and with its counter-case

The earlier research record connected recommendation-first presentation and overreliance to
human decision-support studies [13–15], and question quality to clarification research [16–18].
Its design response was to expose the strongest counter-case and ask genuine forks rather than
hiding them behind a confident answer.

Those studies do not prove one universal interface for all users and decisions. Batching
independent questions was explicitly an operator preference in the original account. Preserve
that label rather than calling every interaction rule research-proven. A routine parameter,
an unresolved requirement and a consequential decision still need their own treatment under the
owning workflow. [SMARTS](/concepts/smarts/) explains comparison and delegated decision scope.

## What the evidence said to leave alone

The original record distinguished factual-task persona studies [19, 20] from behavioral register.
That distinction is important: a result about expertise personas is not automatically a result
about terse language, routing discipline or governance. An unstudied effect is unknown, not proven
beneficial merely because its exact opposite has not been measured.

The role's tools, instructions, context and return contract should therefore be inspected
separately. A role name or confident voice supplies neither security isolation nor verification.

## The same evidence under the brainstorming skill

The historical account also associated challenged recommendations, bounded clarification and a
non-convergence stop with brainstorming. The connection describes the rationale for particular
instructions. It does not mean the papers tested the codeArbiter brainstorming skill or approved
its complete delivery path.

For the present procedure, read the owning [brainstorming reference](/reference/skills/brainstorming/)
and [feature guide](/guides/feature-lane/). Compare current requirements, written artifacts, review
results and approval boundaries. Do not use a research citation to excuse a missing output.

## The test before shipping

The prior narrative reported a small, single-run, simulated-session comparison of two persona
versions. That is historical project-reported evidence. This overhaul has not reconstructed its
full candidate inputs, evaluator outputs and installed-host conditions, so it does not reproduce
its score as current efficacy evidence.

A future claim should bind the candidate prompt and host, model/version, task set, scoring rules,
outputs, repeated runs and limits. A website source test proves that required text remains; a
browser test proves presentation behavior; neither measures agent compliance. An accepted design
and a successfully packaged prompt also do not prove the intended behavioral effect.

## Where to go next

Use [The Persona-Register Split](/concepts/persona-and-context/) to inspect the actual work handoff,
[Just-in-time context](/concepts/jit-context-injection/) for file-scoped advice, and
[Auditability](/concepts/auditability/) to distinguish what a record can prove. Historical
research remains useful when its limits stay attached to the design decision it informed.

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

Historical note retained from the earlier research account: additional context consulted was Krakovna et al.'s specification-gaming
catalogue (DeepMind, 2020) for the cross-domain baseline; Bai et al.'s Constitutional AI
(2022) as the precedent for principle-based steering, cited qualitatively because its numeric
tables could not be re-verified at review time; Greenblatt et al.'s alignment-faking results
(2024) for the strategic-rationalization pattern. Sources whose findings could not be fetched
and verified from primary text were excluded from that earlier account. This overhaul has not independently repeated that literature review.
