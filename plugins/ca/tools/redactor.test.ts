/**
 * Unit tests for redactor.ts — the outbound-boundary secret redactor.
 *
 * Scoped to the SPAN redaction path and the filename denylist. The trigger-word
 * and corpus-parity behaviour of `redactSecrets` is already pinned in
 * farm.unit.test.ts (and, on the hook side, in test_hooklib.py); this file does
 * not restate it.
 *
 * Why a unit file when farm.test.ts already has a PEM case: that case
 * (`redacts a multi-line PEM private key as a span`) drives the whole dispatcher
 * through `spawn()`, so it proves the behaviour end-to-end but exercises the
 * redactor in a CHILD process. It therefore cannot assert on span mechanics
 * directly, and the boundary cases below — an unterminated block, content
 * AFTER the END delimiter, non-trigger-word armor, one-marker-per-span — have
 * no coverage from it at all. Those boundaries are where a span redactor fails
 * quietly: too narrow and key body leaks, too greedy and it eats the rest of
 * the file while still looking like it worked.
 */
import { describe, expect, it } from "vitest";
import { isSecretBearingFilename, redactSecrets } from "./redactor.ts";

const MARKER = "[REDACTED — secret-pattern match removed before transmission]";

// The armor delimiters are ASSEMBLED AT RUNTIME rather than written as literals.
// A committed PEM header line is reported by gitleaks' `private-key` rule — the
// header alone is enough, no body required, which is why this comment does not
// spell one either. .gitleaks.toml is deliberately default-deny, so waiving it
// would mean pinning an anchored copy of this file's exact block shape, which
// then has to be re-derived every time the array is reformatted (see the
// farm.test.ts waiver in that file for what that costs). redactSecrets receives
// a byte-identical string either way, so there is nothing to buy with a waiver.
const ARMOR = "-".repeat(5);
const begin = (label: string): string => `${ARMOR}BEGIN ${label}${ARMOR}`;
const end = (label: string): string => `${ARMOR}END ${label}${ARMOR}`;
const PRIVATE_KEY = "RSA PRIVATE KEY";

// Body lines deliberately carry NO trigger word, so a purely per-line redactor
// would transmit them verbatim. That is the whole point of span redaction. They
// are also deliberately NOT base64-shaped — realistic key material would trip
// the hosted scanner for no gain, since the redactor never inspects the body.
const BODY = [
  "SPANBODYLINEONE0000000000000000000000000000000",
  "SPANBODYLINETWO1111111111111111111111111111111",
  "SPANBODYLINETHREE22222222222222222222222222===",
];

