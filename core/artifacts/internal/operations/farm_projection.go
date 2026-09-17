package operations

import (
	"bytes"
	"net/url"
	"os"
	"path"
	"regexp"
	"strings"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/authority"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/evidence"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/repository"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate"
)

const farmBindingFormat = "codearbiter.farm-binding/0.1.0"
const farmSealFormat = "codearbiter.farm-seal/0.1.0"
const farmMarkerFormat = "codearbiter.farm-marker/0.1.0"

var farmToken = regexp.MustCompile(`^[A-Za-z0-9_./:=+@,-]+$`)
var farmTaskID = regexp.MustCompile(`^[a-z0-9._-]{1,64}$`)
var farmDigest = regexp.MustCompile(`^[0-9a-f]{64}$`)

func farmTarget(p string) bool {
	return validate.Path(p, false) && strings.HasPrefix(p, ".codearbiter/plans/") && strings.HasSuffix(p, ".plan.json") && strings.Count(p, "/") == 2
}

func farmCommand(def object) (string, error) {
	argv := model.Strings(def["argv"])
	if len(argv) == 0 {
		return "", fault.New("FARM_UNSUPPORTED", "farm verification command is empty")
	}
	for _, token := range argv {
		if !farmToken.MatchString(token) {
			return "", fault.New("FARM_UNSUPPORTED", "farm command needs shell-neutral argv tokens")
		}
	}
	command := strings.Join(argv, " ")
	if len(command) > 1024 {
		return "", fault.New("FARM_UNSUPPORTED", "farm command exceeds the runtime limit")
	}
	return command, nil
}

func farmRuntime(v object) error {
	if len(v) != 2 || model.M(v["meta"]) == nil || model.A(v["tasks"]) == nil {
		return fault.New("INVALID_FARM_PROJECTION", "farm plan must contain only meta and tasks")
	}
	meta := model.M(v["meta"])
	if model.S(meta["name"]) == "" || (len(meta) != 1 && len(meta) != 3) {
		return fault.New("INVALID_FARM_PROJECTION", "farm meta must be the canonical name with optional sealed provider enrichment")
	}
	if len(meta) == 3 && (model.S(meta["model"]) == "" || model.S(meta["apiBaseUrl"]) == "") {
		return fault.New("INVALID_FARM_PROJECTION", "farm provider enrichment must contain model and apiBaseUrl together")
	}
	for k := range meta {
		if k != "name" && k != "model" && k != "apiBaseUrl" {
			return fault.New("INVALID_FARM_PROJECTION", "farm meta contains a field outside the minimal projection")
		}
	}
	if len(model.A(v["tasks"])) == 0 || len(model.A(v["tasks"])) > 128 {
		return fault.New("INVALID_FARM_PROJECTION", "farm projection needs 1 to 128 tasks")
	}
	seen := map[string]bool{}
	for _, value := range model.A(v["tasks"]) {
		t := model.M(value)
		id := model.S(t["id"])
		deps, depsOK := t["deps"].([]any)
		paths, pathsOK := t["filesInScope"].([]any)
		if len(t) != 6 || !farmTaskID.MatchString(id) || id == "." || id == ".." || seen[id] || model.S(t["description"]) == "" || !depsOK || !pathsOK || len(paths) == 0 {
			return fault.New("INVALID_FARM_PROJECTION", "farm task identity, description or paths are invalid")
		}
		seen[id] = true
		test, gate := model.M(t["test"]), model.M(t["gate"])
		commands, commandsOK := gate["commands"].([]any)
		if len(test) != 1 || !validate.Path(model.S(test["path"]), false) || len(gate) != 1 || !commandsOK || len(commands) == 0 {
			return fault.New("INVALID_FARM_PROJECTION", "farm test and gate are required closed objects")
		}
		for _, dep := range deps {
			if !farmTaskID.MatchString(model.S(dep)) {
				return fault.New("INVALID_FARM_PROJECTION", "farm dependency is invalid")
			}
		}
		for _, p := range paths {
			if !validate.Path(model.S(p), false) {
				return fault.New("INVALID_FARM_PROJECTION", "farm filesInScope contains an unsafe path")
			}
		}
		for _, command := range commands {
			if model.S(command) == "" || len(model.S(command)) > 1024 {
				return fault.New("INVALID_FARM_PROJECTION", "farm gate contains an invalid command")
			}
		}
	}
	for _, value := range model.A(v["tasks"]) {
		for _, dep := range model.Strings(model.M(value)["deps"]) {
			if !seen[dep] {
				return fault.New("INVALID_FARM_PROJECTION", "farm dependency is outside the projection")
			}
		}
	}
	return nil
}

