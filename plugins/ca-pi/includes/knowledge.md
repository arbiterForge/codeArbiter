# Repository context and decomposition

Project context has five logical documents: **project**, **tech-stack**,
**coding-standards**, **security-controls** and **code-map**. Greenfield
decomposition (interview answers, intended architecture, phases and proposed
work) is one more. They are information for judgment, never permission: no
record grants, blocks or approves an action. Real user stops, host
permissions and the commit and release gates apply as before.

## Which format a repository uses

Resolve the interpreter once by presence
(`PY=python3; { command -v python3 >/dev/null 2>&1 && python3 --version >/dev/null 2>&1; } || PY=python`),
then run `"$PY" "<plugin-root>/hooks/knowledge.py" format`. Every
`knowledge.py` verb below uses that same spelling and prints one JSON object.

- **html** (new scaffolds, and repositories converted with `convert`): the five
  documents are native HTML knowledge in `.codearbiter/context/<name>.html` and
  decomposition is `.codearbiter/decomposition/project.html`. Read and change them
  only through `knowledge.py`; never edit the HTML or its embedded JSON by hand.
- **markdown** (an unconverted repository): the documents are
  `.codearbiter/CONTEXT.md`, `.codearbiter/tech-stack.md`,
  `.codearbiter/coding-standards.md`, `.codearbiter/security-controls.md` and
  `.codearbiter/code-map.md`. Read them directly. Before *changing* context in a
  Markdown repository, offer the explicit conversion below; never convert silently.
  A user may keep the Markdown format: its documents, provenance and existing
  owner procedures keep working unchanged.

In both formats `CONTEXT.md` frontmatter owns activation and stage, and the
`<!-- migration-paths -->`, `<!-- ci-paths -->` and `<!-- deploy-paths -->` blocks
in `security-controls.md` stay the operative scope configuration. Knowledge text
never adds, removes or relaxes a control.

## Read only what the work needs

- `knowledge.py relevant <path> [<path> ...]` — records scoped to those paths,
  repository-wide commands, constraints and conventions, and one explicit hop of
  their links. Unrelated records are counted, oversized ones are named for a
  separate read, and a damaged document is reported without hiding the others.
- `knowledge.py read <doc>` lists a document's records; `read <doc> <ID> ...`
  returns exact records. `knowledge.py commands [--purpose test]` lists declared
  commands.
- A plan task's `task-context` packet already includes its relevant knowledge.

For a selected project work item, resolve the installed `hooks/work.py` through
`includes/helper-invocation.md` and read `work.py context <work_id>` once. The
result identifies the selected work and its attached spec/plan, but explicitly
reports `context_complete: false`; it is not a source or check result. If a
plan task is selected, use that plan's `task-context` with its current model
hash: it batches the task, referenced criteria, dependencies and path-scoped
knowledge. For work without a selected plan task, identify the actual source
paths from the work and current repository, then make one `knowledge.py relevant`
call with those paths. Read named omitted or unresolved records by exact ID
when needed. Do not scan every spec or plan to guess a match from a title.
Read existing open questions and relevant ADR headings index-first when a
decision matters; neither work context nor knowledge records replace those
owners. In a Markdown project, use its existing context documents directly.

A missing or unknown fact is a gap to note or ask about when it matters to the
task in hand, not a reason to stop unrelated work.

## Read security policy before a security decision

Every instruction to consult `security-controls.md` for policy uses this format
rule. First inspect `.codearbiter/CONTEXT.md` for `context-format: html` (or run
`knowledge.py format`). In HTML mode, run `knowledge.py read security-controls`
to list the complete document, then read **all** `CTX-SECURITY-CONTROLS` records
and notes by their exact IDs. Do not rely on `knowledge.py relevant` for a full
policy review. Also read the operative migration, CI and deploy scope blocks in
`.codearbiter/security-controls.md` when they apply. In Markdown mode, read the
full `.codearbiter/security-controls.md` directly. A file containing only scope
blocks is not the project's crypto, secret or boundary policy. A reviewer or
gate that requires a policy must stop if the selected document cannot be read
or if its required policy records are absent; do not treat an empty outline as
an approval. Cite the record IDs or Markdown sections in findings.

## Record what is true, with its basis

Each record has a `type` (`fact`, `command`, `constraint`, `convention`,
`component`, `interface`, `dependency`, `observation`, `identity`, `goal`,
`scope`, `exclusion`; decomposition adds `question`, `capability`, `phase`,
`work_item`, `decision`) and a `basis`:

| basis | use for |
|---|---|
| `user-reported` | what the user said or decided |
| `source-observed` | what you read in the repository; cite it in `source_refs` |
| `inferred` | your reasoned conclusion from evidence |
| `proposed` | a suggestion nobody has adopted yet |
| `unknown` | a gap; save it rather than guess |

`knowledge.py add <doc> --record '<json>'` adds one record (an identical record is
reused, so a retry never duplicates). A record needs `type`, `title`, `statement`,
`basis`, `scope` (`{"paths": [...]}`, empty for repository-wide), `related_refs`
and `source_refs`; a `command` record also needs `command` (`argv`, `cwd`,
`purpose`, `run_state`). Add a cited source first with
`add <doc> --collection sources --record '{"title", "type", "url", "locator", "note"}'`
(`type` such as `repository`; `url` may be null). `update <doc> <ID> --fields '<json>'` and
`retire <doc> <ID> --reason '<text>'` change one record; IDs never change. A
source-faithful passage that does not fit a typed record can be saved with
`add <doc> --collection notes --record '{"title", "text", "basis", "origin"}'`;
`origin` is `{"path": ".codearbiter/<source>.md", "start": 0, "end": <byte-end>}`
for the exact source span, or `null` when no source span exists. A note is not
an approval or operative scope rule. A
declared command keeps `run_state: unrun` until a run is actually reported. Never
record secret values. Decomposition owns intended architecture; the code map owns
what the code actually contains; the selected work owner owns task state; ADRs own accepted
decisions.

## Initialize, convert, promote, merge

- Greenfield or brownfield: `knowledge.py create-missing`, add the records you
  have, then `knowledge.py initialize`. Unanswered questions stay `unknown` or
  `open`; initialization needs the documents to exist and parse. A selected
  legacy board is validated; new native enrollment creates its portable project
  ID with the marker. Keep the returned ID in the enrollment commit before
  independent clones create their first work items.
- Markdown to HTML, only when the user chooses it: `knowledge.py convert`
  creates empty HTML documents and returns the Markdown files, their sections,
  and a fingerprint token. Read every section and add its meaning as sourced
  records or notes (up to 32 per `knowledge.py add` call); omit secret values.
  Map each returned section ID to its saved record or note references in a JSON
  checklist, using `[]` only for sections marked `content=false`. Run
  `knowledge.py convert --finish <token> --coverage @checklist.json`. Cutover
  refuses changed inputs, missing sections, and invalid references, then
  switches formats in one recoverable transaction. The journal retains the
  original bytes.
- `knowledge.py promote <WORK-ID>` sends a selected decomposition work item to
  the chosen native or legacy work owner once; a retry finds the same stable
  work ID even after completion or archival. Candidate records are not
  promoted automatically.
- A Git conflict in a knowledge page: `knowledge.py merge-conflict <path>` merges
  record by record and writes only when no record was changed on both sides.
