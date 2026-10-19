package evidence

import (
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/authority"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/fault"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/render"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/testutil"
)

// reservedListingDirOpens is the directory open that listing an existing
// reserved output root adds. The Linux backend opens the root descriptor even
// for an absent path, so a tree without one already pays that open there.
// Enumerations, by contrast, count one per listed directory on every backend
// (store.OpenStats.EnumOpens).
var reservedListingDirOpens = func() int {
	if runtime.GOOS == "linux" {
		return 0
	}
	return 1
}()

// boundsScan runs exactly one snapshot scan (snapshotOnce) and returns the
// handle-level work it did, counted by the store's open-counting seam.
func boundsScan(t *testing.T, root string) store.OpenStats {
	t.Helper()
	return boundsScanPlan(t, root, nil)
}

func boundsScanPlan(t *testing.T, root string, plan *model.Document) store.OpenStats {
	t.Helper()
	f, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	f.Stats = &store.OpenStats{}
	if _, err := snapshotOnce(f, plan); err != nil {
		t.Fatal(err)
	}
	return *f.Stats
}

// mintReceiptChain writes one complete, valid v0.2.0 receipt chain under the
// reserved artifact root: receipt, captured event, policy-owned authority source
// (the same bytes as the event), observation and evidence context. Every object
// is the closed shape the engine's own capture produces for an observed user
// prompt approval, so authority.Inspect accepts it. It returns the receipt ref and
// the five files' repository paths.
func mintReceiptChain(t *testing.T, root string, n int) (string, []string) {
	t.Helper()
	artifacts := func(v map[string]any) ([]byte, string) {
		b, err := canonical.Marshal(v)
		if err != nil {
			t.Fatal(err)
		}
		return b, canonical.BytesHash(b)
	}
	put := func(sub string, b []byte, h string) string {
		rel := authority.Root + "/" + sub + "/" + h + ".json"
		completionWrite(t, root, rel, b)
		return rel
	}
	sha := func(label string) string { return canonical.BytesHash([]byte(fmt.Sprintf("%s-%d", label, n))) }
	subject := map[string]any{"artifact_id": fmt.Sprintf("SPEC-CHAIN-%d", n), "normative_sha256": sha("normative"), "record_id": fmt.Sprintf("REC-%d", n)}
	sourceText := fmt.Sprintf("Synthetic bounds fixture, not a real approval: %d", n)
	prompt := canonical.BytesHash([]byte(sourceText))
	record := map[string]any{"n": int64(n)}
	recordHash, err := canonical.Hash(record)
	if err != nil {
		t.Fatal(err)
	}
	contextBytes, contextHash := artifacts(map[string]any{
		"format": "codearbiter.evidence-context/0.1.0", "activity": "approval", "subject": subject,
		"input_sha256": sha("input"), "prompt_sha256": prompt, "record_sha256": recordHash, "record": record,
	})
	contextRef := put("evidence-contexts", contextBytes, contextHash)
	payload := map[string]any{}
	payloadHash, err := canonical.Hash(payload)
	if err != nil {
		t.Fatal(err)
	}
	producer := map[string]any{"host": "test", "session_id": fmt.Sprintf("bounds-%d", n), "prompt_sha256": prompt}
	producerHash, err := canonical.Hash(producer)
	if err != nil {
		t.Fatal(err)
	}
	observationBytes, observationHash := artifacts(map[string]any{
		"format": "codearbiter.observation/0.2.0", "kind": "approval", "subject": subject,
		"context_ref": contextRef, "context_sha256": contextHash, "payload_sha256": payloadHash,
		"producer_profile": "host-user-prompt/0.1.0", "producer_run_id": fmt.Sprintf("test:bounds-%d", n),
		"producer_result": producer, "producer_result_sha256": producerHash,
	})
	observationRef := put("observations", observationBytes, observationHash)
	eventBytes, eventHash := artifacts(map[string]any{
		"format": "codearbiter.workflow-event/0.2.0", "kind": "approval", "authority_kind": "user_workflow",
		"subject": subject, "actor": "synthetic test fixture", "origin": "bounds fixture", "verdict": "approved",
		"payload": payload, "source_text": sourceText,
		"observation_ref": observationRef, "observation_sha256": observationHash,
	})
	eventRef := put("events", eventBytes, eventHash)
	sourceRef := put("authority-sources", eventBytes, eventHash)
	receiptBytes, receiptHash := artifacts(map[string]any{
		"format": "codearbiter.receipt/0.2.0", "kind": "approval", "authority_kind": "user_workflow",
		"subject": subject, "event_sha256": eventHash,
		"authority_source_ref": sourceRef, "authority_source_sha256": eventHash,
	})
	receiptRef := put("receipts", receiptBytes, receiptHash)
	return receiptRef, []string{receiptRef, eventRef, sourceRef, observationRef, contextRef}
}

