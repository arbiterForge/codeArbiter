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
  { tag: "H-09", kind: "block", file: "pre-bash.py", line: 10, message: "crypto detected", dynamic: [] },
  { tag: "H-09b", kind: "block", file: "pre-bash.py", line: 20, message: "sensitive line", dynamic: [] },
  { tag: "H-10", kind: "remind", file: "pre-bash.py", line: 30, message: "possible secret", dynamic: [] },
  { tag: "H-10", kind: "block", file: "pre-bash.py", line: 31, message: "possible secret, blocked", dynamic: [] },
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

  it("wraps f-string placeholders in backticks", () => {
    const site: HookCallSite = {
      tag: "H-13",
      kind: "remind",
      file: "post-write-edit.py",
      line: 5,
      message: "{rel}: found an issue on line {line}.",
      dynamic: [],
    };
    const out = renderHooksReference([site], eventMap, "2.8.11", "main");
    expect(out).toContain("`{rel}`");
    expect(out).toContain("`{line}`");
  });
});

describe("renderHooksReference — honest coverage (HW-23)", () => {
  const eventMap = buildEventMap(hooksJson);

  it("never claims runtime equivalence", () => {
    const md = renderHooksReference(callSites, eventMap, "2.8.11", "main");
    expect(md).not.toContain("can never drift");
    expect(md).not.toContain("Every gate ID");
    expect(md).toContain("bounded static scan");
    expect(md).toContain("not proof of every message");
  });

  it("names a dynamic recovery fragment instead of presenting a partial message as complete", () => {
    const site: HookCallSite = {
      tag: "H-09b", kind: "block", file: "_bashguardlib.py", line: 7,
      message: "The staged candidate differs. ", dynamic: ["recovery"],
    };
    const md = renderHooksReference([site], eventMap, "2.8.11", "main");
    expect(md).toContain("Static template only: run-time text from `recovery`");
  });

  it("lists skipped call sites with source links", () => {
    const md = renderHooksReference(callSites, eventMap, "2.8.11", "main",
      [{ file: "pre-edit.py", line: 42 }]);
    expect(md).toContain("## Extraction coverage");
    expect(md).toContain("1 `block()`/`remind()` call(s) could not be attributed");
    expect(md).toContain("plugins/ca/hooks/pre-edit.py#L42");
    const clean = renderHooksReference(callSites, eventMap, "2.8.11", "main", []);
    expect(clean).toContain("was attributed to a gate ID");
  });
});
