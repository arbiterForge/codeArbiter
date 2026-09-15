/** release-applicability.test.ts — codeArbiter's release applicability derivation tests. */
import { createHash } from "node:crypto";
import { describe, expect, it } from "vitest";
import {
  createReleaseApplicabilityRecord,
  deriveVerifiedGovernanceReleases,
  repositoryGit,
  resolveDocumentationBuildIdentity,
  selectCurrentGovernanceReleases,
  serializeReleaseApplicabilityRecord,
  type DirectHookReplayEvidence,
  type ReleaseApplicabilityGit,
  type VerifiedGovernanceRelease,
} from "../../scripts/release-applicability";

const sha = "0123456789abcdef0123456789abcdef01234567";

function targets(overrides: Partial<Record<"ca" | "ca-codex" | "ca-pi", string>> = {}) {
  return `<!-- release-targets -->
[ca]
prefix: ${overrides.ca ?? "v"}
manifest: plugins/ca/.claude-plugin/plugin.json
provenance-manifest: .github/published-tags.json

[ca-codex]
prefix: ${overrides["ca-codex"] ?? "ca-codex-v"}
manifest: plugins/ca-codex/.codex-plugin/plugin.json
provenance-manifest: .github/published-tags.json

[ca-sandbox]
prefix: ca-sandbox-v
manifest: plugins/ca-sandbox/.claude-plugin/plugin.json
provenance-manifest: .github/published-tags.json

[ca-pi]
prefix: ${overrides["ca-pi"] ?? "ca-pi-v"}
manifest: plugins/ca-pi/package.json
manifest: package.json
provenance-manifest: .github/published-tags.json
<!-- /release-targets -->`;
}

function ledger(...tags: string[]) {
  return JSON.stringify({
    $comment: ["test fixture"],
    namespaces: ["v*", "ca-sandbox-v*", "ca-codex-v*", "ca-pi-v*"],
    verified_at: "2026-09-14",
    tags: Object.fromEntries(
      tags.map((tag) => [
        tag,
        { commit_sha: sha, object_sha: sha, object_type: "commit" },
      ]),
    ),
  });
}

function historicalGit(
  manifests: Record<string, unknown>,
  options: { head?: string; dirty?: boolean; missing?: string } = {},
): ReleaseApplicabilityGit & { reads: Array<[string, string]> } {
  const reads: Array<[string, string]> = [];
  return {
    reads,
    readAtCommit(commit, path) {
      reads.push([commit, path]);
      if (options.missing === path) throw new Error("bad object");
      return JSON.stringify(manifests[path]);
    },
    head: () => options.head ?? sha,
    isDirty: () => options.dirty ?? false,
  };
}

