import json,hashlib,collections
from pathlib import Path
ROOT=Path('/workspace/scratch/6dd9dc5f561f');W=ROOT/'audit-work';R=ROOT/'codeArbiter'
tree=json.loads((W/'tree.json').read_text()); files={x['path']:x for x in tree['tree'] if x['type']=='blob'}
records={p:{'path':p,'status':'inventoried; no semantic full-read claim','evidence':'Pinned Git tree blob '+x['sha']} for p,x in files.items()}
rank={'inventoried; no semantic full-read claim':0,'targeted source read':1,'generated source equivalence checked':2,'rendered derivative equivalence checked':2,'complete executable content read; prose comments/docstrings omitted':3,'complete code and markup read; literal CSS omitted':4,'full file read':5}
def mark(p,status,evidence):
 if p not in records:raise ValueError(p)
 if rank[status]>=rank[records[p]['status']]:
  records[p]={'path':p,'status':status,'evidence':evidence,'git_blob':files[p]['sha'],'sha256':hashlib.sha256((R/p).read_bytes()).hexdigest()}
for item in json.loads((W/'root-read-files.json').read_text())['files']:mark(item['path'],'full file read','Root full read; '+str(item['lines'])+' lines')
for name in ['root-site-read-files.txt','root-final-read-files.txt','pi-qualification-read-files.txt','native-read-files.txt','release-ci-read-files.txt','tooling-read-files.txt','generator-read-files.txt','sandbox-workflows-read-files.txt']:
 for line in (W/name).read_text().splitlines():
  line=line.strip()
  if not line or line.startswith('#'):continue
  if line.startswith('FULL RAW | '):line=line.split('|')[1].strip()
  if '\t' in line:line=line.split('\t')[-1]
  if line in records:mark(line,'full file read',name)
  else:raise ValueError((name,line))
hook=json.loads((W/'hooks.json').read_text())['coverage']
for item in hook['read_files']:
 status='complete executable content read; prose comments/docstrings omitted' if item['complete_executable_source_read'] else 'targeted source read'
 mark(item['path'],status,{'manifest':'hooks-read-files.txt','ranges':item['read_ranges'],'purpose':item['purpose']})
surface=json.loads((W/'surfaces.json').read_text())['coverage']
for p in surface['fully_read']:mark(p,'full file read','surfaces.json fully_read')
for p in surface.get('complete_code_and_markup_with_literal_css_omitted',[]):mark(p,'complete code and markup read; literal CSS omitted','surfaces-component-classification.json')
for item in json.loads((W/'hook-copy-equality.json').read_text()):
 assert item['exists'] and item['equal']
 p='plugins/'+item['host']+'/hooks/'+Path(item['source']).name
 mark(p,'generated source equivalence checked','Byte equality with '+item['source']+'; canonical source read by assigned owner')
surface_equality=json.loads((W/'surface-render-equality.json').read_text())
for item in surface_equality:
 assert item['equal'];mark(item['path'],'rendered derivative equivalence checked','Current canonical renderer output equals exact tracked bytes; host '+item['host'])
counts=collections.Counter(v['status'] for v in records.values())
reviewed=sum(v for k,v in counts.items() if rank[k]>=3)
gaps=[]
for p in files:
 if records[p]['status']!='inventoried; no semantic full-read claim':continue
 if p.startswith('core/pysrc/') and p.endswith('.py'):gaps.append(p)
 if p.startswith('core/artifacts/') and p.endswith('.go') and not p.endswith('_test.go'):gaps.append(p)
 if p.startswith('plugins/ca-pi/tools/src/') and p.endswith(('.ts','.tsx')):gaps.append(p)
 if p.startswith('plugins/ca-sandbox/tools/') and p.endswith('.ts') and '.test.' not in p and '/__tests__/' not in p and '/test' not in p and '/__fixtures__/' not in p and not p.endswith('vitest.config.ts'):gaps.append(p)
 if p.startswith('site/scripts/') and p.endswith(('.py','.ts','.mjs')) and '.test.' not in p and not Path(p).name.startswith('test-'):gaps.append(p)
 if p.startswith('site/src/components/') and p.endswith('.astro'):gaps.append(p)
 if p.startswith('.github/scripts/') and p.endswith('.py') and not Path(p).name.startswith(('test_','test-')):gaps.append(p)
assert not gaps, gaps
data={
 'overview':'The audit inventories the entire pinned Git tree and reads the primary implementation/workflow owners. Full text, complete executable content, targeted reads, byte-verified shared copies and renderer-verified derivatives are distinguished per file. Historical reports, most tests, fixtures, static assets and external dependency internals are not misrepresented as independently audited current implementations.',
 'commit':tree['sha'],'inventoried_blobs':len(files),'reviewed_unique_files':reviewed,
 'read_counts':dict(counts),'primary_implementation_read_gaps':gaps,
 'equivalence_checks':{'shared_python_copies':279,'rendered_host_surface_files':len(surface_equality),'build_surface_check':'PASS; claude/codex/pi in sync; no source files written'},
 'definition':'A machine is retained lifecycle/operation state, asynchronous ownership, transaction/recovery state, contextual parser state, or a model-guided workflow that changes allowed next events or observable effects. Pure formatting helpers and explicit teaching diagrams are classified under their owner rather than counted as independent product lifecycles. The table covers identified transitions; it is not a formal proof that every possible interleaving or environment failure has been enumerated.',
 'scope_limits':[
  'No installed or distributed package was qualified by this source audit. Tracked bundled JavaScript and native binaries were inventoried; their complete source equivalence was not independently rebuilt here.',
  'Most test files and historical audit/design records were inventoried rather than read in full. Targeted tests and probes are explicitly listed; earlier audits are not treated as current proof.',
  'Imported third-party runtime internals (including host implementations and Astro/Starlight controls) were not inferred or independently audited. Repo-owned integration state is included.',
  'This is only arbiterForge/codeArbiter. Other organization repositories, separate public websites and Academy release artifacts were not audited or changed.',
  'Read-only source inspection plus bounded fixtures; no Go runtime, real Docker/provider farm, real host GUI, remote publication or external issue/Project mutation.'
 ],
 'project_sources':'Operating contract and relevant portfolio/claim policy were inspected. Older portfolio/claim facts were commit-bound context and were not substituted for live GitHub. Proposed deltas are in the report; no Project Sources were edited.',
 'files':[records[p] for p in sorted(records)]}
(W/'coverage.json').write_text(json.dumps(data,indent=2)+'\n')
print(json.dumps({k:v for k,v in data.items() if k in ['inventoried_blobs','reviewed_unique_files','read_counts','primary_implementation_read_gaps']}))