func farmBase(v object) ([]byte, string, error) {
	base, err := canonical.Clone(v)
	if err != nil {
		return nil, "", err
	}
	meta := model.M(base["meta"])
	delete(meta, "model")
	delete(meta, "apiBaseUrl")
	b, err := canonical.Marshal(base)
	if err != nil {
		return nil, "", err
	}
	return b, canonical.BytesHash(b), nil
}

func stringListEqual(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

func (e *Engine) farmProjectionRows(plan, spec *model.Document, scope string, slice []string, projection object, input string) ([]any, object, error) {
	if len(slice) != len(model.A(projection["tasks"])) {
		return nil, nil, fault.New("INVALID_FARM_PROJECTION", "farm slice and task count disagree")
	}
	inSlice := map[string]string{}
	position := map[string]int{}
	idMapping := object{}
	for index, id := range slice {
		if inSlice[id] != "" {
			return nil, nil, fault.New("INVALID_FARM_PROJECTION", "farm slice repeats a task")
		}
		inSlice[id], position[id] = strings.ToLower(id), index
		idMapping[id] = inSlice[id]
	}
	if err := e.prerequisites(plan); err != nil {
		return nil, nil, err
	}
	if err := e.priorScopes(plan, spec, scope, input); err != nil {
		return nil, nil, err
	}
	rows := []any{}
	for index, id := range slice {
		symbol, ok := plan.Symbols.ByID[id]
		if !ok || symbol.Kind != "tasks" || model.S(symbol.Value["checkpoint"]) != scope {
			return nil, nil, fault.New("INVALID_FARM_PROJECTION", "farm slice task is absent or outside the selected scope")
		}
		if model.S(state(plan, id)["state"]) != "PENDING" {
			return nil, nil, fault.New("NOT_PENDING", "farm slice task requires revalidation/reconciliation rather than dispatch")
		}
		for _, dep := range model.Strings(symbol.Value["depends_on"]) {
			if depPosition, selected := position[dep]; selected {
				if depPosition >= index {
					return nil, nil, fault.New("DEPENDENCY_UNSATISFIED", "farm slice must be in dependency order")
				}
				continue
			}
			depSymbol := plan.Symbols.ByID[dep]
			var err error
			if model.S(depSymbol.Value["checkpoint"]) == scope && model.S(state(plan, dep)["state"]) == "REVIEW" {
				err = evidence.TaskFresh(e.FS, plan, spec, depSymbol.Value, input)
			} else {
				err = evidence.AcceptedFresh(e.FS, plan, spec, dep, input)
			}
			if err != nil {
				return nil, nil, err
			}
		}
		farm := model.M(model.A(projection["tasks"])[index])
		if model.S(farm["id"]) != inSlice[id] || model.S(farm["description"]) != model.S(symbol.Value["title"]) {
			return nil, nil, fault.New("INVALID_FARM_PROJECTION", "farm task identity is not the deterministic source mapping")
		}
		paths := []string{}
		for _, value := range model.A(symbol.Value["paths"]) {
			paths = append(paths, model.S(model.M(value)["path"]))
		}
		if !stringListEqual(model.Strings(farm["filesInScope"]), paths) {
			return nil, nil, fault.New("INVALID_FARM_PROJECTION", "farm filesInScope differs from the canonical task")
		}
		deps := []string{}
		for _, dep := range model.Strings(symbol.Value["depends_on"]) {
			if mapped := inSlice[dep]; mapped != "" {
				deps = append(deps, mapped)
			}
		}
		if !stringListEqual(model.Strings(farm["deps"]), deps) {
			return nil, nil, fault.New("INVALID_FARM_PROJECTION", "farm dependencies differ from the selected slice")
		}
		commands := []string{}
		for _, value := range model.A(symbol.Value["verification"]) {
			command, err := farmCommand(model.M(value))
			if err != nil {
				return nil, nil, err
			}
			commands = append(commands, command)
		}
		if !stringListEqual(model.Strings(model.M(farm["gate"])["commands"]), commands) {
			return nil, nil, fault.New("INVALID_FARM_PROJECTION", "farm gate commands differ from canonical verification")
		}
		testPath := model.S(model.M(farm["test"])["path"])
		found := false
		for _, p := range paths {
			found = found || p == testPath
		}
		if !found {
			return nil, nil, fault.New("INVALID_FARM_PROJECTION", "farm narrow test is not in the canonical task paths")
		}
		definitionHash, _ := canonical.Hash(model.M(model.A(symbol.Value["verification"])[0]))
		rows = append(rows, object{"source_task": id, "farm_task": inSlice[id], "test_path": testPath, "definition_sha256": definitionHash, "command": commands[0]})
	}
	return rows, idMapping, nil
}

func validateFarmAuthorization(receipt *authority.Receipt, plan, spec *model.Document, scope, input, baseHash string, rows []any) error {
	payload := receipt.Payload()
	if len(payload) != 7 || model.S(payload["format"]) != "codearbiter.farm-authorization/0.1.0" || model.S(payload["input_sha256"]) != input || model.S(payload["spec_sha256"]) != spec.NormHash() || model.S(payload["plan_sha256"]) != plan.NormHash() || model.S(payload["scope"]) != scope || model.S(payload["base_sha256"]) != baseHash {
		return fault.New("STALE_EVIDENCE", "farm authorization does not bind the current source and base projection")
	}
	evidenceRows := model.A(payload["red_evidence"])
	if len(evidenceRows) != len(rows) {
		return fault.New("INCOMPLETE_VERIFICATION", "every projected task needs fresh failing-test evidence")
	}
	for i, wantedValue := range rows {
		wanted, got := model.M(wantedValue), model.M(evidenceRows[i])
		exact := []string{"source_task", "farm_task", "test_path", "definition_sha256", "command", "exit", "stdout_sha256", "stderr_sha256"}
		if len(got) != len(exact) {
			return fault.New("STALE_EVIDENCE", "farm red evidence is not a closed record")
		}
		for _, key := range exact {
			if _, present := got[key]; !present {
				return fault.New("STALE_EVIDENCE", "farm red evidence is not a closed record")
			}
		}
		for _, key := range []string{"source_task", "farm_task", "test_path", "definition_sha256", "command"} {
			if model.S(got[key]) != model.S(wanted[key]) {
				return fault.New("STALE_EVIDENCE", "farm red evidence does not match the projection")
			}
		}
		exit, exitOK := got["exit"].(int64)
		if !exitOK || exit < 0 || exit > 255 || exit == model.I(model.M(model.A(plan.Symbols.ByID[model.S(wanted["source_task"])].Value["verification"])[0])["expected_exit"]) || !digestString(model.S(got["stdout_sha256"])) || !digestString(model.S(got["stderr_sha256"])) {
			return fault.New("FAILED_VERIFICATION", "farm narrow test lacks a fresh failing result")
		}
	}
	return nil
}

func digestString(s string) bool {
	return len(s) == 64 && farmDigest.MatchString(s)
}

func (e *Engine) farmProject(r object, entry repository.Entry) (any, error) {
	plan := entry.Doc
	if plan.Kind() != "plan" {
		return nil, fault.New("WRONG_KIND", "farm projection requires an implementation plan")
	}
	target := model.S(r["target"])
	expectedTarget := ".codearbiter/plans/" + model.S(plan.Data["slug"]) + ".plan.json"
	if !farmTarget(target) || target != expectedTarget {
		return nil, fault.New("UNSAFE_PATH", "farm projection target must match the canonical plan slug")
	}
	projection := model.M(r["projection"])
	if err := farmRuntime(projection); err != nil {
		return nil, err
	}
	meta := model.M(projection["meta"])
	if len(meta) != 1 || model.S(meta["name"]) != model.S(plan.Data["slug"]) {
		return nil, fault.New("INVALID_FARM_PROJECTION", "typed base projection may contain only the canonical slug")
	}
	spec, err := e.guards(plan)
	if err != nil {
		return nil, err
	}
	if err = e.prerequisites(plan); err != nil {
		return nil, err
	}
	snap, err := evidence.Snapshot(e.FS, plan)
	if err != nil {
		return nil, err
	}
	input := model.S(snap["sha256"])
	scope := model.S(r["scope"])
	cp, ok := plan.Symbols.ByID[scope]
	if !ok || cp.Kind != "checkpoints" {
		return nil, fault.New("UNKNOWN_SCOPE", "farm scope is absent")
	}
	slice := model.Strings(r["slice"])
	rows, idMapping, err := e.farmProjectionRows(plan, spec, scope, slice, projection, input)
	if err != nil {
		return nil, err
	}
	baseBytes, baseHash, err := farmBase(projection)
	if err != nil {
		return nil, err
	}
	receipt, err := authority.Load(e.FS, model.S(r["receipt"]))
	if err != nil {
		return nil, err
	}
	if err = receipt.Subject(plan, scope, "farm_authorization"); err != nil {
		return nil, err
	}
	if err = validateFarmAuthorization(receipt, plan, spec, scope, input, baseHash, rows); err != nil {
		return nil, err
	}
	projectionBytes := append(baseBytes, '\n')
	binding := object{"format": farmBindingFormat, "projection_path": target, "projection_sha256": canonical.BytesHash(projectionBytes), "base_sha256": baseHash, "plan_id": plan.ID(), "plan_sha256": plan.NormHash(), "spec_id": spec.ID(), "spec_sha256": spec.NormHash(), "input_sha256": input, "scope": scope, "slice": model.List(slice...), "id_mapping": idMapping, "authorization_receipt": receipt.Path, "authorization_sha256": receipt.Hash}
	bindingBytes, err := canonical.Marshal(binding)
	if err != nil {
		return nil, err
	}
	bindingHash := canonical.BytesHash(bindingBytes)
	markerBytes, err := canonical.Marshal(object{"format": farmMarkerFormat, "projection_path": target})
	if err != nil {
		return nil, err
	}
	markerHash := canonical.BytesHash(markerBytes)
	markerPath := authority.Root + "/farm-markers/" + markerHash + ".json"
	out := object{"path": target, "base_sha256": baseHash, "binding": authority.Root + "/farm-bindings/" + bindingHash + ".json", "binding_sha256": bindingHash, "marker": markerPath, "canonical": false, "source_plan": plan.ID()}
	before, readErr := e.FS.Read(target, canonical.MaxBytes)
	if os.IsNotExist(readErr) {
		before = nil
	} else if readErr != nil {
		return nil, readErr
	}
	edits := []store.Edit{{Path: target, Before: before, After: projectionBytes}, {Path: model.S(out["binding"]), After: bindingBytes}}
	markerCurrent, markerErr := e.FS.Read(markerPath, canonical.MaxBytes)
	if os.IsNotExist(markerErr) {
		edits = append(edits, store.Edit{Path: markerPath, After: markerBytes})
	} else if markerErr != nil {
		return nil, markerErr
	} else if !bytes.Equal(markerCurrent, markerBytes) {
		return nil, fault.New("INVALID_OUTPUT", "farm projection marker bytes changed")
	}
	outcome, err := e.FS.Commit(model.S(r["operation_id"]), e.RequestHash, edits, out)
	if err != nil {
		return nil, err
	}
	return mutationResult(outcome), nil
}

type farmDerived struct {
	value object
	path  string
}

func (e *Engine) farmReceipts(kind, format string) ([]farmDerived, error) {
	entries, err := e.FS.List(authority.Root + "/" + kind)
	if os.IsNotExist(err) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	if len(entries) > 1024 {
		return nil, fault.New("MAX_ENTRIES", "too many derived farm receipts")
	}
	out := []farmDerived{}
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".json") {
			return nil, fault.New("INVALID_OUTPUT", "invalid derived farm receipt entry")
		}
		p := authority.Root + "/" + kind + "/" + entry.Name()
		b, readErr := e.FS.Read(p, 1<<20)
		if readErr != nil || canonical.BytesHash(b)+".json" != entry.Name() {
			return nil, fault.New("INVALID_OUTPUT", "derived farm receipt is not content addressed")
		}
		value, parseErr := canonical.Object(b)
		if parseErr != nil || model.S(value["format"]) != format {
			return nil, fault.New("INVALID_OUTPUT", "derived farm receipt is invalid")
		}
		out = append(out, farmDerived{value: value, path: p})
	}
	return out, nil
}

