#!/usr/bin/env python
"""
Benchmark asimov on large synthetic ledgers (issue #242).

For each (analyses, subjects) pair the script builds a fresh project on the
SQLite ledger, fills it from one generated blueprint, and times the commands
which dominate a production monitoring cycle:

``startup`` (the cost of just starting asimov, to subtract from the rest),
``apply``, ``manage build``, ``manage submit`` (dry run), ``monitor``,
``report html``, plus two in-process timings, ``update_graph`` (the per-subject
dependency-graph rebuild which ``get_all_latest`` runs on every pass) and
``update_event`` (the per-subject ledger write which ``monitor`` runs).

``manage submit --dryrun`` prints nothing for these analyses, but it still
rebuilds every subject's dependency graph twice (``get_all_latest``), which is
the cost of interest.

Each analysis is a no-op ``simpletestpipeline``.  Within a subject the
analyses form a chain, and the last one is a fan-in which needs every other
analysis in the subject (``--shape chain-fanin``), or a plain chain
(``--shape chain``).

This is deliberately not part of the test suite: the larger sizes take
minutes to hours.  Run it on demand or from a scheduled job.

Examples
--------
A quick smoke test::

    python scripts/benchmark_large_graphs.py --analyses 100 --subjects 1 10

The compatibility baseline from #242 (about 1000 subjects, 3000 analyses)::

    python scripts/benchmark_large_graphs.py --analyses 3000 --subjects 1000 \\
        --output baseline-0.8.json

Compare two result files::

    python scripts/benchmark_large_graphs.py --compare baseline-0.8.json new.json
"""

import argparse
import configparser
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time

import yaml

OPERATIONS = (
    "startup",
    "apply",
    "build",
    "submit",
    "monitor",
    "report",
    "update_graph",
    "update_event",
)

# Run inside the project directory, in a fresh interpreter, because asimov
# opens the project ledger from the working directory when it is imported.
IN_PROCESS_TIMINGS = r"""
import json, time
import asimov

ledger = asimov.current_ledger
events = ledger.get_event()
out = {}

t = time.perf_counter()
for event in events:
    event.update_graph()
out["update_graph"] = time.perf_counter() - t

t = time.perf_counter()
for event in events:
    ledger.update_event(event)
out["update_event"] = time.perf_counter() - t

out["subjects"] = len(events)
out["analyses"] = sum(len(event.productions) for event in events)
print("BENCHMARK-RESULT " + json.dumps(out))
"""


def split_evenly(total, parts):
    """Split ``total`` into ``parts`` integers which differ by at most one."""
    base, extra = divmod(total, parts)
    return [base + (1 if i < extra else 0) for i in range(parts)]


def make_blueprint(analyses, subjects, shape):
    """Return the blueprint documents for a synthetic project."""
    documents = []
    for s, count in enumerate(split_evenly(analyses, subjects)):
        subject = f"subject{s:04d}"
        documents.append(
            {
                "kind": "subject",
                "name": subject,
                "event time": 1126259462.391 + s,
                "interferometers": ["H1", "L1"],
            }
        )
        names = [f"step{a:04d}" for a in range(count)]
        for a, name in enumerate(names):
            document = {
                "kind": "analysis",
                "name": name,
                "event": subject,
                "pipeline": "simpletestpipeline",
                "status": "ready",
            }
            if a > 0:
                if shape == "chain-fanin" and a == count - 1 and count > 2:
                    document["needs"] = names[:a]
                else:
                    document["needs"] = [names[a - 1]]
            documents.append(document)
    return documents


def run_command(command, cwd, timeout):
    """Run a command and return ``(seconds, returncode, output)``."""
    start = time.perf_counter()
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
        )
        return time.perf_counter() - start, result.returncode, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return None, None, "timeout"


def asimov_command(*arguments):
    """The asimov CLI belonging to the interpreter running this script."""
    return [os.path.join(os.path.dirname(sys.executable), "asimov"), *arguments]


