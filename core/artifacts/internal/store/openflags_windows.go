//go:build windows

package store

// nonblockOpen is zero on Windows, where opening a named pipe never blocks on a
// missing peer the way a darwin FIFO open does.
const nonblockOpen = 0
