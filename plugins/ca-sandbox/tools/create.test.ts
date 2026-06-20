/**
 * create.test.ts — clone-input trust model (T-09 hardening; AC-01 trust boundary).
 *
 * The repo url is the one create input that flows into git's argv inside a
 * networked, root clone container. git reads a leading-`-` value as a flag
 * (argument injection) and its transport-helper syntax (ext::, fd::, file://) runs
 * commands or reads host paths. validateRepoUrl allowlists plain network remotes
 * only; defaultCloneRepo additionally emits `--` before the url. Pure unit layer —
 * no docker; runs everywhere. The end-to-end clone is exercised by lifecycle.test.ts.
 */
import { describe, it, expect } from "vitest";
import {
  validateRepoUrl,
  InvalidRepoUrlError,
  buildCloneArgs,
  APP_DIR,
} from "./create.ts";

describe("validateRepoUrl — clone-input trust model (AC-01)", () => {
  it("accepts plain network remotes (https / ssh / scp-like)", () => {
    expect(() => validateRepoUrl("https://github.com/owner/repo.git")).not.toThrow();
    expect(() => validateRepoUrl("https://gitlab.example.com/a/b")).not.toThrow();
    expect(() => validateRepoUrl("ssh://git@github.com/owner/repo.git")).not.toThrow();
    expect(() => validateRepoUrl("git@github.com:owner/repo.git")).not.toThrow();
  });

  it("REJECTS git argument injection (a url beginning with '-')", () => {
    expect(() => validateRepoUrl("--upload-pack=touch /tmp/pwned")).toThrow(InvalidRepoUrlError);
    expect(() => validateRepoUrl("-x")).toThrow(InvalidRepoUrlError);
  });

  it("REJECTS git transport-helper / local transports (ext::, fd::, file://)", () => {
    expect(() => validateRepoUrl('ext::sh -c "touch /tmp/pwned"')).toThrow(InvalidRepoUrlError);
    expect(() => validateRepoUrl("fd::17")).toThrow(InvalidRepoUrlError);
    expect(() => validateRepoUrl("file:///etc/passwd")).toThrow(InvalidRepoUrlError);
  });

  it("REJECTS other unknown / non-network schemes and empties", () => {
    expect(() => validateRepoUrl("")).toThrow();
    expect(() => validateRepoUrl("http://insecure.example.com/repo")).toThrow(InvalidRepoUrlError);
    expect(() => validateRepoUrl("javascript:alert(1)")).toThrow(InvalidRepoUrlError);
    expect(() => validateRepoUrl("/local/path")).toThrow(InvalidRepoUrlError);
  });
});

describe("buildCloneArgs — argv shape (AC-01 defense in depth)", () => {
  const url = "https://github.com/owner/repo.git";
  const argv = buildCloneArgs(url, "ca-sbx-vol-demo");

  it("emits an end-of-options `--` immediately before the url", () => {
    const sep = argv.indexOf("--");
    expect(sep).toBeGreaterThanOrEqual(0);
    // `--` must sit directly before the untrusted url so a leading-`-` value is an
    // operand to git, never a flag.
    expect(argv[sep + 1]).toBe(url);
    expect(argv[sep + 2]).toBe(APP_DIR);
  });

  it("the `--` follows the clone subcommand and its flags (git parses it)", () => {
    const sep = argv.indexOf("--");
    const clone = argv.indexOf("clone");
    expect(clone).toBeGreaterThanOrEqual(0);
    expect(sep).toBeGreaterThan(clone);
    // Everything between `clone` and `--` is a known flag, never the url.
    expect(argv.slice(clone, sep)).not.toContain(url);
  });
});
