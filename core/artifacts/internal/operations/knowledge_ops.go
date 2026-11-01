package operations

import (
	"os"
	"sort"
	"strings"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/contextdocument"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

const contextPath = ".codearbiter/CONTEXT.md"
const gitAttributesPath = ".codearbiter/.gitattributes"

var artifactAttributes = []string{"specs/*.html -text", "plans/*.html -text", "context/*.html -text", "decomposition/*.html -text"}

// withArtifactAttributes adds any missing no-conversion line for artifact HTML,
// keeping every existing byte.
func withArtifactAttributes(existing []byte) []byte {
	out := string(existing)
	if out == "" {
		out = "# codeArbiter native artifacts are hash-bound to their exact bytes.\n"
	}
	for _, line := range artifactAttributes {
		present := false
		for _, have := range strings.Split(out, "\n") {
			if strings.TrimSpace(have) == line {
				present = true
			}
		}
		if !present {
			if !strings.HasSuffix(out, "\n") {
				out += "\n"
			}
			out += line + "\n"
		}
	}
	return []byte(out)
}

// knowledgeDocuments are the five narrative documents of a converted
// repository, keyed by slug, with the Markdown file each one replaces.
var knowledgeDocuments = []struct{ slug, title, summary, legacy string }{
	{"project", "Project", "Identity, purpose, users, scope and exclusions.", contextPath},
	{"tech-stack", "Tech stack", "Runtime, frameworks, tooling and declared commands.", ".codearbiter/tech-stack.md"},
	{"coding-standards", "Coding standards", "Structural and style conventions.", ".codearbiter/coding-standards.md"},
	{"security-controls", "Security controls", "Trust boundaries, authentication, secret handling and prohibited primitives. Operative scope blocks stay in security-controls.md.", ".codearbiter/security-controls.md"},
	{"code-map", "Code map", "Observed components, interfaces and ownership.", ".codearbiter/code-map.md"},
}

func knowledgeID(slug string) string { return "CTX-" + strings.ToUpper(slug) }

// knowledgeContext returns the knowledge relevant to explicit paths without a
// plan task. It is a bounded read of stored records only.
func (e *Engine) knowledgeContext(r object, budget int) (any, error) {
	paths := []any{}
	for _, p := range model.Strings(r["paths"]) {
		paths = append(paths, object{"path": p})
	}
	out := e.taskKnowledge(object{"paths": paths}, budget-128)
	out["assessment"] = "advisory"
	out["context_complete"] = false
	return out, nil
}

// knowledgeInitialize records that HTML knowledge is structurally available.
// It verifies the selected work owner and creates a portable project identity
// with the marker for a new native project. It does not require answered
// questions, sources or run commands.
func (e *Engine) knowledgeInitialize(r object) (any, error) {
	before, err := e.FS.Read(contextPath, canonical.MaxBytes)
	if err != nil {
		return nil, fault.New("INVALID_CONTEXT_OUTPUT", "CONTEXT.md is absent or unreadable")
	}
	if canonical.BytesHash(before) != model.S(model.M(r["expected"])[contextPath]) {
		return nil, fault.New("REVISION_CONFLICT", "CONTEXT.md changed after it was inspected")
	}
	if !contextdocument.IsHTMLFormat(before) {
		return nil, fault.New("WRONG_FORMAT", "CONTEXT.md does not select HTML knowledge; use the Markdown finalization")
	}
	entries, unreadable, err := repository.LoadKnowledge(e.FS)
	if err != nil {
		return nil, err
	}
	if len(unreadable) > 0 {
		return nil, fault.At(unreadable[0].Code, "", unreadable[0].Path, "a knowledge document is unreadable; repair it before initializing")
	}
	present := map[string]bool{}
	for _, entry := range entries {
		present[entry.Doc.ID()] = true
	}
	for _, doc := range knowledgeDocuments {
		if !present[knowledgeID(doc.slug)] {
			return nil, fault.At("INVALID_CONTEXT_OUTPUT", knowledgeID(doc.slug), "", "knowledge document is absent; create it, even empty, before initializing")
		}
	}
	projectID, _, err := e.projectIdentity()
	if err != nil {
		return nil, err
	}
	nativeNew := false
	if projectID != "" {
		if err := e.refuseLegacyWorkOwner(); err != nil {
			return nil, err
		}
	} else {
		board, err := e.FS.Read(".codearbiter/open-tasks.md", canonical.MaxBytes)
		if err == nil {
			if err := contextdocument.ValidateBoard(board); err != nil {
				return nil, err
			}
			entries, listErr := e.FS.List(".codearbiter/work")
			if listErr != nil && !os.IsNotExist(listErr) {
				return nil, listErr
			}
			if len(entries) != 0 {
				return nil, fault.At("LEGACY_CONFLICT", "", projectPath, "legacy task board and native work state both exist")
			}
		} else if os.IsNotExist(err) {
			entries, listErr := e.FS.List(".codearbiter/work")
			if listErr != nil && !os.IsNotExist(listErr) {
				return nil, listErr
			}
			if len(entries) != 0 {
				return nil, fault.At("INVALID_PROJECT", "", projectPath, "work files exist without a portable project identity")
			}
			nativeNew = true
		} else {
			return nil, err
		}
	}
	after, err := contextdocument.MarkerInsert(before)
	if err != nil {
		return nil, err
	}
	edits := []store.Edit{{Path: contextPath, Before: before, After: after}}
	result := map[string]any{"target_path": contextPath, "document_sha256": canonical.BytesHash(after), "mode": "knowledge-initialize"}
	if projectID != "" {
		result["project_id"] = projectID
	}
	if nativeNew {
		projectID, err = newOpaqueID("PROJECT-")
		if err != nil {
			return nil, err
		}
		projectAfter, err := canonical.Marshal(object{"format": "codearbiter.project", "version": int64(1), "owner": "native", "project_id": projectID})
		if err != nil {
			return nil, err
		}
		if err := e.FS.Mkdir(".codearbiter/work"); err != nil {
			return nil, err
		}
		edits = append(edits, store.Edit{Path: projectPath, Before: nil, After: projectAfter})
		result["project_id"] = projectID
	}
	o, err := e.FS.Commit(model.S(r["operation_id"]), e.RequestHash, edits, result)
	if err != nil {
		return nil, err
	}
	return mutationResult(o), nil
}

type cutoverPlan struct {
	edits    []store.Edit
	expected map[string]any
	coverage []any
}

// decompositionSources lists the interview and synthesis files the
// decomposition records replace, in a stable order.
func decompositionSources(f *store.FS) ([]string, error) {
	out := []string{}
	files, err := f.List(".codearbiter/plans/decomposition")
	if err != nil && !os.IsNotExist(err) {
		return nil, err
	}
	for _, file := range files {
		if !file.IsDir() && strings.HasSuffix(file.Name(), ".md") {
			out = append(out, ".codearbiter/plans/decomposition/"+file.Name())
		}
	}
	plans, err := f.List(".codearbiter/plans")
	if err != nil && !os.IsNotExist(err) {
		return nil, err
	}
	for _, file := range plans {
		name := file.Name()
		if !file.IsDir() && (strings.HasPrefix(name, "01-architecture-breakdown") || strings.HasPrefix(name, "02-phased-build-plan") || strings.HasPrefix(name, "03-task-backlog")) && strings.HasSuffix(name, ".md") {
			out = append(out, ".codearbiter/plans/"+name)
		}
	}
	sort.Strings(out)
	return out, nil
}

func readOptional(f *store.FS, p string) ([]byte, bool, error) {
	b, err := f.Read(p, canonical.MaxBytes)
	if os.IsNotExist(err) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, err
	}
	return b, true, nil
}

