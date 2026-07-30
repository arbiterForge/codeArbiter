import { describe, expect, it } from "vitest";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  commandHostAvailability,
  loadHostCommandCatalogs,
  parseHostCommandCatalog,
} from "../../scripts/generator/host-command-catalog";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");

describe("host command catalogs", () => {
  it("parses each adapter's native command syntax", () => {
    expect(
      [...parseHostCommandCatalog("claude", "| `/ca:statusline` | none | status |")],
    ).toEqual(["statusline"]);
    expect(
      [...parseHostCommandCatalog("codex", "| `$ca-doctor` | none | doctor |")],
    ).toEqual(["doctor"]);
    expect(
      [...parseHostCommandCatalog("pi", "| `/ca-prune` | status | prune |")],
    ).toEqual(["prune"]);
  });

  it("derives availability independently for all three hosts", () => {
    const availability = commandHostAvailability("prune", {
      claude: new Set(["prune"]),
      codex: new Set(["doctor"]),
      pi: new Set(["prune"]),
    });
    expect(availability).toEqual({ claude: true, codex: false, pi: true });
  });

  it("matches the current shipped statusline and prune boundaries", () => {
    const catalogs = loadHostCommandCatalogs(resolve(repoRoot, "plugins/ca"));
    expect(commandHostAvailability("statusline", catalogs)).toEqual({
      claude: true,
      codex: false,
      pi: false,
    });
    expect(commandHostAvailability("prune", catalogs)).toEqual({
      claude: true,
      codex: false,
      pi: true,
    });
  });
});
