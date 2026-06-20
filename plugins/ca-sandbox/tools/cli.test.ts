/**
 * cli.test.ts — T-15. Covers AC-01, AC-09, AC-10, AC-11.
 *
 * The CLI dispatch surface: `sandbox <subcommand> ...` parses each subcommand's
 * args into a typed command object and dispatches to the module that owns the
 * behavior (create.ts / destroy.ts / exec.ts / cp.ts). The subcommands are
 * create / shell / exec / cp / destroy (+ prune, the AC-11 reclaim verb).
 *
 * This task is the WIRING, not the behavior — the modules it calls are tested
 * (and docker-gated) in T-09/T-11/T-12. So these tests are PURE: they prove
 *   1. parseCli(argv) turns each subcommand's args into the right command shape,
 *   2. an UNKNOWN FLAG is rejected (a CliError), and
 *   3. runCli dispatches the parsed command to the correct injected handler with
 *      the correctly-shaped arguments (no real docker — the handlers are fakes).
 *
 * The `--` separator on `exec` is honored verbatim (everything after `--` is the
 * in-container argv, AC-09); `cp` parses the `<id>:<path> <dest>` pull direction
 * (AC-10); create/destroy/prune map to their lifecycle verbs (AC-01/AC-11).
 */
import { describe, it, expect, vi } from "vitest";
import { parseCli, runCli, CliError, type Handlers } from "./cli.ts";

// --------------------------------------------------------------------------
// parseCli — each subcommand parses its own args into a typed command.
// --------------------------------------------------------------------------
describe("parseCli — subcommand recognition", () => {
  it("rejects an empty argv (no subcommand) with a CliError", () => {
    expect(() => parseCli([])).toThrow(CliError);
  });

  it("rejects an unknown subcommand with a CliError", () => {
    expect(() => parseCli(["frobnicate"])).toThrow(CliError);
  });
});

describe("parseCli — create (AC-01)", () => {
  it("parses `create <url>` into a create command with offline default", () => {
    const cmd = parseCli(["create", "https://github.com/o/r"]);
    expect(cmd.kind).toBe("create");
    if (cmd.kind !== "create") throw new Error("type");
    expect(cmd.url).toBe("https://github.com/o/r");
    expect(cmd.netPolicy).toBe("offline");
  });

  it("parses `--net=clone-then-cut` into the netPolicy", () => {
    const cmd = parseCli(["create", "https://x", "--net=clone-then-cut"]);
    if (cmd.kind !== "create") throw new Error("type");
    expect(cmd.netPolicy).toBe("clone-then-cut");
  });

  it("parses `--net allowlist` (space form) into the netPolicy", () => {
    const cmd = parseCli(["create", "https://x", "--net", "allowlist"]);
    if (cmd.kind !== "create") throw new Error("type");
    expect(cmd.netPolicy).toBe("allowlist");
  });

  it("rejects an unknown --net value", () => {
    expect(() => parseCli(["create", "https://x", "--net=sideways"])).toThrow(CliError);
  });

  it("requires a url", () => {
    expect(() => parseCli(["create"])).toThrow(CliError);
  });

  it("rejects an UNKNOWN FLAG on create", () => {
    expect(() => parseCli(["create", "https://x", "--turbo"])).toThrow(CliError);
  });
});

describe("parseCli — exec (AC-09)", () => {
  it("parses `exec <id> -- sh -c 'exit 7'` keeping the post-`--` argv verbatim", () => {
    const cmd = parseCli(["exec", "abc123", "--", "sh", "-c", "exit 7"]);
    expect(cmd.kind).toBe("exec");
    if (cmd.kind !== "exec") throw new Error("type");
    expect(cmd.id).toBe("abc123");
    expect(cmd.argv).toEqual(["sh", "-c", "exit 7"]);
  });

  it("treats flags AFTER `--` as part of the in-container argv, not CLI flags", () => {
    const cmd = parseCli(["exec", "abc123", "--", "ls", "--all"]);
    if (cmd.kind !== "exec") throw new Error("type");
    // `--all` is the container command's flag, not an unknown CLI flag.
    expect(cmd.argv).toEqual(["ls", "--all"]);
  });

  it("requires an id", () => {
    expect(() => parseCli(["exec"])).toThrow(CliError);
  });

  it("requires a non-empty command after `--`", () => {
    expect(() => parseCli(["exec", "abc123", "--"])).toThrow(CliError);
  });

  it("rejects an UNKNOWN FLAG before `--`", () => {
    expect(() => parseCli(["exec", "abc123", "--loud", "--", "ls"])).toThrow(CliError);
  });
});

