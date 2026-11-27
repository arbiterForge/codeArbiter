import json
from pathlib import Path
ROOT=Path('/workspace/scratch/6dd9dc5f561f'); REPO=ROOT/'codeArbiter'
SHA='fd7eb34b2da439551443d09526ab48fd1d1bb9bf'
machines=[]
def M(id,name,paths,rows,storage):
 s=[{'path':p,'symbol':'Complete module'} for p in paths]
 machines.append({'id':id,'name':name,'kind':'implemented','state_storage':storage,'sources':s,
 'states':list(dict.fromkeys(x for r in rows for x in (r[0],r[3]))),
 'state_notation':'Analytical phases of a build-time state owner or parser, not execution authority and not installed-host qualification.',
 'transitions':[dict(zip(['from','event','guard','to','effects','failure_retry'],r),source=s) for r in rows]})

M('SX01','Direct hook proof capture and media settlement',
 ['site/scripts/capture-hook-proof.ts','site/scripts/capture/fixture.ts','site/scripts/capture/py-runner.py','site/scripts/capture/normalize.ts'],[
 ('No fixture','Capture requested','Capture-owned temporary root','Isolated fixture','Create temporary project/home/tmp and allowlisted environment; initialize Git and fixed fixture identity.','Cleanup validates owned root prefix/parent; no current user project is exercised.'),
 ('Fixture prepared','Invoke pre-bash entry','Synthetic PreToolUse payload for git add -A','Observed replay','Run actual Python entry; record status, stderr, index/worktree observations and gate log.','The requested git add command itself is never executed; direct replay cannot prove host discovery.'),
 ('Observed replay','Check expected behavior','Exit2 with H-03, unchanged staged list, note remains untracked and actual block event','Valid capture / exception','Build record with actual entry-source raw SHA256 and hostDiscoveryProven=false.','Any failed behavioral assertion stops capture; captured imports are known by harness but are not all persisted in this proof schema.'),
 ('Valid capture','Compare previous evidence','Normalize timestamps/paths and omit capturedAt; same evidence and no force','No-op','Keep prior JSON/media and report unchanged.','A matching record alone does not read back each media asset; force requests fresh rendering.'),
 ('Changed capture / force','Render media','Validated replay and owned frame root','Media produced / failure','Write frames, MP4, WebM and poster.','Renderer failure leaves the prior proof JSON in place; a later run can retry because new record has not been committed.'),
 ('Media produced','Write record','All requested media rendering returned','Proof record committed','Write hook-proof.json last and report exact capture identity.','This is ordered multi-file output, not one atomic media-plus-record transaction.'),
 ('Any created fixture','finally cleanup','Owned temporary scope','Disposed','Dispose fixture, then remove frame directory even if fixture disposal throws.','Cleanup failure is not reclassified as successful fixture destruction.')],
 'Temporary fixture files and imported-code side record; committed proof JSON/media; per-run in-memory observations')

M('SX02','Documentation examples: capture, pin, validate and render',
 ['site/scripts/capture-context-examples.py','site/scripts/capture-statusline-themes.py','site/scripts/generate-product-example.py','site/scripts/product-example.ts','site/scripts/capture/render.ts','site/scripts/capture/label.ts','site/scripts/capture/targets.ts'],[
 ('Context capture requested','Run disposable helper scenarios','Actual helper modules and local Git fixture','Current observations','Observe initial/repeated injection, source change, unmapped/self-read and budget behavior; record actual file hashes.','Historical SOURCE_REVISION is separately labeled; no live host or approval claim.'),
 ('Current observations','--check / --write / default','Explicit selected capture mode','Compared / stored / printed','Check exact JSON equality, intentionally replace teaching capture, or print it.','Mismatch exits1; an older observation is not silently called current.'),
 ('Theme capture requested','Verify renderer and imported dependencies','Every dependency byte equals pinned historical Git source','Eligible renderer / refusal','Hash actual entry before execution and imported files afterward; use isolated home and mocked project/usage inputs.','No account, billing or installed-host evidence follows from this renderer fixture.'),
 ('Eligible renderer','Render each declared theme','Deterministic input, no fixture ledger writes','Theme records stored','Require expected segments, hash ANSI output and write exact theme inventory.','Missing pin/object, changed dependency or failed assertion stops generation.'),
 ('Native example requested','Resolve engine','Exact reviewed engine digest','Unapproved native example','Create draft spec/plan in temporary repo; require structural/ready success, approval refusal and dispatch refusal.','No approval is manufactured. Failure stops before a complete provenance record is emitted.'),
 ('Unapproved example','Run fixed RED and GREEN tests','Correct exit codes, test count, no ERROR','Captured example','Write observed test results and copy fixed sources; write file inventory/provenance last.','An interruption can leave partial output; build-time consumer must verify full pinned membership/digests.'),
 ('Captured example','Build-time load','Exact file inventory/hashes, inert model tag, draft/no approvals/PENDING tasks, bound native results and expected RED/GREEN','Renderable teaching projection','Project criteria/tasks/results without executing HTML.','Malformed evidence fails build; validation is a fixed fixture contract, not general native validation.'),
 ('Markdown capture fence','Render capture','Safe id, existing matching record, authored fence empty','Filled code fence','Inject captured output and entry-hash label.','Unknown capture, wrong id or prefilled fence fails build instead of merging invented output.')],
 'Pinned example files, per-run fixtures, immutable in-memory projection and generated Markdown AST')

