# Triage & calibration

Triage per wave from disk. The orchestrator's calibrated values are final and override every provisional self-score downstream.

## Dedup

Before calibrating, dedup each new finding against all findings already on disk — match by `dedup_key` and by overlapping locations. A match decides as `duplicate` (`duplicate_of` set), distinct from `combine`.

## Severity rubric (impact x likelihood)

- **critical** — exploitable security hole, data loss/corruption, or an outage path reachable with realistic input.
- **high** — serious correctness/security weakness, latent but plausible; or a systemic architectural defect amplifying other risk.
- **medium** — real defect/debt, limited blast radius or lower likelihood.
- **low** — minor quality, polish, or DX improvement.

## Calibration

For each finding, set `final_severity`/`final_confidence` from the evidence directly — the lens's values are provisional input. For every critical/high, record a `counter_argument` — the strongest case it is lower or a false positive; if compelling, downgrade or reclassify. Calibration is bidirectional: promote under-rated findings too. Optional for criticals: dispatch a fresh-context adversary that sees only the finding + code and tries to refute it, to defeat anchoring.

## Severity priors

Apply as priors on findings that already cleared evidence-or-drop, never to manufacture one: resource-level authz / IDOR → high or critical; injection with reachable user input → high or critical; literal secret → high or critical; async operation with no handler on a critical path → high. A high-marker/high-iteration location (per `ai-markers.md`) nudges one level at most.

## Confidence gate

The bar a finding's `final_confidence` must clear to file, tiered by severity — an uncertain critical is too costly to bury silently, so it gets a lower bar and a softer landing than a low:

| `final_severity` | gate | below the gate |
| --- | --- | --- |
| critical / high | ≥0.5 | → `decision-required`, framed as a question, never dropped silently |
| medium | ≥0.7 | → `investigate` |
| low | ≥0.75 | → `investigate` |

## Low-severity discipline

A `low` is kept only above the confidence gate (≥0.75, see above) with a concrete, actionable remediation. Beyond ~5 lows per lens, aggregate the remainder into a single rollup finding that still lists each `path:line`.

## Decision vocabulary (into `triage.jsonl`)

- **keep** — actionable fix; files as its own issue.
- **combine** — real, merged with siblings under a shared `group_id`; one issue.
- **duplicate** — identical to a recorded finding (`duplicate_of`); distinct from combine.
- **false-positive** — not real; `rationale` required (this tunes future-run noise down — keep it).
- **defer** — real, out of scope/priority now; preserved, not filed this run.
- **accept-risk** — real, consciously not fixing; the risk-acceptance trail.
- **decision-required** — real and significant, but the response is an ADR-grade design choice, not a clear fix; files as a discussion, not a fix ticket.
- **investigate** — undecided, or a medium/low below the confidence gate after calibration; never filed.

Below the confidence gate after calibration: medium/low → `investigate`; critical/high → `decision-required` (see Confidence gate above — never dropped silently). ADR-grade questions also → `decision-required`.

## Per-wave plan

`plans/phase-<n>.md` covers only `keep`/`combine`, grouped by type (lens/category/`group_id`): shared remediation approach, ordered sequence, cross-group `depends_on`, rolled-up acceptance criteria. Roadmap level only — no per-finding code steps. A `decision-required` item gets a one-line "ADR-candidate — resolve via `/ca-adr`" pointer, never an authored ADR.
