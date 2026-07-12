# Codex Documentation Launch Implementation Plan

> **For agentic workers:** Execute this plan task-by-task with a fresh review at each task boundary.
> Do not hand-edit generated reference pages. Do not publish, push, or release.

**Goal:** Announce verified shared enforcement and project-context parity across Claude Code and
Codex throughout the README and documentation site, with host-correct instructions and traceable
evidence.

**Architecture:** One canonical site page owns the parity claim, evidence, verified versions,
publication status, and intentional differences. The README and primary site journey summarize and
link to that page. Operational pages carry explicit host-specific commands only where the hosts
differ, while generated references continue to come from their existing generator.

**Tech stack:** Markdown/MDX, Astro Starlight, TypeScript, Vitest, repository Python verification.

## Global constraints

- Public headline: **“Shared enforcement and project-context parity across Claude Code and Codex.”**
- Verified live baseline: Codex CLI 0.144.1, ca-codex 0.2.4, Windows, 2026-07-11.
- Live evidence: trusted SessionStart injection; `$ca-doctor` 9 OK / 0 WARN / 0 FAIL; `[H-03]`
  PreToolUse block with feedback surfaced.
- The public GitHub-slug install/remove sequence remains labeled post-release until it passes against
  a public default branch containing `ca-codex`.
- Development instructions may show the verified local-clone marketplace flow.
- Intentional differences must remain explicit: no Codex statusline, transcript-pruning engine, or
  Read hook; `$ca-*` instead of `/ca:*`; Codex hook review through `/hooks`.
- `.codearbiter/` is the single shared project-state and enforcement store for both hosts and users.
- Publishing, pushing, merging, and releasing require separate authorization.
- Tasks 1–5 are strictly sequential. Do not dispatch them in parallel: Tasks 1, 3, and 4
  intentionally revisit the same test file, and Tasks 1 and 3 both update site configuration.

---

### Task 1: Pin the public evidence contract and add the canonical support page

**Files:**

- Create: `site/src/content/docs/getting-started/claude-code-and-codex.md`
- Create: `site/test/content/codex-support.test.ts`
- Modify: `site/astro.config.mjs`

**Interfaces:**

- Consumes: `docs/parity.md`, `docs/codex-parity-testing.md`, ADR-0011, ADR-0012.
- Produces: canonical site URL `/getting-started/claude-code-and-codex/` and a source-level evidence
  contract used by later tasks.

- [ ] **Step 1: Write the failing support-page contract**

Create `site/test/content/codex-support.test.ts` with assertions that read the support page and
configuration and require:

```ts
expect(page).toContain("Shared enforcement and project-context parity across Claude Code and Codex");
expect(page).toContain("Codex CLI 0.144.1");
expect(page).toContain("ca-codex 0.2.4");
expect(page).toMatch(/9 OK.*0 WARN.*0 FAIL/s);
expect(page).toContain("[H-03]");
expect(page).toContain("docs/parity.md");
expect(page).toContain("docs/codex-parity-testing.md");
expect(page).toContain("available after the Codex-support release");
expect(page).toMatch(/statusline/i);
expect(page).toMatch(/transcript pruning/i);
expect(page).toMatch(/Read hook/i);
expect(config).toContain("getting-started/claude-code-and-codex");
```

- [ ] **Step 2: Run the focused test and confirm the missing-page failure**

Run: `npm test -- --run test/content/codex-support.test.ts`

Working directory: `site/`

Expected: FAIL because the support page does not exist.

- [ ] **Step 3: Write the canonical support page**

Create the page with these sections:

1. “What parity means” with the exact headline and one-store/two-host explanation.
2. “Verified live on 2026-07-11” with the pinned versions, date, trust flow, that run's doctor
   result, and H-03 block. State that the counts describe the dated evidence event rather than the
   current number of doctor checks.
3. “Verified continuously” naming the adapter, guard, cold-install, validator, generator,
   byte-identity, and dual-host suites with repository-relative source links.
4. “Use one repository from either host” explaining shared `.codearbiter/` state and two-user use.
5. “Install status” showing the local-clone development flow as verified and the GitHub-slug flow as
   available after release, with the post-publication smoke-test gate.
6. “Intentional differences” table for statusline, transcript pruning, Read hook, command spelling,
   agents/reviewer execution, and trust UI.
