#!/usr/bin/env python
"""
Verify that analysis telemetry was actually recorded during a real
end-to-end monitor run.

This is not a pytest test - it's a CI verification script, run after the
real pipelines in a workflow (HTCondor or Slurm) have been built, submitted,
and monitored to completion, following the same pattern as
tests/verify_pipelines.py and (on the labeller branch) tests/verify_labels.py.
Mocked unit tests already cover asimov.telemetry's own logic in isolation
(tests/test_telemetry.py); this checks that the real monitor loop actually
wires it up end-to-end, against whichever scheduler the workflow configured.
"""

import json
import os
import sys

from asimov import current_ledger as ledger


def _telemetry_events(rundir):
    path = os.path.join(rundir, "telemetry.jsonl")
    if not os.path.isfile(path):
        return None
    events = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def _check_analysis(label, analysis):
    """Check one analysis's telemetry. Returns (has_error, is_test_pipeline)."""
    pipeline_str = str(analysis.pipeline).lower()
    is_test_pipeline = "testpipeline" in pipeline_str

    print(f"\nChecking {label}")
    print(f"  Pipeline: {analysis.pipeline}")
    print(f"  Status: {analysis.status}")

    rundir = getattr(analysis, "rundir", None)
    if not rundir:
        print("  No run directory - nothing to check")
        return (is_test_pipeline, is_test_pipeline)  # missing rundir is an error only for test pipelines

    events = _telemetry_events(rundir)
    if events is None:
        print(f"  ✗ No telemetry.jsonl found in {rundir}")
        return (is_test_pipeline, is_test_pipeline)

    event_types = [e.get("event_type") for e in events]
    print(f"  telemetry.jsonl: {len(events)} event(s), types={event_types}")

    error = False
    if is_test_pipeline:
        if "status_change" not in event_types:
            print("  ✗ Expected at least one status_change event, found none")
            error = True
        else:
            print("  ✓ Found status_change event")

        if "resource_snapshot" in event_types:
            print("  ✓ Found resource_snapshot event (scheduler accounting was available)")
        else:
            print("  (no resource_snapshot event - fine if scheduler accounting wasn't ready in time)")

    return (error, is_test_pipeline)


def verify_telemetry():
    print("Verifying analysis telemetry...")

    analyses_checked = 0
    test_pipelines_checked = 0
    errors = []

    for analysis in ledger.project_analyses:
        analyses_checked += 1
        has_error, is_test = _check_analysis(f"project analysis: {analysis.name}", analysis)
        if is_test:
            test_pipelines_checked += 1
        if has_error:
            errors.append(f"project_analyses/{analysis.name}")

    for event in ledger.get_event(None):
        for production in event.productions:
            analyses_checked += 1
            has_error, is_test = _check_analysis(
                f"event analysis: {event.name}/{production.name}", production
            )
            if is_test:
                test_pipelines_checked += 1
            if has_error:
                errors.append(f"{event.name}/{production.name}")

    print("\n" + "=" * 60)
    print("TELEMETRY VERIFICATION SUMMARY")
    print("=" * 60)
    print(f"Total analyses checked: {analyses_checked}")
    print(f"Test-pipeline analyses checked: {test_pipelines_checked}")
    print(f"Errors: {len(errors)}")

    if errors:
        print("\nAnalyses missing expected telemetry:")
        for name in errors:
            print(f"  - {name}")
        print("\n✗ Telemetry verification FAILED")
        return 1

    if test_pipelines_checked == 0:
        print("\n✗ No test-pipeline analyses were found to check at all")
        return 1

    print("\n✓ Telemetry verification PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(verify_telemetry())
