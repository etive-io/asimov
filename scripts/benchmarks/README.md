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