7. Links to install, quickstart, compatibility, enforcement, troubleshooting, parity ledger, and
   reproduction procedure.

- [ ] **Step 4: Add the page to Getting Started navigation**

Insert immediately after Install:

```js
{ label: "Claude Code + Codex", slug: "getting-started/claude-code-and-codex" },
```

- [ ] **Step 5: Run the focused test**

Run: `npm test -- --run test/content/codex-support.test.ts`

Expected: PASS.

- [ ] **Step 6: Commit**

Stage only the three Task 1 files and commit:

```text
docs(site): add verified Claude and Codex support page
```

---

### Task 2: Make the repository README a two-host launch page

**Files:**

- Modify: `README.md`
- Create: `.github/scripts/test_public_codex_docs.py`

**Interfaces:**

- Consumes: canonical support page from Task 1 and generated catalogs
  `plugins/ca/COMMANDS.md`, `plugins/ca-codex/COMMANDS.md`.
- Produces: host-neutral repository landing copy and a cross-surface anti-drift test reused in Task 5.

- [ ] **Step 1: Write failing README assertions**

Create a stdlib `unittest` file that reads `README.md` and requires:

```python
self.assertIn("Shared enforcement and project-context parity across Claude Code and Codex", text)
self.assertIn("codex plugin marketplace add arbiterForge/codeArbiter", text)
self.assertIn("codex plugin add ca-codex@codearbiter", text)
self.assertIn("$ca-init", text)
self.assertIn("$ca-doctor", text)
self.assertIn("plugins/ca-codex/COMMANDS.md", text)
self.assertIn("getting-started/claude-code-and-codex", text)
self.assertRegex(text, r"available after the Codex-support release")
```

Also assert that the opening definition no longer says codeArbiter is only a Claude Code plugin.

- [ ] **Step 2: Run the test and confirm the old README fails**

Run: `python .github/scripts/test_public_codex_docs.py`

Expected: FAIL on the missing headline and Codex install path.

- [ ] **Step 3: Rewrite the README hero and definition**

Make both hosts visible above the fold:

- replace “An orchestration layer for Claude Code” with the exact public headline;
- add separate Claude Code and Codex badges;
- define `ca` and `ca-codex` as sibling plugins over one `.codearbiter/` store;
- link the evidence phrase to the canonical site support page.

- [ ] **Step 4: Replace Install with host-specific paths**

Use separate “Claude Code” and “Codex” subsections. Codex must include:

```text
codex plugin marketplace add arbiterForge/codeArbiter
codex plugin add ca-codex@codearbiter
```

Label those commands available after the Codex-support release, then show the verified local-clone
development alternative. Include `/hooks` trust review, fresh-thread requirement, and `$ca-doctor`.

- [ ] **Step 5: Make activation and architecture host-neutral**

Show `/ca:init` and `$ca-init`; explain alternating or simultaneous Claude/Codex use over the same
checked-in store; update the flow diagram labels from Claude-only tool names to host-neutral terms.
Label the statusline paragraph Claude-only.

- [ ] **Step 6: Update command discovery without duplicating the catalog**

Keep the current `/ca:*` catalog but identify it as Claude spelling. Add a Codex note and link to
`plugins/ca-codex/COMMANDS.md`, explaining the `$ca-*` transformation and two intentional omissions.

- [ ] **Step 7: Run the README assertions**

Run: `python .github/scripts/test_public_codex_docs.py`

Expected: PASS.

- [ ] **Step 8: Commit**

Stage `README.md` and the test, then commit:

```text
docs: announce shared Claude and Codex parity
```

---

### Task 3: Convert the primary site journey to two-host guidance

**Files:**

- Modify: `site/src/content/docs/index.mdx`
- Modify: `site/src/components/InstallTerminal.astro`
- Modify: `site/src/content/docs/overview.md`
- Modify: `site/src/content/docs/getting-started/install.md`
- Modify: `site/src/content/docs/getting-started/quickstart.md`
- Modify: `site/src/content/docs/getting-started/compatibility.md`
- Modify: `site/astro.config.mjs`
- Modify: `site/test/landing/landing-page.test.ts`
- Modify: `site/test/content/codex-support.test.ts`

**Interfaces:**

- Consumes: Task 1 support URL and Task 2 public copy contract.
- Produces: complete install-to-first-block journey for either host.

