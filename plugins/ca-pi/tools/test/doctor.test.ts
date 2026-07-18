import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { afterAll, describe, expect, test } from "vitest";

import {
  collectPiDoctorInput,
  diagnosePi,
  formatPiDoctorReport,
  runPiWrapperSelfTest,
  verifyNativeSkillExpansion,
  type PiDoctorInput,
} from "../src/doctor.ts";

const FIXTURE = mkdtempSync(resolve(tmpdir(), "ca-pi-doctor-unit-"));
const HOSTS = JSON.parse(readFileSync(resolve(import.meta.dirname, "../../../..", "core", "hosts.json"), "utf8")) as {
  hosts: Array<{ name: string; package?: { skill_expansion_fingerprints?: Record<string, string> } }>;
};
const PI_FINGERPRINTS = HOSTS.hosts.find((host) => host.name === "pi")!.package!.skill_expansion_fingerprints!;
const SHIPPED_CHILD = readFileSync(resolve(import.meta.dirname, "../..", "extensions", "codearbiter-child.js"));
const SHIPPED_CHILD_SHA256 = createHash("sha256").update(SHIPPED_CHILD).digest("hex");
const ROOT = resolve(FIXTURE, "ca-pi");
const RUNTIME = resolve(FIXTURE, "pi-runtime");
for (const directory of [
  resolve(ROOT, "extensions"), resolve(ROOT, "hooks"), resolve(ROOT, "skills", "ca-doctor"),
  resolve(RUNTIME, "dist"),
]) mkdirSync(directory, { recursive: true });
for (const file of [
  resolve(ROOT, "extensions", "codearbiter.js"),
  resolve(ROOT, "extensions", "codearbiter-child.js"),
  resolve(ROOT, "hooks", "pi-bridge.py"),
  resolve(ROOT, "skills", "ca-doctor", "SKILL.md"),
  resolve(RUNTIME, "dist", "cli.js"),
  resolve(RUNTIME, "dist", "index.js"),
]) writeFileSync(file, "fixture\n", "utf8");
writeFileSync(
  resolve(ROOT, "extensions", "codearbiter-child.js"),
  "export default function child(pi) { pi.registerTool({ name: 'bash' }); }\n",
  "utf8",
);
afterAll(() => rmSync(FIXTURE, { recursive: true, force: true }));

function healthyInput(): PiDoctorInput {
  return {
    package: {
      root: ROOT,
      name: "ca-pi",
      version: "0.1.0",
      extensionPath: `${ROOT}/extensions/codearbiter.js`,
      scope: "user",
      declared: true,
    },
    trust: { inspected: true, projectTrusted: false, required: false },
    runtime: {
      piVersion: "0.80.10",
      nodeVersion: "22.19.0",
      pythonMajor: 3,
      cliEntry: `${RUNTIME}/dist/cli.js`,
      moduleEntry: `${RUNTIME}/dist/index.js`,
      packageRoot: RUNTIME,
    },
    core: { present: true, bridgeScript: `${ROOT}/hooks/pi-bridge.py` },
    commands: {
      collisions: [],
      ownerPaths: [`${ROOT}/extensions/codearbiter.js`, `${ROOT}/skills/ca-doctor/SKILL.md`],
      expansionVerifiedVersions: ["0.80.5", "0.80.10"],
      expansionMatches: true,
    },
    bridge: { healthy: true },
    child: { present: true, artifact: "enforced", path: `${ROOT}/extensions/codearbiter-child.js` },
    ambientMarker: { present: false, validatedChild: false },
    moduleIdentity: { selfConsistent: true },
    finalArguments: {
      verified: true,
      wrapperSourcePath: `${ROOT}/extensions/codearbiter.js`,
      activeTools: ["bash", "write", "edit", "read"],
      toolSources: {
        bash: `${ROOT}/extensions/codearbiter.js`,
        write: `${ROOT}/extensions/codearbiter.js`,
        edit: `${ROOT}/extensions/codearbiter.js`,
        read: `${ROOT}/extensions/codearbiter.js`,
      },
    },
  };
}

