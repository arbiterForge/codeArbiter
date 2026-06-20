/**
 * T-03 / AC-02 — mount-arg builder.
 *
 * The load-bearing isolation invariant (spec "Load-bearing invariant", AC-01/AC-02):
 * untrusted code in the box can never reach the host filesystem. The single
 * structural guard at the mount layer is: a sandbox container's argv may contain
 * ONLY `type=volume` / `type=tmpfs` mounts, and ANY bind spec — whether expressed
 * as `type=bind` in a --mount spec or as the classic `-v host:container` form —
 * must be REJECTED, never silently dropped. These tests are the RED gate for that
 * builder.
 */
import { describe, it, expect } from "vitest";
import { buildMountArgs, type MountSpec } from "./mounts.ts";

describe("buildMountArgs — bind rejection (AC-02)", () => {
  it("throws on an explicit type=bind spec", () => {
    const specs: MountSpec[] = [
      { type: "bind", source: "/etc/passwd", target: "/work/passwd" } as unknown as MountSpec,
    ];
    expect(() => buildMountArgs(specs)).toThrow(/bind/i);
  });

  it("throws on the classic -v host:container shorthand", () => {
    const specs = [
      { v: "/home/user/secrets:/work/secrets" } as unknown as MountSpec,
    ];
    expect(() => buildMountArgs(specs)).toThrow(/bind/i);
  });

  it("throws on a -v spec given as a bare string", () => {
    expect(() => buildMountArgs(["/var/run/docker.sock:/var/run/docker.sock" as unknown as MountSpec])).toThrow(/bind/i);
  });

  it("throws on an unknown mount type", () => {
    const specs = [
      { type: "npipe", source: "x", target: "/work/x" } as unknown as MountSpec,
    ];
    expect(() => buildMountArgs(specs)).toThrow();
  });

  it("rejects even when a volume spec precedes a bind spec (no partial argv)", () => {
    const specs: MountSpec[] = [
      { type: "volume", source: "ca-sbx-vol-1", target: "/work/repo" },
      { type: "bind", source: "/etc", target: "/work/etc" } as unknown as MountSpec,
    ];
    expect(() => buildMountArgs(specs)).toThrow(/bind/i);
  });
});

describe("buildMountArgs — only volume/tmpfs argv (AC-02)", () => {
  it("emits --mount type=volume argv for a named-volume spec", () => {
    const argv = buildMountArgs([
      { type: "volume", source: "ca-sbx-vol-abc", target: "/work/repo" },
    ]);
    expect(argv).toEqual(["--mount", "type=volume,source=ca-sbx-vol-abc,target=/work/repo"]);
  });

  it("emits --mount type=tmpfs argv for a tmpfs spec (no source)", () => {
    const argv = buildMountArgs([{ type: "tmpfs", target: "/tmp" }]);
    expect(argv).toEqual(["--mount", "type=tmpfs,target=/tmp"]);
  });

  it("honours a read-only volume flag", () => {
    const argv = buildMountArgs([
      { type: "volume", source: "ca-sbx-deps", target: "/deps", readonly: true },
    ]);
    expect(argv).toEqual(["--mount", "type=volume,source=ca-sbx-deps,target=/deps,readonly"]);
  });

  it("returns an empty argv for no specs", () => {
    expect(buildMountArgs([])).toEqual([]);
  });

  it("every generated token's type= field is volume or tmpfs only — never bind", () => {
    const argv = buildMountArgs([
      { type: "volume", source: "ca-sbx-vol-abc", target: "/work/repo" },
      { type: "tmpfs", target: "/run" },
      { type: "tmpfs", target: "/tmp" },
    ]);
    const specTokens = argv.filter((a) => a !== "--mount");
    expect(specTokens.length).toBeGreaterThan(0);
    for (const tok of specTokens) {
      const m = tok.match(/(?:^|,)type=([^,]+)/);
      expect(m).not.toBeNull();
      expect(["volume", "tmpfs"]).toContain(m![1]);
      expect(tok).not.toMatch(/type=bind/);
    }
  });
});