def benchmark_case(analyses, subjects, shape, workdir, timeout, keep):
    """Time every operation for one project size."""
    root = tempfile.mkdtemp(prefix=f"bench-{analyses}x{subjects}-", dir=workdir)
    timings = {}
    notes = {}
    try:
        seconds, code, output = run_command(
            asimov_command("init", "Benchmark", "--root", root), root, timeout
        )
        if code != 0:
            raise RuntimeError(f"asimov init failed: {output[-500:]}")

        # Short-lived jobs: avoid needing an HTCondor schedd for the monitor.
        conf_path = os.path.join(root, ".asimov", "asimov.conf")
        conf = configparser.ConfigParser()
        conf.read(conf_path)
        if not conf.has_section("scheduler"):
            conf.add_section("scheduler")
        conf.set("scheduler", "type", "local")
        with open(conf_path, "w") as handle:
            conf.write(handle)

        blueprint = os.path.join(root, "blueprint.yaml")
        with open(blueprint, "w") as handle:
            yaml.safe_dump_all(make_blueprint(analyses, subjects, shape), handle)

        steps = {
            # Interpreter and import cost, so it can be subtracted from the rest.
            "startup": asimov_command("--help"),
            "apply": asimov_command("apply", "-f", blueprint),
            "build": asimov_command("manage", "build", "--dryrun"),
            "submit": asimov_command("manage", "submit", "--dryrun"),
            "monitor": asimov_command("monitor"),
            "report": asimov_command("report", "html"),
        }
        for name, command in steps.items():
            seconds, code, output = run_command(command, root, timeout)
            timings[name] = seconds
            if code not in (0, None):
                notes[name] = f"exit {code}: {output[-300:].strip()}"
            elif code is None:
                notes[name] = "timeout"
            if name == "apply" and code != 0:
                break  # nothing else is meaningful without a filled ledger

        seconds, code, output = run_command(
            [sys.executable, "-c", IN_PROCESS_TIMINGS], root, timeout
        )
        for line in output.splitlines():
            if line.startswith("BENCHMARK-RESULT "):
                result = json.loads(line[len("BENCHMARK-RESULT "):])
                timings["update_graph"] = result["update_graph"]
                timings["update_event"] = result["update_event"]
                notes["loaded"] = f"{result['analyses']} analyses in {result['subjects']} subjects"
        if "update_graph" not in timings:
            notes["in_process"] = "timeout" if code is None else output[-300:].strip()
    finally:
        if not keep:
            shutil.rmtree(root, ignore_errors=True)
        else:
            notes["kept"] = root
    return {
        "analyses": analyses,
        "subjects": subjects,
        "shape": shape,
        "timings": timings,
        "notes": notes,
    }


def environment_summary():
    """Details needed to compare results from different machines or versions."""
    try:
        import asimov

        version = getattr(asimov, "__version__", "unknown")
    except Exception:
        version = "unknown"
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        ).stdout.strip()
    except Exception:
        commit = "unknown"
    return {
        "asimov": version,
        "commit": commit,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpus": os.cpu_count(),
    }


def format_seconds(value):
    return "timeout" if value is None else f"{value:9.2f}"


def print_table(results):
    header = f"{'analyses':>9} {'subjects':>9} " + " ".join(f"{op:>12}" for op in OPERATIONS)
    print(header)
    print("-" * len(header))
    for case in results:
        row = " ".join(
            f"{format_seconds(case['timings'].get(op)) if op in case['timings'] else '-':>12}"
            for op in OPERATIONS
        )
        print(f"{case['analyses']:>9} {case['subjects']:>9} {row}")
    for case in results:
        for key, note in case["notes"].items():
            if key not in ("loaded",):
                print(f"  [{case['analyses']}x{case['subjects']}] {key}: {note}")


def compare(paths, tolerance):
    """Print the ratio of each timing in the second file to the first."""
    first, second = (json.load(open(path)) for path in paths)
    index = {(c["analyses"], c["subjects"], c["shape"]): c for c in first["results"]}
    worst = 1.0
    print(f"{'analyses':>9} {'subjects':>9} " + " ".join(f"{op:>12}" for op in OPERATIONS))
    for case in second["results"]:
        base = index.get((case["analyses"], case["subjects"], case["shape"]))
        if base is None:
            continue
        cells = []
        for op in OPERATIONS:
            a, b = base["timings"].get(op), case["timings"].get(op)
            if a and b:
                ratio = b / a
                worst = max(worst, ratio)
                cells.append(f"{ratio:11.2f}x")
            else:
                cells.append(f"{'-':>12}")
        print(f"{case['analyses']:>9} {case['subjects']:>9} " + " ".join(cells))
    print(f"\nworst slowdown: {worst:.2f}x (tolerance {tolerance:.2f}x)")
    return 0 if worst <= tolerance else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--analyses", type=int, nargs="+", default=[100],
                        help="Total number of analyses (default: 100).")
    parser.add_argument("--subjects", type=int, nargs="+", default=[1, 10],
                        help="Number of subjects (default: 1 10).")
    parser.add_argument("--shape", choices=["chain", "chain-fanin"], default="chain-fanin")
    parser.add_argument("--timeout", type=int, default=1800,
                        help="Seconds allowed per operation (default: 1800).")
    parser.add_argument("--workdir", default=None,
                        help="Directory to build projects in (default: system temp).")
    parser.add_argument("--keep", action="store_true", help="Keep the generated projects.")
    parser.add_argument("--output", help="Write the results to this JSON file.")
    parser.add_argument("--compare", nargs=2, metavar=("BASELINE", "NEW"),
                        help="Compare two result files instead of running.")
    parser.add_argument("--tolerance", type=float, default=1.25,
                        help="Largest acceptable slowdown with --compare (default: 1.25).")
    args = parser.parse_args(argv)

    if args.compare:
        return compare(args.compare, args.tolerance)

    results = []
    for analyses in args.analyses:
        for subjects in args.subjects:
            if subjects > analyses:
                continue
            print(f"== {analyses} analyses over {subjects} subjects ({args.shape})", flush=True)
            results.append(
                benchmark_case(analyses, subjects, args.shape, args.workdir,
                               args.timeout, args.keep)
            )
            print_table(results[-1:])

    print()
    print_table(results)
    if args.output:
        with open(args.output, "w") as handle:
            json.dump({"environment": environment_summary(), "results": results}, handle, indent=2)
        print(f"\nWrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
