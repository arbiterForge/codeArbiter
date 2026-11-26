import { describe, expect, it } from "vitest";
import { loadMachine } from "./machine-model";
// The viewer is JavaScript ported from the standalone explainer; its message table is checked here.
import { MESSAGE_SITES, messageFor, sitesFor } from "../../src/scripts/machine/messages.js";

const machine = loadMachine();

describe("the viewer's hook messages", () => {
  it("names exactly one block() call site for every key the Guard lab and the example session print", () => {
    for (const key of Object.keys(MESSAGE_SITES)) {
      const sites = sitesFor(key, machine.gates);
      expect(sites, key).toHaveLength(1);
      expect(sites[0].backstop, key).toBe(key.startsWith("G-"));
    }
  });

  it("prints the hook's own text with its run-time value filled in", () => {
    expect(messageFor("H-02", "", machine.gates)).toBe(sitesFor("H-02", machine.gates)[0].message);
    expect(messageFor("H-01c", "main", machine.gates)).toMatch(/^Direct commit to main is prohibited/);
    expect(messageFor("G-01p", "refs/heads/main", machine.gates)).toContain("('refs/heads/main')");
  });

  it("marks a message the hook continues with run-time details instead of cutting it silently", () => {
    const literalStart = sitesFor("H-10b", machine.gates)[0].message;
    expect(literalStart).toMatch(/\s$/);
    expect(messageFor("H-10b", "", machine.gates)).toBe(`${literalStart.trim()} …`);
  });
});
