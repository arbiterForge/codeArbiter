package authority

import (
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/canonical"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/model"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/observation"
	"github.com/arbiterForge/codeArbiter/core/artifacts/internal/store"
)

// chainKind marks a receipt chain that Inspect validated against the
// repository's own reads. The memo holds no receipt bytes of its own: reuse
// rebuilds fresh maps from the verified reads the memo recorded, so a caller that
// edits a returned Receipt cannot alter what a later caller of the same
// operation sees, and a reader that is not the repository's can never seed it.
const chainKind = "receipt-chains"

// reuseReceipt returns the receipt validated earlier in this operation, or nil.
// It is used only by Inspect, which reads through the repository; a snapshot,
// which must find every chain object in its own scan, never takes this path.
func reuseReceipt(f *store.FS, p, hash string) *Receipt {
	if _, ok := f.Memo().Held(chainKind, hash); !ok {
		return nil
	}
	receipt, ok := observation.Recorded(f, p, 1<<20)
	if !ok {
		return nil
	}
	data, err := canonical.Object(receipt)
	if err != nil {
		return nil
	}
	eventHash := model.S(data["event_sha256"])
	eventBytes, ok := observation.Recorded(f, EventRef(eventHash), 1<<20)
	if !ok {
		return nil
	}
	event, err := canonical.Object(eventBytes)
	if err != nil {
		return nil
	}
	return &Receipt{Data: data, Event: event, Path: p, Hash: hash, EventPath: EventRef(eventHash)}
}