func strictFarmBinding(binding object, projectionPath, baseHash string, baseBytes []byte) error {
	projectionBytes := append(append([]byte{}, baseBytes...), '\n')
	if len(binding) != 14 || model.S(binding["format"]) != farmBindingFormat || model.S(binding["projection_path"]) != projectionPath || model.S(binding["base_sha256"]) != baseHash || model.S(binding["projection_sha256"]) != canonical.BytesHash(projectionBytes) {
		return fault.New("INVALID_OUTPUT", "farm binding is not the closed current format")
	}
	for _, key := range []string{"projection_sha256", "base_sha256", "plan_sha256", "spec_sha256", "input_sha256", "authorization_sha256"} {
		if !digestString(model.S(binding[key])) {
			return fault.New("INVALID_OUTPUT", "farm binding contains an invalid digest")
		}
	}
	if model.S(binding["plan_id"]) == "" || model.S(binding["spec_id"]) == "" || model.S(binding["scope"]) == "" || model.S(binding["authorization_receipt"]) == "" || len(model.Strings(binding["slice"])) == 0 || model.M(binding["id_mapping"]) == nil {
		return fault.New("INVALID_OUTPUT", "farm binding contains an invalid identity field")
	}
	return nil
}

func (e *Engine) validateCurrentFarmBinding(binding object, projectionPath string, projection object, baseBytes []byte, baseHash string) (bool, error) {
	if err := strictFarmBinding(binding, projectionPath, baseHash, baseBytes); err != nil {
		return false, err
	}
	entry, err := e.Catalog.Resolve(model.S(binding["plan_id"]))
	if err != nil {
		return false, err
	}
	plan := entry.Doc
	spec, err := e.guards(plan)
	if err != nil {
		return false, err
	}
	snap, err := evidence.Snapshot(e.FS, plan)
	if err != nil {
		return false, err
	}
	input := model.S(snap["sha256"])
	if model.S(binding["plan_sha256"]) != plan.NormHash() || model.S(binding["spec_id"]) != spec.ID() || model.S(binding["spec_sha256"]) != spec.NormHash() || model.S(binding["input_sha256"]) != input {
		return true, fault.New("STALE_EVIDENCE", "farm binding source identities are stale")
	}
	slice := model.Strings(binding["slice"])
	rows, idMapping, err := e.farmProjectionRows(plan, spec, model.S(binding["scope"]), slice, projection, input)
	if err != nil {
		return false, err
	}
	if got := model.M(binding["id_mapping"]); len(got) != len(idMapping) {
		return false, fault.New("INVALID_OUTPUT", "farm binding ID mapping is incomplete")
	} else {
		for key, wanted := range idMapping {
			if model.S(got[key]) != model.S(wanted) {
				return false, fault.New("INVALID_OUTPUT", "farm binding ID mapping differs from the source slice")
			}
		}
	}
	receipt, err := authority.Load(e.FS, model.S(binding["authorization_receipt"]))
	if err != nil || receipt.Hash != model.S(binding["authorization_sha256"]) {
		return false, fault.New("AUTHORITY_UNVERIFIED", "farm authorization receipt is unavailable or changed")
	}
	if err = receipt.Subject(plan, model.S(binding["scope"]), "farm_authorization"); err != nil {
		return false, err
	}
	if err = validateFarmAuthorization(receipt, plan, spec, model.S(binding["scope"]), input, baseHash, rows); err != nil {
		return false, err
	}
	return false, nil
}

