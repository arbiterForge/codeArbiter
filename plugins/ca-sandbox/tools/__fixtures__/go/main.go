// Minimal ca-sandbox go fixture entry point (AC-07).
//
// Std-lib only (no external module to fetch) so nixpacks — or the offline build
// path — produces a runnable image with no network. It prints a stable marker the
// multistack test can match to prove the built image actually runs.
package main

import "fmt"

func main() {
	fmt.Println("GO_FIXTURE OK=true")
}
