# State engine catalog scan measurement — 2026-10-30

Issue: #1042. Host: Windows amd64, AMD Ryzen 9 9950X3D, Go 1.27.1.
These are warm local measurements with `go test -run '^$' -bench
'^BenchmarkCatalogScan/artifacts-(20|200|1024)$' -benchtime=5x -count=1
-benchmem` in `core/artifacts`. Baseline is `d37eaced` (the clean main before
the candidate); candidate is the anchored catalog scan in this change. Each
sample includes view parsing and verification. The five iterations are enough
to identify the large path-check reduction, not a stable latency guarantee.

| Artifacts | Baseline ms/op | Candidate ms/op | Baseline ancestor checks/op | Candidate ancestor checks/op | File opens/op, both |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 20 | 54.04 | 51.92 | 124 | 5 | 20 |
| 200 | 528.00 | 485.70 | 1,204 | 5 | 200 |
| 1,024 | 2,734.48 | 2,471.63 | 6,148 | 5 | 1,024 |

The candidate opens each catalog directory once, reads listed HTML through
that anchor, checks each possible Markdown sibling at read time, and verifies
the directory name still points to the anchor. It retains portable path
validation, symlink/reparse refusal, view verification, duplicate-ID checks,
and the 1,024 artifact/64 MiB caps. Repository, operations, and store Go tests
and vet passed locally. A separate source review found no remaining parity
issue after two safety corrections.

A Windows CPU profile of the candidate's 200-artifact benchmark (`-benchtime=5x
-cpuprofile`) attributed about 88% of its samples to `Scan`, with about 79%
under the per-file anchored open path (`os.Root.OpenFile`/Windows `NtCreateFile`).
The benchmark setup also appears in the profile, so these percentages describe
this run, not a universal production mix. The scan still exceeds the fixed
two-second lock wait at the maximum artifact count; this change does not close
that contention risk.

The unchanged journal benchmark at 200 retained journals, `-benchtime=3x`,
measured 62.21 ms/op and 2.07 MB/op for pending validation, and 114.52 ms/op
and 3.61 MB/op for infrastructure validation. This candidate does not alter
journal recovery or history retention. Outline page assembly was addressed
separately in PR #1050. #1042 remains open for lock contention, journal scaling,
and end-to-end page/operation measurements.
