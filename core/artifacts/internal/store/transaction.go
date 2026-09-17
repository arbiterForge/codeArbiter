package store

import (
	"bytes"
	"fmt"
	"os"
	"path"
	"regexp"
	"strings"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/validate"
)

const meta = ".codearbiter/.artifacts"

var opPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_-]{7,79}$`)

func derivedTransactionTarget(p string, beforeHash, afterHash any, size int64) bool {
	prefix := meta + "/farm-bindings/"
	if strings.HasPrefix(p, meta+"/farm-markers/") {
		prefix = meta + "/farm-markers/"
	}
	if !strings.HasPrefix(p, prefix) || strings.Contains(strings.TrimPrefix(p, prefix), "/") || beforeHash != nil || size <= 0 || size > canonical.MaxBytes {
		return false
	}
	name := strings.TrimSuffix(strings.TrimPrefix(p, prefix), ".json")
	return strings.HasSuffix(p, ".json") && digest(name) && model.S(afterHash) == name
}

type Edit struct {
	Path          string
	Before, After []byte
}
type Outcome struct {
	OperationID string         `json:"operation_id"`
	State       string         `json:"state"`
	Replay      bool           `json:"replay"`
	Paths       []string       `json:"paths"`
	Result      map[string]any `json:"-"`
}

func hash(b []byte) any {
	if b == nil {
		return nil
	}
	return canonical.BytesHash(b)
}
func journalPath(id string) string { return meta + "/transactions/" + id + ".json" }
func (f *FS) step(s string) error {
	if f.Inject != nil {
		return f.Inject(s)
	}
	return nil
}
func (f *FS) journal(id string) (map[string]any, error) {
	if !opPattern.MatchString(id) {
		return nil, fault.New("INVALID_OPERATION_ID", "operation ID must be 8..80 safe characters")
	}
	b, e := f.Read(journalPath(id), 4<<20)
	if e != nil {
		return nil, e
	}
	j, e := canonical.Object(b)
	if e != nil {
		return nil, e
	}
	if e = validJournal(id, j); e != nil {
		return nil, e
	}
	return j, nil
}
func validJournal(id string, j map[string]any) error {
	bad := func() error {
		return fault.New("CORRUPT_JOURNAL", "journal is malformed; preserve bytes and reconcile manually")
	}
	format := model.S(j["format"])
	if !((format == "codearbiter.transaction/0.1.0" && len(j) == 5) || (format == "codearbiter.transaction/0.2.0" && len(j) == 6)) {
		return bad()
	}
	if format == "codearbiter.transaction/0.2.0" {
		if _, present := j["result"]; !present {
			return bad()
		}
		if j["result"] != nil && model.M(j["result"]) == nil {
			return bad()
		}
		data, err := canonical.Marshal(j["result"])
		if err != nil || len(data) > 60000 {
			return bad()
		}
	}
	if model.S(j["operation_id"]) != id || !regexp.MustCompile(`^[0-9a-f]{64}$`).MatchString(model.S(j["request_sha256"])) {
		return bad()
	}
	state := model.S(j["state"])
	if state != "prepared" && state != "committed" && state != "rolled_back" {
		return bad()
	}
	entries := model.A(j["entries"])
	if len(entries) < 1 || len(entries) > 128 {
		return bad()
	}
	seen := map[string]bool{}
	for i, v := range entries {
		r := model.M(v)
		p := model.S(r["path"])
		if len(r) != 6 || !validate.Path(p, false) || seen[p] || (strings.HasPrefix(p, meta+"/") && !derivedTransactionTarget(p, r["before_sha256"], r["after_sha256"], model.I(r["size"]))) {
			return bad()
		}
		seen[p] = true
		expected := path.Join(path.Dir(p), fmt.Sprintf(".ca-artifact-%s-%d.new", id, i))
		if model.S(r["stage"]) != expected || model.S(r["backup"]) != fmt.Sprintf("%s/history/%s-%d.before", meta, id, i) {
			return bad()
		}
		for _, k := range []string{"before_sha256", "after_sha256"} {
			if r[k] != nil && !regexp.MustCompile(`^[0-9a-f]{64}$`).MatchString(model.S(r[k])) {
				return bad()
			}
		}
		if r["before_sha256"] == nil && r["after_sha256"] == nil {
			return bad()
		}
		if model.I(r["size"]) < 0 || model.I(r["size"]) > canonical.MaxBytes {
			return bad()
		}
	}
	return nil
}
func outcome(j map[string]any, replay bool) Outcome {
	o := Outcome{OperationID: model.S(j["operation_id"]), State: model.S(j["state"]), Replay: replay, Paths: []string{}, Result: model.M(j["result"])}
	for _, v := range model.A(j["entries"]) {
		o.Paths = append(o.Paths, model.S(model.M(v)["path"]))
	}
	return o
}
func (f *FS) Lookup(id, requestHash string) (*Outcome, error) {
	j, e := f.journal(id)
	if os.IsNotExist(e) {
		return nil, nil
	}
	if e != nil {
		return nil, e
	}
	if model.S(j["request_sha256"]) != requestHash {
		return nil, fault.New("OPERATION_ID_REUSE", "operation ID was used for different input")
	}
	if model.S(j["state"]) == "prepared" {
		return nil, &fault.Error{Code: "RECOVERY_REQUIRED", Message: "operation has a durable journal; explicitly recover it", OperationID: id}
	}
	if model.S(j["state"]) == "rolled_back" {
		return nil, &fault.Error{Code: "OPERATION_ROLLED_BACK", Message: "this operation was rolled back; inspect current state and use a new operation ID for a new write", OperationID: id}
	}
	o := outcome(j, true)
	return &o, nil
}
func (f *FS) Pending() ([]string, error) {
	names, e := f.List(meta + "/transactions")
	if os.IsNotExist(e) {
		return []string{}, nil
	}
	if e != nil {
		return nil, e
	}
	out := []string{}
	for _, n := range names {
		if n.IsDir() {
			return nil, fault.New("CORRUPT_JOURNAL", "unexpected transaction subdirectory")
		}
		if strings.HasSuffix(n.Name(), ".next") {
			continue
		}
		if !strings.HasSuffix(n.Name(), ".json") {
			return nil, fault.New("CORRUPT_JOURNAL", "unexpected transaction file")
		}
		id := strings.TrimSuffix(n.Name(), ".json")
		j, e := f.journal(id)
		if e != nil {
			return nil, e
		}
		if model.S(j["state"]) == "prepared" {
			out = append(out, id)
		}
	}
	return out, nil
}
func (f *FS) current(rel string) ([]byte, error) {
	b, e := f.Read(rel, canonical.MaxBytes)
	if os.IsNotExist(e) {
		return nil, nil
	}
	return b, e
}
func (f *FS) Commit(id, requestHash string, edits []Edit, result ...map[string]any) (Outcome, error) {
	if len(result) > 1 {
		return Outcome{}, fault.New("INVALID_TRANSACTION", "at most one durable result is permitted")
	}
	var response any
	if len(result) == 1 {
		encoded, err := canonical.Marshal(result[0])
		if err != nil || len(encoded) > 60000 {
			return Outcome{}, fault.New("INVALID_TRANSACTION", "durable response exceeds its bounded contract")
		}
		response, err = canonical.Object(encoded)
		if err != nil {
			return Outcome{}, err
		}
	}
	if !opPattern.MatchString(id) {
		return Outcome{}, fault.New("INVALID_OPERATION_ID", "operation ID must be 8..80 safe characters")
	}
	if old, e := f.Lookup(id, requestHash); e != nil {
		return Outcome{}, e
	} else if old != nil {
		return *old, nil
	}
	if pending, e := f.Pending(); e != nil {
		return Outcome{}, e
	} else if len(pending) > 0 {
		return Outcome{}, fault.New("RECOVERY_REQUIRED", "reconcile pending transaction before another write")
	}
	if len(edits) < 1 || len(edits) > 128 {
		return Outcome{}, fault.New("INVALID_TRANSACTION", "transaction requires 1..128 edits")
	}
	seen := map[string]bool{}
	for _, ed := range edits {
		derived := derivedTransactionTarget(ed.Path, hash(ed.Before), hash(ed.After), int64(len(ed.After)))
		if !validate.Path(ed.Path, false) || (strings.HasPrefix(ed.Path, meta+"/") && !derived) || seen[ed.Path] || ed.Before == nil && ed.After == nil || len(ed.After) > canonical.MaxBytes {
			return Outcome{}, fault.New("INVALID_TRANSACTION", "unsafe, repeated or oversized transaction target")
		}
		seen[ed.Path] = true
		actual, e := f.current(ed.Path)
		if e != nil {
			return Outcome{}, e
		}
		if !bytes.Equal(actual, ed.Before) || (actual == nil) != (ed.Before == nil) {
			return Outcome{}, fault.New("REVISION_CONFLICT", "file differs from the expected bytes")
		}
	}
	if e := f.Mkdir(meta + "/transactions"); e != nil {
		return Outcome{}, e
	}
	if e := f.Mkdir(meta + "/history"); e != nil {
		return Outcome{}, e
	}
	entries := []any{}
	stages := []string{}
	backups := []string{}
	durable := false
	defer func() {
		if !durable {
			for _, p := range append(stages, backups...) {
				_ = f.remove(p)
			}
		}
	}()
	for i, ed := range edits {
		stage := path.Join(path.Dir(ed.Path), fmt.Sprintf(".ca-artifact-%s-%d.new", id, i))
		backup := fmt.Sprintf("%s/history/%s-%d.before", meta, id, i)
		if ed.Before != nil {
			if e := f.createOrCompare(backup, ed.Before, 0600); e != nil {
				return Outcome{}, e
			}
			backups = append(backups, backup)
		}
		if ed.After != nil {
			if e := f.createOrCompare(stage, ed.After, 0644); e != nil {
				return Outcome{}, e
			}
			stages = append(stages, stage)
		}
		entries = append(entries, map[string]any{"path": ed.Path, "stage": stage, "backup": backup, "before_sha256": hash(ed.Before), "after_sha256": hash(ed.After), "size": int64(len(ed.After))})
		if e := f.step(fmt.Sprintf("after-stage-%d", i)); e != nil {
			return Outcome{}, e
		}
	}
	j := map[string]any{"format": "codearbiter.transaction/0.2.0", "operation_id": id, "request_sha256": requestHash, "state": "prepared", "entries": entries, "result": response}
	jb, e := canonical.Marshal(j)
	if e != nil {
		return Outcome{}, e
	}
	if e = f.create(journalPath(id), jb, 0600); e != nil {
		return Outcome{}, e
	}
	durable = true
	uncertain := func(e error) (Outcome, error) {
		return outcome(j, false), &fault.Error{Code: "COMMIT_OUTCOME_UNKNOWN", Message: "durable operation needs reconciliation; do not resubmit under a new ID", OperationID: id}
	}
	if e = f.step("after-journal"); e != nil {
		return uncertain(e)
	}
	for i, ed := range edits {
		r := model.M(entries[i])
		actual, e := f.current(ed.Path)
		if e != nil {
			return uncertain(e)
		}
		if hash(actual) != r["before_sha256"] {
			return uncertain(fault.New("REVISION_CONFLICT", "target changed after journal"))
		}
		if e = f.step(fmt.Sprintf("before-replace-%d", i)); e != nil {
			return uncertain(e)
		}
		if ed.After == nil {
			e = f.remove(ed.Path)
		} else {
			e = f.replace(model.S(r["stage"]), ed.Path, ed.Before == nil)
		}
		if e != nil {
			return uncertain(e)
		}
		if e = f.step(fmt.Sprintf("after-replace-%d", i)); e != nil {
			return uncertain(e)
		}
	}
	j["state"] = "committed"
	jb, e = canonical.Marshal(j)
	if e != nil {
		return uncertain(e)
	}
	if e = f.updateMetadata(journalPath(id), jb); e != nil {
		return uncertain(e)
	}
	if e = f.step("after-complete"); e != nil {
		return uncertain(e)
	}
	return outcome(j, false), nil
}

// Recover must be called while holding the repository's exclusive writer lock.
// A third-party edit matching neither before nor after is never overwritten.
func (f *FS) Recover(id, mode string) (Outcome, error) {
	if mode != "complete" && mode != "rollback" {
		return Outcome{}, fault.New("INVALID_RECOVERY", "select complete or rollback")
	}
	j, e := f.journal(id)
	if e != nil {
		return Outcome{}, e
	}
	if model.S(j["state"]) != "prepared" {
		return outcome(j, true), nil
	}
	entries := model.A(j["entries"])
	for _, v := range entries {
		r := model.M(v)
		b, e := f.current(model.S(r["path"]))
		if e != nil {
			return Outcome{}, e
		}
		h := hash(b)
		if h != r["before_sha256"] && h != r["after_sha256"] {
			return Outcome{}, fault.New("RECOVERY_CONFLICT", "target has unrelated edits; no recovery write performed")
		}
	}
	// Validate all required recovery inputs before touching any target.
	for _, v := range entries {
		r := model.M(v)
		b, e := f.current(model.S(r["path"]))
		if e != nil {
			return Outcome{}, e
		}
		want := r["after_sha256"]
		src := model.S(r["stage"])
		if mode == "rollback" {
			want = r["before_sha256"]
			src = model.S(r["backup"])
		}
		if hash(b) == want || want == nil {
			continue
		}
		input, e := f.Read(src, canonical.MaxBytes)
		if e != nil || hash(input) != want {
			return Outcome{}, fault.New("CORRUPT_JOURNAL", "required recovery bytes are missing or changed")
		}
	}
	for i, v := range entries {
		r := model.M(v)
		p := model.S(r["path"])
		b, e := f.current(p)
		if e != nil {
			return Outcome{}, e
		}
		want := r["after_sha256"]
		if mode == "rollback" {
			want = r["before_sha256"]
		}
		if hash(b) == want {
			continue
		}
		if want == nil {
			if e = f.remove(p); e != nil {
				return Outcome{}, e
			}
			continue
		}
		src := model.S(r["stage"])
		if mode == "rollback" {
			backup, e := f.Read(model.S(r["backup"]), canonical.MaxBytes)
			if e != nil {
				return Outcome{}, e
			}
			src = path.Join(path.Dir(p), fmt.Sprintf(".ca-artifact-%s-%d.restore", id, i))
			if old, e := f.current(src); e != nil {
				return Outcome{}, e
			} else if old != nil {
				if hash(old) != want {
					return Outcome{}, fault.New("RECOVERY_CONFLICT", "unexpected recovery staging bytes")
				}
			} else if e = f.create(src, backup, 0644); e != nil {
				return Outcome{}, e
			}
		}
		if e = f.replace(src, p, b == nil); e != nil {
			return Outcome{}, e
		}
	}

	for _, v := range entries {
		r := model.M(v)
		stage := model.S(r["stage"])
		if b, e := f.current(stage); e != nil {
			return Outcome{}, e
		} else if b != nil {
			if hash(b) != r["after_sha256"] {
				return Outcome{}, fault.New("RECOVERY_CONFLICT", "unused stage changed")
			}
			if e = f.remove(stage); e != nil {
				return Outcome{}, e
			}
		}
	}
	if mode == "complete" {
		j["state"] = "committed"
	} else {
		j["state"] = "rolled_back"
	}
	b, e := canonical.Marshal(j)
	if e != nil {
		return Outcome{}, e
	}
	if e = f.updateMetadata(journalPath(id), b); e != nil {
		return Outcome{}, &fault.Error{Code: "COMMIT_OUTCOME_UNKNOWN", Message: "recovery applied but acknowledgment is uncertain", OperationID: id}
	}
	return outcome(j, false), nil
}

// PutReceipt is create-only infrastructure for the governed adapter. It is not
// exposed as a generic approval operation. Receipt contents must be validated
// separately before they can authorize anything.
func (f *FS) PutReceipt(name string, b []byte) error {
	if !regexp.MustCompile(`^[0-9a-f]{64}\.json$`).MatchString(name) || len(b) > 1<<20 {
		return fault.New("INVALID_RECEIPT", "receipt filename must be its SHA-256 digest")
	}
	if canonical.BytesHash(b) != strings.TrimSuffix(name, ".json") {
		return fault.New("INVALID_RECEIPT", "receipt content digest mismatch")
	}
	return f.create(meta+"/receipts/"+name, b, 0600)
}

// A process death before the durable journal can leave immutable staging bytes.
// Reusing exactly those bytes is safe because no target replacement is possible
// before the journal. Different bytes under the same operation ID are rejected.
func (f *FS) createOrCompare(p string, b []byte, mode uint32) error {
	old, e := f.current(p)
	if e != nil {
		return e
	}
	if old != nil {
		if bytes.Equal(old, b) {
			return nil
		}
		return fault.New("OPERATION_ID_REUSE", "orphan staging bytes differ from the retry")
	}
	return f.create(p, b, mode)
}

// RollbackMigration reverses only a completed Markdown->HTML cutover, not an
// arbitrary content edit (which would rewind an HTML document revision).
// It is itself a journaled transaction, and refuses every intervening edit.
func (f *FS) RollbackMigration(id, requestHash, cutover string) (Outcome, error) {
	j, e := f.journal(cutover)
	if e != nil {
		return Outcome{}, e
	}
	if model.S(j["state"]) != "committed" {
		return Outcome{}, fault.New("INVALID_CUTOVER", "only a committed cutover can be rolled back; use recover for an uncertain transaction")
	}
	entries := model.A(j["entries"])
	if len(entries) != 2 && len(entries) != 4 {
		return Outcome{}, fault.New("INVALID_CUTOVER", "not a spec/plan pair cutover")
	}
	edits := []Edit{}
	seen := map[string]bool{}
	for _, v := range entries {
		r := model.M(v)
		p := model.S(r["path"])
		if !strings.HasPrefix(p, ".codearbiter/specs/") && !strings.HasPrefix(p, ".codearbiter/plans/") {
			return Outcome{}, fault.New("INVALID_CUTOVER", "cutover target outside canonical locations")
		}
		base := strings.TrimSuffix(strings.TrimSuffix(p, ".html"), ".md")
		if strings.HasSuffix(p, ".html") && r["before_sha256"] == nil && r["after_sha256"] != nil {
			seen[base+".html"] = true
		} else if strings.HasSuffix(p, ".md") && r["before_sha256"] != nil && r["after_sha256"] == nil {
			seen[base+".md"] = true
		} else {
			return Outcome{}, fault.New("INVALID_CUTOVER", "cutover must only replace Markdown sources with new HTML")
		}
		current, e := f.current(p)
		if e != nil {
			return Outcome{}, e
		}
		if hash(current) != r["after_sha256"] {
			return Outcome{}, fault.New("RECOVERY_CONFLICT", "candidate changed after cutover; rollback would discard work")
		}
		var restore []byte
		if r["before_sha256"] != nil {
			restore, e = f.Read(model.S(r["backup"]), canonical.MaxBytes)
			if e != nil || hash(restore) != r["before_sha256"] {
				return Outcome{}, fault.New("CORRUPT_JOURNAL", "cutover source backup is unavailable or changed")
			}
		}
		edits = append(edits, Edit{Path: p, Before: current, After: restore})
	}
	for name := range seen {
		base := strings.TrimSuffix(strings.TrimSuffix(name, ".html"), ".md")
		if !seen[base+".html"] || !seen[base+".md"] {
			return Outcome{}, fault.New("INVALID_CUTOVER", "cutover pair names do not match")
		}
	}
	return f.Commit(id, requestHash, edits)
}