describe("selectCurrentGovernanceReleases", () => {
  it("selects the highest stable SemVer independently for every governance host (O-01)", () => {
    const selected = selectCurrentGovernanceReleases(
      targets(),
      ledger(
        "v2.9.0",
        "v2.10.0-beta.1",
        "v2.10.0",
        "ca-codex-v0.9.9",
        "ca-codex-v0.10.0-rc.1",
        "ca-codex-v0.9.10",
        "ca-pi-v0.10.9",
        "ca-pi-v0.11.0",
        "ca-sandbox-v99.0.0",
      ),
    );

    expect(selected).toEqual([
      { target: "ca", version: "2.10.0", tag: "v2.10.0", publicationCommit: sha },
      {
        target: "ca-codex",
        version: "0.9.10",
        tag: "ca-codex-v0.9.10",
        publicationCommit: sha,
      },
      {
        target: "ca-pi",
        version: "0.11.0",
        tag: "ca-pi-v0.11.0",
        publicationCommit: sha,
      },
    ]);
  });

  it.each([
    ["missing target", targets().replace(/\n\[ca-pi\][\s\S]*?(?=\n<!-- \/release-targets -->)/, "")],
    ["duplicate target", targets().replace("[ca-codex]", "[ca]\n[ca-codex]")],
    ["unsupported target", targets().replace("[ca-sandbox]", "[unknown-host]")],
    ["malformed target", targets({ "ca-codex": "not semver prefix " })],
  ])("rejects %s data (O-02)", (_case, releaseTargets) => {
    expect(() =>
      selectCurrentGovernanceReleases(
        releaseTargets,
        ledger("v1.0.0", "ca-codex-v1.0.0", "ca-pi-v1.0.0"),
      ),
    ).toThrow();
  });

  it("rejects malformed ledger JSON (O-02)", () => {
    expect(() => selectCurrentGovernanceReleases(targets(), "{not-json"))
      .toThrow(/ledger/i);
  });

  it.each([
    ["missing bounded block", "[ca]\nprefix: v\nmanifest: package.json"],
    ["missing manifest", targets().replace("manifest: plugins/ca/.claude-plugin/plugin.json\n", "")],
    ["duplicate manifest", targets().replace(
      "manifest: plugins/ca/.claude-plugin/plugin.json",
      "manifest: plugins/ca/.claude-plugin/plugin.json\nmanifest: plugins/ca/.claude-plugin/plugin.json",
    )],
  ])("rejects %s release declarations (O-02)", (_case, declarations) => {
    expect(() => selectCurrentGovernanceReleases(
      declarations, ledger("v1.0.0", "ca-codex-v1.0.0", "ca-pi-v1.0.0"),
    )).toThrow();
  });

  it("rejects malformed matching tags instead of silently skipping them (O-02)", () => {
    expect(() =>
      selectCurrentGovernanceReleases(
        targets(),
        ledger("v1.0.0", "ca-codex-vwat", "ca-pi-v1.0.0"),
      ),
    ).toThrow(/ca-codex-vwat/);
  });

  it("rejects a target with only prerelease receipts (O-02)", () => {
    expect(() =>
      selectCurrentGovernanceReleases(
        targets(),
        ledger("v1.0.0", "ca-codex-v1.0.0-beta.1", "ca-pi-v1.0.0"),
      ),
    ).toThrow(/stable.*ca-codex/i);
  });
});

