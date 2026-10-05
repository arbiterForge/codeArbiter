# Cost, profiles and concurrency

Use the trusted `tribunal.py` helper's `inventory`, `profile` and `estimate` modes
described in schemas (`{{PLUGIN_ROOT}}/skills/tribunal/references/schemas.md`).
Mechanical extraction runs no project code. Its tracked-file sizes and bounded
parsers are facts, not a model review; unavailable fields stay explicit.

## Resolve the host before recommending settings

Profiles express work, never provider model identifiers:

| Lens or role | Profile |
|---|---|
| orchestrator | deep |
| appsec | deep |
| reliability | deep |
| architecture | deep |
| semantic-contract | deep |
| change-closure | standard |
| secrets-supply | standard |
| migration | standard |
| test-fidelity | standard |
| performance | standard |
| observability | standard |
| typesafety | standard |
| coverage | standard |
| infra | standard |
| serious-finding verifier (same generic reviewer, verify mode) | deep |
| optional map-structure / map-deps semantic classification | extract |

Observe the active host's `fresh_threads`, `model_override`, `reasoning_override`,
available `models` and `reasoning_levels`. Populate `profiles` only with available
settings, then call `profile` for each selected profile. Recommend the strongest
supported reasoning setting for deep work; do not invent a model name, effort
control or external provider. Missing overrides inherit configured settings and
record limitations. Do not silently change the acknowledged settings or budget.

Fresh thread capability is separate from native agent registration. In particular,
`agents: false` does not imply that fresh host threads are unavailable. Dispatch
the selected trusted role/card into a fresh thread when supported. If not,
explicitly record inline/shared-context execution and
`verification_independence: limited`; it cannot clear serious-finding verification.
No additional registered agent is needed for verification.

## Evidence-based token band

`estimate` accepts `packet_bytes` (sum across selected lens packets; repeated
evidence counts each time), `profile_counts`, `verification_candidates`,
`extraction_bytes` (inventory/mapper context delivered to the model, not bytes
Python scanned), and `concurrency`. Include all approved reasoning work, including
optional mappers, when recording the estimate inputs.

The current estimator is a disclosed heuristic: bytes/4, profile multipliers
deep=6, standard=3, extract=1, 1,000 tokens per role and a half-to-double band.
Verification adds the average packet plus an allowance. It returns `token_band`,
`inputs`, `assumptions`, `limitations`, and unavailable measured usage/price.
Show these inputs and the broad band before cost acknowledgment. Compatible
historical usage may inform a separately labelled calibration; never present the
heuristic as measured usage, dollars or a quality guarantee.

Reduce total work through a narrower scope, applicability-based lens selection,
smaller packets, deterministic preprocessing or a validated lower profile.
Concurrency is capped at five and further limited by actual host capacity.
Lower concurrency affects elapsed time and peak resources; it does not reduce total tokens.

## Default waves

| Wave | Lenses |
|---|---|
| 1 | appsec, architecture, reliability, semantic-contract |
| 2 | secrets-supply, migration, test-fidelity, change-closure |
| 3 | coverage, infra, observability, performance, typesafety |

Remove inapplicable lenses without renumbering waves. Record the selected
partition, profiles, capability limits, applicability and estimate in
`run-started.detail` through `start --detail`. Resume uses that partition.
Any material increase beyond acknowledged work returns to the cost gate.

## Optional mappers

Use map-structure or map-deps only for unresolved semantic relationships after
deterministic extraction. Supply a compact bounded packet and precise questions;
do not use model agents for basic counting or enumeration. Record their limits
and evidence in the risk map. The coordinator alone dispatches reviewers,
verifiers and these optional mappers; specialists never dispatch children.
