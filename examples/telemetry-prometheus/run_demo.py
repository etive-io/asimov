#!/usr/bin/env python
"""
Drive a couple of real asimov analyses to completion with the Prometheus
telemetry sink enabled, so there's something real to look at in Grafana.

This uses the real asimov CLI throughout (asimov init/apply/manage/monitor -
exactly the commands you'd run by hand), configured to run jobs via
LocalProcessScheduler so the demo needs nothing beyond Docker (no real
HTCondor or Slurm cluster required). Run `docker compose up -d` in this
directory first - see README.md.
"""

import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.join(HERE, "demo-project")
PUSHGATEWAY_URL = os.environ.get(
    "ASIMOV_PROMETHEUS_PUSHGATEWAY_URL", "http://localhost:9091"
)


def run(*args, **kwargs):
    print(f"$ {' '.join(args)}")
    kwargs.setdefault("check", True)
    kwargs.setdefault("cwd", PROJECT_DIR)
    return subprocess.run(args, **kwargs)


def main():
    if os.path.isdir(PROJECT_DIR):
        import shutil
        shutil.rmtree(PROJECT_DIR)
    os.makedirs(PROJECT_DIR)

    os.environ["ASIMOV_PROMETHEUS_PUSHGATEWAY_URL"] = PUSHGATEWAY_URL
    os.environ.setdefault("ASIMOV_TESTING", "1")

    # Scoped to this script's own process tree via environment variables -
    # deliberately NOT `git config --global`, which would overwrite your
    # real git identity on disk for every repo on this machine, not just
    # this throwaway demo project.
    os.environ.setdefault("GIT_AUTHOR_NAME", "Telemetry demo")
    os.environ.setdefault("GIT_AUTHOR_EMAIL", "you@example.com")
    os.environ.setdefault("GIT_COMMITTER_NAME", "Telemetry demo")
    os.environ.setdefault("GIT_COMMITTER_EMAIL", "you@example.com")

    print(f"Pushing telemetry to {PUSHGATEWAY_URL}\n")

    # --root must be explicit: `asimov init` otherwise defaults to the cwd
    # it was launched from (HERE), not PROJECT_DIR.
    run("asimov", "init", "Telemetry demo", "--root", PROJECT_DIR, "--engine", "yamlfile", cwd=HERE)

    run("asimov", "configuration", "update", "scheduler/type", "local")
    run("asimov", "apply", "-f", os.path.join(HERE, "config.yaml"))
    run("asimov", "apply", "-f", os.path.join(HERE, "event.yaml"))
    run("asimov", "apply", "-f", os.path.join(HERE, "analysis.yaml"), "-e", "GW150914_095045")
    run("asimov", "apply", "-f", os.path.join(HERE, "analysis2.yaml"), "-e", "GW150914_095045")

    run("asimov", "manage", "build", "submit")

    # The submitted jobs sleep for 2s before writing their results file, so
    # a handful of monitor cycles is enough to see them go running -> finished
    # (a status_change event) and pick up a resource_snapshot from
    # LocalProcessScheduler.collect_history() along the way.
    print("\nWaiting for the local jobs to complete (they take a few seconds)...")
    for _ in range(6):
        time.sleep(2)
        run("asimov", "monitor")

    print(
        "\nDone. Telemetry has been pushed to the Pushgateway.\n"
        f"  - Pushgateway: {PUSHGATEWAY_URL}\n"
        "  - Prometheus:  http://localhost:9090/graph?g0.expr=asimov_analysis_event\n"
        "  - Grafana:     http://localhost:3000/d/asimov-telemetry\n"
        f"\nLocal telemetry.jsonl files are also under {PROJECT_DIR}/working/"
    )


if __name__ == "__main__":
    sys.exit(main())