- [ ] **Step 1: Extend the landing and journey tests first**

Require the landing title/description/tagline to name both hosts, require the install component to
render both host labels and both install command sets, and require install/quickstart/compatibility
to contain `/ca:doctor`, `$ca-doctor`, `.codearbiter/`, and the support-page link.

- [ ] **Step 2: Run the focused site tests and confirm failure**

Run:

```text
npm test -- --run test/landing/landing-page.test.ts test/content/codex-support.test.ts
```

Expected: FAIL on Claude-only title, tagline, install terminal, and compatibility matrix.

- [ ] **Step 3: Update global metadata and landing hero**

Change the page title, description, H1, tagline, “what” block, gate explanation, and tool-boundary
steps to host-neutral copy. Add a concise verified-parity callout linking to the support page.

- [ ] **Step 4: Make the install terminal present two host paths**

Retain the Claude commands and statusline step under a Claude label. Add the Codex marketplace/add,
`/hooks`, `$ca-init`, and `$ca-doctor` sequence under a Codex label, with the pre-release availability
marker. Preserve the existing semantic region/list/listitem and reduced-motion contracts.

- [ ] **Step 5: Rewrite overview and install**

Define the two sibling plugins and shared store. Install must provide prerequisites once, then
separate host sections with exact commands, activation, trust, and verification. It must explicitly
state that neither plugin is required for the other host to read existing `.codearbiter/` state.

- [ ] **Step 6: Rewrite quickstart as parallel host tracks**

Keep one conceptual scenario, but show host-specific invocation spellings at every command step.
End both tracks with their doctor command and the expected H-03 block.

- [ ] **Step 7: Expand compatibility matrix**

Add pinned Codex minimum/live-verified versions, describe `commandWindows` and the verdict adapter,
separate the Claude interpreter fallback from Codex’s OS-specific handler, and label statusline,
transcript pruning, Read hook, and reviewer execution differences.

- [ ] **Step 8: Run focused tests and typecheck**

Run:

```text
npm test -- --run test/landing/landing-page.test.ts test/content/codex-support.test.ts
npm run typecheck
```

Expected: PASS.

- [ ] **Step 9: Commit**

Stage only Task 3 files and commit:

```text
docs(site): make the getting-started journey host-aware
```

---

### Task 4: Correct deeper operational and lifecycle documentation

**Files:**

- Modify: `site/src/content/docs/enforcement.md`
- Modify: `site/src/content/docs/hooks.md`
- Modify: `site/src/content/docs/guides/opt-in-a-repo.md`
- Modify: `site/src/content/docs/faq.md`
- Modify: `site/src/content/docs/guides/troubleshooting.md`
- Modify: `site/src/content/docs/guides/uninstalling.md`
- Modify: `site/src/content/docs/guides/the-statusline.md`
- Modify: `site/src/content/docs/getting-started/claude-code-and-codex.md`
- Modify: `site/test/content/codex-support.test.ts`

**Interfaces:**

- Consumes: host syntax and intentional-differences table from Task 1.
- Produces: consistent operational guidance for enforcement, diagnosis, opt-in, exit, and
  Claude-only features.

- [ ] **Step 1: Add failing operational-doc assertions**

Require:

- enforcement and hooks pages to name both hosts and explain Codex structured deny adaptation;
- opt-in to show `/ca:init` and `$ca-init`;
- FAQ to answer mixed-host/two-user use;
- troubleshooting to show `/ca:doctor` and `$ca-doctor`, `/hooks`, and no Codex statusline check;
- uninstalling to show both plugin removal commands and preservation of `.codearbiter/`;
- statusline guide to say Claude Code only near its title;
- the support page to contain a dated Codex documentation-launch note with its evidence links.

- [ ] **Step 2: Run the focused test and confirm failure**

Run: `npm test -- --run test/content/codex-support.test.ts`

Expected: FAIL on missing host-aware operational content.

- [ ] **Step 3: Update enforcement and hooks**

Explain the shared Python guard core, host adapters, Claude exit-2 boundary, Codex structured deny
boundary, shared activation flag, and identical audit/store outcome. Avoid claiming every tool emits
hooks on Codex; preserve the Read-hook limitation.

- [ ] **Step 4: Update opt-in, FAQ, and troubleshooting**