func (e *Engine) currentFarmBinding(projectionPath string, projection object) (object, string, error) {
	baseBytes, baseHash, err := farmBase(projection)
	if err != nil {
		return nil, "", err
	}
	receipts, err := e.farmReceipts("farm-bindings", farmBindingFormat)
	if err != nil {
		return nil, "", err
	}
	valid := []farmDerived{}
	stale := false
	for _, candidate := range receipts {
		if model.S(candidate.value["base_sha256"]) != baseHash || model.S(candidate.value["projection_path"]) != projectionPath {
			continue
		}
		isStale, candidateErr := e.validateCurrentFarmBinding(candidate.value, projectionPath, projection, baseBytes, baseHash)
		if isStale {
			stale = true
			continue
		}
		if candidateErr != nil {
			return nil, "", candidateErr
		}
		valid = append(valid, candidate)
	}
	if len(valid) > 0 {
		// Fully validated current bindings differ only by their immutable
		// authorization receipt. Reauthorization of unchanged source is safe and
		// must be replayable; choose the content-addressed path deterministically.
		for i := 1; i < len(valid); i++ {
			if valid[i].path < valid[0].path {
				valid[0], valid[i] = valid[i], valid[0]
			}
		}
		return valid[0].value, valid[0].path, nil
	}
	if stale {
		return nil, "", fault.New("STALE_EVIDENCE", "farm binding source identities are stale")
	}
	return nil, "", nil
}

