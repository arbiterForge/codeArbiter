package store

import (
	"fmt"
	"sort"
	"strings"
)

// SupportedBackends declares, per GOOS, the native storage backend this
// source builds. It is a source capability only: whether a package for that
// platform was natively tested or released is a separate qualification record.
var SupportedBackends = map[string]string{
	"darwin":  "darwin-osroot-flock",
	"linux":   "linux-openat-flock",
	"windows": "windows-osroot-lockfileex",
}

// unsupportedPlatformMessage is the bounded diagnostic for a GOOS with no
// declared backend. It names the actual platform and the declared backends.
func unsupportedPlatformMessage(goos string) string {
	names := make([]string, 0, len(SupportedBackends))
	for name := range SupportedBackends {
		names = append(names, name)
	}
	sort.Strings(names)
	return fmt.Sprintf("repository operations are unavailable on %s: this source declares no native storage backend for it (declared: %s); use a declared platform. Source declarations are not a release qualification", goos, strings.Join(names, ", "))
}
