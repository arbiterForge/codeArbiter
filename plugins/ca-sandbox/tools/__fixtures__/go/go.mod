// Minimal ca-sandbox go fixture module (AC-07).
//
// go.mod is the go DEPENDENCY MANIFEST the dephash hashes. It pins the module
// path and the go toolchain line; a change to either is a dep change that bumps
// the dephash and forces a rebuild (AC-05 model). The fixture is std-lib only so
// it builds OFFLINE — no module download — keeping the multistack build hermetic.
module ca-sbx-fixture-go

go 1.21