describe("historical release applicability", () => {
  it("reads every declared manifest at its receipt commit and requires exact tag/version equality (O-03)", () => {
    const git = historicalGit({
      "plugins/ca/.claude-plugin/plugin.json": { version: "2.17.11" },
      "plugins/ca-codex/.codex-plugin/plugin.json": { version: "0.9.11" },
      "plugins/ca-pi/package.json": { version: "0.10.13" },
      "package.json": { version: "0.10.13" },
    });

    const verified = deriveVerifiedGovernanceReleases(
      targets(),
      ledger("v2.17.11", "ca-codex-v0.9.11", "ca-pi-v0.10.13"),
      git,
    );

    expect(verified).toEqual([
      {
        target: "ca",
        version: "2.17.11",
        tag: "v2.17.11",
        publicationCommit: sha,
        manifestPath: "plugins/ca/.claude-plugin/plugin.json",
        manifestPaths: ["plugins/ca/.claude-plugin/plugin.json"],
      },
      {
        target: "ca-codex",
        version: "0.9.11",
        tag: "ca-codex-v0.9.11",
        publicationCommit: sha,
        manifestPath: "plugins/ca-codex/.codex-plugin/plugin.json",
        manifestPaths: ["plugins/ca-codex/.codex-plugin/plugin.json"],
      },
      {
        target: "ca-pi",
        version: "0.10.13",
        tag: "ca-pi-v0.10.13",
        publicationCommit: sha,
        manifestPath: "plugins/ca-pi/package.json",
        manifestPaths: ["plugins/ca-pi/package.json", "package.json"],
      },
    ]);
    expect(git.reads).toEqual([
      [sha, "plugins/ca/.claude-plugin/plugin.json"],
      [sha, "plugins/ca-codex/.codex-plugin/plugin.json"],
      [sha, "plugins/ca-pi/package.json"],
      [sha, "package.json"],
    ]);
  });

  it("rejects a historical manifest whose version does not exactly match its selected tag (O-04)", () => {
    const git = historicalGit({
      "plugins/ca/.claude-plugin/plugin.json": { version: "99.0.0" },
      "plugins/ca-codex/.codex-plugin/plugin.json": { version: "0.9.11" },
      "plugins/ca-pi/package.json": { version: "0.10.13" },
      "package.json": { version: "0.10.13" },
    });

    expect(() =>
      deriveVerifiedGovernanceReleases(
        targets(),
        ledger("v2.17.11", "ca-codex-v0.9.11", "ca-pi-v0.10.13"),
        git,
      ),
    ).toThrow(/v2\.17\.11.*99\.0\.0|99\.0\.0.*v2\.17\.11/);
  });

  it("rejects an invalid receipt commit before attempting historical lookup (O-05)", () => {
    const git = historicalGit({});
    const invalidLedger = ledger("v2.17.11", "ca-codex-v0.9.11", "ca-pi-v0.10.13")
      .replaceAll(sha, "main");

    expect(() => deriveVerifiedGovernanceReleases(targets(), invalidLedger, git))
      .toThrow(/commit.*40.*hex|40.*hex.*commit/i);
    expect(git.reads).toEqual([]);
  });

  it("rejects a missing historical Git object with the affected tag and path (O-05)", () => {
    const missing = "plugins/ca-codex/.codex-plugin/plugin.json";
    const git = historicalGit(
      {
        "plugins/ca/.claude-plugin/plugin.json": { version: "2.17.11" },
        "plugins/ca-pi/package.json": { version: "0.10.13" },
        "package.json": { version: "0.10.13" },
      },
      { missing },
    );

    expect(() =>
      deriveVerifiedGovernanceReleases(
        targets(),
        ledger("v2.17.11", "ca-codex-v0.9.11", "ca-pi-v0.10.13"),
        git,
      ),
    ).toThrow(new RegExp(`ca-codex-v0\\.9\\.11.*${missing.replace(/[/.]/g, "\\$&")}`));
  });

  it("rejects a secondary historical manifest version mismatch (O-04)", () => {
    const git = historicalGit({
      "plugins/ca/.claude-plugin/plugin.json": { version: "2.17.11" },
      "plugins/ca-codex/.codex-plugin/plugin.json": { version: "0.9.11" },
      "plugins/ca-pi/package.json": { version: "0.10.13" },
      "package.json": { version: "0.10.12" },
    });

    expect(() =>
      deriveVerifiedGovernanceReleases(
        targets(),
        ledger("v2.17.11", "ca-codex-v0.9.11", "ca-pi-v0.10.13"),
        git,
      ),
    ).toThrow(/ca-pi-v0\.10\.13.*0\.10\.12|0\.10\.12.*ca-pi-v0\.10\.13/);
  });

  it.each([
    ["malformed JSON", "{not-json", /not valid JSON/i],
    ["missing version", JSON.stringify({ name: "ca-pi" }), /no version/i],
  ])("rejects a %s historical manifest (O-04)", (_case, value, message) => {
    const git = historicalGit({
      "plugins/ca/.claude-plugin/plugin.json": { version: "2.17.11" },
      "plugins/ca-codex/.codex-plugin/plugin.json": { version: "0.9.11" },
      "plugins/ca-pi/package.json": { version: "0.10.13" },
      "package.json": { version: "0.10.13" },
    });
    git.readAtCommit = (_commit, path) =>
      path === "package.json" ? value : JSON.stringify({
        version: path.includes("ca-codex") ? "0.9.11" : path.includes("ca-pi") ? "0.10.13" : "2.17.11",
      });

    expect(() => deriveVerifiedGovernanceReleases(
      targets(), ledger("v2.17.11", "ca-codex-v0.9.11", "ca-pi-v0.10.13"), git,
    )).toThrow(message);
  });
});

describe("release declaration provenance contract", () => {
  it.each([
    ["missing", targets().replace(/provenance-manifest: \.github\/published-tags\.json\n/, "")],
    ["duplicate", targets().replace(
      "provenance-manifest: .github/published-tags.json",
      "provenance-manifest: .github/published-tags.json\nprovenance-manifest: .github/published-tags.json",
    )],
    ["divergent", targets().replace(
      /\[ca-codex\]([\s\S]*?)provenance-manifest: \.github\/published-tags\.json/,
      "[ca-codex]$1provenance-manifest: .github/other-tags.json",
    )],
  ])("rejects %s governed provenance-manifest declaration (O-03)", (_case, declarations) => {
    expect(() => selectCurrentGovernanceReleases(
      declarations, ledger("v1.0.0", "ca-codex-v1.0.0", "ca-pi-v1.0.0"),
    )).toThrow(/provenance/i);
  });
});