const remediation = {
  package: "Reinstall ca-pi from the approved pinned Git tag, then restart Pi.",
  trust: "Run /trust in Pi, inspect the project, grant trust only if you accept it, then start a new session.",
  version: "Upgrade Pi to 0.80.5 or 0.80.10 and Node to >=22.19.0, then restart Pi.",
  python: "Upgrade or install Python 3, then run /ca-doctor again.",
  core: "Reinstall ca-pi to restore the generated shared core, then run /ca-doctor again.",
  commands: "Remove conflicting command owners or run Pi 0.80.5/0.80.10, then restart Pi and run /ca-doctor.",
  bridge: "Reinstall ca-pi and Python 3, then run /ca-doctor again.",
  child: "Reinstall ca-pi if the hardened child artifact is missing or tampered, then run /ca-doctor again.",
  "ambient-marker": "Remove CODEARBITER_SUBAGENT from the parent environment and restart Pi.",
  "module-identity": "Reinstall the active Pi CLI and ca-pi from their approved origins, then restart Pi.",
  "final-arguments": "Reinstall ca-pi, remove competing mutating tool definitions, and run /ca-doctor again.",
} as const;

const ACTIVE_DISPATCH_MESSAGE =
  "Supported Pi 0.80.5/0.80.10 public extension APIs cannot submit this deterministic self-test through the active dispatcher; the wrapper self-test does not exercise active dispatch.";
const ACTIVE_DISPATCH_REMEDIATION =
  "Require passing supported-version real-host promotion/CI evidence before closing PI-AC-28.";

function brokenFixture(id: keyof typeof remediation): PiDoctorInput {
  const input = healthyInput();
  switch (id) {
    case "package": input.package.declared = false; break;
    case "trust": input.trust = { inspected: true, projectTrusted: false, required: true }; break;
    case "version": input.runtime.piVersion = "0.80.4"; break;
    case "python": input.runtime.pythonMajor = 2; break;
    case "core": input.core.present = false; break;
    case "commands": input.commands.expansionMatches = false; break;
    case "bridge": input.bridge.healthy = false; break;
    case "child": input.child.artifact = "unknown"; break;
    case "ambient-marker": input.ambientMarker.present = true; break;
    case "module-identity": input.runtime.moduleEntry = "C:/unrelated/index.js"; break;
    case "final-arguments": input.finalArguments.wrapperSourcePath = "C:/foreign.js"; break;
  }
  return input;
}