describe("parseCli — cp (AC-10)", () => {
  it("parses `cp <id>:<path> <dest>` into the pull-only triple", () => {
    const cmd = parseCli(["cp", "abc123:/work/out.txt", "./out.txt"]);
    expect(cmd.kind).toBe("cp");
    if (cmd.kind !== "cp") throw new Error("type");
    expect(cmd.id).toBe("abc123");
    expect(cmd.containerPath).toBe("/work/out.txt");
    expect(cmd.hostDest).toBe("./out.txt");
  });

  it("rejects a source without the `<id>:` container prefix (no host->container push)", () => {
    expect(() => parseCli(["cp", "./local.txt", "abc123:/work/in.txt"])).toThrow(CliError);
  });

  it("requires both a source and a dest", () => {
    expect(() => parseCli(["cp", "abc123:/work/out.txt"])).toThrow(CliError);
  });

  it("rejects an UNKNOWN FLAG on cp", () => {
    expect(() => parseCli(["cp", "abc:/work/x", "./x", "--force"])).toThrow(CliError);
  });
});

describe("parseCli — destroy / prune (AC-11)", () => {
  it("parses `destroy <id>` into a destroy command", () => {
    const cmd = parseCli(["destroy", "abc123"]);
    expect(cmd.kind).toBe("destroy");
    if (cmd.kind !== "destroy") throw new Error("type");
    expect(cmd.id).toBe("abc123");
    expect(cmd.keepVolume).toBe(false);
  });

  it("parses `destroy <id> --keep-volume`", () => {
    const cmd = parseCli(["destroy", "abc123", "--keep-volume"]);
    if (cmd.kind !== "destroy") throw new Error("type");
    expect(cmd.keepVolume).toBe(true);
  });

  it("requires an id for destroy", () => {
    expect(() => parseCli(["destroy"])).toThrow(CliError);
  });

  it("rejects an UNKNOWN FLAG on destroy", () => {
    expect(() => parseCli(["destroy", "abc123", "--now"])).toThrow(CliError);
  });

  it("parses bare `prune` (no id) into a prune command", () => {
    const cmd = parseCli(["prune"]);
    expect(cmd.kind).toBe("prune");
  });

  it("rejects an UNKNOWN FLAG on prune", () => {
    expect(() => parseCli(["prune", "--all"])).toThrow(CliError);
  });
});

describe("parseCli — shell", () => {
  it("parses `shell <id>` into a shell command with a default shell", () => {
    const cmd = parseCli(["shell", "abc123"]);
    expect(cmd.kind).toBe("shell");
    if (cmd.kind !== "shell") throw new Error("type");
    expect(cmd.id).toBe("abc123");
    expect(cmd.shell).toBe("sh");
  });

  it("parses `shell <id> --shell=bash`", () => {
    const cmd = parseCli(["shell", "abc123", "--shell=bash"]);
    if (cmd.kind !== "shell") throw new Error("type");
    expect(cmd.shell).toBe("bash");
  });

  it("requires an id for shell", () => {
    expect(() => parseCli(["shell"])).toThrow(CliError);
  });

  it("rejects an UNKNOWN FLAG on shell", () => {
    expect(() => parseCli(["shell", "abc123", "--root"])).toThrow(CliError);
  });
});

