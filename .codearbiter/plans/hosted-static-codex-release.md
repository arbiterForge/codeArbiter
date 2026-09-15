# Hosted Static ca-codex Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task in the recorded isolated worktree. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the mandatory self-hosted Windows desktop proof with a trusted GitHub-hosted static package contract, publish the pending parity `ca-codex` release, and load it through the supported local marketplace path.

**Architecture:** Keep the existing bounded candidate ZIP reader and resource-graph validator in `.github/scripts/check_codex_skill_resources.py`, strengthen its candidate-only mode with manifest/front-matter/hook checks, and make both manual and automatic release lanes rebuild and validate the exact final-tree archive locally. Remove the self-hosted desktop workflow and executable broker stack. Treat release inputs as inert data while executing verifier code only from the trusted release tree.

**Tech Stack:** GitHub Actions YAML, Python 3 standard library, PowerShell asset retirement, Git/GitHub CLI, Codex marketplace tooling.

**Spec:** `.codearbiter/specs/hosted-static-codex-release.md`

## Global Constraints

- Preserve ADR-0031's canonical `core/` kernel, deterministic generators, separate Claude/Codex packages, compatibility alias, and Forge-only Pi decisions.
- Supersede only ADR-0031 Decision 5's mandatory actual-Windows desktop release evidence through a forward-only ADR.
- No self-hosted runner, personal-PC CI, desktop/MSIX installation, device authorization, API credential, billable API access, UAC, Hyper-V, or network mutation.
- Candidate bytes are inert; trusted release-tree code performs all verification and publication.
- Missing, malformed, ambiguous, escaping, stale, or mismatched static package evidence fails closed.
- Preserve the user-owned dirty main checkout; all changes remain in `C:\Users\brenn\projects\codeArbiter-worktrees\hosted-static-codex-release` on `codex/hosted-static-codex-release`.
- Merge only after required CI is green, CodeRabbit concerns are resolved or dispositioned, and the exact reviewed head is reverified.
- Do not invent `ca-codex` 0.7.6 unless shipped plugin payload bytes change and the declared release gate requires a successor version.

## Acceptance coverage

| Spec criterion | Implemented and verified by |
|---|---|
| AC-1 | Tasks 1, 3, and 4 remove and prohibit every self-hosted/desktop dependency. |
| AC-2 | Task 4 deletes the desktop workflow, executable boundary, and active references. |
| AC-3 | Tasks 1 and 3 replace receipt/artifact requirements with failing-first hosted workflow contracts. |
| AC-4 | Task 2 adds the static manifest, front-matter, hook, path, graph, and digest regressions. |
| AC-5 | Tasks 1 and 3 pin impact routing plus both aggregate registrations. |
| AC-6 | Tasks 2 and 3 bind release execution to trusted-tree code and inert candidate bytes. |
| AC-7 | Tasks 2 through 5 run focused and whole-branch verification. |
| AC-8 | Task 6 verifies CI, CodeRabbit, review head, and merge identity. |
| AC-9 | Task 6 verifies the governed tag, Release, provenance, manifest, changelog, and archive identity. |
| AC-10 | Task 6 performs the supported local marketplace update and fresh-task `$ca-doctor` proof. |

---

### Task 1: Forward-only decision and failing release-contract tests

**Files:**
- Create through `$ca-adr`: `.codearbiter/decisions/0032-hosted-static-codex-release-evidence.md`
- Modify: `.codearbiter/decisions/decision-log.md`
- Modify: `.codearbiter/security-controls.md`
- Modify: `.codearbiter/tech-stack.md`
- Modify: `.github/scripts/test_release_workflow.py`
- Modify: `.github/scripts/test_ci_impact.py`

**Interfaces:**
- Consumes: approved spec AC-1 through AC-8 and ADR-0031 Decision 5.
- Produces: a forward-only proposed ADR superseding only the desktop-evidence clause; RED tests defining hosted-only release wiring and removal of active desktop infrastructure.

- [ ] **Step 1: Author the proposed forward-only ADR through `$ca-adr`**

