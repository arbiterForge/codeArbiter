# performance — lens mandate

Executed by `tribunal-lens-reviewer` under the `performance` assignment.

## Purpose / failure family
Find demonstrable latency, throughput or resource failures under a supported
workload, including repeated expensive work and unbounded growth.

## Applicability
There is a documented SLO/resource constraint, observed benchmark/profile, clear
asymptotic bound, plausible hot-path repeated I/O, unbounded growth or demonstrable
scale multiplier.

## Skip conditions
No supported workload or performance premise can be established. Lack of a
benchmark alone is not a skip when the code establishes an unbounded cost path.

## Scope emphasis
Actual hot paths, data access, subprocess/network fan-out, queues/caches and
resource lifetimes, with cold and bounded operations identified separately.

## Required reading
- Finding record (`${CLAUDE_PLUGIN_ROOT}/skills/tribunal/references/finding-record.md`) and review risk (`${CLAUDE_PLUGIN_ROOT}/skills/tribunal/references/review-risk.md`).
- `${CLAUDE_PROJECT_DIR}/.codearbiter/tech-stack.md` — data layer, cache and runtime
  model; relevant SLOs, supported scale, profiles and benchmark conditions.

## Deterministic probes
Inspect query/I/O/subprocess counts along a bounded path, loop nesting, fan-out
and retention/eviction bounds. Read existing profiles and query/index evidence;
do not infer production cost from a loop signature or unrelated benchmark.

## Review questions
- Does repeated I/O or over-fetching multiply cost on a plausibly exercised path?
- Can growth, fan-out or retention escape the stated resource bound?
- Does blocking work violate an established latency/concurrency constraint?
- Do cache misses, invalidation or keys create the demonstrated cost or stale result?
- Does the recommendation address the measured/bounded mechanism at supported scale?

## False-positive guards / non-findings
Cold bounded loops, small fixed collections and deliberately uncached work may
be appropriate. "Could cache or memoize" is not a finding. A different index or
algorithm needs a workload and cost argument; benchmark noise is not a regression.

## Evidence requirements
Provide the observed or documented workload/scale premise, or an explicit
asymptotic/resource bound and reachable input multiplier. Show the costly path
and expected consequence, separating measurement from inference. For absent
batching/cache/limits, state the search universe through callers and data/resource
owners; centralized bounds can refute the claim.

## Exposure metric
Count of workload/path pairs evaluated with their premise and bound, identifying
which conclusions are measured and which are statically inferred.

## Escalation / cross-lens handoff
Send wrong cached results or races to reliability, externally exploitable
resource exhaustion to appsec, and missing benchmark discrimination to coverage.
Combine evidence when the cost and correctness symptoms share one cause.

## Out of scope
Speculative micro-optimization, universal caching and unsupported production
latency claims.