M('SX03','Documentation release and proof applicability derivation',
 ['site/scripts/release-applicability.ts','site/src/release-applicability-presentation.ts','site/src/pages/release-applicability.json.ts'],[
 ('Release declarations and ledger','Parse','Bounded target block; required targets/manifests; exact duplicate-free ledger schema','Valid release inputs / rejection','Collect per-target tag prefixes and original-publication receipts.','Malformed target/version/SHA/receipt refuses build.'),
 ('Valid release inputs','Select current governance releases','Highest stable SemVer tag in local inventory for each target','Selected tag rows','Name selected commit publicationCommit; mark original receipt recorded/not-recorded independently.','There is no GitHub Release status input. Tag-only and draft-release tags are not distinguished from published releases here.'),
 ('Selected tag rows','Read historical manifests and Pi contract','Exact selected commit; manifest versions equal tag; exact AST Set declaration','Version-bound rows / rejection','Read historical payload manifests and supported Pi versions at the selected tag.','Historical reads cannot by themselves establish that a GitHub Release or package was distributed.'),
 ('Build identity requested','Resolve HEAD/environment','Exact HEAD; Actions SHA equals HEAD when GITHUB_ACTIONS=true','Build identity','Local mode observes dirty worktree; Actions mode returns dirty=false after SHA check.','Actions branch does not independently call isDirty; equality of HEAD and GITHUB_SHA alone does not attest a clean working tree.'),
 ('Replay source evidence','Compare digests','Exact pre-bash source path, direct replay type and hostDiscoveryProven=false','applicable / mismatch','Compare only the replay entry-file raw digest with current and selected-tag entry bytes.','This is entry-source applicability, not imported-dependency equivalence or host registration proof.'),
 ('Derived record','Publish generated site data','Complete identity and applicability object','Generated JSON and presentation','Write record; static endpoint serializes it; display checks applicable equals both match flags.','Inconsistent display input throws. A successful JSON projection does not add publication evidence absent from its inputs.')],
 'Build-time tag inventory, original receipt ledger, historical source snapshots and generated site JSON')

M('SX04','Version-fact extraction, process cache and token resolution',
 ['site/scripts/version-facts.ts','site/src/content.config.ts'],[
 ('Facts uncached','First request','Repository root found by required sentinels','Facts loading','Read owner sources/manifests and require exactly one matching declaration; compare Node declared/enforced floor and Codex minimum/CI floor.','Ambiguous, malformed or disagreeing declarations throw; no remembered version fallback.'),
 ('Facts loading','Read release-applicability record','Missing file ENOENT versus another failure','Partial fact map / failure','If absent, leave release/pi-supported facts unknown; if present parse required host rows and supported versions.','Unreadable or malformed present record is not treated as absent.'),
 ('Facts loaded','Cache process result','Successful complete load','Cached','Reuse one fact map for subsequent calls in the process.','A later file change is not observed until a new process or uncached owner path; cache lifetime is part of the build contract.'),
 ('Content contains fact token','Resolve','Own property exists and token grammar complete','Substituted content / build error','Replace tokens in prose, code, HTML and selected frontmatter fields.','Unknown token or malformed residue fails instead of publishing a literal or guessed version.')],
 'One module-level VersionFacts cache plus build-time content AST')

