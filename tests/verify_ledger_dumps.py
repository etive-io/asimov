#!/usr/bin/env python
"""
Verify the ledger dumps written by asimov's bundled testing pipelines.

Run from the root of a project in which the multi-event end-to-end scenario
has been applied and run (see .github/workflows/testing-pipelines.yml):

* two events, one of which has several analyses, reviewed differently
  (approved, rejected, never reviewed);
* an ``asimov apply --update`` of the first event *after* some of its
  analyses exist, followed by a further analysis;
* a subject analysis and a project analysis whose filters select only the
  approved analyses.

Every check that fails is reported, and the exit status is non-zero if any did.
"""

import glob
import json
import sys

from asimov import current_ledger as ledger
from asimov.pipelines.testing._dump import DUMP_FILENAME, ledger_dump

FIRST = "GW150914_095045"
SECOND = "GW151226_033853"

failures = []


def check(condition, message):
    print(f"  {'ok  ' if condition else 'FAIL'} {message}")
    if not condition:
        failures.append(message)


def load_dumps():
    dumps = {}
    for path in sorted(glob.glob(f"working/**/{DUMP_FILENAME}", recursive=True)):
        with open(path) as handle:
            dump = json.load(handle)
        dumps[dump["analysis"]["name"]] = dump
    return dumps


def encompassed(dump):
    return sorted(
        (item["subject"], item["name"]) for item in dump.get("encompassed analyses", [])
    )


def visible(dump):
    return {item["name"]: item for item in dump["visible analyses"]}


def current_analysis(subject, name):
    for analysis in ledger.get_event(subject)[0].productions:
        if analysis.name == name:
            return analysis
    raise KeyError(f"{subject}/{name}")


dumps = load_dumps()
print(f"Found {len(dumps)} ledger dumps: {', '.join(sorted(dumps))}")

expected = {
    "test-simple-pipeline",
    "test-simple-rejected",
    "test-simple-unreviewed",
    "test-simple-after-update",
    "test-simple-second-event",
    "test-subject-pipeline",
    "test-subject-approved",
    "test-project-pipeline",
    "test-project-approved",
}
print("\nEvery analysis wrote a dump")
check(expected <= set(dumps), f"missing dumps: {sorted(expected - set(dumps))}")

# ---------------------------------------------------------------------------
print("\nA simple analysis is dumped with the ledger information available to it")
simple = dumps["test-simple-pipeline"]
check(simple["analysis"]["pipeline"] == "SimpleTestPipeline", "pipeline is recorded")
check(simple["subjects"][0]["name"] == FIRST, "its subject is recorded")
check(
    simple["analysis"]["effective settings"]["data"]["segment length"] == 4,
    "effective settings include the settings inherited from the subject",
)
check("encompassed analyses" not in simple, "a simple analysis encompasses nothing")

# ---------------------------------------------------------------------------
print("\nOutputs of previous analyses are visible to later ones")
later = visible(dumps["test-simple-after-update"])
check("test-simple-pipeline" in later, "the earlier analysis is visible")
check(
    "results.dat" in [f["path"] for f in later["test-simple-pipeline"]["files"]],
    "... along with the files it produced",
)
check(
    SECOND not in {item["subject"] for item in later.values()},
    "analyses of another event are not visible to a simple analysis",
)

# ---------------------------------------------------------------------------
print("\nasimov apply --update changes what later analyses see, and only those")
after = dumps["test-simple-after-update"]
check(
    after["analysis"]["effective settings"]["data"]["segment length"] == 8,
    "the new analysis sees the updated segment length",
)
check(
    after["subjects"][0]["settings"]["data"]["segment length"] == 8,
    "... and the subject's updated settings",
)
check(
    simple["analysis"]["effective settings"]["data"]["segment length"] == 4,
    "the dump of an existing analysis still shows the old segment length",
)
now = ledger_dump(current_analysis(FIRST, "test-simple-pipeline"))
check(
    now["analysis"]["effective settings"]["data"]["segment length"] == 4,
    "... and so does the ledger, when it is reloaded",
)
check(
    now["subjects"][0]["settings"]["data"]["segment length"] == 8,
    "... while the subject itself has the new value",
)
check(
    now["analysis"]["effective settings"]["waveform"]
    == simple["analysis"]["effective settings"]["waveform"],
    "the existing analysis's waveform settings are unchanged",
)

# ---------------------------------------------------------------------------
print("\nA subject analysis encompasses exactly the analyses its filter selects")
approved = dumps["test-subject-approved"]
check(
    encompassed(approved) == [(FIRST, "test-simple-pipeline")],
    f"review: approved selects only the approved analysis (got {encompassed(approved)})",
)
check(
    {"test-simple-rejected", "test-simple-unreviewed"}
    <= set(visible(approved)),
    "the excluded analyses are still visible to it",
)
check(
    visible(approved)["test-simple-rejected"]["review status"] == "REJECTED",
    "... with their review status recorded",
)
by_needs = dumps["test-subject-pipeline"]
check(
    encompassed(by_needs) == [(FIRST, "test-simple-pipeline")],
    "an analysis naming its inputs with needs: lists them too",
)

# ---------------------------------------------------------------------------
print("\nA project analysis spans events and encompasses only approved analyses")
project = dumps["test-project-approved"]
check(
    [subject["name"] for subject in project["subjects"]] == [FIRST, SECOND],
    "both events are listed",
)
check(
    encompassed(project)
    == [(FIRST, "test-simple-pipeline"), (SECOND, "test-simple-second-event")],
    f"only the approved analyses are encompassed (got {encompassed(project)})",
)
check(
    {"test-simple-rejected", "test-simple-unreviewed", "test-simple-after-update"}
    <= set(visible(project)),
    "analyses it does not encompass are still visible to it",
)

print()
if failures:
    print(f"FAIL: {len(failures)} checks failed")
    sys.exit(1)
print("All ledger dump checks passed")
