# Product tour evidence

The saved-search example separates three kinds of evidence:

- `saved-searches/spec.request.json` and `plan.request.json` define documentation drafts.
  The latter is a generation template: the script fills its source binding from the created spec.
- `public/examples/saved-searches/{specs,plans}/saved-searches.html` are actual native engine output.
  Do not edit their HTML or embedded models. Their capture manifest pins whole-file digests.
- The baseline and completed Python implementations are deliberately different fixture inputs.
  The captured tests demonstrate the bounded serializer, not a host workflow, approval or PR.

`python site/scripts/generate-product-example.py --engine <reviewed-native-executable>` regenerates
only in temporary repositories. It refuses a binary that differs from the recorded hosted build.
To update that build, review its source tree and provenance and intentionally update the pin;
this documentation helper must never become the installed product's binary-resolution mechanism.
The script invokes create, identity, validate and eligible. It never invokes approve, capture,
accept-scope, a model provider, or a product commit/release lane.

`python site/scripts/capture-statusline-themes.py` calls the existing statusline renderer with
isolated mocked project/session/accounting reads. It emits ANSI capture data for five actual
palettes, not live usage. The site decodes a bounded SGR subset into escaped text spans.

The greenfield Markdown documents are authored examples, not generated interview evidence. They
intentionally expose unresolved questions and must not be presented as approved initialization.
The host panels are syntax explanations, not fabricated terminal captures. Product-tour controls
only select visible content; they do not store learner progress or perform project actions.

Rollback removes the new showcase links/components or reverts the documentation commit. It does
not migrate project state, modify Academy fixtures or change an adapter package.