// recordedEntries counts the live records and notes a knowledge document holds.
func recordedEntries(d *model.Document) int {
	n := 0
	normative := model.M(d.Data["normative"])
	for _, collection := range []string{"records", "notes"} {
		for _, v := range model.A(normative[collection]) {
			if model.S(model.M(v)["status"]) != "retired" && model.M(v)["retired"] != true {
				n++
			}
		}
	}
	return n
}

// planCutover checks that the model has recorded the Markdown context as
// knowledge and builds the switch-over edits. It never reads meaning from
// the Markdown: conversion is inference by the agent, through ordinary
// record writes. Nothing is written here.
func (e *Engine) planCutover() (*cutoverPlan, error) {
	ctx, ok, err := readOptional(e.FS, contextPath)
	if err != nil {
		return nil, err
	}
	if !ok {
		return nil, fault.New("NOT_INITIALIZED", "CONTEXT.md is absent; run init first")
	}
	if contextdocument.IsHTMLFormat(ctx) {
		return nil, fault.New("ALREADY_CONVERTED", "CONTEXT.md already selects HTML knowledge")
	}
	converted, bodyStart, err := contextdocument.ConvertedContext(ctx)
	if err != nil {
		return nil, err
	}
	entries, unreadable, err := repository.LoadKnowledge(e.FS)
	if err != nil {
		return nil, err
	}
	if len(unreadable) > 0 {
		return nil, fault.At(unreadable[0].Code, "", unreadable[0].Path, "a knowledge document is unreadable; repair it before the cutover")
	}
	docs := map[string]*model.Document{}
	for _, entry := range entries {
		docs[entry.Doc.ID()] = entry.Doc
	}
	plan := &cutoverPlan{expected: map[string]any{contextPath: canonical.BytesHash(ctx)}, coverage: []any{}}
	for _, doc := range knowledgeDocuments {
		d := docs[knowledgeID(doc.slug)]
		if d == nil {
			return nil, fault.At("NOT_PREPARED", knowledgeID(doc.slug), "", "knowledge document is absent; run knowledge.py convert to create it, then record the Markdown content")
		}
		raw, present, start := ctx, true, bodyStart
		if doc.legacy != contextPath {
			start = 0
			raw, present, err = readOptional(e.FS, doc.legacy)
			if err != nil {
				return nil, err
			}
			plan.expected[doc.legacy] = nil
			if present {
				plan.expected[doc.legacy] = canonical.BytesHash(raw)
			}
		}
		// Report meaningful section coverage; validation uses the section
		// checklist below rather than a coarse record count for the whole file.
		content := false
		if present {
			sections, err := contextdocument.Sections(raw, start, doc.title)
			if err != nil {
				return nil, err
			}
			for _, section := range sections {
				content = content || section.Content
			}
		}
		recorded := recordedEntries(d)
		plan.coverage = append(plan.coverage, object{"source": doc.legacy, "artifact_id": d.ID(), "content": content, "recorded": int64(recorded)})
		switch {
		case doc.legacy == contextPath:
			plan.edits = append(plan.edits, store.Edit{Path: contextPath, Before: ctx, After: converted})
		case !present:
		case doc.slug == "security-controls":
			controls, err := contextdocument.ConfigOnlyControls(raw)
			if err != nil {
				return nil, err
			}
			plan.edits = append(plan.edits, store.Edit{Path: doc.legacy, Before: raw, After: controls})
		default:
			plan.edits = append(plan.edits, store.Edit{Path: doc.legacy, Before: raw})
		}
		prov := ".codearbiter/.provenance/" + map[bool]string{true: "CONTEXT", false: doc.slug}[doc.slug == "project"] + ".json"
		if b, ok, err := readOptional(e.FS, prov); err != nil {
			return nil, err
		} else if ok {
			// Markdown provenance describes files that no longer exist after
			// cutover; its bytes stay in the journal's before-image.
			plan.edits = append(plan.edits, store.Edit{Path: prov, Before: b})
			plan.expected[prov] = canonical.BytesHash(b)
		}
	}
	// Native HTML is bound to its exact bytes; keep Git from converting the
	// line endings of the new pages on a Windows checkout.
	attributes, present, err := readOptional(e.FS, gitAttributesPath)
	if err != nil {
		return nil, err
	}
	if after := withArtifactAttributes(attributes); !present || string(after) != string(attributes) {
		var before []byte
		plan.expected[gitAttributesPath] = nil
		if present {
			before = attributes
			plan.expected[gitAttributesPath] = canonical.BytesHash(attributes)
		}
		plan.edits = append(plan.edits, store.Edit{Path: gitAttributesPath, Before: before, After: after})
	}
	decomp, err := decompositionSources(e.FS)
	if err != nil {
		return nil, err
	}
	interview := false
	for _, p := range decomp {
		b, _, err := readOptional(e.FS, p)
		if err != nil {
			return nil, err
		}
		sections, err := contextdocument.Sections(b, 0, "")
		if err != nil {
			return nil, err
		}
		for _, section := range sections {
			interview = interview || section.Content
		}
		plan.expected[p] = canonical.BytesHash(b)
		plan.edits = append(plan.edits, store.Edit{Path: p, Before: b})
	}
	if len(decomp) > 0 {
		d := docs["DECOMP-PROJECT"]
		recorded := 0
		if d != nil {
			recorded = recordedEntries(d)
		}
		plan.coverage = append(plan.coverage, object{"source": ".codearbiter/plans/", "artifact_id": "DECOMP-PROJECT", "content": interview, "recorded": int64(recorded)})
	}
	if len(plan.edits) > 128 {
		return nil, fault.New("INVALID_TRANSACTION", "cutover exceeds 128 files; record and remove some decomposition sources first")
	}
	return plan, nil
}

