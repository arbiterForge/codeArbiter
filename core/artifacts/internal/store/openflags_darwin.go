//go:build darwin

package store

import "syscall"

// nonblockOpen makes every portable open non-blocking on darwin, so a FIFO
// planted in place of a listed file or directory cannot hang the open before the
// type and identity checks that follow refuse it. Regular files and directories
// ignore the flag.
const nonblockOpen = syscall.O_NONBLOCK