func (e *Engine) hasFarmMarker(projectionPath string) (bool, error) {
	receipts, err := e.farmReceipts("farm-markers", farmMarkerFormat)
	if err != nil {
		return false, err
	}
	matched := false
	for _, candidate := range receipts {
		if len(candidate.value) != 2 || model.S(candidate.value["format"]) != farmMarkerFormat || !farmTarget(model.S(candidate.value["projection_path"])) {
			return false, fault.New("INVALID_OUTPUT", "farm marker is not the closed current format")
		}
		matched = matched || model.S(candidate.value["projection_path"]) == projectionPath
	}
	return matched, nil
}

func (e *Engine) loadFarm(pathname string) ([]byte, object, error) {
	if !farmTarget(pathname) {
		return nil, nil, fault.New("UNSAFE_PATH", "farm projection path is outside the canonical plan directory")
	}
	b, err := e.FS.Read(pathname, 8<<20)
	if err != nil {
		return nil, nil, err
	}
	value, err := canonical.Object(bytes.TrimSpace(b))
	if err != nil {
		return nil, nil, err
	}
	if err = farmRuntime(value); err != nil {
		return nil, nil, err
	}
	canonicalBytes, err := canonical.Marshal(value)
	if err != nil || !bytes.Equal(b, append(canonicalBytes, '\n')) {
		return nil, nil, fault.New("INVALID_FARM_PROJECTION", "farm projection bytes must use the canonical engine encoding")
	}
	return b, value, nil
}

