package store

// OpenStats is a test-only counting seam over the handle-level work a scan does
// (ADR-0042 AC-08). A nil *OpenStats, the production value, counts nothing and
// costs one nil check per primitive. Assign FS.Stats before a scan to measure it.
//
//   - DirOpens: directory handles anchored for descent (OpenDir, OpenSub and the
//     one-shot directory opens of ListUnfollowed).
//   - EnumOpens: directory enumerations. The portable backends open an extra
//     handle for each; the Linux backend rewinds and enumerates the anchoring
//     descriptor itself. Both count one per enumeration, so the bound is the
//     same on every platform.
//   - FileOpens: input-file opens (Read, Stat, ReadEntry).
//   - AncestorChecks: per-path-component resolutions from the repository root
//     (an Lstat or openat of one ancestor component by name).
//   - EntryChecks: per-entry identity checks of a name against its anchored
//     directory (an Lstat or fstatat of one listed entry, before or after it is
//     opened), so the seam measures all handle-level work and not only opens.
type OpenStats struct {
	DirOpens       int
	EnumOpens      int
	FileOpens      int
	AncestorChecks int
	EntryChecks    int
}

func (s *OpenStats) dirOpen() {
	if s != nil {
		s.DirOpens++
	}
}

func (s *OpenStats) enumOpen() {
	if s != nil {
		s.EnumOpens++
	}
}

func (s *OpenStats) fileOpen() {
	if s != nil {
		s.FileOpens++
	}
}

func (s *OpenStats) ancestor() {
	if s != nil {
		s.AncestorChecks++
	}
}

func (s *OpenStats) entryCheck() {
	if s != nil {
		s.EntryChecks++
	}
}
