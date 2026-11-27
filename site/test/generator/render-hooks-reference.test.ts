import { describe, it, expect } from "vitest";
import {
  renderHooksReference,
  buildEventMap,
  eventsFor,
  type HooksJson,
} from "../../scripts/generator/render-hooks-reference";
import type { HookCallSite } from "../../scripts/generator/extract-hook-gates";

const hooksJson: HooksJson = {
  hooks: {
    PreToolUse: [
      {
        matcher: "Bash|PowerShell",
        hooks: [
          { command: 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/pre-bash.py"' },
          { command: 'python3 -c "" || python "${CLAUDE_PLUGIN_ROOT}/hooks/pre-bash.py"' },
        ],
      },
    ],
    SessionStart: [
      {
        hooks: [{ command: 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/session-start.py"' }],
      },
    ],
  },
};

const callSites: HookCallSite[] = [
  { tag: "H-09", kind: "block", file: "pre-bash.py", line: 10, message: "crypto detected" },
  { tag: "H-09b", kind: "block", file: "pre-bash.py", line: 20, message: "sensitive line" },
  { tag: "H-10", kind: "remind", file: "pre-bash.py", line: 30, message: "possible secret" },
  { tag: "H-10", kind: "block", file: "pre-bash.py", line: 31, message: "possible secret, blocked" },
];

describe("buildEventMap / eventsFor", () => {
  it("maps a script to its EventName (matcher) label", () => {
    const map = buildEventMap(hooksJson);
    expect(map.get("pre-bash.py")).toEqual(["PreToolUse (Bash|PowerShell)"]);
  });

  it("maps a script with no matcher to a bare EventName label", () => {
    const map = buildEventMap(hooksJson);
    expect(map.get("session-start.py")).toEqual(["SessionStart"]);
  });

  it("hand-maps git-enforce.py to the git backstop label, bypassing hooks.json", () => {
    const map = buildEventMap(hooksJson);
    expect(eventsFor("git-enforce.py", map)).toEqual(["git backstop"]);
  });

  it("attributes extracted shared-library gates to their registered entry hook", () => {
    const map = buildEventMap(hooksJson);
    expect(eventsFor("_bashguardlib.py", map)).toEqual(["PreToolUse (Bash|PowerShell)"]);
  });

  it("returns an empty list for a script registered nowhere", () => {
    const map = buildEventMap(hooksJson);
    expect(eventsFor("nowhere.py", map)).toEqual([]);
  });
});

describe("renderHooksReference", () => {
  const eventMap = buildEventMap(hooksJson);
  const md = renderHooksReference(callSites, eventMap, "2.8.11", "main");

  it("renders frontmatter with title Hook Gates", () => {
    expect(md).toContain("title: Hook Gates");
  });

  it("orders sections in natural gate-ID order: H-09 before H-09b before H-10", () => {
    const iH09 = md.indexOf("## H-09\n");
    const iH09b = md.indexOf("## H-09b");
    const iH10 = md.indexOf("## H-10\n");
    expect(iH09).toBeGreaterThan(-1);
    expect(iH09b).toBeGreaterThan(iH09);
    expect(iH10).toBeGreaterThan(iH09b);
  });

  it("shows the Blocking badge for a block-only tag", () => {
    const section = md.slice(md.indexOf("## H-09b"), md.indexOf("## H-10\n"));
    expect(section).toContain("**Blocking**");
    expect(section).not.toContain("**Advisory**");
  });

  it("shows both badges when a tag has both a block and a remind call site", () => {
    const section = md.slice(md.indexOf("## H-10\n"));
    expect(section).toContain("**Blocking**");
    expect(section).toContain("**Advisory**");
  });

  it("renders a line-pinned permalink in the expected format", () => {
    expect(md).toContain(
      "https://github.com/arbiterForge/codeArbiter/blob/main/plugins/ca/hooks/pre-bash.py#L10",
    );
  });

  it("renders f-string placeholders as inline code", () => {
    const site: HookCallSite = {
      tag: "H-13",
      kind: "remind",
      file: "post-write-edit.py",
      line: 5,
      message: "{rel}: found an issue on line {line}.",
    };
    const out = renderHooksReference([site], eventMap, "2.8.11", "main");
    expect(out).toContain("<code>{rel}</code>");
    expect(out).toContain("<code>{line}</code>");
  });

  it("keeps every message character for character, out of Markdown and smart typography", () => {
    const site: HookCallSite = {
      tag: "H-20",
      kind: "block",
      file: "pre-bash.py",
      line: 7,
      message: "'--no-verify' / '-n' skip hooks; use `git commit` with *globs* and <tags> intact.",
    };
    const out = renderHooksReference([site], eventMap, "2.8.11", "main");
    // Backticks are printed, not turned into code: the terminal shows them, so a reader can
    // match a pasted message with find-in-page.
    expect(out).toContain("<blockquote class=\"ca-hook-message\"><p>'--no-verify' / '-n' skip hooks; use `git commit` with *globs* and &lt;tags&gt; intact.</p>");
    expect(out).toContain('<p class="ca-hook-message__source"><a href="https://github.com/arbiterForge/codeArbiter/blob/main/plugins/ca/hooks/pre-bash.py#L7"><code>pre-bash.py:7</code></a></p>');
    expect(out).not.toMatch(/^> /m);
  });
});