// --------------------------------------------------------------------------
// runCli — dispatch the parsed command to the right (injected) handler.
// --------------------------------------------------------------------------
function fakeHandlers(): Handlers {
  return {
    create: vi.fn(async () => ({
      id: "id1",
      volumeName: "vol1",
      image: "img1",
      containerId: "cid1",
      notes: [],
    })),
    destroy: vi.fn(() => ({
      id: "id1",
      removedContainers: ["cid1"],
      removedVolumes: ["vol1"],
      keptVolumes: [],
    })),
    prune: vi.fn(() => ({ removedContainers: [], removedVolumes: [] })),
    exec: vi.fn(() => ({
      id: "id1",
      exitCode: 7,
      stdout: "",
      stderr: "",
      durationMs: 1,
      truncated: false,
    })),
    cp: vi.fn(() => ({ code: 0, stdout: "", stderr: "" })),
    shell: vi.fn(() => 0),
  };
}

describe("runCli — dispatch to modules (AC-01/09/10/11)", () => {
  it("dispatches create -> handlers.create(url, {netPolicy, keepVolume})", async () => {
    const h = fakeHandlers();
    const code = await runCli(["create", "https://x", "--net=clone-then-cut"], h);
    expect(code).toBe(0);
    expect(h.create).toHaveBeenCalledTimes(1);
    const [url, opts] = (h.create as any).mock.calls[0];
    expect(url).toBe("https://x");
    expect(opts.netPolicy).toBe("clone-then-cut");
  });

  it("dispatches exec -> handlers.exec(id, argv) and returns the inner exitCode (AC-09)", async () => {
    const h = fakeHandlers();
    const code = await runCli(["exec", "abc123", "--", "sh", "-c", "exit 7"], h);
    expect(h.exec).toHaveBeenCalledWith("abc123", ["sh", "-c", "exit 7"]);
    // The CLI propagates the in-container exit code as its own (AC-09 exitCode:7).
    expect(code).toBe(7);
  });

  it("dispatches cp -> handlers.cp(id, containerPath, hostDest) (AC-10)", async () => {
    const h = fakeHandlers();
    const code = await runCli(["cp", "abc123:/work/out.txt", "./out.txt"], h);
    expect(h.cp).toHaveBeenCalledWith("abc123", "/work/out.txt", "./out.txt");
    expect(code).toBe(0);
  });

  it("dispatches destroy -> handlers.destroy(id, {keepVolume}) (AC-11)", async () => {
    const h = fakeHandlers();
    await runCli(["destroy", "abc123", "--keep-volume"], h);
    const [id, opts] = (h.destroy as any).mock.calls[0];
    expect(id).toBe("abc123");
    expect(opts.keepVolume).toBe(true);
  });

  it("dispatches prune -> handlers.prune() (AC-11)", async () => {
    const h = fakeHandlers();
    await runCli(["prune"], h);
    expect(h.prune).toHaveBeenCalledTimes(1);
  });

  it("dispatches shell -> handlers.shell(id, shell) and returns its code", async () => {
    const h = fakeHandlers();
    const code = await runCli(["shell", "abc123", "--shell=bash"], h);
    expect(h.shell).toHaveBeenCalledWith("abc123", "bash");
    expect(code).toBe(0);
  });

  it("returns a non-zero code and does NOT throw on an unknown flag", async () => {
    const h = fakeHandlers();
    const code = await runCli(["create", "https://x", "--turbo"], h);
    expect(code).not.toBe(0);
    expect(h.create).not.toHaveBeenCalled();
  });

  it("a non-zero exec exit code propagates as the CLI's code", async () => {
    const h = fakeHandlers();
    (h.exec as any).mockReturnValueOnce({
      id: "id1",
      exitCode: 42,
      stdout: "",
      stderr: "",
      durationMs: 1,
      truncated: false,
    });
    const code = await runCli(["exec", "abc123", "--", "false"], h);
    expect(code).toBe(42);
  });

  it("a non-zero cp exit code propagates as the CLI's code", async () => {
    const h = fakeHandlers();
    (h.cp as any).mockReturnValueOnce({ code: 1, stdout: "", stderr: "no such file" });
    const code = await runCli(["cp", "abc:/work/missing", "./x"], h);
    expect(code).toBe(1);
  });
});
