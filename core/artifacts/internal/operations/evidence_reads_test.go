package operations

import (
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/authority"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/evidence"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/observation"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

// Evidence objects are content addressed, so within one engine operation (one
// store handle) an object that many receipts reference needs one read and one
// schema validation (SPEC-SHIP-SET-EVIDENCE-INPUTS AC-12, DEC-07). The ledger
// below counts both per object, using the store's read seam and the validation
// seam, over operations run through the real engine against real receipt chains.

var evidenceObjectDirs = []string{"receipts", "events", "authority-sources", "observations", "evidence-contexts"}

type evidenceLedger struct {
	mu          sync.Mutex
	opens       map[string]int // root-relative reads (store.FS.Read)
	scans       map[string]int // reads by a scan of an anchored directory (Dir.ReadEntry)
	validations map[string]int
	started     time.Time
	elapsed     time.Duration
}

func evidenceObjectPath(rel string) bool {
	for _, dir := range evidenceObjectDirs {
		if strings.HasPrefix(rel, ".codearbiter/.artifacts/"+dir+"/") {
			return true
		}
	}
	return false
}

func (l *evidenceLedger) open(rel string, anchored bool) {
	if !evidenceObjectPath(rel) {
		return
	}
	l.mu.Lock()
	if anchored {
		l.scans[rel]++
	} else {
		l.opens[rel]++
	}
	l.mu.Unlock()
}

func (l *evidenceLedger) validate(kind, hash string) {
	l.mu.Lock()
	l.validations[kind+"/"+hash]++
	l.mu.Unlock()
}

// measured runs exactly one engine operation with the ledger installed on the
// store handle that operation opens for itself. Preparation (reading the current
// revision, say) happens before the hook is installed so it is not counted.
func (h *farmHarness) measured(op string, r object) (*evidenceLedger, object) {
	h.t.Helper()
	l := &evidenceLedger{opens: map[string]int{}, scans: map[string]int{}, validations: map[string]int{}}
	openStore = func(root string) (*store.FS, error) {
		f, err := store.Open(root)
		if err == nil {
			f.SetReadHook(l.open)
			f.SetValidateHook(l.validate)
		}
		return f, err
	}
	defer func() { openStore = store.Open }()
	l.started = time.Now()
	out := h.run(op, r)
	l.elapsed = time.Since(l.started)
	return l, out
}

func (h *farmHarness) measuredMutate(op, id string, r object) (*evidenceLedger, object) {
	h.t.Helper()
	d := h.doc(id)
	r["artifact_id"] = id
	r["operation_id"] = h.next()
	r["expected"] = object{"revision": d.Revision(), "model_sha256": d.Hash()}
	return h.measured(op, r)
}

// assertOnce checks one engine operation. Three guarantees are separate:
//
//   - no evidence object is read root-relative more than once;
//   - no evidence object is schema-validated more than once, however many
//     receipts or scans reach it;
//   - a scan (the snapshot's input scan, run once per pass and again by the
//     completion workspace checks, which exist to re-observe the store) reads each
//     reserved file exactly once per pass, so every file is read the same number of
//     times, and that is the number of passes.
func (l *evidenceLedger) assertOnce(t *testing.T, name string) (passes int) {
	t.Helper()
	if len(l.validations) == 0 || len(l.opens)+len(l.scans) == 0 {
		t.Fatalf("%s touched no evidence objects (reads=%d scans=%d validations=%d); the measurement is vacuous", name, len(l.opens), len(l.scans), len(l.validations))
	}
	most := 0
	for rel, n := range l.opens {
		if n > most {
			most = n
		}
		if n > 1 {
			t.Errorf("%s read evidence object %s root-relative %d times; want at most once", name, rel, n)
		}
	}
	for key, n := range l.validations {
		if n > 1 {
			t.Errorf("%s schema-validated evidence object %s %d times; want at most once", name, key, n)
		}
	}
	for rel, n := range l.scans {
		if passes == 0 {
			passes = n
		}
		if n != passes {
			t.Errorf("%s scans read %s %d times but other objects %d times; a scan must read each file once per pass", name, rel, n, passes)
		}
	}
	t.Logf("%s: %d objects read root-relative (max %d each), %d objects read by %d scan pass(es), %d validated (max once each), %s",
		name, len(l.opens), most, len(l.scans), passes, len(l.validations), l.elapsed.Round(time.Millisecond))
	return passes
}

func evidenceFiles(t *testing.T, root string) []string {
	t.Helper()
	files := []string{}
	for _, dir := range evidenceObjectDirs {
		entries, err := os.ReadDir(filepath.Join(root, ".codearbiter", ".artifacts", dir))
		if os.IsNotExist(err) {
			continue
		}
		if err != nil {
			t.Fatal(err)
		}
		for _, entry := range entries {
			files = append(files, ".codearbiter/.artifacts/"+dir+"/"+entry.Name())
		}
	}
	sort.Strings(files)
	return files
}

func receiptCount(t *testing.T, root string) int {
	t.Helper()
	entries, err := os.ReadDir(filepath.Join(root, ".codearbiter", ".artifacts", "receipts"))
	if err != nil {
		t.Fatal(err)
	}
	return len(entries)
}

// evidenceScenario is what one fixture measured: the scan passes each operation
// made, and how many receipt chains the store held at the end.
type evidenceScenario struct {
	passes   map[string]int
	receipts int
}

// completeTask drives one task through the engine's own capture path: start,
// verification in workspace, a spec review, and the task review. Only the first
// task of a scope is measured when measureReview is set.
func completeTask(t *testing.T, h *farmHarness, id, workspace, material string, measureReview bool) (verification string, ledger *evidenceLedger) {
	t.Helper()
	startNativeV1FixtureTask(t, h, id)
	verification = completionVerification(t, h, id, workspace)
	cr := completionContext(t, h, id, "spec_review", []string{verification}, []string{material})
	context := h.derived(model.S(cr["context_ref"]))
	source, _ := nativeV1ReviewSourceForContext(t, h, id, "spec_review", cr)
	review := h.run("capture-observation", source)["receipt"]
	request := object{"task": id, "verification_receipt": verification, "review_receipt": review, "completion_sha256": context["completion_sha256"]}
	if measureReview {
		ledger, _ = h.measuredMutate("task-review", "PLAN-EXAMPLE", request)
	} else {
		h.mutate("task-review", "PLAN-EXAMPLE", request)
	}
	return verification, ledger
}

// acceptScope captures the quality review of a scope and measures accept-scope.
func acceptScope(t *testing.T, h *farmHarness, scope, material string, receipts []string) *evidenceLedger {
	t.Helper()
	quality := completionContext(t, h, scope, "quality_review", receipts, []string{material})
	qcontext := h.derived(model.S(quality["context_ref"]))
	source, _ := nativeV1ReviewSourceForContext(t, h, scope, "quality_review", quality)
	review := h.run("capture-observation", source)["receipt"]
	ledger, _ := h.measuredMutate("accept-scope", "PLAN-EXAMPLE", object{"scope": scope, "receipt": review, "completion_sha256": qcontext["completion_sha256"]})
	return ledger
}

// evidenceReadScenario mints real receipt chains through the engine's own capture
// path (spec and plan approvals, per-task verification and review, quality
// review, plus `extra` further approvals nothing yet references) and measures
// index, snapshot, read, task-review and accept-scope once each. Two scopes are
// accepted, CP-01 over two completed tasks (T-001 in the artifact root, T-002 in
// a linked worktree) and then CP-02 over one, so the same scenario compares an
// accepted scope of two tasks with one of a single task. With sameRoot both
// tasks of CP-01 are verified in the artifact root itself, so a scope of two
// tasks names one workspace root twice and the scan-pass count of its acceptance
// can be compared with a scope of one.
func evidenceReadScenario(t *testing.T, extra int, sameRoot bool) evidenceScenario {
	t.Helper()
	h, linked := completionHarness(t)
	for i := 0; i < extra; i++ {
		h.capture("PLAN-EXAMPLE", "PLAN-EXAMPLE", "approval", object{})
	}
	material := filepath.Join(testutil.Root(t), "matrix.txt")
	if err := os.WriteFile(material, []byte("Task completion evidence matrix\n"), 0600); err != nil {
		t.Fatal(err)
	}
	ledgers := map[string]*evidenceLedger{}
	receipts := []string{}
	for i, id := range []string{"T-001", "T-002"} {
		root := h.root
		if i == 1 && !sameRoot {
			root = linked
		}
		verification, ledger := completeTask(t, h, id, root, material, i == 0)
		receipts = append(receipts, verification)
		if ledger != nil {
			ledgers["task-review"] = ledger
		}
	}
	ledgers["accept-scope"] = acceptScope(t, h, "CP-01", material, receipts)
	// A scope of one completed task, accepted after the scope of two.
	verification, _ := completeTask(t, h, "T-003", h.root, material, false)
	ledgers["accept-scope (1 task)"] = acceptScope(t, h, "CP-02", material, []string{verification})
	ledgers["read"], _ = h.measured("read", object{"artifact_id": "PLAN-EXAMPLE", "symbol": "T-001", "budget": int64(65536)})
	ledgers["index"], _ = h.measured("index", object{"budget": int64(4096)})
	snapshot, _ := h.measured("snapshot", object{"artifact_id": "PLAN-EXAMPLE"})
	ledgers["snapshot"] = snapshot

	out := evidenceScenario{passes: map[string]int{}}
	for _, name := range []string{"read", "index", "task-review", "accept-scope", "accept-scope (1 task)", "snapshot"} {
		out.passes[name] = ledgers[name].assertOnce(t, name)
	}
	// A snapshot is two complete passes (it compares them to reject a concurrent
	// edit). Each reads every reserved evidence file exactly once and validates its
	// receipt chains from those bytes: no chain object is read root-relative, and
	// none is read a second time within a pass.
	for _, rel := range evidenceFiles(t, h.root) {
		if n := snapshot.scans[rel]; n != 2 {
			t.Errorf("snapshot scans read %s %d times; want exactly twice (once per pass)", rel, n)
		}
		if n := snapshot.opens[rel]; n != 0 {
			t.Errorf("snapshot read %s root-relative %d times; a snapshot validates chains from its scan bytes", rel, n)
		}
	}
	out.receipts = receiptCount(t, h.root)
	return out
}

func TestEvidenceObjectsReadOnce(t *testing.T) {
	small := evidenceReadScenario(t, 0, false)
	large := evidenceReadScenario(t, 6, false)
	// Two tasks in the SAME workspace root: the root's state is computed once and
	// reused, so accepting the two-task scope costs the passes of the one-task scope.
	same := evidenceReadScenario(t, 0, true)
	t.Logf("receipt chains: small fixture %d, large fixture %d", small.receipts, large.receipts)
	if large.receipts < 12 || large.receipts <= small.receipts {
		t.Fatalf("fixtures do not scale: %d then %d receipts; want the large fixture to hold at least 12 chains", small.receipts, large.receipts)
	}
	// Scan passes are bounded by a constant: they must not grow with the number
	// of receipts (small against large fixture) or with the number of completed
	// tasks in the accepted scope (CP-01 holds two, CP-02 one).
	for name, passes := range small.passes {
		if large.passes[name] != passes {
			t.Errorf("%s made %d scan passes on the small fixture and %d on the large one; passes must not grow with receipts", name, passes, large.passes[name])
		}
	}
	if same.passes["accept-scope"] != small.passes["accept-scope"] {
		t.Errorf("accept-scope over two tasks in one workspace root made %d scan passes; the mixed-root scope made %d", same.passes["accept-scope"], small.passes["accept-scope"])
	}
	for _, run := range []evidenceScenario{small, large, same} {
		if run.passes["accept-scope"] != run.passes["accept-scope (1 task)"] {
			t.Errorf("accept-scope made %d scan passes over a scope of two tasks and %d over one; passes must not grow with tasks", run.passes["accept-scope"], run.passes["accept-scope (1 task)"])
		}
	}
}

// A failed or absent object is never reused: after a transient failure the same
// store handle must still accept the object once it is valid again, while an
// object that was validated is not read again.
func TestEvidenceReuseNeverCachesErrorsOrAbsence(t *testing.T) {
	h := newFarmHarness(t)
	h.createPair()
	spec := h.doc("SPEC-EXAMPLE")
	approvals := model.A(model.M(spec.Data["governance"])["approvals"])
	if len(approvals) == 0 {
		t.Fatal("approved spec fixture has no approval receipt")
	}
	ref := model.S(model.M(approvals[0])["source_ref"])
	eventPath := ""
	{
		f, err := store.Open(h.root)
		if err != nil {
			t.Fatal(err)
		}
		r, err := authority.Inspect(f, ref)
		f.Close()
		if err != nil {
			t.Fatal(err)
		}
		eventPath = r.EventPath
	}
	disk := filepath.Join(h.root, filepath.FromSlash(eventPath))
	original, err := os.ReadFile(disk)
	if err != nil {
		t.Fatal(err)
	}
	moved := disk + ".away"
	for _, damage := range []struct {
		name  string
		apply func()
		undo  func()
	}{
		{"absent", func() { os.Rename(disk, moved) }, func() { os.Rename(moved, disk) }},
		{"corrupt", func() { os.WriteFile(disk, []byte(`{"changed":true}`), 0600) }, func() { os.WriteFile(disk, original, 0600) }},
	} {
		t.Run(damage.name, func(t *testing.T) {
			f, err := store.Open(h.root)
			if err != nil {
				t.Fatal(err)
			}
			defer f.Close()
			reads := 0
			f.SetReadHook(func(rel string, _ bool) {
				if rel == eventPath {
					reads++
				}
			})
			damage.apply()
			if _, err = authority.Inspect(f, ref); err == nil {
				damage.undo()
				t.Fatalf("%s event was accepted", damage.name)
			}
			if _, err = authority.Inspect(f, ref); err == nil {
				damage.undo()
				t.Fatalf("%s event was accepted on retry", damage.name)
			}
			if reads != 2 && damage.name == "absent" {
				t.Errorf("absence was cached: %d event reads across two failed attempts; want 2", reads)
			}
			damage.undo()
			before := reads
			if _, err = authority.Inspect(f, ref); err != nil {
				t.Fatalf("a valid event after a transient %s failure was refused on the same handle: %v", damage.name, err)
			}
			if reads != before+1 {
				t.Errorf("recovery read the event %d times; want 1", reads-before)
			}
			// Now validated: the same handle must not read it, or any other object
			// of the chain, again.
			damage.apply()
			defer damage.undo()
			before = reads
			if _, err = authority.Inspect(f, ref); err != nil {
				t.Fatalf("validated receipt was not reused: %v", err)
			}
			if reads != before {
				t.Errorf("validated event was read again (%d reads)", reads-before)
			}
		})
	}
}

// A snapshot takes every receipt-chain object from its own scan. An object the
// scan does not hold fails the chain closed even when an earlier read in the
// same operation already validated it.
func TestSnapshotNeverFallsBackToRootRelativeReadForChainObject(t *testing.T) {
	h := newFarmHarness(t)
	h.createPair()
	spec := h.doc("SPEC-EXAMPLE")
	approvals := model.A(model.M(spec.Data["governance"])["approvals"])
	ref := model.S(model.M(approvals[0])["source_ref"])
	f, err := store.Open(h.root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	r, err := authority.Inspect(f, ref)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = evidence.Snapshot(f, nil); err != nil {
		t.Fatalf("snapshot of an intact store failed: %v", err)
	}
	disk := filepath.Join(h.root, filepath.FromSlash(r.EventPath))
	if err = os.Remove(disk); err != nil {
		t.Fatal(err)
	}
	if _, err = authority.Inspect(f, ref); err != nil {
		t.Fatalf("reuse within the operation should still serve the validated receipt: %v", err)
	}
	if _, err = evidence.Snapshot(f, nil); err == nil {
		t.Fatal("snapshot accepted a receipt whose event is missing from its scan because it was validated earlier")
	}
}

// A snapshot drops the bytes of reserved objects no receipt names, but still
// refuses an invalid one: bounding the scan's memory must not skip a check.
func TestSnapshotChecksUnreferencedEvidenceObjects(t *testing.T) {
	for _, dir := range []string{"events", "authority-sources", "observations", "evidence-contexts"} {
		t.Run(dir, func(t *testing.T) {
			h := newFarmHarness(t)
			h.createPair()
			f, err := store.Open(h.root)
			if err != nil {
				t.Fatal(err)
			}
			defer f.Close()
			if _, err = evidence.Snapshot(f, nil); err != nil {
				t.Fatalf("snapshot of an intact store failed: %v", err)
			}
			h.forge(dir, object{"format": "not-an-evidence-object"})
			if _, err = evidence.Snapshot(f, nil); err == nil {
				t.Fatalf("snapshot accepted a schema-invalid, unreferenced %s object", dir)
			}
		})
	}
}

// evidenceReceiptFixture opens a store on a real approved receipt chain and
// returns the receipt reference with its event path.
func evidenceReceiptFixture(t *testing.T) (root, ref, eventPath string) {
	t.Helper()
	h := newFarmHarness(t)
	h.createPair()
	approvals := model.A(model.M(h.doc("SPEC-EXAMPLE").Data["governance"])["approvals"])
	if len(approvals) == 0 {
		t.Fatal("approved spec fixture has no approval receipt")
	}
	ref = model.S(model.M(approvals[0])["source_ref"])
	f, err := store.Open(h.root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	r, err := authority.Inspect(f, ref)
	if err != nil {
		t.Fatal(err)
	}
	return h.root, ref, r.EventPath
}

func objectName(ref string) string {
	return strings.TrimSuffix(ref[strings.LastIndex(ref, "/")+1:], ".json")
}

// A caller that edits the bytes a read returned must not alter what the rest of
// the operation sees: the memo neither keeps the caller's slice nor hands out its
// own.
func TestEvidenceReuseServesCopiesNotTheMemosBytes(t *testing.T) {
	root, ref, eventPath := evidenceReceiptFixture(t)
	f, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	first, err := observation.ReadRecorded(f, ref, 1<<20)
	if err != nil {
		t.Fatal(err)
	}
	first[0] ^= 0xff
	second, ok := observation.Recorded(f, ref, 1<<20)
	if !ok || canonical.BytesHash(second) != objectName(ref) {
		t.Fatalf("editing the slice a read returned corrupted the recorded copy (ok=%v)", ok)
	}
	second[0] ^= 0xff
	third, err := observation.ReadRecorded(f, ref, 1<<20)
	if err != nil || canonical.BytesHash(third) != objectName(ref) {
		t.Fatalf("editing the slice a hit returned corrupted the recorded copy (%v)", err)
	}
	// The validators return the same guarantee: edit what a validated load
	// returned, and a second load in the operation still yields authentic bytes.
	r, err := authority.Inspect(f, ref)
	if err != nil {
		t.Fatal(err)
	}
	_, b, err := authority.LoadSourceMemo(f.Memo(), observation.FSReader(f), authority.EventRef(model.S(r.Data["event_sha256"])), model.S(r.Data["event_sha256"]))
	if err == nil {
		b[0] ^= 0xff
	}
	ev, err := observation.ReadRecorded(f, eventPath, 1<<20)
	if err != nil || canonical.BytesHash(ev) != objectName(eventPath) {
		t.Fatalf("event bytes were corrupted through a validator's returned slice (%v)", err)
	}
	if _, err = authority.Inspect(f, ref); err != nil {
		t.Fatalf("receipt no longer validates after callers edited returned slices: %v", err)
	}
}

// A reader that is not the repository's own can never seed a reusable object: a
// chain validated against such a reader is checked again, from disk, by the next
// Inspect on the store handle.
func TestNonStoreReaderNeverSeedsReuse(t *testing.T) {
	root, ref, eventPath := evidenceReceiptFixture(t)
	f, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	disk := func(p string, limit int64) ([]byte, error) {
		return os.ReadFile(filepath.Join(root, filepath.FromSlash(p)))
	}
	b, err := disk(ref, 1<<20)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = authority.InspectMemo(f.Memo(), ref, b, disk); err != nil {
		t.Fatalf("chain did not validate against the disk reader: %v", err)
	}
	away := filepath.Join(root, filepath.FromSlash(eventPath))
	if err = os.Rename(away, away+".away"); err != nil {
		t.Fatal(err)
	}
	defer os.Rename(away+".away", away)
	if _, err = authority.Inspect(f, ref); err == nil {
		t.Fatal("a non-store reader seeded reuse: Inspect skipped the disk read of an absent event")
	}
}

// Bytes that do not hash to their name are never recorded or served, yet the
// approval fingerprint still reports them exactly as before.
func TestMismatchedBytesAreNeverRecorded(t *testing.T) {
	root, ref, eventPath := evidenceReceiptFixture(t)
	disk := filepath.Join(root, filepath.FromSlash(eventPath))
	original, err := os.ReadFile(disk)
	if err != nil {
		t.Fatal(err)
	}
	corrupt := []byte(`{"changed":true}`)
	if err = os.WriteFile(disk, corrupt, 0600); err != nil {
		t.Fatal(err)
	}
	defer os.WriteFile(disk, original, 0600)
	f, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	reads := 0
	f.SetReadHook(func(rel string, _ bool) {
		if rel == eventPath {
			reads++
		}
	})
	got, err := observation.ReadRecorded(f, eventPath, 1<<20)
	if err != nil || string(got) != string(corrupt) {
		t.Fatalf("ReadRecorded changed what the disk holds: %q %v", got, err)
	}
	if _, ok := observation.Recorded(f, eventPath, 1<<20); ok {
		t.Fatal("bytes that do not hash to their name were recorded")
	}
	if _, err = observation.ReadRecorded(f, eventPath, 1<<20); err != nil || reads != 2 {
		t.Fatalf("mismatched bytes were served from the memo (%d reads, %v)", reads, err)
	}
	spec := model.Document{Data: map[string]any{"governance": map[string]any{"approvals": []any{map[string]any{"source_ref": ref}}}}}
	vector := authority.InspectionVector(f, &spec)
	if vector[eventPath] != canonical.BytesHash(corrupt) {
		t.Errorf("fingerprint of mismatched event = %v; want the hash of the bytes on disk", vector[eventPath])
	}
}

// Recording stops silently once a memo holds its byte budget; every read still
// succeeds and validates.
func TestRawReadBudgetStopsRecording(t *testing.T) {
	root, ref, _ := evidenceReceiptFixture(t)
	f, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	f.SetRawBudget(1)
	reads := 0
	f.SetReadHook(func(rel string, _ bool) {
		if rel == ref {
			reads++
		}
	})
	for i := 0; i < 2; i++ {
		if _, err = authority.Inspect(f, ref); err != nil {
			t.Fatalf("read over the budget failed: %v", err)
		}
	}
	if _, ok := observation.Recorded(f, ref, 1<<20); ok || reads != 2 {
		t.Errorf("recording continued past the budget (%d reads)", reads)
	}
}