// knowledgeCutover switches a Markdown repository to HTML knowledge in one
// journaled transaction, after the agent has recorded the Markdown content.
// Preview writes nothing and returns the input identities; apply requires
// them unchanged, so content edited after the agent read it is never lost.
func (e *Engine) knowledgeCutover(r object) (any, error) {
	if model.S(r["mode"]) == "sections" {
		sources, sections, err := e.sourceSections()
		if err != nil {
			return nil, err
		}
		requestedCursor := model.I(r["cursor"])
		if requestedCursor < 0 || requestedCursor > int64(len(sections)) {
			return nil, fault.New("INVALID_CURSOR", "section cursor is outside the inventory")
		}
		listed := []any{}
		out := object{"mode": "sections", "sources": sources, "sections": listed, "next_cursor": nil}
		for i := range sections {
			if int64(i) < requestedCursor {
				continue
			}
			listed = append(listed, sections[i].view)
			out["sections"] = listed
			out["next_cursor"] = int64(i + 1)
			encoded, err := canonical.Marshal(out)
			if err != nil {
				return nil, err
			}
			if len(encoded) > 60_000 {
				listed = listed[:len(listed)-1]
				if len(listed) == 0 {
					return nil, fault.New("SECTION_PAGE_TOO_LARGE", "one section plus source inventory exceeds the response limit")
				}
				out["sections"] = listed
				out["next_cursor"] = int64(i)
				return out, nil
			}
			if len(listed) == 64 {
				return out, nil
			}
		}
		out["next_cursor"] = nil
		return out, nil
	}
	if replay, err := e.FS.Lookup(model.S(r["operation_id"]), e.RequestHash); err != nil {
		return nil, err
	} else if replay != nil && model.S(r["mode"]) == "apply" {
		return mutationResult(*replay), nil
	}
	plan, err := e.planCutover()
	if err != nil {
		return nil, err
	}
	if model.S(r["mode"]) == "apply" {
		expected := model.M(r["expected"])
		if len(expected) != len(plan.expected) {
			return nil, fault.New("REVISION_CONFLICT", "the Markdown inputs changed after they were read; read them again")
		}
		for p, want := range plan.expected {
			got, ok := expected[p]
			if !ok || (want == nil) != (got == nil) || (want != nil && model.S(got) != want) {
				return nil, fault.At("REVISION_CONFLICT", "", p, "a Markdown input changed after it was read; record the change, then start again")
			}
		}
	}
	sources, sections, err := e.sourceSections()
	if err != nil {
		return nil, err
	}
	for p, hash := range sources {
		if plan.expected[p] != hash {
			return nil, fault.At("REVISION_CONFLICT", "", p, "Markdown changed during section inventory")
		}
	}
	if err := e.validateSectionCoverage(sections, r["coverage"]); err != nil {
		return nil, err
	}
	paths := []any{}
	for _, edit := range plan.edits {
		action := "rewrite"
		if edit.Before == nil {
			action = "create"
		} else if edit.After == nil {
			action = "remove"
		}
		paths = append(paths, object{"path": edit.Path, "action": action})
	}
	if model.S(r["mode"]) == "preview" {
		return object{"mode": "preview", "expected": plan.expected, "sources": sources, "coverage": plan.coverage, "edits": paths,
			"note": "Nothing is written by preview; removed and rewritten originals stay in the transaction before-images."}, nil
	}
	result := map[string]any{"mode": "knowledge-cutover", "edits": paths}
	o, err := e.FS.Commit(model.S(r["operation_id"]), e.RequestHash, plan.edits, result)
	if err != nil {
		return nil, err
	}
	out := mutationResult(o)
	out["coverage"] = plan.coverage
	return out, nil
}