M('SX05','Historical atlas source binding and generated projection',
 ['site/scripts/execution-maps/atlas.ts','site/scripts/execution-maps/atlas-model.ts','site/scripts/execution-maps/atlas-command.ts','site/scripts/execution-maps/atlas-theme.ts','site/scripts/execution-maps/atlas-render.ts','site/scripts/generate-atlas.ts'],[
 ('Atlas requested','Load historical graph','Declared repository/revision and complete internally consistent references/geometry','Historical atlas','Clone saved graph, validate IDs, sources, command routes, edges, layouts and source update membership.','The graph describes routes; geometry and gate labels are not executable authorization.'),
 ('Historical atlas','Revalidate source inventory','Exact selected blob or pinned historical commit; safe real source paths','Bound current source view / rejection','Batch-read offline Git objects with environment repository selectors removed; compare current normalized bytes with reviewed bytes.','Missing objects or drift stops build. Only root changelog may gain notes above intact reviewed history under its explicit rule.'),
 ('Bound source view','Resolve command owner','Literal whole-file SKILL_ENTRY may redirect once','Canonical description','Read description from exact command/skill source; project host exclusions and form.','No recursive template/filename guessing; malformed or multiline unsupported description rejects.'),
 ('Bound source view','Reconcile roster and retired routes','Registry plus explicitly retired routes equals historical catalog; lens roster unchanged','Current labels on historical geometry','Hide invocations for retired routes, use pinned historical metadata for them; project selected-work labels and attach source-update boundary.','An unchanged shape is not proof of current release/host behavior; retired commands remain historical boxes.'),
 ('Validated atlas','Resolve theme','Safe noncyclic named site design tokens','Renderable atlas','Resolve one CSS token source; escape authored labels and generate SVG/HTML/reading views.','Missing/cyclic or unsafe token values throw.'),
 ('Renderable atlas','Generate portable edition','Browser transpilation succeeds','Generated files','Write interactive HTML, script-free reading guide, each view SVG and source ledger beneath atlas commit directory.','Outputs are sequential writes; interrupted export can be partial and needs regeneration/read-back.')],
 'Exact source pins, fresh per-call read cache, static graph clone, CSS token resolver stack and generated files')

M('SX06','Site metadata, graph and link build gates',
 ['site/scripts/academy-wayfinding.ts','site/scripts/concept-directory.ts','site/scripts/guide-directory.ts','site/scripts/journey-navigation.ts','site/scripts/reference-sidebar.ts','site/scripts/topic-map.ts','site/scripts/link-audit.ts','site/scripts/link-audit/lib.ts','site/scripts/rehype-base-links.ts','site/scripts/rehype-table-shell.ts','site/scripts/diagram-audit.ts','site/scripts/generate-diagrams.ts','site/scripts/execution-maps/render.ts','site/scripts/execution-maps/locations.ts','site/scripts/decision-evidence.ts'],[
 ('Authored metadata','Resolve navigation','Unique known entries, complete metadata, valid tracks and explicit next lesson','Ordered navigation / failure','Build guide/concept/Academy/reference projections; keep reading position separate from completion.','Missing prerequisites can be external labels; missing next lesson is not inferred. Unknown inventory or duplicate membership fails the relevant owner.'),
 ('Topic map','Validate closure','Known pages/lessons, nonempty nonduplicate lists, every lesson mapped','Resolved topic graph / failure','Join real page titles and lesson references; return per-lesson pages.','Unknown/unmapped membership throws with explicit problems.'),
 ('Content AST','Transform links/tables','Root-absolute unprefixed local links; unwrapped eligible table','Projected AST','Prefix base idempotently; wrap tables and add row labels only to unambiguous authored-guide tables.','Complex tables retain scrolling form; no invented column association.'),
 ('Reviewed diagram model','Render SVG','Validated graph and safe labels/namespaces','Generated diagrams','Render the explicit teaching graph, then sequentially write declared assets.','Illustrative/historical diagrams do not execute workflow transitions; interrupted generation can leave a mixed output set.'),
 ('Diagram files','Audit style/geometry','Required root marker/title/description, font/color inventory and measured label bounds','Pass / violations','Report violations and exit1 for CLI failure.','This checks the declared visual grammar, not semantic truth of the workflow diagram.'),
 ('Built dist','Audit internal targets','Nonempty HTML inventory and required assets','Pass / link failures','Classify external/fragment skip, contained resolution, outside-base, missing and redirect target; cache redirect observations per file.','Zero pages fails. The regex scan checks double-quoted href/src targets; it is not a full browser navigation proof.'),
 ('Pure teaching cases','Validate teaching data','Correct identity, known sources, local continuation links and complete cases','Valid data / errors','Check structural teaching invariants.','Pinned quotes and tests are drift alerts; they do not authenticate choices or prove implementation.')],
 'Build-local sets, counters, link/redirect cache, recursive AST and generated assets; no product execution state')