func (e *Engine) farmSeal(r object) (any, error) {
	projectionPath := model.S(r["projection_path"])
	bytesValue, projection, err := e.loadFarm(projectionPath)
	if err != nil {
		return nil, err
	}
	binding, bindingPath, err := e.currentFarmBinding(projectionPath, projection)
	if err != nil {
		return nil, err
	}
	if binding == nil {
		return nil, fault.New("FARM_BINDING_MISSING", "typed farm projection has no current base binding")
	}
	meta, provenance := model.M(projection["meta"]), model.M(r["provenance"])
	if model.S(meta["model"]) == "" || model.S(meta["apiBaseUrl"]) == "" || model.S(meta["model"]) != model.S(provenance["model"]) || model.S(meta["apiBaseUrl"]) != model.S(provenance["api_base_url"]) {
		return nil, fault.New("INVALID_FARM_ENRICHMENT", "projection enrichment and provider provenance disagree")
	}
	parsed, parseErr := url.Parse(model.S(meta["apiBaseUrl"]))
	if parseErr != nil || (parsed.Scheme != "https" && !(parsed.Scheme == "http" && (parsed.Hostname() == "127.0.0.1" || parsed.Hostname() == "localhost"))) || parsed.User != nil {
		return nil, fault.New("INVALID_FARM_ENRICHMENT", "farm apiBaseUrl must use HTTPS or bare loopback HTTP")
	}
	fullHash := canonical.BytesHash(bytesValue)
	seal := object{"format": farmSealFormat, "projection_path": projectionPath, "projection_sha256": fullHash, "binding": bindingPath, "binding_sha256": path.Base(strings.TrimSuffix(bindingPath, ".json")), "model": provenance["model"], "api_base_url": provenance["api_base_url"], "selection_source": provenance["selection_source"], "origin": provenance["origin"]}
	sealBytes, err := canonical.Marshal(seal)
	if err != nil {
		return nil, err
	}
	sealHash := canonical.BytesHash(sealBytes)
	if err = e.FS.PutDerived("farm-seals", sealHash, sealBytes); err != nil {
		return nil, err
	}
	return object{"seal": authority.Root + "/farm-seals/" + sealHash + ".json", "seal_sha256": sealHash, "projection_sha256": fullHash, "binding_sha256": seal["binding_sha256"]}, nil
}