Use the decision-lifecycle marker/template and attribute the decision to the user. Set `supersedes: 0031-cross-host-plugin-root-and-agent-charter-resolution`, state explicitly that only Decision 5 is superseded, and govern:

```yaml
governs:
  - .github/workflows/release.yml
  - .github/workflows/ci.yml
  - .github/scripts/check_codex_skill_resources.py
  - .github/scripts/verify_codex_candidate_provenance.py
  - plugins/ca-codex/**
```

Append the required user-attributed decision-log entry. ADR-0032 was explicitly ratified and is now `accepted` under DECISION-0052.

- [ ] **Step 2: Update mutable security and test documentation**

Replace active descriptions of protected desktop secrets/tooling with the hosted static boundary: trusted release-tree verifier, bounded inert candidate parsing, deterministic archive reconstruction, no credentials, and no self-hosted infrastructure. Preserve the former desktop material only in immutable historical records.

- [ ] **Step 3: Write the failing release workflow contract**

Replace `CodexCandidateProvenanceTest` assertions with tests equivalent to:

```python
def test_manual_and_auto_codex_publishers_require_hosted_static_candidate_validation(self):
    for job_name in ("codex-provenance", "auto-codex-provenance"):
        block = job_block(job_name)
        self.assertIn("--candidate-contract-only", block)
        self.assertIn("git archive", block)
        self.assertNotIn("gh run download", block)
        self.assertNotIn("codex-desktop-candidate", block)
        self.assertNotIn("candidate-resolution.json", block)

def test_release_candidate_validation_executes_only_checked_out_trusted_code(self):
    block = job_block("auto-codex-provenance")
    self.assertIn("trusted/.github/scripts/check_codex_skill_resources.py", block)
    self.assertNotIn("candidate/.github/scripts", block)
```

- [ ] **Step 4: Write the failing CI impact/removal contract**

Replace desktop-workflow tests with assertions equivalent to:

```python
def test_codex_static_package_changes_reach_the_required_hosted_lane(self):
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    self.assertIn("codex-resource-contract", aggregate_needs(workflow))
    self.assertIn("needs['codex-resource-contract'].result", aggregate_required_results(workflow))
    self.assertNotIn("codex-desktop-candidate.yml", workflow)
    self.assertNotIn("codex-desktop-ephemeral", workflow)
```

Assert `.github/actionlint.yaml` contains no custom self-hosted label and active workflow inventory contains no `runs-on: [self-hosted`.

- [ ] **Step 5: Run the focused tests and verify RED**

Run:

```powershell
python .github/scripts/test_release_workflow.py
python .github/scripts/test_ci_impact.py
```

Expected: failures specifically identify receipt downloads, desktop workflow references, self-hosted labels, and missing hosted candidate-only validation. Any unrelated failure is investigated before proceeding.

---

### Task 2: Strengthen the static candidate package contract

**Files:**
- Modify: `.github/scripts/check_codex_skill_resources.py`
- Modify: `.github/scripts/test_codex_skill_resources.py`
- Modify: `.github/scripts/verify_codex_candidate_provenance.py`
- Modify: `.github/scripts/test_codex_candidate_provenance.py`

**Interfaces:**
- Consumes: `_candidate_package_files(path) -> dict[str, bytes]`, `candidate_resource_contract(path) -> dict`, canonical `plugins/ca-codex` package layout.
- Produces: `candidate_static_contract(path) -> dict[str, Any]`; release-mode provenance derived from final-tree candidate bytes without receipts or attestations.

- [ ] **Step 1: Add failing static package-shape tests**

Build temporary candidate directories/ZIPs from the real package fixture and mutate one property per test. Pin failures for:

