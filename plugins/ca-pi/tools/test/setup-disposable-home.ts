/**
 * setup-disposable-home.ts — issue #464.
 *
 * `.codearbiter/security-controls.md` states verbatim that tests use disposable
 * Pi homes and dummy credentials and NEVER inspect or mutate the real auth
 * store. `runner-isolation.test.ts` contradicted that across roughly 25 tests:
 * its request fixture spreads `process.env`, so every case that did not
 * explicitly override `HOME` / `PI_CODING_AGENT_DIR` resolved the operator's
 * actual `~/.pi/agent/auth.json`.
 *
 * A control document that describes behaviour the suite does not follow is
 * worse than no document — reviewers cite it, and it is wrong. And reading a
 * real credential store during an ordinary test run is the exact boundary
 * ADR-0016 and ADR-0019 exist to police; it also makes the suite's result
 * depend on developer machine state.
 *
 * This runs BEFORE any test file, per worker, and repoints the home the whole
 * process resolves at a disposable root seeded with an obviously fake record.
 * Fixing the class rather than the instances is deliberate: the fixture spread
 * is what leaked, so every future test inherits the disposable home for free
 * instead of each author remembering an override. Tests that set their own
 * `HOME` / `PI_CODING_AGENT_DIR` are unaffected — they already point somewhere
 * disposable, which is what they were demonstrating.
 *
 * Every variable `os.homedir()` consults is set, not just `HOME`: on Windows
 * Node reads `USERPROFILE` first, then `HOMEDRIVE` + `HOMEPATH`, and ignores
 * `HOME` entirely.
 */
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";

/** Unmistakably fake, and shaped like a real record so a reader that parses it
 * still gets a valid document rather than a confusing crash. */
export const DUMMY_AUTH = {
  openai: { type: "api_key", key: "dummy-disposable-home-not-a-credential" },
} as const;

const root = mkdtempSync(resolve(tmpdir(), "ca-pi-operator-home-"));
const agent = resolve(root, ".pi", "agent");
mkdirSync(agent, { recursive: true });
writeFileSync(resolve(agent, "auth.json"), JSON.stringify(DUMMY_AUTH), "utf8");

process.env.HOME = root;
process.env.USERPROFILE = root;
delete process.env.HOMEDRIVE;
delete process.env.HOMEPATH;
process.env.PI_CODING_AGENT_DIR = agent;
// Read by the guard in security.test.ts, which asserts the redirection actually
// took effect rather than trusting that this file ran.
process.env.CODEARBITER_TEST_DISPOSABLE_HOME = root;

// Best-effort: a leaked temp home must never be the thing that fails a suite.
process.on("exit", () => {
  try {
    rmSync(root, { recursive: true, force: true });
  } catch {
    /* ignore */
  }
});