M('SX07','Captured terminal style decoder',
 ['site/scripts/statusline-capture.ts'],[
 ('Initial style','Read plain segment','Input<=100000 characters and no unsupported control bytes','Text token','Emit literal text with current foreground/background/bold attributes.','Never emit capture bytes as HTML; unsupported terminal controls throw.'),
 ('Current style','Read SGR','Recognized reset/bold/default color/RGB sequence','Updated style','Change only recognized style state; dim/italic codes intentionally do not change emitted text.','Invalid RGB or unsupported SGR rejects instead of interpreting arbitrary terminal control.'),
 ('Theme capture file','Validate inventory and per-output digest','Exact declared theme order and matching ANSI SHA256','Tokenized theme capture','Apply decoder to each matching captured output.','Digest proves captured bytes, not renderer freshness or live account/host state.')],
 'Per-string style fields, offset and emitted token list')

findings=[{'id':'SX-F01','severity':'medium','status':'source-confirmed and pure source-function probe; no actual unpublished production tag alleged',
 'title':'Documentation derives published-release state from tag presence alone',
 'detail':'selectCurrentGovernanceReleases chooses the highest stable local tag, accepts an empty original-publication receipt ledger, and labels its commit publicationCommit. Historical manifest equality and Pi-source parsing validate content identity but do not observe GitHub Release draft/published status. The publication workflow can create a tag before publishing. Therefore tag-only/draft and published states collapse at this site boundary.',
 'sources':[{'path':'site/scripts/release-applicability.ts','symbol':'selectCurrentGovernanceReleases, deriveVerifiedGovernanceReleases, createReleaseApplicabilityRecord'},{'path':'site/src/release-applicability-presentation.ts','symbol':'presentProofApplicability'},{'path':'.github/actions/publish-target/action.yml','symbol':'tag, draft and publication stages'}],
 'probe':'probe-site-publication-result.json: synthetic stable tags and zero receipts are selected; no GitHub/network operation was performed.',
 'recommendation':'Feed a durable observed non-draft publication record into site selection, keyed to immutable tag and payload identity. If that observation is unavailable, label a tag as a tag and leave publication unknown. Do not restore a stale receipt ledger as a blanket new-release gate.'}]
for m in machines:
 for s in m['sources']:assert (REPO/s['path']).is_file(),s
data={'commit':SHA,'machines':machines,'findings':findings}
(ROOT/'audit-work/site-extra.json').write_text(json.dumps(data,indent=2)+'\n')
paths=Path(ROOT/'audit-work/root-site-extra.txt').read_text().splitlines()
paths=[p for p in paths if p not in ['site/scripts/execution-maps/model.ts','site/scripts/execution-maps/workflows.ts']]
paths+=['site/src/content.config.ts','site/src/pages/examples/context-observations.json.ts','site/src/pages/release-applicability.json.ts','site/src/release-applicability-presentation.ts','.coderabbit.yaml','.github/dependabot.yml','.github/ISSUE_TEMPLATE/config.yml','.github/actionlint.yaml']
(ROOT/'audit-work/root-site-read-files.txt').write_text('\n'.join(sorted(set(paths)))+'\n')
print(json.dumps({'machines':len(machines),'transitions':sum(len(m['transitions']) for m in machines),'full_extra_files':len(set(paths))}))