describe("original-publication ledger validation", () => {
  function mutateLedger(mutator: (document: Record<string, unknown>) => void): string {
    const document = JSON.parse(ledger("v1.0.0", "ca-codex-v1.0.0", "ca-pi-v1.0.0"));
    mutator(document);
    return JSON.stringify(document);
  }

  it.each([
    ["unexpected top-level key", mutateLedger((document) => { document.extra = true; })],
    ["wrong namespaces", mutateLedger((document) => { document.namespaces = ["v*"]; })],
    ["invalid date", mutateLedger((document) => { document.verified_at = "today"; })],
    ["malformed unselected governed tag", mutateLedger((document) => {
      (document.tags as Record<string, unknown>)["ca-sandbox-vwat"] = {
        object_sha: sha, object_type: "commit", commit_sha: sha,
      };
    })],
    ["extra receipt key", mutateLedger((document) => {
      ((document.tags as Record<string, Record<string, unknown>>)["v1.0.0"]).extra = true;
    })],
    ["zero identity", mutateLedger((document) => {
      ((document.tags as Record<string, Record<string, unknown>>)["v1.0.0"]).commit_sha = "0".repeat(40);
    })],
    ["uppercase identity", mutateLedger((document) => {
      ((document.tags as Record<string, Record<string, unknown>>)["v1.0.0"]).object_sha = sha.toUpperCase();
    })],
    ["invalid object type", mutateLedger((document) => {
      ((document.tags as Record<string, Record<string, unknown>>)["v1.0.0"]).object_type = "tree";
    })],
    ["commit identity mismatch", mutateLedger((document) => {
      ((document.tags as Record<string, Record<string, unknown>>)["v1.0.0"]).object_sha = "1".repeat(40);
    })],
  ])("rejects %s (O-02)", (_case, publishedTags) => {
    expect(() => selectCurrentGovernanceReleases(targets(), publishedTags)).toThrow(/ledger|receipt|tag/i);
  });

  it("rejects duplicate JSON keys instead of accepting the last value (O-02)", () => {
    const publishedTags = ledger("v1.0.0", "ca-codex-v1.0.0", "ca-pi-v1.0.0")
      .replace('"verified_at":"2026-09-14"', '"verified_at":"2026-09-14","verified_at":"2026-09-15"');
    expect(() => selectCurrentGovernanceReleases(targets(), publishedTags)).toThrow(/duplicate/i);
  });

  it("rejects a numeric prerelease identifier with leading zeroes even when a stable tag exists (O-02)", () => {
    expect(() => selectCurrentGovernanceReleases(
      targets(), ledger("v1.0.0", "v2.0.0-01", "ca-codex-v1.0.0", "ca-pi-v1.0.0"),
    )).toThrow(/v2\.0\.0-01/);
  });
});

describe("repository Git adapter", () => {
  it("uses --no-lazy-fetch for every historical object read (O-05)", () => {
    const calls: Array<readonly string[]> = [];
    const git = repositoryGit("C:/repo", (_root, args) => {
      calls.push(args);
      return "{}";
    });
    git.readAtCommit(sha, "package.json");
    expect(calls).toEqual([["--no-lazy-fetch", "show", `${sha}:package.json`]]);
  });
});

describe("documentation build identity", () => {
  it("binds a GitHub Actions build to an exact 40-hex GITHUB_SHA equal to HEAD (O-06)", () => {
    const git = historicalGit({}, { head: sha, dirty: true });

    expect(
      resolveDocumentationBuildIdentity(git, {
        GITHUB_ACTIONS: "true",
        GITHUB_SHA: sha.toUpperCase(),
      }),
    ).toEqual({ mode: "github-actions", commit: sha, dirty: false });
  });

  it.each([
    ["missing", undefined, sha],
    ["not 40-hex", "main", sha],
    ["different from HEAD", "fedcba9876543210fedcba9876543210fedcba98", sha],
  ])("rejects a %s GitHub Actions build identity (O-06)", (_case, githubSha, head) => {
    const git = historicalGit({}, { head });
    expect(() =>
      resolveDocumentationBuildIdentity(git, {
        GITHUB_ACTIONS: "true",
        ...(githubSha === undefined ? {} : { GITHUB_SHA: githubSha }),
      }),
    ).toThrow(/GITHUB_SHA/i);
  });

  it("records the exact local HEAD and dirty state without using a branch name (O-06)", () => {
    const git = historicalGit({}, { head: sha.toUpperCase(), dirty: true });
    expect(resolveDocumentationBuildIdentity(git, {})).toEqual({
      mode: "local",
      commit: sha,
      dirty: true,
    });
  });
});

