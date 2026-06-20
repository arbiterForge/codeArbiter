// Minimal ca-sandbox node fixture entry point (AC-06).
//
// It imports a REAL dependency (is-odd) baked out-of-tree at /deps and prints a
// marker. The marker carries:
//   - DEP_OK=<bool> : that the baked dep resolved at runtime (require succeeded
//     AND its function returns the right answer), and
//   - SRC=<tag>     : a source-version tag the layering test edits IN the volume
//     to prove the in-place edit takes effect on re-run.
//
// The layering test seeds a named volume with this file, runs it once (expects
// SRC=original + DEP_OK=true), then rewrites SRC in the volume and re-runs
// (expects SRC=edited + DEP_OK=true — deps survive the edit).
const isOdd = require("is-odd");

const SRC = "original";
const depOk = isOdd(3) === true && isOdd(4) === false;

console.log(`NODE_FIXTURE SRC=${SRC} DEP_OK=${depOk}`);
