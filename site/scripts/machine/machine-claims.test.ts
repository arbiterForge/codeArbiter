import { describe, expect, it } from "vitest";
import { checkClaims, pythonFunctionBody, type MachineClaim } from "./machine-claims";

const HOOKLIB = [
  "import sys",
  "",
  "def _log_gate_event(kind, tag, msg):",
  "    pass",
  "",
  "def block(tag, msg):",
  '    """Refuse the call."""',
  '    _log_gate_event("BLOCK", tag, msg)',
  '    print(f"BLOCKED [{tag}]: {msg}", file=sys.stderr)',
  "    sys.exit(2)",
  "",
  "",
  "def remind(tag, msg):",
  '    print(f"REMINDER [{tag}]: {msg}", file=sys.stderr)',
  "",
  "# a trailing comment at column 0 ends the body",
  "CONSTANT = 1",
].join("\n");

const claim = (check: MachineClaim["check"]): MachineClaim => ({ id: "c", statement: "s", check });
const read = (files: Record<string, string>) => (path: string) => {
  if (!(path in files)) throw new Error(`ENOENT: ${path}`);
  return files[path];
};

describe("pythonFunctionBody", () => {
  it("returns the indented body of a top-level function and stops at the next top-level line", () => {
    const body = pythonFunctionBody(HOOKLIB, "block");
    expect(body).toContain('_log_gate_event("BLOCK", tag, msg)');
    expect(body).not.toContain("def remind");
    expect(pythonFunctionBody(HOOKLIB, "remind")).not.toContain("CONSTANT");
  });

  it("returns undefined when the function is not defined at the top level", () => {
    expect(pythonFunctionBody(HOOKLIB, "warn")).toBeUndefined();
    expect(pythonFunctionBody("class A:\n    def block(self):\n        pass\n", "block")).toBeUndefined();
  });
});

describe("pythonFunctionBody with real-world layouts", () => {
  it("keeps a multi-line signature out of the body and the whole body in", () => {
    const source = "def block(\n    tag,\n    msg,\n):\n    _log_gate_event(\"BLOCK\", tag, msg)\n    sys.exit(2)\n\nX = 1\n";
    const body = pythonFunctionBody(source, "block")!;
    expect(body).toContain("_log_gate_event");
    expect(body).toContain("sys.exit(2)");
    expect(body).not.toContain("X = 1");
  });

  it("does not end the body at a comment that starts in column 0", () => {
    const source = "def block(tag, msg):\n    first()\n# a column-0 comment inside the body\n    _log_gate_event(\"BLOCK\", tag, msg)\n\ndef remind(tag, msg):\n    pass\n";
    expect(pythonFunctionBody(source, "block")).toContain("_log_gate_event");
  });
});

describe("checkClaims", () => {
  const files = { "hooks/_hooklib.py": HOOKLIB, "hooks/prompt.py": "MODEINJECT_PREFIX = 'x'\nkey = 'compaction-generation'\n" };

  it("passes when every claim holds", () => {
    const findings = checkClaims([
      claim({ type: "python-function-calls", file: "hooks/_hooklib.py", function: "block", call: "_log_gate_event" }),
      claim({ type: "python-function-avoids", file: "hooks/_hooklib.py", function: "remind", call: "_log_gate_event" }),
      claim({ type: "contains", file: "hooks/prompt.py", text: ["MODEINJECT_PREFIX", "compaction-generation"] }),
    ], read(files));
    expect(findings).toEqual([]);
  });

  it("reports a function that stopped making the call the machine describes", () => {
    const findings = checkClaims(
      [claim({ type: "python-function-calls", file: "hooks/_hooklib.py", function: "remind", call: "_log_gate_event" })],
      read(files),
    );
    expect(findings).toHaveLength(1);
    expect(findings[0]).toMatch(/claim c no longer holds: remind\(\) in hooks\/_hooklib.py does not call _log_gate_event/);
  });

  it("reports a function that started making a call the machine says it avoids", () => {
    const findings = checkClaims(
      [claim({ type: "python-function-avoids", file: "hooks/_hooklib.py", function: "block", call: "_log_gate_event" })],
      read(files),
    );
    expect(findings[0]).toMatch(/block\(\) in hooks\/_hooklib.py now calls _log_gate_event/);
  });

  it("ignores calls that only appear in comments, docstrings or strings", () => {
    const disabled = [
      "def block(tag, msg):",
      '    """Calls _log_gate_event(kind, tag, msg) before refusing."""',
      '    # _log_gate_event("BLOCK", tag, msg)',
      '    note = "_log_gate_event(BLOCK)"',
      "    sys.exit(2)",
    ].join("\n");
    const findings = checkClaims(
      [claim({ type: "python-function-calls", file: "hooks/off.py", function: "block", call: "_log_gate_event" })],
      read({ "hooks/off.py": disabled }),
    );
    expect(findings[0]).toMatch(/block\(\) in hooks\/off.py does not call _log_gate_event/);
  });

  it("checks code text inside one function, ignoring the same text in comments", () => {
    const exits = "def block(tag, msg):\n    sys.exit(2)\n";
    const commented = "def block(tag, msg):\n    # sys.exit(2)\n    return 0\n";
    const check = { type: "python-function-contains", file: "hooks/b.py", function: "block", text: "sys.exit(2)" } as const;
    expect(checkClaims([claim(check)], read({ "hooks/b.py": exits }))).toEqual([]);
    expect(checkClaims([claim(check)], read({ "hooks/b.py": commented }))[0]).toMatch(/block\(\) in hooks\/b.py no longer contains sys.exit\(2\)/);
  });

  it("reports a missing function, a missing file and missing text instead of passing silently", () => {
    const findings = checkClaims([
      claim({ type: "python-function-avoids", file: "hooks/_hooklib.py", function: "warn", call: "_log_gate_event" }),
      claim({ type: "contains", file: "hooks/gone.py", text: ["x"] }),
      claim({ type: "contains", file: "hooks/prompt.py", text: ["MODEINJECT_PREFIX", "generation-ledger"] }),
    ], read(files));
    expect(findings).toHaveLength(3);
    expect(findings[0]).toMatch(/warn\(\) is not defined/);
    expect(findings[1]).toMatch(/cannot read hooks\/gone.py/);
    expect(findings[2]).toMatch(/does not contain "generation-ledger"/);
  });
});