describe("deterministic release applicability record", () => {
  const currentHook = "current and published hook bytes\n";
  const replayDigest = createHash("sha256").update(currentHook).digest("hex");
  const proof: DirectHookReplayEvidence = {
    evidenceKind: "direct-hook-invocation-rendered-replay",
    hostDiscoveryProven: false,
    source: "plugins/ca/hooks/pre-bash.py",
    sourceSha256: replayDigest,
  };
  const releases: VerifiedGovernanceRelease[] = [
    {
      target: "ca",
      version: "2.17.11",
      tag: "v2.17.11",
      publicationCommit: sha,
      manifestPath: "plugins/ca/.claude-plugin/plugin.json",
      manifestPaths: ["plugins/ca/.claude-plugin/plugin.json"],
    },
    {
      target: "ca-codex",
      version: "0.9.11",
      tag: "ca-codex-v0.9.11",
      publicationCommit: "1111111111111111111111111111111111111111",
      manifestPath: "plugins/ca-codex/.codex-plugin/plugin.json",
      manifestPaths: ["plugins/ca-codex/.codex-plugin/plugin.json"],
    },
    {
      target: "ca-pi",
      version: "0.10.13",
      tag: "ca-pi-v0.10.13",
      publicationCommit: "2222222222222222222222222222222222222222",
      manifestPath: "plugins/ca-pi/package.json",
      manifestPaths: ["plugins/ca-pi/package.json", "package.json"],
    },
  ];

  function proofGit(publishedHook: string): ReleaseApplicabilityGit {
    return {
      readAtCommit(commit, path) {
        expect([commit, path]).toEqual([sha, proof.source]);
        return publishedHook;
      },
      head: () => sha,
      isDirty: () => false,
    };
  }

  it("requires the replay digest to match both current and latest-published ca source bytes (O-07)", () => {
    const record = createReleaseApplicabilityRecord({
      build: { mode: "github-actions", commit: sha, dirty: false },
      releases,
      proof,
      currentHookSource: currentHook,
      git: proofGit(currentHook),
    });

    expect(record.proof).toMatchObject({
      applicable: true,
      claim: "direct-hook-replay-source-applicability",
      replayDigest,
      currentSource: { path: proof.source, digest: replayDigest, matchesReplay: true },
      publishedSource: {
        path: proof.source,
        publicationCommit: sha,
        digest: replayDigest,
        matchesReplay: true,
      },
    });
    expect(record.proof.statement).toMatch(/applies.*latest published ca artifact/i);
  });

  it.each([
    ["current", "changed current hook\n", currentHook, false, true],
    ["published", currentHook, "changed published hook\n", true, false],
  ])(
    "records an explicit %s-source mismatch without throwing or calling it compatibility (O-08)",
    (_source, currentSource, publishedSource, currentMatches, publishedMatches) => {
      const record = createReleaseApplicabilityRecord({
        build: { mode: "local", commit: sha, dirty: true },
        releases,
        proof,
        currentHookSource: currentSource,
        git: proofGit(publishedSource),
      });

      expect(record.proof.applicable).toBe(false);
      expect(record.proof.currentSource.matchesReplay).toBe(currentMatches);
      expect(record.proof.publishedSource.matchesReplay).toBe(publishedMatches);
      expect(record.proof.statement).toMatch(/mismatch/i);
      expect(record.proof.statement).not.toMatch(/compatib/i);
      expect(JSON.stringify(record.proof)).not.toMatch(/compatib/i);
    },
  );

  it.each([
    ["empty evidence kind", { ...proof, evidenceKind: "" }],
    ["relabeled evidence kind", { ...proof, evidenceKind: "direct-hook-registration-proof" }],
    ["non-boolean discovery result", { ...proof, hostDiscoveryProven: "false" }],
    ["promoted host discovery result", { ...proof, hostDiscoveryProven: true }],
    ["non-canonical source", { ...proof, source: "../pre-bash.py" }],
    ["invalid replay digest", { ...proof, sourceSha256: "not-a-digest" }],
  ])("rejects malformed direct-hook proof evidence: %s (O-07)", (_case, invalidProof) => {
    expect(() => createReleaseApplicabilityRecord({
      build: { mode: "local", commit: sha, dirty: false },
      releases,
      proof: invalidProof as DirectHookReplayEvidence,
      currentHookSource: currentHook,
      git: proofGit(currentHook),
    })).toThrow(/direct-hook|replay|source/i);
  });

  it("rejects missing latest-published hook bytes (O-07)", () => {
    const git: ReleaseApplicabilityGit = {
      readAtCommit() { throw new Error("missing object"); },
      head: () => sha,
      isDirty: () => false,
    };
    expect(() => createReleaseApplicabilityRecord({
      build: { mode: "local", commit: sha, dirty: false },
      releases,
      proof,
      currentHookSource: currentHook,
      git,
    })).toThrow(/published hook source/i);
  });

  it("rejects an unsupported verified release row (O-09)", () => {
    expect(() => createReleaseApplicabilityRecord({
      build: { mode: "local", commit: sha, dirty: false },
      releases: [...releases, {
        ...releases[0],
        target: "ca-sandbox",
      } as unknown as VerifiedGovernanceRelease],
      proof,
      currentHookSource: currentHook,
      git: proofGit(currentHook),
    })).toThrow(/unsupported/i);
  });

  it.each([
    ["missing", releases.filter((release) => release.target !== "ca-pi"), /missing.*ca-pi/i],
    ["duplicate", [...releases, { ...releases[0] }], /duplicate.*ca/i],
  ])("rejects %s verified release rows (O-09)", (_case, invalidReleases, message) => {
    expect(() => createReleaseApplicabilityRecord({
      build: { mode: "local", commit: sha, dirty: false },
      releases: invalidReleases,
      proof,
      currentHookSource: currentHook,
      git: proofGit(currentHook),
    })).toThrow(message);
  });

  it("emits one deterministic record with exact identities, ordered sources, and explicit non-certification (O-09)", () => {
    const input = {
      build: { mode: "local" as const, commit: sha, dirty: true },
      releases,
      proof,
      currentHookSource: currentHook,
      git: proofGit(currentHook),
    };
    const record = createReleaseApplicabilityRecord(input);
    const reordered = createReleaseApplicabilityRecord({
      ...input,
      releases: [...releases].reverse(),
    });

    expect(record).toMatchObject({
      schemaVersion: 1,
      evidenceBoundary: {
        claim: "release-and-build-identity",
        doesNotCertify: [
          "runtime compatibility",
          "installation success",
          "universal host certification",
          "host discovery or registration",
        ],
      },
      build: { mode: "local", commit: sha, dirty: true },
    });
    expect(record.hosts.map(({ target, version, tag, publicationCommit }) => ({
      target,
      version,
      tag,
      publicationCommit,
    }))).toEqual(releases.map(({ target, version, tag, publicationCommit }) => ({
      target,
      version,
      tag,
      publicationCommit,
    })));
    expect(record.evidenceSources).toEqual([
      { kind: "release-declarations", path: ".codearbiter/release-targets.md" },
      { kind: "original-publication-receipts", path: ".github/published-tags.json" },
      {
        kind: "historical-manifest",
        path: "plugins/ca/.claude-plugin/plugin.json",
        commit: sha,
      },
      {
        kind: "historical-manifest",
        path: "plugins/ca-codex/.codex-plugin/plugin.json",
        commit: "1111111111111111111111111111111111111111",
      },
      {
        kind: "historical-manifest",
        path: "plugins/ca-pi/package.json",
        commit: "2222222222222222222222222222222222222222",
      },
      {
        kind: "historical-manifest",
        path: "package.json",
        commit: "2222222222222222222222222222222222222222",
      },
      { kind: "documentation-build", commit: sha },
      { kind: "direct-hook-replay", path: "site/src/assets/proof/hook-proof.json" },
      { kind: "current-hook-source", path: proof.source },
      { kind: "published-hook-source", path: proof.source, commit: sha },
    ]);
    expect(serializeReleaseApplicabilityRecord(record)).toBe(
      serializeReleaseApplicabilityRecord(reordered),
    );
    expect(serializeReleaseApplicabilityRecord(record)).toBe(
      `${JSON.stringify(record, null, 2)}\n`,
    );
  });
});