func strictFarmSeal(seal object) error {
	if len(seal) != 9 || model.S(seal["format"]) != farmSealFormat || !farmTarget(model.S(seal["projection_path"])) || !digestString(model.S(seal["projection_sha256"])) || !digestString(model.S(seal["binding_sha256"])) || model.S(seal["binding"]) != authority.Root+"/farm-bindings/"+model.S(seal["binding_sha256"])+".json" || model.S(seal["model"]) == "" || model.S(seal["api_base_url"]) == "" || model.S(seal["origin"]) == "" {
		return fault.New("INVALID_OUTPUT", "farm seal is not the closed current format")
	}
	switch model.S(seal["selection_source"]) {
	case "canary", "cache", "websearch", "environment", "manual":
	default:
		return fault.New("INVALID_OUTPUT", "farm seal has an invalid selection source")
	}
	return nil
}

func (e *Engine) currentFarmSeal(fullHash, bindingPath, modelName, apiBase string) (object, string, error) {
	receipts, err := e.farmReceipts("farm-seals", farmSealFormat)
	if err != nil {
		return nil, "", err
	}
	valid := []farmDerived{}
	for _, candidate := range receipts {
		if model.S(candidate.value["projection_sha256"]) != fullHash || model.S(candidate.value["binding"]) != bindingPath || model.S(candidate.value["model"]) != modelName || model.S(candidate.value["api_base_url"]) != apiBase {
			continue
		}
		if err = strictFarmSeal(candidate.value); err != nil {
			return nil, "", err
		}
		valid = append(valid, candidate)
	}
	if len(valid) > 1 {
		return nil, "", fault.New("AMBIGUOUS_EVIDENCE", "multiple farm seals match the execution bytes and provider")
	}
	if len(valid) == 1 {
		return valid[0].value, valid[0].path, nil
	}
	return nil, "", nil
}

func (e *Engine) farmVerify(r object) (any, error) {
	projectionPath := model.S(r["projection_path"])
	bytesValue, projection, err := e.loadFarm(projectionPath)
	if err != nil {
		return nil, err
	}
	binding, bindingPath, err := e.currentFarmBinding(projectionPath, projection)
	if err != nil {
		return nil, err
	}
	if binding == nil {
		marked, markerErr := e.hasFarmMarker(projectionPath)
		if markerErr != nil {
			return nil, markerErr
		}
		if marked {
			return nil, fault.New("FARM_BINDING_MISSING", "typed farm projection has lost its current source binding")
		}
		html := strings.TrimSuffix(projectionPath, ".plan.json") + ".html"
		if _, statErr := e.FS.Stat(html); statErr == nil {
			return nil, fault.New("FARM_BINDING_MISSING", "HTML farm projection has no current base binding")
		} else if !os.IsNotExist(statErr) {
			return nil, statErr
		}
		return object{"typed": false, "phase": r["phase"], "legacy_unchanged": true}, nil
	}
	if model.S(r["phase"]) == "canary" {
		if len(model.M(projection["meta"])) != 1 || canonical.BytesHash(bytesValue) != model.S(binding["projection_sha256"]) {
			return nil, fault.New("STALE_EVIDENCE", "canary requires the exact un-enriched base projection bytes")
		}
		return object{"typed": true, "phase": "canary", "binding": bindingPath, "base_sha256": binding["base_sha256"], "projection_sha256": canonical.BytesHash(bytesValue)}, nil
	}
	modelName, apiBase := model.S(r["effective_model"]), model.S(r["effective_api_base_url"])
	if modelName == "" || apiBase == "" {
		return nil, fault.New("FARM_SEAL_MISSING", "dispatch verification requires effective provider identity")
	}
	fullHash := canonical.BytesHash(bytesValue)
	seal, sealPath, err := e.currentFarmSeal(fullHash, bindingPath, modelName, apiBase)
	if err != nil {
		return nil, err
	}
	if seal == nil {
		return nil, fault.New("FARM_SEAL_MISSING", "exact execution bytes and effective provider are not sealed")
	}
	return object{"typed": true, "phase": "dispatch", "binding": bindingPath, "seal": sealPath, "projection_sha256": fullHash}, nil
}