```python
def test_candidate_contract_rejects_missing_plugin_manifest(): ...
def test_candidate_contract_rejects_manifest_name_or_version_shape(): ...
def test_candidate_contract_rejects_missing_skill_frontmatter(): ...
def test_candidate_contract_rejects_skill_name_path_mismatch(): ...
def test_candidate_contract_rejects_missing_agent_classification(): ...
def test_candidate_contract_rejects_missing_hook_target(): ...
def test_candidate_contract_rejects_non_plugin_root_hook_vocabulary(): ...
def test_candidate_contract_rejects_resource_path_escape(): ...
def test_candidate_contract_is_deterministic_for_identical_file_maps(): ...
```

Reuse existing bounded ZIP tests; do not create a second archive parser.

- [ ] **Step 2: Implement `candidate_static_contract` minimally**

The function reads once through `_candidate_package_files`, validates `.codex-plugin/plugin.json`, validates required YAML-front-matter keys using a deliberately constrained scalar parser, validates skill/routine/agent path-to-name invariants, validates `hooks/hooks.json` and every `${PLUGIN_ROOT}/...` target against the file map, calls the existing resource-graph logic, and returns a deterministic manifest:

```python
{
    "sha256": package_sha256,
    "package_sha256": package_sha256,
    "plugin_version": version,
    "selected_paths": resources["selected_paths"],
    "relative_reads": resources["relative_reads"],
    "resource_sha256": resources["sha256"],
}
```

`--candidate-contract-only` prints this public result and no secret-bearing/raw candidate content.

- [ ] **Step 3: Simplify release provenance to final-tree static identity**

Remove receipt, attestation, PR commit-R, and downloaded-candidate modes from `verify_codex_candidate_provenance.py`. Retain strict Git object validation and deterministic `git archive` construction. The supported interface becomes:

```text
verify_codex_candidate_provenance.py --repo <trusted-tree> --final-ref <40-hex> --json
```

It resolves the final tree, archives only `plugins/ca-codex/`, validates it with trusted checker code, and emits commit/tree/archive/package/resource digests. Option-shaped refs and missing/malformed payloads fail before archive execution.

- [ ] **Step 4: Run focused static/provenance tests and verify GREEN**

Run:

```powershell
python .github/scripts/test_codex_skill_resources.py
python .github/scripts/test_codex_candidate_provenance.py
python .github/scripts/check_codex_skill_resources.py --candidate-contract-only --candidate-package plugins/ca-codex --json
python .github/scripts/verify_codex_candidate_provenance.py --repo . --final-ref (git rev-parse HEAD) --json
```

Expected: all tests pass; both commands report the same declared version and compatible deterministic package/resource identities.

---

### Task 3: Rewire hosted CI and release jobs

