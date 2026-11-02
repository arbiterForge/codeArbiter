/** targets.ts - every guide example that is captured from a deterministic tool (DEC-05).
 *
 * Only codeArbiter's own scripts appear here: the override writer, the
 * statusline wiring script and the project scaffolder. Requests a person types
 * and narration a model writes are not reproducible, so they are never targets;
 * the guides label them illustrative instead (guide-examples.json).
 */

import type { CaptureTarget } from "./harness";

const GATE_REASON =
  "design review: retain the deprecated v2 compatibility selector until the documented v3 removal release; supported v2 clients still depend on it, this commit only";

export const CAPTURE_TARGETS: CaptureTarget[] = [
  {
    id: "override-gate-row",
    title: "The audit row an ordinary override appends",
    tool: "plugins/ca/hooks/append-override.py",
    args: ["--gate", "design-review", "--reason", GATE_REASON],
    setup: (fixture) => {
      fixture.initGit({ email: "you@example.com" });
      fixture.write(".codearbiter/overrides.log", "");
    },
    show: { file: ".codearbiter/overrides.log", tail: 1 },
    expectExitCode: 0,
  },
  {
    id: "override-security-row",
    title: "The audit row a security-critical override appends",
    tool: "plugins/ca/hooks/append-override.py",
    args: [
      "--security-finding",
      "request-derived string reaches a shell command in tools/export.py",
      "--reason",
      "reviewed: the value is checked against a fixed allowlist before use, this change only",
    ],
    setup: (fixture) => {
      fixture.initGit({ email: "you@example.com" });
      fixture.write(".codearbiter/overrides.log", "");
    },
    show: { file: ".codearbiter/overrides.log", tail: 1 },
    expectExitCode: 0,
  },
  {
    id: "statusline-refusal",
    title: "What /ca:statusline prints when settings.json is not valid JSON",
    tool: "plugins/ca/hooks/wire-statusline.py",
    args: ["install"],
    setup: (fixture) => {
      // A half-written file: the parser's message for a missing value is the same on every Python 3.
      fixture.writeHome(".claude/settings.json", '{ "theme": \n');
    },
    show: { stream: "stderr" },
    expectExitCode: 1,
  },
  {
    id: "context-scaffold-frontmatter",
    title: "The activation frontmatter the scaffolder writes to CONTEXT.md",
    tool: "plugins/ca/hooks/init-codearbiter.py",
    args: [],
    setup: (fixture) => {
      fixture.initGit();
    },
    show: { file: ".codearbiter/CONTEXT.md", head: 5 },
    expectExitCode: 0,
  },
];