// directoryCount counts the directories below root a scan visits: every
// directory except the reserved artifact output root, which is read by its own
// pass and never walked.
func directoryCount(t *testing.T, root string) int {
	t.Helper()
	reserved := filepath.Join(root, filepath.FromSlash(authority.Root))
	n := 0
	err := filepath.WalkDir(root, func(p string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() && p != root {
			if strings.HasPrefix(p, reserved) {
				return filepath.SkipDir
			}
			n++
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	return n
}

// TestPortableSnapshotOpensBounded proves SPEC AC-08: one scan anchors each
// visited directory with one anchor open plus one listing open and opens each
// input file at most once, with no per-file ancestor re-check, so the cost does
// not grow with file depth. It counts opens through the store seam; it never
// reads a clock.
func TestPortableSnapshotOpensBounded(t *testing.T) {
	const perDir = 3
	dirs := []string{"", "d1/", "d1/d2/", "d1/d2/d3/", "d1/d2/d3/d4/", "d1/d2/d3/d4/d5/"}
	spread := testutil.Root(t)
	deep := testutil.Root(t)
	empty := testutil.Root(t)
	files := 0
	for i, d := range dirs {
		for n := 0; n < perDir; n++ {
			completionWrite(t, spread, fmt.Sprintf("%sf%d_%d.txt", d, i, n), []byte(fmt.Sprintf("spread %d %d\n", i, n)))
			// Same file count, every file at the deepest level (depth 6).
			completionWrite(t, deep, fmt.Sprintf("%sf%d_%d.txt", dirs[len(dirs)-1], i, n), []byte(fmt.Sprintf("deep %d %d\n", i, n)))
			files++
		}
	}
	// All three trees hold .codearbiter (so constant ancestor work is in the
	// baseline); the two scanned trees also hold the normative catalog directories,
	// which a "." walk reaches and the always-include pass must not anchor or list a
	// second time.
	for _, root := range []string{spread, deep, empty} {
		completionWrite(t, root, ".codearbiter/keep.txt", []byte("keep\n"))
	}
	for _, root := range []string{spread, deep} {
		for _, kind := range []string{"specs", "plans"} {
			completionWrite(t, root, ".codearbiter/"+kind+"/keep.txt", []byte(kind+"\n"))
		}
	}
	files += 2
	extraDirs := len(dirs) - 1 + 2 // the "." walk exists in the empty baseline too; plus specs and plans
	if d := directoryCount(t, spread) - directoryCount(t, empty); d != extraDirs {
		t.Fatalf("fixture: %d added directories on disk, want %d", d, extraDirs)
	}

	base := boundsScan(t, empty)
	for name, root := range map[string]string{"spread": spread, "deep": deep} {
		got := boundsScan(t, root)
		t.Logf("%s: %+v (empty baseline %+v, %d files, %d added directories)", name, got, base, files, extraDirs)
		if d := got.DirOpens - base.DirOpens; d > extraDirs {
			t.Errorf("%s: %d directory opens for %d added directories (one anchor open each)", name, d, extraDirs)
		}
		if d := got.EnumOpens - base.EnumOpens; d > extraDirs {
			t.Errorf("%s: %d enumeration opens for %d added directories (one listing open each)", name, d, extraDirs)
		}
		if d := got.FileOpens - base.FileOpens; d > files {
			t.Errorf("%s: %d file opens for %d input files (at most once each)", name, d, files)
		}
		if d := got.AncestorChecks - base.AncestorChecks; d != 0 {
			t.Errorf("%s: %d per-file ancestor checks; the count must not depend on file depth", name, d)
		}
	}
	// Non-vacuous: the trees really were walked, and opens did happen.
	got := boundsScan(t, spread)
	if got.FileOpens-base.FileOpens < files || got.DirOpens-base.DirOpens < extraDirs {
		t.Fatalf("counting seam saw too little work: %+v vs base %+v", got, base)
	}

	// Real receipt chains: every evidence object (receipt, event, authority
	// source, observation, evidence context) is opened at most once per scan and no
	// ancestor or per-entry check depends on the chain count. A receipt validated
	// by re-reading its chain through root-relative paths would open ten files and
	// re-walk four ancestors for every chain.
	const objectsPerChain = 5
	chains := func(count int) string {
		root := testutil.Root(t)
		completionWrite(t, root, "src/a.txt", []byte("a\n"))
		for i := 0; i < count; i++ {
			ref, paths := mintReceiptChain(t, root, i)
			if len(paths) != objectsPerChain || paths[0] != ref {
				t.Fatalf("unexpected chain %v", paths)
			}
		}
		return root
	}
	one, many := chains(1), chains(7)
	a, b := boundsScan(t, one), boundsScan(t, many)
	t.Logf("1 chain %+v; 7 chains %+v", a, b)
	if grew := b.FileOpens - a.FileOpens; grew > objectsPerChain*6 {
		t.Errorf("6 added chains caused %d file opens (at most one per evidence object, %d)", grew, objectsPerChain*6)
	}
	if grew := b.FileOpens - a.FileOpens; grew < objectsPerChain*6 {
		t.Errorf("chains were not read at all: %d added file opens", grew)
	}
	if b.AncestorChecks != a.AncestorChecks {
		t.Errorf("ancestor checks grew with the chain count: %d -> %d", a.AncestorChecks, b.AncestorChecks)
	}
	if b.EntryChecks-a.EntryChecks > 2*objectsPerChain*6 {
		t.Errorf("per-entry checks grew beyond two per evidence object: %d -> %d", a.EntryChecks, b.EntryChecks)
	}
}

// TestPortableSnapshotNormativeArtifactsOpenOnce guards the always-include pass:
// sealed specs and plans are input files, so each is opened once per scan
// whether the walk reached it (a "." root) or only the always-include pass did
// (scoped roots), and the specs and plans directories themselves cost one anchor
// open plus one listing open each in the same scan, not one per consumer. Counts
// are compared exactly against a tree with no artifact directories, so a second
// anchor or listing of a directory the walk already visited is a failure.
func TestPortableSnapshotNormativeArtifactsOpenOnce(t *testing.T) {
	spec := testutil.Seal(t, testutil.Spec())
	plan := testutil.Seal(t, testutil.Plan(spec))
	specBytes, err := render.Render(spec)
	if err != nil {
		t.Fatal(err)
	}
	planBytes, err := render.Render(plan)
	if err != nil {
		t.Fatal(err)
	}
	build := func(pairs int) string {
		root := testutil.Root(t)
		completionWrite(t, root, "src/a.txt", []byte("a\n"))
		for i := 0; i < pairs; i++ {
			completionWrite(t, root, fmt.Sprintf(".codearbiter/specs/s%d.html", i), specBytes)
			completionWrite(t, root, fmt.Sprintf(".codearbiter/plans/p%d.html", i), planBytes)
		}
		return root
	}
	const few, many = 1, 5
	for name, policy := range map[string]*model.Document{
		"dot roots":    nil,
		"scoped roots": snapshotPolicy(t, []string{"src"}, nil),
	} {
		a, b := boundsScanPlan(t, build(few), policy), boundsScanPlan(t, build(many), policy)
		t.Logf("%s: %d artifact pairs %+v; %d pairs %+v", name, few, a, many, b)
		none, full := build(0), build(many)
		base := boundsScanPlan(t, none, policy)
		// Directories the artifacts add: .codearbiter, specs and plans.
		added := directoryCount(t, full) - directoryCount(t, none)
		if added != 3 {
			t.Fatalf("%s: fixture adds %d directories, want 3", name, added)
		}
		for label, got := range map[string]store.OpenStats{"few": a, "many": b} {
			if d := got.DirOpens - base.DirOpens; d != added {
				t.Errorf("%s/%s: %d directory opens for %d added directories (one anchor open each)", name, label, d, added)
			}
			if d := got.EnumOpens - base.EnumOpens; d != added {
				t.Errorf("%s/%s: %d enumerations for %d added directories (one each)", name, label, d, added)
			}
		}
		if b.AncestorChecks != a.AncestorChecks {
			t.Errorf("%s: ancestor checks grew with artifact count: %d -> %d", name, a.AncestorChecks, b.AncestorChecks)
		}
		if grew, added := b.FileOpens-a.FileOpens, 2*(many-few); grew > added {
			t.Errorf("%s: %d added artifacts caused %d file opens (at most once each)", name, added, grew)
		}
		if b.FileOpens-a.FileOpens < 2*(many-few) {
			t.Errorf("%s: artifacts were not read at all: %+v vs %+v", name, a, b)
		}
	}
}

// TestPortableSnapshotOutputReceiptsOpenOnce guards the reserved-output pass:
// each generated receipt is read once relative to its anchored directory, so the
// scan's ancestor checks do not grow with the receipt count.
func TestPortableSnapshotOutputReceiptsOpenOnce(t *testing.T) {
	build := func(receipts int) string {
		root := testutil.Root(t)
		completionWrite(t, root, "src/a.txt", []byte("a\n"))
		for i := 0; i < receipts; i++ {
			b := []byte(fmt.Sprintf(`{"format":"codearbiter.context-token/0.1.0","n":%d}`, i))
			completionWrite(t, root, ".codearbiter/.artifacts/context-tokens/"+canonical.BytesHash(b)+".json", b)
		}
		return root
	}
	const few, many = 1, 9
	a, b := boundsScan(t, build(few)), boundsScan(t, build(many))
	t.Logf("%d receipts %+v; %d receipts %+v", few, a, many, b)
	if b.AncestorChecks != a.AncestorChecks {
		t.Errorf("ancestor checks grew with receipt count: %d -> %d", a.AncestorChecks, b.AncestorChecks)
	}
	if grew := b.FileOpens - a.FileOpens; grew != many-few {
		t.Errorf("%d added receipts caused %d file opens (exactly one each)", many-few, grew)
	}
}

// TestReceiptChainFixtureIsRealAndInspectWithFailsClosed pins the fixture used by
// the bounds test to the real validator (so the counts above are not measuring
// chains the scan would reject), and pins the byte-based entry point: with the
// objects supplied by an index it opens no file at all, and an object the index
// does not hold fails closed instead of falling back to the repository.
func TestReceiptChainFixtureIsRealAndInspectWithFailsClosed(t *testing.T) {
	root := testutil.Root(t)
	ref, paths := mintReceiptChain(t, root, 3)
	f, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	if _, err := authority.Inspect(f, ref); err != nil {
		t.Fatalf("fixture chain is not a valid receipt chain: %v", err)
	}
	index := map[string][]byte{}
	for _, p := range paths {
		b, err := f.Read(p, canonical.MaxBytes)
		if err != nil {
			t.Fatal(err)
		}
		index[p] = b
	}
	f.Stats = &store.OpenStats{}
	lookup := func(rel string, limit int64) ([]byte, error) {
		b, ok := index[rel]
		if !ok || int64(len(b)) > limit {
			return nil, os.ErrNotExist
		}
		return b, nil
	}
	if _, err := authority.InspectWith(ref, index[ref], lookup); err != nil {
		t.Fatalf("InspectWith over the full index: %v", err)
	}
	if *f.Stats != (store.OpenStats{}) {
		t.Fatalf("InspectWith touched the repository: %+v", *f.Stats)
	}
	for _, missing := range paths[1:] {
		partial := func(rel string, limit int64) ([]byte, error) {
			if rel == missing {
				return nil, os.ErrNotExist
			}
			return lookup(rel, limit)
		}
		_, err := authority.InspectWith(ref, index[ref], partial)
		if err == nil || (fault.Code(err) != "AUTHORITY_UNVERIFIED" && fault.Code(err) != "OBSERVATION_UNVERIFIED") {
			t.Errorf("missing %s: InspectWith = %v, want a fail-closed unverified error", missing, err)
		}
	}
}

// TestSnapshotRefusesOversizedReceipt: a receipt over the 1 MiB receipt limit
// fails the scan as unverified even when its name matches its bytes and it is
// canonical JSON, exactly as authority.Inspect refuses it through a file read.
func TestSnapshotRefusesOversizedReceipt(t *testing.T) {
	root := testutil.Root(t)
	completionWrite(t, root, "src/a.txt", []byte("a\n"))
	pad := strings.Repeat("a", (1<<20)+1-len(`{"pad":""}`))
	b := []byte(`{"pad":"` + pad + `"}`)
	if len(b) != (1<<20)+1 {
		t.Fatalf("fixture is %d bytes", len(b))
	}
	completionWrite(t, root, authority.Root+"/receipts/"+canonical.BytesHash(b)+".json", b)
	f, err := store.Open(root)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	if _, err := snapshotOnce(f, nil); fault.Code(err) != "AUTHORITY_UNVERIFIED" {
		t.Fatalf("oversized receipt: %v, want AUTHORITY_UNVERIFIED", err)
	}
}

// farmBindingFixture writes n plan projections and, when withBindings is set, a
// farm binding for each whose base hash matches, so each projection is read once
// through its binding.
func farmBindingFixture(t *testing.T, n int, withBindings bool) string {
	t.Helper()
	root := testutil.Root(t)
	completionWrite(t, root, "src/a.txt", []byte("a\n"))
	for i := 0; i < n; i++ {
		projection := fmt.Sprintf(".codearbiter/plans/p%d.plan.json", i)
		body := []byte(fmt.Sprintf(`{"meta":{"model":"m","apiBaseUrl":"u"},"n":%d}`, i))
		completionWrite(t, root, projection, body)
		if !withBindings {
			continue
		}
		v, err := canonical.Object(body)
		if err != nil {
			t.Fatal(err)
		}
		base, err := canonical.Clone(v)
		if err != nil {
			t.Fatal(err)
		}
		meta := model.M(base["meta"])
		delete(meta, "model")
		delete(meta, "apiBaseUrl")
		baseBytes, err := canonical.Marshal(base)
		if err != nil {
			t.Fatal(err)
		}
		b, err := canonical.Marshal(map[string]any{"format": "codearbiter.farm-binding/0.1.0", "projection_path": projection, "base_sha256": canonical.BytesHash(baseBytes)})
		if err != nil {
			t.Fatal(err)
		}
		completionWrite(t, root, authority.Root+"/farm-bindings/"+canonical.BytesHash(b)+".json", b)
	}
	return root
}

// TestPortableSnapshotFarmBindingsAnchorProjectionsOnce guards AC-08 for farm
// bindings: each projection is read by the walk itself, relative to the plans
// directory it already anchored and listed, so neither ancestor checks nor
// directory opens grow with the binding count.
func TestPortableSnapshotFarmBindingsAnchorProjectionsOnce(t *testing.T) {
	const few, many = 1, 7
	a, b := boundsScan(t, farmBindingFixture(t, few, true)), boundsScan(t, farmBindingFixture(t, many, true))
	plain := boundsScan(t, farmBindingFixture(t, many, false))
	t.Logf("%d bindings %+v; %d bindings %+v; no bindings %+v", few, a, many, b, plain)
	if b.AncestorChecks != a.AncestorChecks {
		t.Errorf("ancestor checks grew with the farm binding count: %d -> %d", a.AncestorChecks, b.AncestorChecks)
	}
	if b.DirOpens != a.DirOpens || b.EnumOpens != a.EnumOpens {
		t.Errorf("directory work grew with the farm binding count: %+v -> %+v", a, b)
	}
	// Reading bindings adds the farm-bindings directory's anchor and, where the
	// backend does not already pay it for an absent root, the reserved output
	// root's listing open. The plans directory is not anchored again for the
	// projections.
	if d := b.DirOpens - plain.DirOpens; d != 1+reservedListingDirOpens {
		t.Errorf("farm bindings added %d directory opens over the same tree without them, want %d", d, 1+reservedListingDirOpens)
	}
	// Two file opens per binding: the binding itself and its projection.
	if grew := b.FileOpens - a.FileOpens; grew != 2*(many-few) {
		t.Errorf("%d added bindings caused %d file opens, want %d (binding plus projection)", many-few, grew, 2*(many-few))
	}
}

// TestPortableSnapshotScopedRootsShareAnchoredPrefixes guards AC-08 for explicit
// roots: the ancestors that several scoped roots share are anchored and listed
// once per scan, so each added root costs only its own directory.
func TestPortableSnapshotScopedRootsShareAnchoredPrefixes(t *testing.T) {
	build := func() string {
		root := testutil.Root(t)
		for _, d := range []string{"a/b", "a/c", "a/d", "e/f/g"} {
			completionWrite(t, root, d+"/x.txt", []byte(d+"\n"))
		}
		return root
	}
	scan := func(roots ...string) store.OpenStats {
		return boundsScanPlan(t, build(), snapshotPolicy(t, roots, nil))
	}
	one := scan("a/b")
	two := scan("a/b", "a/c")
	three := scan("a/b", "a/c", "a/d")
	deep := scan("a/b", "e/f/g")
	t.Logf("1 root %+v; 2 roots %+v; 3 roots %+v; a/b + e/f/g %+v", one, two, three, deep)
	// "." and "a" are shared: every further sibling root adds its own directory only.
	for label, step := range map[string][2]store.OpenStats{"second": {one, two}, "third": {two, three}} {
		if d := step[1].DirOpens - step[0].DirOpens; d != 1 {
			t.Errorf("%s sibling root added %d directory opens, want 1 (its own directory)", label, d)
		}
		if d := step[1].EnumOpens - step[0].EnumOpens; d != 1 {
			t.Errorf("%s sibling root added %d enumerations, want 1 (its own directory)", label, d)
		}
		if step[1].AncestorChecks != step[0].AncestorChecks {
			t.Errorf("%s sibling root changed ancestor checks: %d -> %d", label, step[0].AncestorChecks, step[1].AncestorChecks)
		}
	}
	// A root on a separate branch adds its own new ancestors (e, f) plus itself (g); "." is shared.
	if d := deep.DirOpens - one.DirOpens; d != 3 {
		t.Errorf("root under a new branch added %d directory opens, want 3 (e, f, g)", d)
	}
	if d := deep.EnumOpens - one.EnumOpens; d != 3 {
		t.Errorf("root under a new branch added %d enumerations, want 3 (e, f, g)", d)
	}
}