**Files:**
- Modify: `.github/workflows/release.yml`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/actionlint.yaml`
- Modify: `.github/scripts/test_release_workflow.py`
- Modify: `.github/scripts/test_ci_impact.py`

**Interfaces:**
- Consumes: Task 2's trusted `--candidate-contract-only` and `--final-ref` CLI contracts.
- Produces: hosted-only `codex-resource-contract`, `codex-provenance`, and `auto-codex-provenance` jobs registered in merge/release gates.

- [ ] **Step 1: Replace manual release receipt download**

In `codex-provenance`, remove `actions: read`, receipt parsing, `gh run download`, and downloaded archive input. Check out `${{ github.sha }}` without credentials and run the trusted final-tree verifier. Keep `release-codex.needs: [preflight, codex-provenance]`.

- [ ] **Step 2: Replace automatic release receipt download**

Keep the trusted/candidate checkout separation for `workflow_run`, but execute only `trusted/.github/scripts/verify_codex_candidate_provenance.py --repo candidate --final-ref $CANDIDATE_SHA --json`. Remove actions-read permission and all receipt/artifact download logic. Keep ancestry verification tying the successful CI commit to the current trusted main release tree.

- [ ] **Step 3: Reduce the required resource job to static checks**

Remove desktop paths, desktop workflow paths, and desktop boundary tests from `codex-resources` filters and the `codex-resource-contract` job. Run:

```yaml
- run: python .github/scripts/test_codex_skill_resources.py
- run: python .github/scripts/test_codex_candidate_provenance.py
- run: python .github/scripts/check_codex_skill_resources.py --fixtures-only
- run: python .github/scripts/check_codex_skill_resources.py --candidate-contract-only --candidate-package plugins/ca-codex --json
- run: python .github/scripts/verify_codex_candidate_provenance.py --repo . --final-ref "$GITHUB_SHA" --json
```

Preserve dual registration in `ci-passed.needs` and `required_results`.

- [ ] **Step 4: Remove the actionlint self-hosted exception**

Delete `codex-desktop-ephemeral` configuration; leave unrelated actionlint policy intact.

- [ ] **Step 5: Run workflow contracts and actionlint-equivalent checks**

Run:

```powershell
python .github/scripts/test_release_workflow.py
python .github/scripts/test_ci_impact.py
python .github/scripts/verify_codex_candidate_provenance.py --repo . --final-ref (git rev-parse HEAD) --json
```

Expected: all pass, no active workflow uses self-hosted runners, and both release paths are bound to trusted static validation.

---

### Task 4: Retire desktop-proof executable infrastructure

**Files:**
- Delete: `.github/workflows/codex-desktop-candidate.yml`
- Delete: `.github/desktop-proof-boundary.json`
- Delete: `.github/scripts/Invoke-CodeArbiterDesktopCandidate.ps1`
- Delete: `.github/scripts/Invoke-CodeArbiterDesktopUiDriver.ps1`
- Delete: `.github/scripts/Invoke-CodeArbiterDesktopRouteProbe.ps1`
- Delete: `.github/scripts/test_codex_desktop_boundary.py`
- Modify: `.github/scripts/check_codex_skill_resources.py`
- Modify: `.github/scripts/test_codex_skill_resources.py`
- Modify: `.github/scripts/test_ci_impact.py`

**Interfaces:**
- Consumes: Task 3's hosted-only workflows.
- Produces: no executable desktop path or CLI surface; static archive bounds become checker-owned constants rather than values loaded from a deleted desktop manifest.

- [ ] **Step 1: Pin archive limits in the static verifier**

Move the already reviewed conservative candidate ZIP limits into a static package-contract constant owned by `check_codex_skill_resources.py`. Preserve the exact limits and all oversized/high-ratio/non-regular/path-collision regressions.

- [ ] **Step 2: Remove desktop-only checker modes and tests**

Delete `--surface desktop`, `--import-receipt`, `--desktop-boundary-contract-only`, receipt/attestation validation, Store/MSIX identity, broker/VM/network/teardown helpers, and their dedicated tests. Preserve backend CLI/app-server characterization and candidate-only static validation.

- [ ] **Step 3: Delete executable desktop assets**

Delete the workflow, manifest, three PowerShell programs, and desktop boundary test suite listed above. Do not delete immutable historical ADRs, plans, reports, or audit entries.

- [ ] **Step 4: Prove active-reference closure**

Run:

```powershell
rg -n "codex-desktop-candidate|Invoke-CodeArbiterDesktop|desktop-proof-boundary|codex-desktop-ephemeral|runs-on:\s*\[self-hosted" .github .codearbiter/tech-stack.md .codearbiter/security-controls.md
```

Expected: no active workflow, script, mutable security control, or tech-stack reference. Historical spec/plan/ADR references may remain and are explicitly excluded from this command's active-surface interpretation.

- [ ] **Step 5: Run the focused suite**

Run:

```powershell
python .github/scripts/test_codex_skill_resources.py
python .github/scripts/test_codex_candidate_provenance.py
python .github/scripts/test_release_workflow.py
python .github/scripts/test_ci_impact.py
python tools/build-surface.py --check
python .github/scripts/check-plugin-refs.py ca-codex
```

Expected: all pass with no desktop test invocation or missing active file.

---

### Task 5: Governance, package, and whole-branch verification

**Files:**
- Modify only if required by verified payload scope: `plugins/ca-codex/CHANGELOG.md`, `plugins/ca-codex/.codex-plugin/plugin.json`
- Modify: `.codearbiter/plans/hosted-static-codex-release.md` status cells
- Generated files only through canonical generators if required

**Interfaces:**
- Consumes: Tasks 1-4 complete diff.
- Produces: release-ready reviewed branch whose payload/version relationship is mechanically valid.

- [ ] **Step 1: Determine payload/version effect mechanically**

Run the repository payload-scope/version gates against `origin/main`. If no shipped `plugins/ca-codex/**` bytes changed, retain pending 0.7.5. If shipped bytes changed, follow the declared affected-package version and changelog gate; do not choose a version manually.

- [ ] **Step 2: Run required generators and drift checks**

Run:

```powershell
python tools/build-surface.py --check
python tools/sync-core.py --check
python tools/build-host-packages.py --check
python .github/scripts/check-plugin-refs.py ca-codex
```

- [ ] **Step 3: Run focused regression suites fresh**

Run the six Task 4 focused commands from a clean process, then syntax-compile every changed Python file.

- [ ] **Step 4: Run the repository-required whole-branch gates**

Use `.codearbiter/tech-stack.md` and CI impact planning to execute every applicable local gate. Record exact commands, counts, skips, and artifacts; do not call skipped unavailable hosted checks passing.

- [ ] **Step 5: Review the complete diff**

Run `$ca-review` over the full branch diff, resolve every BLOCK finding, and rerun affected tests. Confirm no personal path, runner label, credential, VM, switch, or network detail is introduced.

---

### Task 6: Governed delivery, release, and local plugin proof

**Files:**
- Commit only the reviewed Task 1-5 diff through `$ca-commit`
- PR through `$ca-pr`
- Release through `$ca-release ca-codex` and the declared GitHub workflow
- Local marketplace cache updated only through the supported plugin update flow

**Interfaces:**
- Consumes: exact reviewed branch head, green required CI, resolved/dispositioned CodeRabbit review, continuing merge authority.
- Produces: merged hosted-only release gate, published parity `ca-codex`, supported local install, fresh-task `$ca-doctor` proof.

- [ ] **Step 1: Commit and open the PR through governed lanes**

Use `$ca-commit`, push the `codex/hosted-static-codex-release` branch, and open the PR through `$ca-pr`. The PR body names the desktop-proof clause supersession, static validation retained/strengthened, deleted infrastructure, zero-spend boundary, and exact verification evidence.

- [ ] **Step 2: Watch CI and CodeRabbit**

Use `$ca-watch` plus direct review-thread inspection. On red, diagnose and fix through the appropriate governed lane. For each CodeRabbit concern, either change code and verify it or record a technical disposition supported by tests/source; resolve/retire the thread.

- [ ] **Step 3: Merge under continuing authority**

Immediately before merge, verify required CI green, zero unresolved CodeRabbit threads, CodeRabbit approval or documented dispositions, mergeability, and exact reviewed head SHA. Merge through the repository-required method and verify the landed tree/commit.

- [ ] **Step 4: Verify the release baseline and publish**

Run `$ca-release --dry-run ca-codex` against the clean post-merge state, resolve any honest blocker, and then use the governed release path. Verify `ca-codex-v<version>`, GitHub Release, manifest, changelog, published-tags provenance, and deterministic archive identity independently.

- [ ] **Step 5: Update the supported local marketplace plugin**

Use the plugin-creator update reference and CLI cachebuster/reinstall flow for the CodeArbiter marketplace source. Do not hand-edit marketplace state or copy plugin files into a cache. Verify the selected installed version and package root.

- [ ] **Step 6: Prove fresh-task loading**

Start a fresh Codex task after the update, run `$ca-doctor`, and record exact package ownership, version, resource completeness, hook enforcement, and harmless live-fire results. No Windows desktop/MSIX installation is performed.

- [ ] **Step 7: Complete the campaign only after the charter-wide audit**

Update `campaign.html` transactionally after each material state change. Mark complete only when release, local install, fresh-task doctor, Claude/Codex parity, Forge-only Pi compatibility, and every charter completion criterion have direct current evidence.
