package evidence

import (
	"encoding/base64"
	"path/filepath"
	"runtime"
	"sort"
	"strings"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/authority"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/observation"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/schema"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

const MaxCompletionMaterial = 64 << 10
const MaxCompletionMaterials = 256 << 10

func equalCompletion(a, b any) bool {
	x, ex := canonical.Hash(a)
	y, ey := canonical.Hash(b)
	return ex == nil && ey == nil && x == y
}

func completionMaterialKey(path string) string {
	if runtime.GOOS == "windows" {
		return strings.ToLower(path)
	}
	return path
}

func completionMaterial(path string) (map[string]any, error) {
	if !filepath.IsAbs(path) || filepath.Clean(path) != path {
		return nil, fault.New("UNSAFE_COMPLETION_MATERIAL", "supporting evidence must name an absolute regular file without indirection")
	}
	parts := strings.Split(filepath.ToSlash(path), "/")
	for i, part := range parts {
		if strings.EqualFold(part, ".codearbiter") && i+1 < len(parts) {
			section := strings.ToLower(parts[i+1])
			if section == ".artifacts" || (section == "specs" || section == "plans") && i+3 == len(parts) && strings.EqualFold(filepath.Ext(path), ".html") {
				return nil, fault.New("UNSAFE_COMPLETION_MATERIAL", "canonical artifacts and authority evidence must use their native API references")
			}
		}
	}
	b, err := CompletionReadFile(path, MaxCompletionMaterial)
	if err != nil {
		return nil, err
	}
	return map[string]any{"source_path": path, "sha256": canonical.BytesHash(b), "size_bytes": int64(len(b)), "content_base64": base64.StdEncoding.EncodeToString(b)}, nil
}

func completionIDs(context map[string]any) []string {
	if model.S(context["activity"]) == "spec_review" {
		return []string{model.S(model.M(context["task"])["id"])}
	}
	ids := []string{}
	for _, v := range model.A(context["tasks"]) {
		ids = append(ids, model.S(model.M(v)["id"]))
	}
	sort.Strings(ids)
	return ids
}

func selectedVerification(f *store.FS, plan, spec *model.Document, ref, input string) (map[string]any, error) {
	r, err := authority.Load(f, ref)
	if err != nil {
		return nil, err
	}
	id := model.S(model.M(r.Data["subject"])["record_id"])
	task, ok := plan.Symbols.ByID[id]
	if !ok || task.Kind != "tasks" || task.Retired || model.S(r.Data["kind"]) != "verification" {
		return nil, fault.New("INVALID_COMPLETION_SELECTION", "selected receipt is not a current task verification")
	}
	if err = TaskPayload(r, plan, spec, task.Value, input); err != nil {
		return nil, err
	}
	obs, _, err := observation.Load(f, model.S(r.Event["observation_ref"]), model.S(r.Event["observation_sha256"]))
	if err != nil {
		return nil, err
	}
	if model.S(obs["producer_profile"]) != observation.QualifiedCommandProfile {
		return nil, fault.New("UNQUALIFIED_COMPLETION_VERIFICATION", "completion review requires a current qualified verifier observation")
	}
	producer := model.M(obs["producer_result"])
	return map[string]any{
		"task_id": id, "receipt_ref": r.Path, "receipt_sha256": r.Hash, "event_ref": r.EventPath, "event_sha256": r.Data["event_sha256"],
		"source_ref": r.Data["authority_source_ref"], "source_sha256": r.Data["authority_source_sha256"],
		"observation_ref": r.Event["observation_ref"], "observation_sha256": r.Event["observation_sha256"],
		"context_ref": obs["context_ref"], "context_sha256": obs["context_sha256"],
		"command_bindings": producer["command_bindings"], "workspace_after": producer["workspace_after"],
	}, nil
}

// ReviewContext follows the retained native receipt chain, never a caller's
// packet. A definition-only review has no completion evidence retroactively.
func ReviewContext(f *store.FS, r *authority.Receipt) (map[string]any, error) {
	obs, _, err := observation.Load(f, model.S(r.Event["observation_ref"]), model.S(r.Event["observation_sha256"]))
	if err != nil {
		return nil, err
	}
	c, _, err := observation.LoadContext(f, model.S(obs["context_ref"]), model.S(obs["context_sha256"]))
	return c, err
}

// LatestTaskCompletion preserves a task's explicit completion contract. An
// ordinary or stale receipt cannot silently downgrade it on a later consume.
func LatestTaskCompletion(f *store.FS, plan *model.Document, id string) (*authority.Receipt, error) {
	state := model.M(model.M(model.M(plan.Data["execution"])["tasks"])[id])
	refs := model.Strings(state["evidence_refs"])
	if state["completion_review_receipt"] != nil || state["completion_sha256"] != nil {
		ref, expected := model.S(state["completion_review_receipt"]), model.S(state["completion_sha256"])
		if ref == "" || expected == "" {
			return nil, fault.New("COMPLETION_REQUIRED", "task completion selection is incomplete")
		}
		retained := false
		for _, value := range refs {
			if value == ref {
				retained = true
			}
		}
		if !retained {
			return nil, fault.New("COMPLETION_REQUIRED", "selected completion receipt is not retained in task evidence")
		}
		r, err := authority.Load(f, ref)
		if err != nil {
			return nil, err
		}
		if model.S(r.Data["kind"]) != "spec_review" || model.S(r.Payload()["completion_sha256"]) != expected {
			return nil, fault.New("COMPLETION_REQUIRED", "selected completion receipt does not match its durable identity")
		}
		return r, nil
	}
	for i := len(refs) - 1; i >= 0; i-- {
		r, err := authority.Load(f, refs[i])
		if err != nil {
			return nil, err
		}
		if model.S(r.Data["kind"]) == "spec_review" && r.Payload()["completion_sha256"] != nil {
			return r, nil
		}
	}
	return nil, nil
}

func completedRow(context map[string]any, id string) map[string]any {
	for _, v := range model.A(model.M(context["completion"])["verifications"]) {
		row := model.M(v)
		if model.S(row["task_id"]) == id {
			return row
		}
	}
	return nil
}

// BuildCompletion performs the initial exact raw-verifier proof. Previously
// published completion packets permit schema-validated artifact progress to
// change; their current normalized closure must still match exactly.
func BuildCompletion(f *store.FS, plan, spec *model.Document, context, selection map[string]any) (map[string]any, error) {
	if model.S(context["activity"]) != "spec_review" && model.S(context["activity"]) != "quality_review" {
		return nil, fault.New("INVALID_COMPLETION_SELECTION", "completion evidence applies only to reviews")
	}
	ids := completionIDs(context)
	wanted, seen := map[string]bool{}, map[string]bool{}
	for _, id := range ids {
		wanted[id] = true
	}
	rows := []any{}
	priorMaterials := map[string]any{}
	for _, ref := range model.Strings(selection["verification_receipts"]) {
		row, err := selectedVerification(f, plan, spec, ref, model.S(context["input_sha256"]))
		if err != nil {
			return nil, err
		}
		id := model.S(row["task_id"])
		if !wanted[id] || seen[id] {
			return nil, fault.New("INVALID_COMPLETION_SELECTION", "each intended task needs exactly one selected verification")
		}
		seen[id] = true
		prior, err := LatestTaskCompletion(f, plan, id)
		if err != nil {
			return nil, err
		}
		var previous map[string]any
		if prior != nil {
			previous, err = ReviewContext(f, prior)
			if err != nil {
				return nil, err
			}
		}
		oldRow := completedRow(previous, id)
		if model.S(context["activity"]) == "quality_review" && (oldRow == nil || oldRow["receipt_ref"] != ref) {
			return nil, fault.New("COMPLETION_REQUIRED", "quality completion must preserve the exact verifier selected by each task completion review")
		}
		if oldRow != nil && oldRow["receipt_ref"] == ref {
			if err = TaskPayload(prior, plan, spec, plan.Symbols.ByID[id].Value, model.S(context["input_sha256"])); err != nil {
				return nil, err
			}
			if err = ValidateCompletion(f, plan, spec, previous); err != nil {
				return nil, err
			}
			row["consumer_workspace_after"] = oldRow["consumer_workspace_after"]
			for _, v := range model.A(model.M(previous["completion"])["materials"]) {
				m := model.M(v)
				priorMaterials[model.S(m["source_path"])] = m
			}
		} else {
			raw, err := CompletionWorkspaces(f, model.A(row["command_bindings"]), false)
			if err != nil {
				return nil, err
			}
			if !equalCompletion(raw, row["workspace_after"]) {
				return nil, fault.New("WORKSPACE_DRIFT", "selected verification worktree bytes or identity changed")
			}
			normalized, err := CompletionWorkspaces(f, model.A(row["command_bindings"]), true)
			if err != nil {
				return nil, err
			}
			row["consumer_workspace_after"] = normalized
		}
		rows = append(rows, row)
	}
	if len(seen) != len(wanted) {
		return nil, fault.New("INVALID_COMPLETION_SELECTION", "completion selection must cover every intended task")
	}
	sort.Slice(rows, func(i, j int) bool {
		return model.S(model.M(rows[i])["task_id"]) < model.S(model.M(rows[j])["task_id"])
	})
	materials, paths, total := []any{}, map[string]bool{}, int64(0)
	for _, path := range model.Strings(selection["supporting_files"]) {
		if paths[completionMaterialKey(path)] {
			return nil, fault.New("INVALID_COMPLETION_SELECTION", "duplicate supporting evidence source")
		}
		paths[completionMaterialKey(path)] = true
		material, err := completionMaterial(path)
		if err != nil {
			return nil, err
		}
		total += model.I(material["size_bytes"])
		if total > MaxCompletionMaterials {
			return nil, fault.New("MAX_BYTES", "completion supporting evidence exceeds 256 KiB")
		}
		if old := priorMaterials[path]; old != nil && !equalCompletion(old, material) {
			return nil, fault.New("STALE_EVIDENCE", "scope completion changed selected task supporting material")
		}
		delete(priorMaterials, path)
		materials = append(materials, material)
	}
	if model.S(context["activity"]) == "quality_review" && len(priorMaterials) != 0 {
		return nil, fault.New("COMPLETION_REQUIRED", "scope completion must retain every task completion supporting material")
	}
	sort.Slice(materials, func(i, j int) bool {
		return model.S(model.M(materials[i])["source_path"]) < model.S(model.M(materials[j])["source_path"])
	})
	packet := map[string]any{"format": "codearbiter.completion-evidence/0.1.0", "verifications": rows, "materials": materials}
	if es := schema.ValidateWith(observation.CompletionSchema(), packet); len(es) > 0 {
		return nil, &es[0]
	}
	return packet, nil
}

// ValidateCompletion rechecks the immutable verifier chain, exact selected
// source bytes, and normalized mapped worktree closure at capture and consume.
func ValidateCompletion(f *store.FS, plan, spec *model.Document, context map[string]any) error {
	packet := model.M(context["completion"])
	if packet == nil {
		return fault.New("COMPLETION_REQUIRED", "review has no selected completed evidence")
	}
	h, err := canonical.Hash(packet)
	if err != nil || h != model.S(context["completion_sha256"]) {
		return fault.New("STALE_EVIDENCE", "completion packet digest does not match")
	}
	if es := schema.ValidateWith(observation.CompletionSchema(), packet); len(es) > 0 {
		return &es[0]
	}
	wanted := map[string]bool{}
	for _, id := range completionIDs(context) {
		wanted[id] = true
	}
	for _, value := range model.A(packet["verifications"]) {
		row := model.M(value)
		id := model.S(row["task_id"])
		if !wanted[id] {
			return fault.New("INVALID_COMPLETION_SELECTION", "completion task selection is duplicate or foreign")
		}
		delete(wanted, id)
		fresh, err := selectedVerification(f, plan, spec, model.S(row["receipt_ref"]), model.S(context["input_sha256"]))
		if err != nil {
			return err
		}
		closure, err := CompletionWorkspaces(f, model.A(fresh["command_bindings"]), true)
		if err != nil {
			return err
		}
		fresh["consumer_workspace_after"] = closure
		if !equalCompletion(fresh, row) {
			return fault.New("WORKSPACE_DRIFT", "completed review selected verification or mapped worktree changed")
		}
	}
	if len(wanted) > 0 {
		return fault.New("INVALID_COMPLETION_SELECTION", "completion selection does not cover its tasks")
	}
	paths, total := map[string]bool{}, int64(0)
	for _, value := range model.A(packet["materials"]) {
		row := model.M(value)
		path := model.S(row["source_path"])
		if paths[completionMaterialKey(path)] {
			return fault.New("INVALID_COMPLETION_SELECTION", "duplicate supporting evidence")
		}
		paths[completionMaterialKey(path)] = true
		fresh, err := completionMaterial(path)
		if err != nil {
			return err
		}
		if !equalCompletion(fresh, row) {
			return fault.New("STALE_EVIDENCE", "selected supporting evidence changed")
		}
		total += model.I(row["size_bytes"])
		if total > MaxCompletionMaterials {
			return fault.New("MAX_BYTES", "completion supporting evidence exceeds 256 KiB")
		}
	}
	if model.S(context["activity"]) == "quality_review" {
		return qualityCompletionSelection(f, plan, model.S(model.M(context["subject"])["record_id"]), context)
	}
	return nil
}

func CompletionReview(f *store.FS, r *authority.Receipt, plan, spec *model.Document, expected, verification string) error {
	h := model.S(r.Payload()["completion_sha256"])
	if expected != "" && h != expected {
		return fault.New("COMPLETION_REQUIRED", "review does not bind the explicitly selected completed evidence")
	}
	if h == "" {
		return nil
	}
	c, err := ReviewContext(f, r)
	if err != nil {
		return err
	}
	if model.S(c["completion_sha256"]) != h {
		return fault.New("COMPLETION_REQUIRED", "review payload completion identity differs from its context")
	}
	if verification != "" {
		rows := model.A(model.M(c["completion"])["verifications"])
		if len(rows) != 1 || model.S(model.M(rows[0])["receipt_ref"]) != verification {
			return fault.New("COMPLETION_REQUIRED", "task review must use its exact selected verification receipt")
		}
	}
	return ValidateCompletion(f, plan, spec, c)
}

func QualityCompletion(f *store.FS, r *authority.Receipt, plan, spec *model.Document, scope, expected string) error {
	if err := CompletionReview(f, r, plan, spec, expected, ""); err != nil {
		return err
	}
	c, err := ReviewContext(f, r)
	if err != nil {
		return err
	}
	return qualityCompletionSelection(f, plan, scope, c)
}

func qualityCompletionSelection(f *store.FS, plan *model.Document, scope string, c map[string]any) error {
	for _, id := range model.Strings(plan.Symbols.ByID[scope].Value["tasks"]) {
		prior, err := LatestTaskCompletion(f, plan, id)
		if err != nil {
			return err
		}
		if prior == nil {
			if c["completion"] != nil {
				return fault.New("COMPLETION_REQUIRED", "scope completion requires completion review for every task")
			}
			continue
		}
		if c["completion"] == nil {
			return fault.New("COMPLETION_REQUIRED", "scope review cannot downgrade completed task evidence")
		}
		previous, err := ReviewContext(f, prior)
		if err != nil {
			return err
		}
		if !equalCompletion(completedRow(previous, id), completedRow(c, id)) {
			return fault.New("COMPLETION_REQUIRED", "scope review substituted its task completion verification")
		}
		selected := map[string]any{}
		for _, m := range model.A(model.M(c["completion"])["materials"]) {
			row := model.M(m)
			selected[model.S(row["source_path"])] = row
		}
		for _, m := range model.A(model.M(previous["completion"])["materials"]) {
			row := model.M(m)
			if !equalCompletion(row, selected[model.S(row["source_path"])]) {
				return fault.New("COMPLETION_REQUIRED", "scope review omitted task supporting evidence")
			}
		}
	}
	return nil
}