describe("redactSecrets — PEM span redaction", () => {
  it("collapses a BEGIN..END block to exactly one marker and emits no body line", () => {
    const out = redactSecrets(
      ["const pem = `", begin(PRIVATE_KEY), ...BODY, end(PRIVATE_KEY), "`;"].join("\n"),
    );

    for (const body of BODY) expect(out).not.toContain(body);
    // Exactly one marker: a per-line redactor would emit five (header + 3 body
    // + footer), so the count is what distinguishes span redaction from the
    // per-line fallback — not merely "a marker is present".
    expect(out.split(MARKER).length - 1).toBe(1);
    expect(out).toBe(["const pem = `", MARKER, "`;"].join("\n"));
  });

  it("stops the span at the END delimiter and preserves the content after it", () => {
    const out = redactSecrets(
      [
        begin(PRIVATE_KEY),
        ...BODY,
        end(PRIVATE_KEY),
        "export const PORT = 8080;",
        "export const NAME = 'after-the-span';",
      ].join("\n"),
    );

    // The span must be exclusive-of-what-follows. A `while` that dropped its
    // PEM_END test would run to end-of-content and swallow both lines below
    // while still redacting the key — indistinguishable from success unless
    // the survivors are asserted.
    expect(out).toBe([MARKER, "export const PORT = 8080;", "export const NAME = 'after-the-span';"].join("\n"));
  });

  it("redacts through end-of-content when the block is never terminated", () => {
    const out = redactSecrets([begin(PRIVATE_KEY), ...BODY, "trailing = 1;"].join("\n"));

    for (const body of BODY) expect(out).not.toContain(body);
    // An unterminated block takes the rest of the content with it, deliberately:
    // a truncated armored body is still key material. `trailing = 1;` is inside
    // the span and must NOT survive.
    expect(out).not.toContain("trailing = 1;");
    expect(out).toBe(MARKER);
  });

  it("spans armor that carries no trigger word at all", () => {
    // CERTIFICATE matches neither `BEGIN.*PRIVATE` nor any other SECRET_LINE
    // pattern, so this block reaches the span path only via PEM_BEGIN. If span
    // detection were folded into the trigger-word test, the body would ship.
    const out = redactSecrets(
      [begin("CERTIFICATE"), ...BODY, end("CERTIFICATE"), "done = true;"].join("\n"),
    );

    for (const body of BODY) expect(out).not.toContain(body);
    expect(out).toBe([MARKER, "done = true;"].join("\n"));
  });

  it("redacts two separate blocks independently rather than merging them", () => {
    const out = redactSecrets(
      [
        begin("CERTIFICATE"),
        BODY[0],
        end("CERTIFICATE"),
        "between = 'kept';",
        begin(PRIVATE_KEY),
        BODY[1],
        end(PRIVATE_KEY),
      ].join("\n"),
    );

    // Two markers, and the line between them survives: a span that resumed
    // scanning from the wrong index would either merge the blocks (eating
    // `between`) or re-enter the second BEGIN as ordinary content.
    expect(out).toBe([MARKER, "between = 'kept';", MARKER].join("\n"));
  });

  it("matches the delimiter only on its own line, so prose about a key is not a span", () => {
    // The delimiter regexes are anchored. An inline mention must fall through
    // to per-line handling — where `PRIVATE` still trips SECRET_LINE, so the
    // line is redacted, but as ONE line and without consuming what follows.
    const out = redactSecrets(
      [`the header reads ${begin(PRIVATE_KEY)} inline`, "next = 'must survive';"].join("\n"),
    );

    expect(out).toBe([MARKER, "next = 'must survive';"].join("\n"));
  });
});

describe("isSecretBearingFilename — basename denylist", () => {
  it.each([
    [".env", true],
    ["config/.env.production", true],
    ["deploy/certs/server.pem", true],
    ["keys/id_rsa", true],
    ["keys/id_ed25519.pub", true],
    ["secrets\\api.key", true],
    ["store/keystore.p12", true],
    ["store/keystore.pfx", true],
  ])("denies %s", (relPath, expected) => {
    expect(isSecretBearingFilename(relPath)).toBe(expected);
  });

  it.each([
    ["src/environment.ts", false],
    ["docs/env.md", false],
    ["src/keyboard.ts", false],
    ["src/monkey.ts", false],
    ["README.md", false],
  ])("allows %s", (relPath, expected) => {
    expect(isSecretBearingFilename(relPath)).toBe(expected);
  });

  it("matches on the basename, not anywhere in the path", () => {
    // A directory named `.env` must not condemn an ordinary file beneath it —
    // the denylist is a basename rule, and a substring implementation would
    // read this as a hit.
    expect(isSecretBearingFilename(".env/notes.md")).toBe(false);
    expect(isSecretBearingFilename("src/id_rsa/index.ts")).toBe(false);
  });

  it("is case-insensitive on both the name and the extension", () => {
    expect(isSecretBearingFilename("CONFIG/.ENV")).toBe(true);
    expect(isSecretBearingFilename("certs/SERVER.PEM")).toBe(true);
    expect(isSecretBearingFilename("keys/ID_RSA")).toBe(true);
  });
});