describe("Pi structured doctor", () => {
  test.each(Object.keys(remediation) as Array<keyof typeof remediation>)(
    "returns one exact remediation for broken %s",
    (fixture) => {
      const result = diagnosePi(brokenFixture(fixture));
      const unhealthy = result.filter((row) => row.state === "unhealthy");
      expect(unhealthy).toHaveLength(1);
      expect(unhealthy[0]).toEqual(expect.objectContaining({
        id: fixture,
        remediation: remediation[fixture],
      }));
    },
  );

  test("reports exact active origins and limits the module-identity claim", () => {
    const result = diagnosePi(healthyInput());
    expect(result).toHaveLength(12);
    expect(result.filter((row) => !["child", "active-dispatch"].includes(row.id)).every((row) => row.state === "healthy")).toBe(true);
    expect(result.find((row) => row.id === "child")).toMatchObject({ state: "healthy" });
    expect(result.find((row) => row.id === "active-dispatch")).toEqual({
      id: "active-dispatch",
      state: "degraded",
      message: ACTIVE_DISPATCH_MESSAGE,
      remediation: ACTIVE_DISPATCH_REMEDIATION,
    });
    expect(result.find((row) => row.id === "package")?.message).toBe(
      `ca-pi 0.1.0 is active from ${ROOT} as a user package.`,
    );
    expect(result.find((row) => row.id === "module-identity")?.message).toBe(
      `Active Pi CLI ${RUNTIME}/dist/cli.js; module ${RUNTIME}/dist/index.js; ` +
      `package ${RUNTIME}; version 0.80.10. Module identity is self-consistent with the ` +
      "operator-launched Pi runtime; this does not prove publisher authenticity.",
    );
    expect(result.find((row) => row.id === "trust")?.message).toContain("repository is dormant");
    expect(result.find((row) => row.id === "commands")?.message).toContain("0.80.5, 0.80.10");
  });

  test("diagnoses both command ownership collisions and DECISION-0018 expansion drift", () => {
    const collision = healthyInput();
    collision.commands.collisions = [{ command: "ca-doctor", reason: "foreign-owner", owner: "C:/foreign.js" }];
    expect(diagnosePi(collision).find((row) => row.id === "commands")).toMatchObject({ state: "unhealthy" });

    const unverifiedVersion = healthyInput();
    unverifiedVersion.runtime.piVersion = "0.80.7";
    expect(diagnosePi(unverifiedVersion).find((row) => row.id === "version")).toMatchObject({ state: "unhealthy" });
    expect(diagnosePi(unverifiedVersion).find((row) => row.id === "commands")).toMatchObject({ state: "unhealthy" });
  });

  test("uses an independent version-specific expansion fingerprint and detects local drift", () => {
    expect(verifyNativeSkillExpansion("0.80.5", PI_FINGERPRINTS)).toBe(true);
    expect(verifyNativeSkillExpansion("0.80.10", PI_FINGERPRINTS)).toBe(true);
    expect(verifyNativeSkillExpansion("0.80.10", PI_FINGERPRINTS, (...args) => `${args.join(":")} drift`)).toBe(false);
    expect(verifyNativeSkillExpansion("0.80.7", PI_FINGERPRINTS)).toBe(false);
  });

  test("recognizes only the exact shipped hardened child bytes", async () => {
    const childPath = resolve(ROOT, "extensions", "codearbiter-child.js");
    writeFileSync(childPath, SHIPPED_CHILD);
    const extensionPath = resolve(ROOT, "extensions", "codearbiter.js");
    const skillPath = resolve(ROOT, "skills", "ca-doctor", "SKILL.md");
    const sourceInfo = (path: string) => ({
      path, source: "fixture", scope: "user" as const, origin: "package" as const, baseDir: ROOT,
    });
    const commands = [
      { name: "ca-doctor", source: "extension" as const, sourceInfo: sourceInfo(extensionPath) },
      { name: "skill:ca-doctor", source: "skill" as const, sourceInfo: sourceInfo(skillPath) },
    ];
    const collected = await collectPiDoctorInput({
      packageRoot: ROOT,
      packageScope: "user",
      extensionPath,
      runtime: healthyInput().runtime,
      context: { cwd: ROOT, signal: undefined, ui: { notify: () => undefined, setStatus: () => undefined } },
      commands,
      catalog: [{ name: "doctor", description: "doctor", skillPath: "skills/ca-doctor/SKILL.md" }],
      bridge: { call: async () => ({ version: 1, outcome: "allow" }) },
      bridgePrepared: true,
      projectTrustRequired: false,
      childPath,
      wrapperSourcePath: extensionPath,
      activeTools: ["bash", "write", "edit"],
      allTools: ["bash", "write", "edit"].map((name) => ({ name, sourceInfo: sourceInfo(extensionPath) })),
      expansionFingerprints: PI_FINGERPRINTS,
      childFingerprint: SHIPPED_CHILD_SHA256,
    });
    expect(collected.child.artifact).toBe("enforced");
    expect(diagnosePi(collected).find((row) => row.id === "child")).toMatchObject({ state: "healthy" });

    for (const suffix of [
      "\npi.registerTool({ name: 'bash' });\n",
      "\n// .registerTool( and tool_call are inert text\nconst bait = 'tool_call';\n",
    ]) {
      writeFileSync(childPath, Buffer.concat([SHIPPED_CHILD, Buffer.from(suffix)]));
      const changed = await collectPiDoctorInput({
        packageRoot: ROOT,
        packageScope: "user",
        extensionPath,
        runtime: healthyInput().runtime,
        context: { cwd: ROOT, signal: undefined, ui: { notify: () => undefined, setStatus: () => undefined } },
        commands,
        catalog: [{ name: "doctor", description: "doctor", skillPath: "skills/ca-doctor/SKILL.md" }],
        bridge: { call: async () => ({ version: 1, outcome: "allow" }) },
        bridgePrepared: true,
        projectTrustRequired: false,
        childPath,
        wrapperSourcePath: extensionPath,
        activeTools: ["bash", "write", "edit"],
        allTools: ["bash", "write", "edit"].map((name) => ({ name, sourceInfo: sourceInfo(extensionPath) })),
        expansionFingerprints: PI_FINGERPRINTS,
        childFingerprint: SHIPPED_CHILD_SHA256,
      });
      expect(changed.child.artifact, suffix).toBe("unknown");
      expect(diagnosePi(changed).find((row) => row.id === "child"), suffix).toMatchObject({ state: "unhealthy" });
    }
  });

  test("reports enabled global untrusted state without a bridge probe or wrapper self-test", async () => {
    const extensionPath = resolve(ROOT, "extensions", "codearbiter.js");
    const skillPath = resolve(ROOT, "skills", "ca-doctor", "SKILL.md");
    const sourceInfo = (path: string) => ({
      path, source: "fixture", scope: "user" as const, origin: "package" as const, baseDir: ROOT,
    });
    let bridgeCalls = 0;
    const collected = await collectPiDoctorInput({
      packageRoot: ROOT,
      packageScope: "user",
      extensionPath,
      runtime: { ...healthyInput().runtime, pythonMajor: null },
      context: {
        cwd: ROOT,
        signal: undefined,
        isProjectTrusted: () => false,
        ui: { notify: () => undefined, setStatus: () => undefined },
      },
      commands: [
        { name: "ca-doctor", source: "extension" as const, sourceInfo: sourceInfo(extensionPath) },
        { name: "skill:ca-doctor", source: "skill" as const, sourceInfo: sourceInfo(skillPath) },
      ],
      catalog: [{ name: "doctor", description: "doctor", skillPath: "skills/ca-doctor/SKILL.md" }],
      bridge: { call: async () => { bridgeCalls += 1; return { version: 1, outcome: "allow" }; } },
      bridgePrepared: false,
      projectTrustRequired: true,
      childPath: resolve(ROOT, "extensions", "codearbiter-child.js"),
      wrapperSourcePath: extensionPath,
      activeTools: [],
      allTools: [],
      expansionFingerprints: PI_FINGERPRINTS,
      childFingerprint: SHIPPED_CHILD_SHA256,
    });
    let wrapperCalls = 0;
    const wrapper = await runPiWrapperSelfTest({
      enabled: true,
      projectTrusted: false,
      executeBash: async () => { wrapperCalls += 1; return {}; },
    });
    const diagnoses = diagnosePi(collected);

    expect(bridgeCalls).toBe(0);
    expect(wrapperCalls).toBe(0);
    expect(diagnoses.find((row) => row.id === "trust")).toMatchObject({ state: "unhealthy" });
    expect(diagnoses.find((row) => row.id === "python")).toMatchObject({ state: "degraded" });
    expect(diagnoses.find((row) => row.id === "bridge")).toMatchObject({ state: "degraded" });
    expect(diagnoses.find((row) => row.id === "final-arguments")).toMatchObject({ state: "degraded" });
    expect(wrapper).toMatchObject({ state: "degraded", message: expect.stringContaining("project trust") });
  });

  test("rejects unrelated package, runtime, core, child, and wrapper paths despite forged healthy booleans", () => {
    const forged = healthyInput();
    forged.package.extensionPath = "C:/unrelated/codearbiter.js";
    forged.runtime.moduleEntry = "C:/unrelated/index.js";
    forged.core.bridgeScript = "C:/unrelated/pi-bridge.py";
    forged.child.path = "C:/unrelated/codearbiter-child.js";
    (forged.finalArguments as unknown as { wrapperSourcePath: string }).wrapperSourcePath = "C:/foreign.js";
    const result = diagnosePi(forged);
    for (const id of ["package", "core", "child", "module-identity", "final-arguments"]) {
      expect(result.find((row) => row.id === id), id).toMatchObject({ state: "unhealthy" });
    }
  });

  test("wrapper self-test calls only the stored wrapper with the exact H-03 dry-run", async () => {
    const calls: Array<Record<string, unknown>> = [];
    const diagnosis = await runPiWrapperSelfTest({
      enabled: true,
      executeBash: async (input) => {
        calls.push(input);
        throw new Error("BLOCKED [H-03]: wildcard staging is prohibited");
      },
    });
    expect(calls).toEqual([{ command: "git add --all --dry-run" }]);
    expect(diagnosis).toEqual({
      id: "wrapper-self-test",
      state: "healthy",
      message: "The stored governed Pi bash wrapper returned the exact shared-core H-03 block for git add --all --dry-run; no staging occurred.",
      remediation: "Run /ca-doctor again in an arbiter-enabled repository after restoring or upgrading Pi/ca-pi.",
    });
  });

  test("wrapper self-test is unhealthy if the dry-run executes or lacks an exact H-03 block", async () => {
    const executed = await runPiWrapperSelfTest({ enabled: true, executeBash: async () => ({ content: [] }) });
    const wrong = await runPiWrapperSelfTest({
      enabled: true,
      executeBash: async () => { throw new Error("BLOCKED [H-19]"); },
    });
    const bait = await runPiWrapperSelfTest({
      enabled: true,
      executeBash: async () => { throw new Error("wrapper did not return [H-03]"); },
    });
    expect(executed.state).toBe("unhealthy");
    expect(wrong.state).toBe("unhealthy");
    expect(bait.state).toBe("unhealthy");
    expect(formatPiDoctorReport([...diagnosePi(healthyInput()), executed])).toContain("UNHEALTHY");
  });

  test("wrapper self-test skips while dormant without claiming active dispatch", async () => {
    let called = false;
    const result = await runPiWrapperSelfTest({
      enabled: false,
      executeBash: async () => { called = true; },
    });
    expect(called).toBe(false);
    expect(result).toMatchObject({ id: "wrapper-self-test", state: "degraded" });
    expect(result.message).toContain("was skipped");
    expect(JSON.stringify([result, ...diagnosePi(healthyInput())])).not.toContain("live-fire");
  });
});