Add mixed-host workflows and exact commands. Troubleshooting must separate Claude statusline checks
from Codex hook trust and fresh-thread checks. Both hosts must end at the same doctor verdict.

- [ ] **Step 5: Update uninstalling and statusline**

Give separate removal instructions, clarify that uninstalling either host leaves project state for
the other, and label the entire statusline guide Claude-only without implying a Codex defect.

- [ ] **Step 6: Add the dated launch note to the handcrafted support page**

Record the 2026-07-11 verification and 2026-07-12 documentation launch on the support page, linking
to the repository evidence and stating the public marketplace release gate. Do not edit
`site/src/content/docs/changelog.md`; it is generated from the root `CHANGELOG.md`.

- [ ] **Step 7: Run focused tests**

Run: `npm test -- --run test/content/codex-support.test.ts`

Expected: PASS.

- [ ] **Step 8: Commit**

Stage only Task 4 files and commit:

```text
docs(site): document Codex operations and host differences
```

---

### Task 5: Generate, audit, and verify the complete launch

**Files:**

- Modify only if generated by command: `site/src/content/docs/reference/**`
- Modify only if generated by command: `site/src/generated/sidebar.json`
- Modify only if generated by command: `site/src/content/docs/changelog.md`
- Modify: `.github/workflows/ci.yml` if the new public-doc test is not already reached by CI.

**Interfaces:**

- Consumes: all prior tasks.
- Produces: buildable, link-clean site and repository-wide evidence packet.

- [ ] **Step 1: Confirm CI executes the public-doc contract**

Inspect `.github/workflows/ci.yml`. If no existing Python test discovery invokes
`.github/scripts/test_public_codex_docs.py`, add an explicit step:

```yaml
- name: Validate public Codex documentation
  run: python .github/scripts/test_public_codex_docs.py
```

- [ ] **Step 2: Regenerate site-owned outputs**

Run: `npm run gen`

Working directory: `site/`

Review every generated diff; do not accept unrelated churn.

- [ ] **Step 3: Run the full site suite**

From `site/`, run in order:

```text
npm test
npm run typecheck
npm run build
npm run link-audit
```

Expected: all commands exit 0; build emits the new support page; link audit reports no broken links.

- [ ] **Step 4: Run repository documentation and parity verification**

From the repository root, run:

```text
python .github/scripts/test_public_codex_docs.py
python .github/scripts/test_codex_adapter.py
python .github/scripts/test_hooks_cold_install.py
python .github/scripts/test_dual_host_store.py
python .github/scripts/test_hook_guards.py
python .github/scripts/test_validate_codex_plugin.py
python .github/scripts/validate_codex_plugin.py
python .github/scripts/check-plugin-refs.py
python tools/build-surface.py --check
python tools/sync-core.py --check
```

Expected: every command exits 0 with no drift.

- [ ] **Step 5: Audit public claims manually**

Search README and handcrafted site docs for Claude-only definitions. For each match, classify it as:

- intentionally Claude-only and labeled;
- a host-specific command paired with its Codex form; or
- stale copy to correct before proceeding.

Verify every version/evidence statement links to the support page or repository evidence.

- [ ] **Step 6: Render-check the launch pages**

Inspect the built landing, support, install, quickstart, compatibility, troubleshooting, and
uninstall pages. Confirm headings, tables, command blocks, callouts, navigation, and mobile wrapping
remain readable. Fix source files, then repeat Steps 2–3 if any visual issue appears.

- [ ] **Step 7: Commit final generated and CI changes**

Stage only reviewed generated outputs and any CI change, then commit:

```text
test(docs): enforce the Codex support evidence contract
```

- [ ] **Step 8: Record the publication blocker in the handoff**

State that the docs are complete but the site announcement must not be deployed until the Codex
payload is present on the public default branch and a clean Codex 0.144.1 home passes:

The `codex plugin list --json` spelling was confirmed locally on Codex 0.144.1 during development;
the complete public-slug sequence below remains unconfirmed until the payload is published.

```text
codex plugin marketplace add arbiterForge/codeArbiter
codex plugin add ca-codex@codearbiter
codex plugin list --json
codex plugin remove ca-codex@codearbiter
codex plugin list --json
```

Do not perform that publication, push, merge, or release within this plan.
