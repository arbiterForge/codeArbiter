#!/usr/bin/env python3
"""Temporary PR843 preparation. Creates a tested Git object; NEVER updates a ref.

The final candidate removes this script and its triggering workflow. The only
GitHub writes this helper makes are new blobs, a preserving tree, and a commit.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile

REPO = 'arbiterForge/codeArbiter'
BRANCH = 'refs/heads/codex/autonomy-routing-integration'
SOURCE = 'cb8d6247807091c39dc92c96c2a8cb1bfbc587d1'
TEMP_PATHS = ('.github/workflows/pr843-prepare.yml', '.github/scripts/pr843_prepare.py')
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(os.environ['RUNNER_TEMP']) / 'pr843-prepared'
EXPECTED = {
    'core/surface/SPRINT.md': '62f169f1a3d69a4d2b161c354f9a508db9188a5d',
    'core/surface/skills/subagent-driven-development/SKILL.md': '77fdeccd9450280c1ba704581d50376c3ddb1ab5',
    'core/surface/includes/redirect.md': '77868c3eee9d6bbb38b2ad169b6b14564aed9986',
    'core/surface/arbiter.md': '0a508191bfbc31c67ca84fd52fe9b2c5e9326c92',
    '.github/scripts/test_artifact_surface.py': 'c97d259d25d7bd0c2bb80f9fcac5f0384802073f',
    '.github/scripts/test_persona_composition.py': 'acbab815a8aafbee76052e53f9b0f1a578062a17',
}


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in {'GH_TOKEN', 'GITHUB_TOKEN', 'NODE_AUTH_TOKEN'}}
    p = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    if check and p.returncode:
        raise RuntimeError(f'{args[0]} failed ({p.returncode}): {p.stderr[-2000:]}')
    return p


def git(*args: str) -> str:
    return run('git', *args).stdout.strip()


def oid(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def write(path: str, content: str) -> None:
    if '\r' in content:
        raise ValueError(f'CR bytes not allowed in {path}')
    (ROOT / path).write_text(content, encoding='utf-8', newline='\n')


def replace(path: str, old: str, new: str) -> None:
    s = read(path)
    if s.count(old) != 1:
        raise ValueError(f'{path}: expected exactly one edit anchor, found {s.count(old)}')
    write(path, s.replace(old, new))


RECOVERY_TESTS = '''\n\nclass TestSprintRecoveryAndLimits(unittest.TestCase):
    """PR843: repair permission is not acceptance, scope, or publication authority."""

    def sprint_surfaces(self):
        yield "core/surface/SPRINT.md", read("core/surface/SPRINT.md")
        for plugin, _, _, _ in HOSTS:
            rel = f"{plugin}/SPRINT.md"
            yield rel, read(rel)

    def engine_surfaces(self):
        yield "core/surface/skills/subagent-driven-development/SKILL.md", read("core/surface/skills/subagent-driven-development/SKILL.md")
        for plugin, skilldir, _, _ in HOSTS:
            rel = f"{plugin}/{skilldir}/subagent-driven-development/SKILL.md"
            yield rel, read(rel)

    def test_failed_quality_blocks_acceptance_not_authorized_repair(self):
        for rel, text in self.sprint_surfaces():
            with self.subTest(rel=rel):
                self.assertIn("blocks acceptance, not authorized repair", text)
                self.assertIn("only after initial spec-and-plan approval", text)
                self.assertIn("every invalidated review", text)

    def test_recovery_reuses_current_typed_authority(self):
        for rel, text in self.sprint_surfaces():
            with self.subTest(rel=rel):
                for token in ("task-reconcile", "scope-reconcile", "context ticket", "real policy events"):
                    self.assertIn(token, text)
                self.assertIn("Never manufacture an approval or a receipt", text)
                self.assertIn("HTML farm remains disabled", text)

    def test_identical_failure_changes_strategy_not_user_interview(self):
        for rel, text in self.sprint_surfaces():
            with self.subTest(rel=rel):
                self.assertIn("stop that retry strategy", text)
                self.assertIn("independently eligible work", text)
                self.assertIn("not automatically another user checkpoint", text)
                self.assertIn("do not report the incomplete plan as accepted", text)

    def test_real_hard_stops_and_commit_permission_survive(self):
        for rel, text in self.sprint_surfaces():
            with self.subTest(rel=rel):
                self.assertIn("security CRITICAL", text)
                self.assertIn("does not grant commit, provider, spending, disclosure, or publication authority", text)
                self.assertIn("MUST NOT merge to the default branch or discard autonomously", text)
                self.assertIn("STOP for explicit user approval of the sprint spec AND the", text)

    def test_child_calls_parent_recovery_without_auto_passing_gate(self):
        for rel, text in self.engine_surfaces():
            with self.subTest(rel=rel):
                self.assertIn("Recovery within the approved sprint", text)
                self.assertIn("Never redispatch merely to evade a failing gate", text)
                self.assertNotIn("A `tdd` BLOCK halts the loop; do not", text)
                self.assertNotIn("even under `/sprint`. These never auto-proceed", text)

    def test_legacy_dependency_sentence_does_not_override_typed_eligibility(self):
        for rel, text in self.engine_surfaces():
            with self.subTest(rel=rel):
                self.assertIn("For Markdown, confirm every dependency task is `ACCEPTED`", text)
                self.assertIn("For HTML, use the engine's eligibility and current evidence", text)
                self.assertIn("do not replace its same-checkpoint `REVIEW` rule", text)

    def test_scoped_continuation_and_full_plan_proof_remain(self):
        for rel, text in self.engine_surfaces():
            with self.subTest(rel=rel):
                self.assertIn("Do NOT hand to `commit-gate`; the caller owns that decision", text)
                self.assertIn("_preflight_current_acceptance", text)
                self.assertIn("real authority or security block", text)
'''


def apply_changes() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    run('git', 'archive', '--format=zip', '-o', str(OUT / 'input-source.zip'), 'HEAD')
    if os.environ.get('GITHUB_REPOSITORY') != REPO or os.environ.get('GITHUB_REF') != BRANCH:
        raise RuntimeError('Wrong repository or branch')
    run('git', 'merge-base', '--is-ancestor', SOURCE, 'HEAD')
    for path, expected in EXPECTED.items():
        if oid((ROOT / path).read_bytes()) != expected:
            raise RuntimeError(f'Unexpected source movement: {path}')
    if git('status', '--porcelain'):
        raise RuntimeError('Preparation requires a clean checkout')

    test_path = '.github/scripts/test_routing_and_cleanup_surface.py'
    replace(test_path, '\nif __name__ == "__main__":', RECOVERY_TESTS + '\n\nif __name__ == "__main__":')
    red = run(sys.executable, test_path, 'TestSprintRecoveryAndLimits', '-v', check=False)
    (OUT / 'recovery-red.log').write_text(red.stdout + red.stderr)
    if red.returncode != 1 or 'FAILED (failures=' not in red.stderr or 'ERROR:' in red.stderr:
        raise RuntimeError('Expected assertion-only RED against old sprint contracts')

    replace('core/surface/includes/redirect.md',
            'The existing `mode --ops` contract owns local runtime work that leaves tracked files and Git\nhistory unchanged.',
            'The existing `mode --ops` contract in `{{PLUGIN_ROOT}}/includes/ops-mode.md` owns local runtime\nwork that leaves tracked files and Git history unchanged.')

    persona_test = '.github/scripts/test_persona_composition.py'
    safety = read('core/surface/includes/safety-core.md')
    authority = safety.split('Within already-authorized scope,', 1)[1].split('\n\n---', 1)[0]
    authority = 'Within already-authorized scope,' + authority
    replace(persona_test,
            '    "A parameter is yours to decide only when it is reversible, has one sensible answer, "\n    "and is recorded where the user will review it"',
            '    ' + repr(authority))
    additional = '''\n\ndef test_decision_authority_negative_controls():
    """A reviewed wording update must not erase the scope/authority boundary."""
    current = norm(read(SAFETY_CORE))
    for before, after in (
        ("Within already-authorized scope", "Outside authorized scope"),
        ("This does not grant initial scope approval", "This grants initial scope approval"),
        ("confirmations above remain mandatory", "confirmations above are optional"),
    ):
        check(before in current, "missing authority mutation target: " + before)
        seeded = current.replace(before, after, 1)
        check(ANCHOR_DECISION_AUTHORITY not in seeded,
              "authority anchor accepted a weakened scope/confirmation boundary")
'''
    replace(persona_test, '\nTESTS = [', additional + '\n\nTESTS = [\n    test_decision_authority_negative_controls,')

    artifact_test = '.github/scripts/test_artifact_surface.py'
    replace(artifact_test, 'ARTIFACT_GUIDANCE_PATHS = (',
            '# Historical artifact-policy baseline is immutable. PR843 separately reviewed\n'
            '# the resident routing body; do not freeze all future policy to the pilot.\n'
            'STARTUP_CONTENT_REVISIONS = {\n'
            '    "core/surface/arbiter.md": "cb8d6247807091c39dc92c96c2a8cb1bfbc587d1",\n'
            '}\n\nARTIFACT_GUIDANCE_PATHS = (')
    replace(artifact_test,
            '            self.assertEqual(digest, fixture["sha256"], fixture["path"])',
            '            revision = STARTUP_CONTENT_REVISIONS.get(fixture["path"], POLICY_BASELINE_REVISION)\n'
            '            expected_digest = hashlib.sha256(git_bytes(revision, fixture["path"])).hexdigest()\n'
            '            self.assertEqual(digest, expected_digest, fixture["path"])')
    extra = '''    def test_reviewed_startup_revision_is_narrow_and_reachable(self) -> None:
        self.assertEqual(set(STARTUP_CONTENT_REVISIONS), {"core/surface/arbiter.md"})
        for path, revision in STARTUP_CONTENT_REVISIONS.items():
            self.assertIn(path, POLICY_STARTUP_FIXTURES)
            self.assertRegex(revision, r"^[0-9a-f]{40}$")
            result = subprocess.run(["git", "merge-base", "--is-ancestor", revision, "HEAD"],
                                    cwd=ROOT, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0)

    def test_reviewed_startup_content_still_rejects_drift_and_eager_schema(self) -> None:
        for path, revision in STARTUP_CONTENT_REVISIONS.items():
            approved = git_bytes(revision, path)
            self.assertNotEqual(hashlib.sha256(approved + b"\\n").hexdigest(),
                                hashlib.sha256(approved).hexdigest())
            forbidden = self.baseline["forbidden_startup_markers"]
            self.assertTrue(forbidden)
            seeded = approved.decode() + "\\n" + forbidden[0] + "\\n"
            self.assertTrue(eager_markers(seeded, forbidden))

'''
    replace(artifact_test, '    def test_startup_fixtures_do_not_eager_load_artifact_content(self) -> None:',
            extra + '    def test_startup_fixtures_do_not_eager_load_artifact_content(self) -> None:')

    sprint = 'core/surface/SPRINT.md'
    recovery = '''## Recovery within the approved sprint

A failed TDD, coverage, lint, or fresh-verification result blocks acceptance, not authorized repair.
This section applies only after initial spec-and-plan approval and only inside that approved scope.
Classify the failure before acting: an implementation defect or stale proof takes the owning repair
or reconciliation path; a real authority or security block takes the hard-gate path below.

Read the diagnostics and current state, give the author a corrective brief containing the failed
obligation and relevant evidence, and rerun the original gate plus every invalidated review.
Never redispatch merely to evade a failing gate. Do not weaken tests, invent an exemption, broaden
scope, or accept a self-reported pass to continue. Use SMARTS and the existing sprint log for material
method choices, not another approval interview for an already-authorized correction.

For HTML, load `{{PLUGIN_ROOT}}/includes/artifacts.md` and use the exact current identity,
`eligible`, and applicable `task-reconcile` or `scope-reconcile` operations before redispatch.
Obtain a fresh complete context ticket and capture real policy events for every required receipt.
Never manufacture an approval or a receipt, edit execution cells, or create a shadow ledger.
An invalidated proof needs the appropriate fresh verification/review, not automatic reimplementation.

Unchanged failure plus unchanged inputs is not progress. After two consecutive corrective attempts
with the same failure and no new evidence, stop that retry strategy. Choose a different authorized
approach supported by a new diagnosis, or preserve a bounded blocked-task report and continue
independently eligible work. This is not automatically another user checkpoint. Ask only for the
specific missing fact or authority when that is the blocker; do not report the incomplete plan as accepted.

A `commit-gate` refusal returns to its named repair/reconciliation prerequisite. Recovery does not
grant commit, provider, spending, disclosure, or publication authority. Security CRITICAL findings,
unresolved `[CONFIRM-NN]` decisions, irreversible operations, and the hard gates below remain stops.
HTML farm remains disabled. This recovery path does not change farm-only intent or authorize a
silent premium fallback, another provider, or more spending after a farm circuit-breaker abort.

'''
    # Keep the preservation assertion on one line in both canonical and rendered text.
    recovery = recovery.replace('Recovery does not\ngrant commit,', 'Recovery does not grant commit,')
    replace(sprint, '## Phase 3 — Land & summarize · gate: BLOCK', recovery + '## Phase 3 — Land & summarize · gate: BLOCK')
    replace(sprint,
            '- A `tdd` BLOCK, a security CRITICAL finding, or a `[CONFIRM-NN]` that SMARTS cannot resolve from the spec.',
            '- A security CRITICAL finding, or a `[CONFIRM-NN]` that requires a missing user decision.\n'
            '  An ordinary failing TDD/verification result instead takes Recovery within the approved sprint;\n'
            '  it remains blocked from acceptance until the original gate and required reviews pass.')
    replace(sprint, '- MUST surface a repeated hard-gate-trip pattern as a planning/confidence signal, not grind past it.',
            '- MUST surface a repeated hard-gate-trip pattern as a planning/confidence signal, not grind past it.\n'
            '- MUST diagnose and repair ordinary in-scope quality failures through Recovery within the approved sprint;\n'
            '  never auto-pass a gate or treat recovery as additional authority.')

    engine = 'core/surface/skills/subagent-driven-development/SKILL.md'
    replace(engine, '- Confirm every dependency task is `ACCEPTED` before selecting.',
            '- For Markdown, confirm every dependency task is `ACCEPTED` before selecting.\n'
            '- For HTML, use the engine\'s eligibility and current evidence; do not replace its same-checkpoint `REVIEW` rule\n'
            '  with the legacy `ACCEPTED` sentence or infer eligibility from a displayed status.')
    replace(engine,
            'Gate: the subagent reports `tdd` complete — all six phases green. A `tdd` BLOCK halts the loop; do not\nre-dispatch around it.',
            'Gate: all six `tdd` phases must be green before acceptance. Never redispatch merely to evade a failing gate.\n'
            'Under an approved `/sprint`, an ordinary implementation/test failure routes to **Recovery within the\n'
            'approved sprint** in `{{PLUGIN_ROOT}}/SPRINT.md`; rerun the original gate after an evidence-led correction.\n'
            'An attended invocation returns the blocked prerequisite to its caller. A real authority or security block\n'
            'halts the affected work and is surfaced under the hard rules, in either mode.')
    # Keep the named section cross-reference unbroken for targeted contract assertions.
    replace(engine, '**Recovery within the\napproved sprint**', '**Recovery within the approved sprint**')
    replace(engine, '- MEDIUM and LOW findings are recorded; the user decides whether they block.',
            '- MEDIUM and LOW findings are recorded; the active caller owns their disposition. Under an approved\n'
            '  `/sprint`, use its existing delegated decision rules rather than adding a per-finding user checkpoint.\n'
            '  In attended execution the user retains that decision; mandatory project policy still applies.')
    replace(engine,
            '- MUST halt and surface to the user on a `tdd` BLOCK, a security CRITICAL finding, or an unresolved `[CONFIRM-NN]` inside the loop — and on a `commit-gate` failure at the finish handoff — even under `/sprint`. These never auto-proceed.',
            '- MUST halt and surface a real authority or security block, including security CRITICAL findings and\n'
            '  unresolved `[CONFIRM-NN]` decisions. Ordinary TDD/verification failures and finish-time stale proof\n'
            '  under an approved sprint take Recovery within the approved sprint in `{{PLUGIN_ROOT}}/SPRINT.md`.\n'
            '  A failed gate never auto-passes, and recovery never grants missing commit authority.')

    # Reconcile only the three independently acquired original-run receipts. Do
    # not edit old tag identities or extend the closed legacy ledger.
    sys.path.insert(0, str(ROOT / '.github/scripts'))
    import reconcile_tag_receipt as reconcile
    ledger_path = '.github/published-tags.json'
    original = json.loads(read(ledger_path))
    legacy = reconcile.load_legacy_manifest(json.loads(read('.github/legacy-published-tags.json')))
    ledger = original
    release_sha = '5c876dd885598c248fa777e951dac4e628688d73'
    identities = (
        ('v2.21.7', '1fd5d6caaef147e7dfb8e1d40a8b11d20b3d1d26'),
        ('ca-codex-v0.13.7', '2a19e150aeedb6f75ab1575eb9a9cd2bd12fb87d'),
        ('ca-pi-v0.14.7', 'a3fcb053793ee5694083c2025c5e658b9bf995e7'),
    )
    for tag, object_sha in identities:
        identity = {'commit_sha': release_sha, 'object_sha': object_sha, 'object_type': 'tag'}
        receipt = {'schema_version': 1, 'repo': REPO, 'tag': tag, 'identity': identity,
                   'source': {'kind': 'hosted-tag-observation', 'run_id': 35537578654,
                              'run_attempt': 1, 'workflow_sha': release_sha}}
        expected = {'repo': REPO, 'tag': tag, 'commit': release_sha, 'run_id': 35537578654,
                    'run_attempt': 1, 'workflow_sha': release_sha}
        candidate = reconcile.reconcile(ledger, receipt, expected, legacy_tags=set(legacy))
        if candidate is not None:
            ledger = candidate
    for tag, entry in original['tags'].items():
        if ledger['tags'][tag] != entry:
            raise RuntimeError('Historical tag entry changed')
    write(ledger_path, json.dumps(ledger, indent=2, ensure_ascii=True) + '\n')

    versions = (
        ('plugins/ca/.claude-plugin/plugin.json', '2.21.7', '2.21.8', 'CHANGELOG.md', 'v'),
        ('plugins/ca-codex/.codex-plugin/plugin.json', '0.13.7', '0.13.8', 'plugins/ca-codex/CHANGELOG.md', 'ca-codex-v'),
        ('plugins/ca-pi/package.json', '0.14.7', '0.14.8', 'plugins/ca-pi/CHANGELOG.md', 'ca-pi-v'),
    )
    for manifest, old, new, changelog, prefix in versions:
        if run('git', 'show-ref', '--verify', '--quiet', 'refs/tags/' + prefix + new, check=False).returncode != 1:
            raise RuntimeError('Candidate tag already exists or cannot be classified')
        replace(manifest, '"version": "' + old + '"', '"version": "' + new + '"')
        notes = ('## [' + new + '] - 2026-09-21\n\n### Fixed\n\n'
                 '- Route understood requests to the existing workflow without compulsory\n'
                 '  command syntax; keep questions and draft-only requests non-mutating.\n'
                 '- Recover ordinary quality failures inside an approved sprint through\n'
                 '  the original gates and current typed evidence, without adding routine\n'
                 '  user checkpoints or expanding authority. HTML farm remains disabled.\n\n')
        replace(changelog, '## [Unreleased]\n\n', '## [Unreleased]\n\n' + notes)
    replace('README.md', 'alt="version 2.21.7" src="https://img.shields.io/badge/version-2.21.7-',
            'alt="version 2.21.8" src="https://img.shields.io/badge/version-2.21.8-')

    review = 'docs/reviews/2026-09-21-autonomy-routing-integration.md'
    write(review, read(review) + '''\n## Second slice: CI repair and bounded sprint recovery\n\nThe failed first-slice run was 35653563527 at cb8d6247807091c39dc92c96c2a8cb1bfbc587d1.\nThe official generator and original routing suite passed; broader composition tests\nexposed the stale decision-authority anchor and missing ops-mode link. Artifact\nstartup checks still pinned the pre-review resident persona. That historical\nbaseline is retained, with a separate exact reviewed revision for the changed\npersona; registration parity and eager-artifact checks remain enforced.\n\nOrdinary quality failures now return through the same original gate and invalidated\nreviews under an approved sprint. Initial spec/plan approval, real authority/security\nblocks, immutable records, and HTML farm restrictions remain unchanged. Typed\neligibility overrides the legacy ACCEPTED-dependency sentence explicitly. This does\nnot resolve initial approval choreography, all farm recovery, or commit delegation.\n\nThe three missing publication-ledger entries were recovered from the original\nsuccessful release run 35537578654, attempt 1, workflow/source commit\n5c876dd885598c248fa777e951dac4e628688d73. Independently acquired artifacts:\n\n| Tag | Original receipt artifact | Verified archive SHA-256 |\n|---|---|---|\n| v2.21.7 | 10613213900 | 55aeb520adb4ae6054455baf4b819eebb0d53e336ba994365e56c18dfa6e2b47 |\n| ca-codex-v0.13.7 | 10613189302 | 4dc5adc7dda8729d20a3302992e23d8690867a075f7a3fdc256f0958c6c9c90d |\n| ca-pi-v0.14.7 | 10612799631 | a9b77decc6036bc7ab044514061082bb54e344d251b3fa05cf17560adbb211d1 |\n\nThe existing reconcile_tag_receipt helper validates the append-only candidate. No\nold identity is replaced, no legacy entry is promoted, and no tag is moved. The\nnext patch versions and their notes are candidate metadata, not publication proof.\n\nA temporary branch-only preparation job uses a complete checkout and official\ngenerators. It never updates a ref; the candidate removes its two helper files.\nIts result must be inspected before the connector fast-forwards this PR branch.\nProduct tests, generated parity, installed-host behavior and live-model routing\nremain distinct evidence layers. Exact executed commands/results are retained in\nthe preparation artifact and the PR update, not inferred from this document.\n''')
    (OUT / 'apply-complete.json').write_text(json.dumps({'head': git('rev-parse', 'HEAD'), 'source': SOURCE}))


TEST_COMMANDS = [
    ['tools/build-surface.py', '--check'],
    ['tools/build-host-packages.py', '--check'],
    ['.github/scripts/test_routing_and_cleanup_surface.py', '-v'],
    ['.github/scripts/test_persona_composition.py'],
    ['.github/scripts/test_artifact_surface.py'],
    ['.github/scripts/test_recorded_intent_surface.py'],
    ['.github/scripts/test_mode_surface.py'],
    ['.github/scripts/test_build_surface.py'],
    ['.github/scripts/check_destructive_registry.py'],
    ['.github/scripts/check_routing_index_parity.py'],
    ['.github/scripts/check_docs_contract.py'],
    ['.github/scripts/check_badge_consistency.py'],
    ['.github/scripts/test_reconcile_tag_receipt.py'],
    ['.github/scripts/test_tag_immutability.py'],
]


def validate() -> None:
    run(sys.executable, 'tools/build-surface.py')
    run(sys.executable, 'tools/build-host-packages.py')
    results = []
    for n, command in enumerate(TEST_COMMANDS):
        p = run(sys.executable, *command, check=False)
        name = f'{n:02d}-' + Path(command[0]).stem + '.log'
        (OUT / name).write_text(p.stdout + p.stderr)
        print(f'{p.returncode}: {" ".join(command)}', flush=True)
        results.append({'command': [sys.executable, *command], 'exit_code': p.returncode, 'log': name})
    run('git', 'diff', '--check')
    (OUT / 'tests.json').write_text(json.dumps(results, indent=2) + '\n')
    (OUT / 'candidate.diff').write_text(run('git', 'diff', '--no-ext-diff').stdout)
    # Full edited text is a review artifact, not startup context or a secret-bearing archive.
    changed = git('diff', '--name-only').splitlines()
    with zipfile.ZipFile(OUT / 'candidate-files.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for path in changed:
            z.write(ROOT / path, path)
    (OUT / 'changed-files.json').write_text(json.dumps(changed, indent=2) + '\n')
    if any(x['exit_code'] for x in results):
        raise RuntimeError('Candidate has failing checks; no Git object will be uploaded')
    (OUT / 'validated.json').write_text(json.dumps({'head': git('rev-parse', 'HEAD'), 'changed': changed}))


def api(method: str, endpoint: str, payload: dict | None = None) -> dict:
    # No caller-controlled host, no redirects, and no token passed to child processes.
    url = 'https://api.github.com/repos/' + REPO + endpoint
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method,
        headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
                 'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
                 'Content-Type': 'application/json'})
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise RuntimeError('Unexpected API redirect')
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=45) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        # Error bodies are intentionally not printed because they can contain request metadata.
        raise RuntimeError(f'Git object API returned HTTP {exc.code}') from None


def upload() -> None:
    if os.environ.get('GITHUB_REPOSITORY') != REPO or os.environ.get('GITHUB_REF') != BRANCH:
        raise RuntimeError('Wrong publication scope')
    evidence = json.loads((OUT / 'validated.json').read_text())
    head = git('rev-parse', 'HEAD')
    if evidence['head'] != head or head != os.environ['GITHUB_SHA']:
        raise RuntimeError('Candidate checkout identity changed')
    if api('GET', '/git/ref/heads/codex/autonomy-routing-integration')['object']['sha'] != head:
        raise RuntimeError('Branch moved; do not construct a stale candidate')
    permitted = {
        'core/surface/includes/redirect.md', 'core/surface/SPRINT.md',
        'core/surface/skills/subagent-driven-development/SKILL.md',
        '.github/scripts/test_artifact_surface.py', '.github/scripts/test_persona_composition.py',
        '.github/scripts/test_routing_and_cleanup_surface.py', '.github/published-tags.json',
        'plugins/ca/.claude-plugin/plugin.json', 'plugins/ca-codex/.codex-plugin/plugin.json',
        'plugins/ca-pi/package.json', 'package.json', 'README.md', 'CHANGELOG.md',
        'plugins/ca-codex/CHANGELOG.md', 'plugins/ca-pi/CHANGELOG.md',
        'docs/reviews/2026-09-21-autonomy-routing-integration.md',
    }
    for plugin, directory in [('ca','skills'),('ca-codex','routines'),('ca-pi','routines')]:
        permitted.update({f'plugins/{plugin}/SPRINT.md', f'plugins/{plugin}/includes/redirect.md',
                          f'plugins/{plugin}/{directory}/subagent-driven-development/SKILL.md'})
    changed = git('diff', '--name-only').splitlines()
    if changed != evidence['changed'] or set(changed) - permitted:
        raise RuntimeError('Candidate changed paths differ from the reviewed allowlist')
    entries = []
    inventory = []
    for path in changed:
        data = (ROOT / path).read_bytes()
        mode, kind, _ = git('ls-tree', 'HEAD', '--', path).split('\t', 1)[0].split()
        if kind != 'blob' or mode not in ('100644', '100755'):
            raise RuntimeError('Unexpected file kind or mode')
        blob = api('POST', '/git/blobs', {'content': data.decode('utf-8'), 'encoding':'utf-8'})['sha']
        if blob != oid(data):
            raise RuntimeError('Uploaded blob identity mismatch')
        entries.append({'path':path, 'mode':mode, 'type':'blob', 'sha':blob})
        inventory.append({'path':path, 'git_blob_sha':blob, 'bytes':len(data)})
    for path in TEMP_PATHS:
        entries.append({'path':path, 'mode':'100644', 'type':'blob', 'sha':None})
    tree = api('POST', '/git/trees', {'base_tree':git('rev-parse', 'HEAD^{tree}'), 'tree':entries})['sha']
    commit = api('POST', '/git/commits', {
        'message':'fix: recover approved sprint work and repair CI contracts\n\n'
                  'Retain historical startup evidence, update the reviewed persona fixture,\n'
                  'restore the ops reference, and pin delegated-authority safeguards.\n'
                  'Reconcile original publication receipts without moving tags.\n'
                  'Advance affected candidate versions and notes with the payload.\n\n'
                  'CHANGELOG: Fixed bounded sprint recovery and intent-routing contracts.',
        'tree':tree, 'parents':[head],
    })['sha']
    (OUT / 'candidate.json').write_text(json.dumps({'commit':commit, 'tree':tree, 'parent':head,
        'branch_updated':False, 'removed_temporary_helpers':list(TEMP_PATHS), 'files':inventory}, indent=2)+'\n')
    print('Prepared unreferenced candidate commit: ' + commit)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=('apply','validate','upload'))
    args = parser.parse_args()
    {'apply':apply_changes, 'validate':validate, 'upload':upload}[args.phase]()
