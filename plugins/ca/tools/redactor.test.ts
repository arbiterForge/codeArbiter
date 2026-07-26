/**
 * Unit tests for redactor.ts — the outbound-boundary secret redactor.
 *
 * Scoped to the SPAN redaction path and the filename denylist, plus the two
 * SECRET_LINE properties nothing else in the tree pins (see below).
 *
 * Why a unit file when farm.test.ts already has a PEM case: that case
 * (`redacts a multi-line PEM private key as a span`) drives the whole dispatcher
 * through `spawn()`, so it proves the behaviour end-to-end but exercises the
 * redactor in a CHILD process — which the v8 coverage provider does not
 * instrument. It also plants exactly one shape: unindented armor, at column 0,
 * with well-formed delimiters. The regressions that actually leak key material
 * are the near misses around that shape, and they are what this file pins:
 * indented armor, a body line carrying inline armor, a delimiter with trailing
 * prose, and an unterminated block.
 *
 * Each case below states which single-point change to redactor.ts it kills.
 * That is not decoration — an adversarial pass on the first cut of this file
 * found 16 of 21 realistic mutants surviving while it reported 100% lines and
 * 87.5% branches on the module. Coverage is not the property being tested here;
 * "does the assertion fail when the source is wrong" is.
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
  it("collapses a BEGIN..END block to exactly one marker", () => {
    const out = redactSecrets(
      ["const pem = `", begin(PRIVATE_KEY), ...BODY, end(PRIVATE_KEY), "`;"].join("\n"),
    );

    // Exact whole-output equality throughout this file. A per-line redactor
    // would emit five markers here, so the shape of the output — not merely
    // "the body is absent" — is what separates span redaction from the
    // per-line fallback.
    expect(out).toBe(["const pem = `", MARKER, "`;"].join("\n"));
  });

  it("stops the span at the END delimiter and preserves the content after it", () => {
    // Kills: dropping `!PEM_END.test(...)` from the while condition, which runs
    // the span to end-of-content. The key is still redacted under that mutant,
    // so only the SURVIVORS distinguish it from correct behaviour.
    const out = redactSecrets(
      [
        begin(PRIVATE_KEY),
        ...BODY,
        end(PRIVATE_KEY),
        "export const PORT = 8080;",
        "export const NAME = 'after-the-span';",
      ].join("\n"),
    );

    expect(out).toBe([MARKER, "export const PORT = 8080;", "export const NAME = 'after-the-span';"].join("\n"));
  });

  it("redacts through end-of-content when the block is never terminated", () => {
    // A truncated armored body is still key material, so an unterminated block
    // takes the rest of the content with it. `trailing = 1;` is INSIDE the span.
    const out = redactSecrets([begin(PRIVATE_KEY), ...BODY, "trailing = 1;"].join("\n"));

    expect(out).toBe(MARKER);
  });

  it("spans INDENTED armor, whose body a column-0-only matcher transmits", () => {
    // Kills: removing `.trim()` from either delimiter test (redactor.ts:115 and
    // :121). Both survived the first cut of this file because every delimiter in
    // it sat at column 0. Indented armor is routine — a PEM inside a YAML block
    // scalar, or inside an indented template literal.
    //
    // Without the BEGIN trim: the header still trips SECRET_LINE's
    // `BEGIN.*PRIVATE` and is redacted per-line, but the indented BODY carries
    // no trigger word and ships verbatim. That is the leak this pins.
    // Without the END trim: the span never closes and swallows `after = 3;`.
    const out = redactSecrets(
      ["  " + begin(PRIVATE_KEY), "  " + BODY[0], "  " + end(PRIVATE_KEY), "after = 3;"].join("\n"),
    );

    expect(out).toBe([MARKER, "after = 3;"].join("\n"));
  });

  it("does not let a body line's INLINE end-armor close the span early", () => {
    // Kills: dropping PEM_END's `^` anchor. Under that mutant the span closes on
    // the body line below, and the two lines after it — real key body — ship.
    const out = redactSecrets(
      [
        begin(PRIVATE_KEY),
        `${BODY[0]} ${end(PRIVATE_KEY)}`,
        BODY[1],
        BODY[2],
        end(PRIVATE_KEY),
        "after = 2;",
      ].join("\n"),
    );

    expect(out).toBe([MARKER, "after = 2;"].join("\n"));
  });

  it("does not open a span on a BEGIN delimiter carrying trailing prose", () => {
    // Kills: dropping PEM_BEGIN's `-----\s*$` end anchor. Under that mutant a
    // documentation line opens a span and swallows the remainder of the file.
    // CERTIFICATE is used so SECRET_LINE has no trigger word to match on either
    // — the line must survive VERBATIM, which is the strongest form of the
    // assertion.
    const line = `${begin("CERTIFICATE")} <- what the header looks like`;
    const out = redactSecrets([line, "after = 5;"].join("\n"));

    expect(out).toBe([line, "after = 5;"].join("\n"));
  });

  it("does not open a span on a BEGIN delimiter carrying LEADING prose", () => {
    // The mirror of the case above, and it needs its own test: that one pins
    // PEM_BEGIN's `-----\s*$` end anchor, this one pins its `^` start anchor.
    // Here the armor sits at the END of the line, so the end anchor still
    // matches and only `^` stands between a comment and a span that swallows
    // the remainder of the file.
    const line = `// the header shape is ${begin("CERTIFICATE")}`;
    const out = redactSecrets([line, "after = 6;"].join("\n"));

    expect(out).toBe([line, "after = 6;"].join("\n"));
  });

  it("spans armor that carries no trigger word at all", () => {
    // CERTIFICATE matches no SECRET_LINE pattern, so this block reaches the span
    // path only via PEM_BEGIN. Kills: folding span detection into the
    // trigger-word test.
    const out = redactSecrets(
      [begin("CERTIFICATE"), ...BODY, end("CERTIFICATE"), "done = true;"].join("\n"),
    );

    expect(out).toBe([MARKER, "done = true;"].join("\n"));
  });

  it("redacts two separate blocks independently rather than merging them", () => {
    // Kills: resuming the scan from the wrong index, which either merges the
    // blocks (eating `between`) or re-enters the second BEGIN as content.
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

    expect(out).toBe([MARKER, "between = 'kept';", MARKER].join("\n"));
  });

  it("treats an inline delimiter mention as one line, not a span", () => {
    // Kills: dropping PEM_BEGIN's `^` anchor. `PRIVATE` still trips SECRET_LINE
    // so the line itself is redacted — but as ONE line, without consuming what
    // follows.
    const out = redactSecrets(
      [`the header reads ${begin(PRIVATE_KEY)} inline`, "next = 'must survive';"].join("\n"),
    );

    expect(out).toBe([MARKER, "next = 'must survive';"].join("\n"));
  });

  it("passes a lone END delimiter through, carrying no span state into it", () => {
    // Documented, previously unasserted: an END with no BEGIN is not armor and
    // holds no key material, so it survives verbatim rather than opening or
    // closing anything.
    const out = redactSecrets([end(PRIVATE_KEY), "after = 4;"].join("\n"));

    expect(out).toBe([end(PRIVATE_KEY), "after = 4;"].join("\n"));
  });
});

describe("redactSecrets — SECRET_LINE properties nothing else pins", () => {
  // farm.unit.test.ts pins the shared corpus (architecture-001) and the #439
  // prefix shapes, which between them cover `password`, AKIA, ghp_ and Bearer.
  // These two are NOT covered there: an adversarial pass confirmed that dropping
  // `token` from the pattern set, and dropping the whole pattern's `i` flag,
  // both survive every non-spawn suite in the tree.
  it("redacts a bare `token` trigger word", () => {
    expect(redactSecrets("const token = abc;")).toBe(MARKER);
  });

  it("matches trigger words case-insensitively", () => {
    expect(redactSecrets("API_KEY = value")).toBe(MARKER);
    expect(redactSecrets("PASSWORD = value")).toBe(MARKER);
  });
});

describe("isSecretBearingFilename — basename denylist", () => {
  it.each([
    [".env"],
    ["config/.env.production"],
    ["deploy/certs/server.pem"],
    ["keys/id_rsa"],
    ["keys/id_rsa.pub"],
    ["keys/id_ed25519.pub"],
    ["keys/id_ecdsa"],
    ["keys/id_ecdsa.pub"],
    ["store/keystore.p12"],
    ["store/keystore.pfx"],
    // BACKSLASH separators, against ANCHORED rules. The measurement platform is
    // Windows, and `split(/[\\/]/)` -> `split(/\//)` survived the entire tree on
    // the first cut of this file: the only backslash case then present was
    // `secrets\api.key`, which matches the SUFFIX rule `/\.key$/i` and so passes
    // whether or not the basename was extracted. Under that mutant a denylisted
    // private key is read and its contents cross the trust boundary.
    ["keys\\id_rsa"],
    ["config\\.env"],
    ["secrets\\api.key"],
  ])("denies %s", (relPath) => {
    expect(isSecretBearingFilename(relPath)).toBe(true);
  });

  it.each([
    // Each allow-case kills one specific rule-weakening mutation, and no two
    // kill the same one:
    ["src/environment.ts"], // `/^\.env$/i` -> `/env/i`
    ["config/apikey"], //     `/\.key$/i`  -> `/key$/i`  (the escaped dot)
    ["src/pemantle.ts"], //   `/\.pem$/i`  -> `/pem/i`
  ])("allows %s", (relPath) => {
    expect(isSecretBearingFilename(relPath)).toBe(false);
  });

  it("matches on the basename, not anywhere in the path", () => {
    // A directory named `.env` must not condemn an ordinary file beneath it.
    expect(isSecretBearingFilename(".env/notes.md")).toBe(false);
    expect(isSecretBearingFilename("src/id_rsa/index.ts")).toBe(false);
  });

  it("is case-insensitive on both the name and the extension", () => {
    expect(isSecretBearingFilename("CONFIG/.ENV")).toBe(true);
    expect(isSecretBearingFilename("certs/SERVER.PEM")).toBe(true);
    expect(isSecretBearingFilename("keys/ID_RSA")).toBe(true);
  });
});
