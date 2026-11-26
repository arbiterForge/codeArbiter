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
