# Codex distribution protection contract

The release workflow first publishes the immutable `ca-codex-dist-v*` tag from
the qualified archive, finalizes and reads back the GitHub Release, and only
then advances `ca-codex-marketplace`. The marketplace commit carries an
append-only `.agents/plugins/codex-distribution-tags.json` ledger binding every
distribution tag to its Git commit, source commit, package cohort digest, and
archive digest. Promotion uses an expected-head lease and fails on drift.

The repository owner must install GitHub repository rulesets matching
`.github/codex-distribution-policy.json`: reject creation, deletion, and update of
`ca-codex-dist-v*`; reject deletion, update, and force-push of
`ca-codex-marketplace`;
and grant the sole bypass to a dedicated GitHub App whose App ID is supplied as
`CODEX_DISTRIBUTION_APP_ID` by the protected `codex-distribution` environment.
The general GitHub Actions integration (actor 15368) is explicitly refused.
Source control remains the reviewed desired-state contract, not
evidence that the remote rules are installed. Immediately before the first
distribution write, the release action fetches each live ruleset through the
GitHub API and fails closed unless its enforcement, ref conditions, rule types,
and sole publisher bypass exactly satisfy that contract.

Create a protected GitHub Actions environment named `codex-distribution` and
store two independent GitHub App identities as environment secrets:

- `CODEX_DISTRIBUTION_APP_ID`, `CODEX_DISTRIBUTION_APP_INSTALLATION_ID`, and
  `CODEX_DISTRIBUTION_APP_PRIVATE_KEY` belong to the publisher. Install it only
  on this repository with Actions read, Contents read/write, and Metadata read.
  Its numeric App ID must be the sole Integration bypass actor in both rulesets.
- `CODEX_RULESET_VERIFIER_APP_ID`,
  `CODEX_RULESET_VERIFIER_APP_INSTALLATION_ID`, and
  `CODEX_RULESET_VERIFIER_APP_PRIVATE_KEY` belong to a separate verifier. GitHub
  returns `bypass_actors` only to callers with ruleset write access, so this App
  requires repository Administration read/write and Metadata read. It must not
  be a bypass actor and needs no Contents write permission.

The verifier credential is used only for the two fail-closed ruleset reads; the
publisher credential is used only for artifact retrieval and distribution
writes. The workflow mints short-lived installation tokens inside the two Codex
publisher jobs, masks them, removes both temporary private-key files, and passes
no write-capable repository `GITHUB_TOKEN` to those jobs. This separation means
the sole bypass publisher cannot alter its own protection and the ruleset
administrator cannot publish through the protected refs. Each live check also
fails closed unless the configured publisher and verifier App IDs are distinct.
