# Benchmark baselines

`baseline-0.8.json` holds timings for `scripts/benchmark_large_graphs.py` on the
0.8 code (SQLite ledger, local scheduler, one chain per subject with a final
fan-in), recorded before cross-subject `needs:` (#231) and strategies (#232).

All times are wall-clock seconds and include about 1.6 s of interpreter and import
startup, which is reported separately as `startup`. They come from one 4-core
machine, so compare runs from the same machine, not absolute numbers.

To check a change against the baseline, run the same sizes and compare:

    python scripts/benchmark_large_graphs.py --analyses 100 1000 --subjects 1 10 100 --output new.json
    python scripts/benchmark_large_graphs.py --analyses 3000 --subjects 1000 --output new-prod.json
    python scripts/benchmark_large_graphs.py --compare scripts/benchmarks/baseline-0.8.json new.json

`--compare` exits non-zero if any operation is slower than `--tolerance`
(default 1.25x) times the baseline.

## Results: 0.8 and the 0.9 development branch

`current-0.9-dev.json` has the same cases on `main` after the performance work in
#251, #252, #254, #255, #256, #258 and #260, with event git repositories off by default
(#253). It adds two cases, 5000 analyses in one subject and over 1000 subjects, which the
0.8 code could not run in a reasonable time. Seconds, from one 4-core machine, each
including about 1.5 s of interpreter startup:

| analyses x subjects | apply | build | submit | monitor | report |
|---|---|---|---|---|---|
| 100 x 1 | 5.4 -> 2.0 | 2.1 -> 1.4 | 2.3 -> 1.7 | 1.9 -> 1.6 | 1.7 -> 1.6 |
| 100 x 10 | 2.6 -> 2.2 | 2.8 -> 1.4 | 1.6 -> 1.5 | 1.8 -> 1.6 | 1.8 -> 1.5 |
| 100 x 100 | 7.5 -> 2.9 | 13.5 -> 1.5 | 1.7 -> 1.5 | 1.9 -> 1.9 | 1.8 -> 1.5 |
| 1000 x 1 | 700 -> 7.8 | 30.6 -> 2.0 | 53.6 -> 1.9 | 32.4 -> 2.0 | 7.9 -> 1.9 |
| 1000 x 10 | 38.0 -> 8.1 | 6.3 -> 2.3 | 7.1 -> 2.0 | 5.4 -> 2.5 | 2.7 -> 2.3 |
| 1000 x 100 | 35.7 -> 8.4 | 14.4 -> 1.8 | 2.9 -> 2.0 | 3.1 -> 2.8 | 2.6 -> 2.1 |
| 3000 x 1000 | 948 -> 27.8 | 134 -> 3.5 | 4.8 -> 3.4 | 9.4 -> 7.6 | 4.2 -> 3.5 |
| 5000 x 1 | 39.7 | 10.3 | 11.0 | 10.4 | 10.8 |
| 5000 x 1000 | 35.7 | 4.4 | 4.1 | 9.4 | 4.2 |

The in-process `update_graph` and `update_event` timings are in the JSON. The first
fell from 1.2 s to 0.03 s at 1000 x 1; the second is unchanged (about 0.1 s at
1000 x 10, 1.8-2.0 s at 3000 x 1000). `--compare` flags `update_event` at 1000 x 10
(0.102 s -> 0.139 s, 1.37x); repeated runs gave 0.10, 0.09 and 0.10 s, so that is noise
in a 0.1 s measurement and not a slowdown.

Two things changed between the files besides the code. The 0.8 `build` at many subjects
includes creating a git repository for each event, which was the default then; the 0.9
default is off (#253). And the 5000-analysis cases have no 0.8 figure to compare with.
