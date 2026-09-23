/** Build-time fixture checks, not a substitute for the native artifact validator.
 * HTML is never executed here. Its entire bytes are pinned by the checked-in
 * capture manifest, then the small subset needed for this exhibit is projected.
 */
import { createHash } from 'node:crypto';
import { readFileSync, lstatSync } from 'node:fs';
import { join, resolve } from 'node:path';

export interface Criterion {
  id: string; title: string; statement: string; preconditions: string[]; trigger: string;
  verification: { planned_target: string; oracle: string; negative_control: string; evidence_state: string };
}
export interface Task {
  id: string; title: string; criterion_refs: string[]; depends_on: string[];
  paths: { path: string; action: string }[];
  verification: { argv: string[]; required_tests: string[]; assertion: string }[];
}
export interface Spec {
  artifact_id: string; kind: 'spec'; revision: number;
  governance: { state: string; approvals: unknown[] };
  integrity: { normative_sha256: string; model_sha256: string };
  normative: { title: string; summary: string; criteria: Criterion[] };
}
export interface Plan extends Omit<Spec, 'kind' | 'normative'> {
  kind: 'plan';
  normative: { title: string; tasks: Task[]; spec_ref: { artifact_id: string; normative_sha256: string; binding_mode: string } };
  execution: { tasks: Record<string, { state: string }> };
}
export interface Run { argv: string[]; exit_code: number; output: string }
export interface Provenance {
  schema_version: number; authority: string; source: string; source_commit: string;
  engine_sha256: string; evidence_boundary: string; files: Record<string, string>;
}
// npm's site scripts run from site/; import.meta.url points at a prerender chunk after bundling.
const defaultRoot = resolve(process.cwd(), 'public/examples/saved-searches');
const required = ['baseline.py', 'completed.py', 'test_export_csv.py', 'spec.request.json', 'plan.request.json',
  'specs/saved-searches.html', 'plans/saved-searches.html', 'test-runs.json', 'native-validation.json'];
const fail = (why: string): never => { throw new Error(`Product example: ${why}`); };

export function loadProductExample(root = defaultRoot) {
  const read = (path: string): Buffer => {
    const absolute = join(root, path);
    if (!lstatSync(absolute).isFile()) fail(`not a regular file: ${path}`);
    return readFileSync(absolute);
  };
  const provenance: Provenance = JSON.parse(read('provenance.json').toString());
  if (provenance.schema_version !== 1 || provenance.authority !== 'unapproved documentation fixture') fail('unapproved fixture identity missing');
  if (!/^[a-f0-9]{40}$/.test(provenance.source_commit) || !/^[a-f0-9]{64}$/.test(provenance.engine_sha256)) fail('capture identity missing');
  if (JSON.stringify(Object.keys(provenance.files).sort()) !== JSON.stringify([...required].sort())) fail('capture inventory changed');
  for (const path of required) {
    const actual = createHash('sha256').update(read(path)).digest('hex');
    if (actual !== provenance.files[path]) fail(`capture digest mismatch: ${path}`);
  }
  function model(path: string): unknown {
    const html = read(path).toString();
    // This is a fixed native-renderer fixture, not an arbitrary HTML sanitizer.
    // Require its exact inert model tag and reject any additional opening or
    // closing script token, including whitespace/mixed-case and unclosed forms.
    const opening = '<script id="ca-artifact-model" type="application/json">';
    const start = html.indexOf(opening);
    const end = html.indexOf('</script>', start + opening.length);
    const lower = html.toLowerCase();
    if (start < 0 || end < 0 || lower.split('<script').length !== 2 || lower.split('</script').length !== 2) fail('unexpected script surface');
    return JSON.parse(html.slice(start + opening.length, end));
  }
  const spec = model('specs/saved-searches.html') as Spec;
  const plan = model('plans/saved-searches.html') as Plan;
  if (spec.kind !== 'spec' || plan.kind !== 'plan') fail('pair kinds');
  for (const document of [spec, plan]) {
    if (document.governance.state !== 'draft' || document.governance.approvals.length !== 0) fail('fixture acquired approval');
  }
  const binding = plan.normative.spec_ref;
  if (binding.binding_mode !== 'draft_preview' || binding.artifact_id !== spec.artifact_id || binding.normative_sha256 !== spec.integrity.normative_sha256) fail('draft pair binding');
  if (Object.values(plan.execution.tasks).some((task) => task.state !== 'PENDING')) fail('fixture acquired execution state');
  const known = new Set(spec.normative.criteria.map((criterion) => `${spec.artifact_id}#${criterion.id}`));
  if (known.size !== spec.normative.criteria.length) fail('duplicate criterion');
  if (plan.normative.tasks.some((task) => !task.criterion_refs.length || task.criterion_refs.some((ref) => !known.has(ref)))) fail('orphan task or criterion');
  const criteria = spec.normative.criteria.map((criterion) => ({ ...criterion,
    tasks: plan.normative.tasks.filter((task) => task.criterion_refs.includes(`${spec.artifact_id}#${criterion.id}`)),
  }));
  if (criteria.some((criterion) => !criterion.tasks.length || criterion.verification.evidence_state !== 'planned')) fail('coverage or planned-evidence boundary');
  const validation = JSON.parse(read('native-validation.json').toString());
  for (const [kind, doc] of [['specs', spec], ['plans', plan]] as const) {
    for (const gate of ['structural', 'ready']) {
      const result = validation[`${kind}_${gate}`]?.result;
      if (!result?.valid || result.model_sha256 !== doc.integrity.model_sha256 || result.normative_sha256 !== doc.integrity.normative_sha256) fail('native validation does not bind these bytes');
    }
    if (validation[`${kind}_approved`]?.result?.valid !== false) fail('expected approval refusal missing');
  }
  if (validation.draft_eligibility?.error?.code !== 'DRAFT_BINDING') fail('draft dispatch refusal missing');
  const runs: { red: Run; green: Run } = JSON.parse(read('test-runs.json').toString());
  if (runs.red.exit_code !== 1 || runs.green.exit_code !== 0 || !runs.red.output.includes('FAILED (failures=2)') || !runs.green.output.includes('Ran 3 tests')) fail('fixture test boundary');
  return { spec, plan, criteria, provenance, runs, validation };
}
