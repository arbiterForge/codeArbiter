# Coding standards — codeArbiter (the framework repo itself)

Style, structure, naming, and banned patterns for code in THIS repo. The canonical
test/lint/build commands live in `tech-stack.md`; this file is conventions only.
Prose artifacts (skills, commands, agents, `ORCHESTRATOR.md`) are governed by the
plugin's own authoring gates (`skill-author` v2 house style), not by this file.

## Where code lives

- **Python hooks** — `plugins/ca/hooks/*.py`. Stdlib only.
- **TypeScript farm dispatcher** — `plugins/ca/tools/*.ts`, shipped as built `farm.js`.
- **ca-sandbox sibling** — `plugins/ca-sandbox/tools/*.ts` (ADR-0007), same TS rules.

## Python (hooks)

- `#!/usr/bin/env python3` shebang on every hook.
- The file opens with a `# codeArbiter — <one-line purpose>.` comment, then a short
  block stating what it guards/computes and its design invariants (see any
  `_*lib.py` for the shape).
- **Stdlib only — no third-party imports, ever.** Hooks must run on a stock
  Windows/macOS/Linux Python with nothing installed; the cold-install matrix proves
  it. Adding a dependency is a banned pattern, not a judgment call.
- Shared logic goes in a leading-underscore library module `_<name>lib.py`
  (`_hooklib`, `_taskboardlib`, `_metricslib`, …), imported by the thin entry-point
  hooks. Keep entry points thin; keep testable logic in the lib.
- Naming: `snake_case` for functions and variables, `UPPER_SNAKE` for module
  constants, `CapWords` for the rare `namedtuple`/class.
- Library design invariants (mirror the existing `_*lib.py`):
  - Zero side effects at import time — no git calls, no file I/O on import.
  - Pure functions, testable with synthetic input; isolate filesystem access to one
    named reader (e.g. `read_board()`).
  - **Never raise on malformed user input** — degrade to a surfaced warning. A hook
    that can crash the SessionStart path is a defect, not an edge case.
- Document the public API in the file header as `name(args) -> type` lines.
- Enforcement hooks carry a stable `H-NN` ID (letter suffix for a split gate, e.g.
  `H-09b`); cite the ID in code comments and in the matching test.
- Floor check for any touched hook: `python -m py_compile <file>` — no linter is
  configured (see `tech-stack.md`).

## TypeScript (farm dispatcher)

- `strict: true` is non-negotiable (`tools/tsconfig.json`); `npm run typecheck` must
  pass clean.
- The file opens with a `/** … */` JSDoc block: `<file> — codeArbiter's <purpose>.`
- Naming: `camelCase` for values/functions, `CapWords` for types/interfaces. ES
  module imports with explicit `.ts` extensions (bundler resolution).
- The plugin ships the **built** `farm.js`, never `farm.ts`. After any `.ts` change
  run `npm run build`; a stale bundle (`git diff --quiet -- farm.js` fails) is a
  release blocker.
- Security-sensitive paths (URL / base-URL validation, secret handling) keep their
  existing guards and tests — see `security-controls.md`.

## File headers and copyright

- License is MIT; the copyright holder of record is **"codeArbiter contributors"**
  (`LICENSE`).
- **No per-file license or SPDX headers.** The single root `LICENSE` governs; new
  files carry no copyright header. The `# codeArbiter — …` / `/** … */` purpose
  comment is documentation, not a license header.

## Line endings and encoding

- UTF-8, no BOM. Canonical EOL is **LF** for all tracked text.
- `.gitattributes` enforces LF for `*.sh`, `*.py`, and `hooks/*` (CRLF breaks bash
  shebangs and is noisy in Python). The same LF convention applies to `.md`, `.ts`,
  `.json`, and `.yml`, but is not yet enforced by `.gitattributes` there. An edit
  MUST NOT flip LF to CRLF; normalize to LF before staging. A diff that introduces
  CRLF on a tracked text file is rejected at review.
