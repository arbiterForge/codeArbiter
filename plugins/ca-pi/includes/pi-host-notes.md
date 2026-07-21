# Pi host notes: operational deltas from the shared surface

Load this before dispatching roles, editing append-only audit files, or using
Pi-native compaction. The governance rules remain canonical under `core/`; this
file maps those actions to Pi's extension API.

## Commands and tools

- Use `/ca-<name>` for the generated top-level aliases. `/skill:ca-<name>` is
  the host-native fallback when an alias is unavailable. Do not send slash text
  to the model as a substitute for loading the skill body.
- Pi's human-readable generated skill catalog is `plugins/ca-pi/SKILLS.md`,
  outside the loader-scanned `plugins/ca-pi/skills/` directory. The generated
  machine catalog remains under `plugins/ca-pi/generated/`.
- Pi built-ins map as `bash` (EXEC), `write` (WRITE), `edit` (EDIT), and `read`
  (READ). `codearbiter_dispatch` and `codearbiter_farm_preview` are parent-only
  EXEC tools. Unknown or foreign replacement tools fail closed.
- The parent registers repository-aware dispatch, farm preview, and native
  compaction only after the current session reports affirmative project trust,
  the repository is enabled, and the enforcement lifecycle is ready.
- Execute mode asks before governed mutations or external side effects and
  silently allows classified reads. Plan mode is read-only except for the
  current canonical spec, plan, and plan-ledger files; source, configuration,
  unrelated project-state, and external mutations deny.
- `codearbiter_background_bash` and `/ca-jobs list|tail|cancel` are bounded,
  session-only parent capabilities. Jobs and their metadata terminate at
  shutdown and are never restored from Pi session entries.
- Append-only audit files must use an operation whose final arguments preserve
  the existing prefix and append at the tail. A replacement, truncation, delete,
  or opaque operation blocks under H-05.

## Host-specific surfaces

- ca-pi installs its rich footer in every interactive parent repository,
  including dormant repositories. Universal Pi-owned usage facts render
  globally; rate-window telemetry is omitted rather than fabricated. The
  governance row renders only when the repository is enabled and affirmatively
  trusted.
- `/ca-prune` selects shared semantic policy. The active Pi session is compacted
  through the native compaction event; codeArbiter does not rewrite Pi session
  JSONL. The private summarizer uses the hardened child runner with zero tools.
- Author and reviewer work uses fresh child Pi processes through
  `codearbiter_dispatch`. Single, chain, and parallel modes share bounded depth,
  concurrency, timeout, cancellation, output, and process-tree cleanup.
- `/ca-sprint --farm` remains Feature Forge `preview`. Pi's parent calls the one
  checked-in `plugins/ca/tools/farm.js` contract. No Pi-specific farm engine is
  shipped, and ordinary child environments never receive `FARM_API_KEY`.

## Trust and diagnostics

- A global install remains dormant in repositories without an enabled
  `.codearbiter/CONTEXT.md`. An enabled repository still requires Pi's
  affirmative project-trust decision before repository-aware startup.
- Run `/ca-doctor` to inspect the active package path, canonical Pi CLI and
  package origin, command ownership, supported-version expansion fingerprints,
  Python/core/bridge health, child fingerprint, final mutator wrappers, footer
  initialization, background-manager health, and the H-03 wrapper self-test.
- Unverified background cleanup makes the manager unhealthy, blocks later
  launches, and directs the operator to `/ca-doctor`. Doctor never includes job
  labels or IDs, commands, environment data, or output.
- Footer, permission UI, plan UI, and background-job capabilities are
  parent-interactive only and absent from RPC, JSON, print, and hardened child
  inventories.
- The doctor module-identity row proves self-consistency between the
  operator-launched Pi CLI, imported module, package root, and reported version.
  It does not prove publisher authenticity. Verify the source separately with
  `pi list` and `pi config`.
- Supported promotion targets are Pi 0.80.5 and Pi 0.80.10. npm packaging and a
  Pi-native embedded farm worker are future spikes, not installed dependencies.
