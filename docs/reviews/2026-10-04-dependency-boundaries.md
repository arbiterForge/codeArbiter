# Dependency boundaries

Research for [#882](https://github.com/arbiterForge/codeArbiter/issues/882),
against main `4a578c5a`, on 2026-10-04. This report clarifies the existing rules
and recommends small wording changes; it does not approve dependencies or
change policy.

## Classify execution and distribution separately

A dependency can belong to more than one class. Classify transitive components
the same way as direct dependencies, by what executes and what ships.

| Class | Meaning | Example | Existing controls |
| --- | --- | --- | --- |
| Development | Runs during local authoring, analysis or tests | Vitest; a separate Go analyzer module | License, registry/source, vulnerability and install-script review still apply. |
| Build/CI | Runs while producing or checking a release | esbuild; Python conformance tools; pinned Pi test host | Review the exact tool graph and execution boundary. A compromised builder can change shipped output. |
| Runtime | Required when the installed product runs | Python, Node and the selected host; a library imported by a hook | Enforce each surface's runtime contract and supported host versions. |
| Distributed | Third-party code or assets included in the delivered artifact | A compiled-in Go library, bundled JavaScript, copied package or WASM asset | Review license and supply-chain obligations against the actual package contents, even if the manifest labels the input a dev dependency. |

A host-provided runtime is a consumer prerequisite even when it is not copied
into the plugin. Conversely, a tool can execute during a build without its code
being distributed. An npm `devDependencies` entry alone proves neither absence
from a bundle nor absence of execution risk.

## What dependency-free means here

- **Python hooks:** standard library only, as required by
  [coding standards](../../.codearbiter/coding-standards.md) and
  [security controls](../../.codearbiter/security-controls.md#hook-security-python).
  A third-party Python test harness does not make that package available to hooks.
- **Artifact engine:** the current [Go module](../../core/artifacts/go.mod) has
  no external requirements. A library compiled into its binary is distributed
  code, even when no library needs to be downloaded at runtime. A separately
  invoked analyzer does not become an engine dependency merely because it
  inspects the engine.
- **Plugin payload:** its package has no runtime npm dependency graph. This does
  not mean consumers need no host, Node or Python. Existing package checks
  inspect delivered paths and bundled content, in addition to manifest fields.
- **Development toolchain:** it is not dependency-free. The repository already
  uses reviewed npm build/test graphs and a hashed Python conformance lock.

For Go, keep an adopted analyzer's graph separate from the engine module; a
tool-only requirement in the engine module would still change that module's
declared graph. For Python, install the conformance lock in its separate test
environment. For npm, inspect bundle/package output when assessing whether a
development dependency becomes distributed code.

## Guidance that needs clearer wording

| Current source | Ambiguity | Recommended clarification |
| --- | --- | --- |
| [Dependency command](../../core/surface/commands/add-dep.md) | The one-off exception requires a user-named tool, while its opening graph-based explanation can sound broader. | Keep the exact one-off conditions visible: named, pinned, once, no manifest/lock/script/CI adoption. A recurring script is adoption even without a manifest. |
| [Dependency reviewer](../../core/surface/agents/dependency-reviewer.md) | Manifest fields and generic CVE severity guidance can obscure surface-specific policy. | State execution class and distribution class, then apply the repository's license scopes and advisory exceptions. |
| [Security controls](../../.codearbiter/security-controls.md) | License permission can be limited to development/build use or one exact CI tool. | Preserve these restrictions; approving a tool does not authorize copying it into the product. |
| [Tech stack](../../.codearbiter/tech-stack.md) | Unqualified "dependency-free" and "high everywhere" phrases can hide host prerequisites and explicitly accepted advisories. | Qualify the relevant surface and link the existing exception records. |
| [Pi package checks](../../.github/scripts/test_pi_package.py) and [artifact package tests](../../.github/scripts/test_artifact_package.py) | Package contents and dependency declarations answer different questions. | Keep both forms of evidence; a clean manifest is not a complete distribution check. |

## Small follow-through

Use the dependency command's existing resource area for one shared definition
table, referenced by its reviewer and the repository's tech stack. Keep
repository-specific license and advisory authority in `security-controls.md`.
Do not duplicate those exceptions in a generic skill.

Reuse existing lock, audit, signature and package-content checks. A reviewed
exact lock can supply the evidence for repeated installs; only changed inputs
or a new policy exception need a new decision. The current one-off tool rule
still requires confirmation; changing that rule is a separate owner decision.
No new CI workflow, approval service, self-hosted runner or general dependency
framework is needed to resolve this clarification.
