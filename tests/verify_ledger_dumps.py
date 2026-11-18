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
  approved analyses;
* project defaults for the simple testing pipeline, an analysis which
  overrides settings it would inherit, and a rerun of the first analysis with
  narrower priors.

As well as the ledger dumps, it checks the configuration file each testing
pipeline renders (``config.ini``) and the job's standard output, which prints
both.

Every check that fails is reported, and the exit status is non-zero if any did.
"""

import configparser
import glob
import json
import os
import sys

from asimov import current_ledger as ledger
from asimov.pipelines.testing._config import CONFIG_FILENAME, built_config_path
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


def load_configs():
    """Every rendered configuration, by analysis name, with its run directory."""
    configs = {}
    for path in sorted(glob.glob(f"working/**/{CONFIG_FILENAME}", recursive=True)):
        parser = configparser.ConfigParser(interpolation=None, delimiters=("=",))
        parser.optionxform = str
        with open(path) as handle:
            parser.read_file(handle)
        configs[parser["analysis"]["name"]] = (parser, os.path.dirname(path))
    return configs


def job_output(rundir):
    """The job's standard output (HTCondor, Slurm or local), or None."""
    for pattern in ("test*_job.out", "slurm_*.out", "local_job.out"):
        found = sorted(glob.glob(os.path.join(rundir, pattern)))
        if found:
            with open(found[-1]) as handle:
                return handle.read()
    return None


def printed(output, filename):
    """The text the job printed between the markers for ``filename``."""
    begin, end = f"===== BEGIN {filename} =====", f"===== END {filename} ====="
    if not output or begin not in output or end not in output:
        return None
    lines = output.split(begin, 1)[1].split(end, 1)[0].strip("\n").splitlines()
    return "\n".join(line for line in lines if not line.startswith("# source:"))


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
    "test-simple-override",
    "test-simple-rerun",
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

# ---------------------------------------------------------------------------
# Configuration files and job output
# ---------------------------------------------------------------------------
configs = load_configs()
print(f"\nFound {len(configs)} configuration files: {', '.join(sorted(configs))}")

print("\nEvery analysis rendered a configuration file")
check(expected <= set(configs), f"missing configurations: {sorted(expected - set(configs))}")


def setting(name, section, key):
    try:
        return configs[name][0][section][key]
    except KeyError:
        return None


# ---------------------------------------------------------------------------
print("\nThe job got the configuration asimov manage build made, and printed it")
for name in sorted(expected & set(configs)):
    parser, rundir = configs[name]
    with open(os.path.join(rundir, CONFIG_FILENAME)) as handle:
        staged = handle.read()
    subject = FIRST if name != "test-simple-second-event" else SECOND
    analysis = None
    if name.startswith("test-project"):
        analysis = next((a for a in ledger.project_analyses if a.name == name), None)
    else:
        try:
            analysis = current_analysis(subject, name)
        except KeyError:
            pass
    built = built_config_path(analysis) if analysis is not None else None
    if built and os.path.exists(built):
        with open(built) as handle:
            check(handle.read() == staged, f"{name}: staged config.ini is the built one ({built})")
    else:
        check(False, f"{name}: asimov manage build left a configuration at {built}")
    output = job_output(rundir)
    check(output is not None, f"{name}: the job's standard output was found")
    check(
        printed(output, CONFIG_FILENAME) == staged.strip("\n"),
        f"{name}: the job printed its configuration",
    )
    dumped = printed(output, DUMP_FILENAME)
    try:
        dumped = json.loads(dumped) if dumped else None
    except ValueError:
        dumped = None
    check(
        dumped is not None and dumped["analysis"]["name"] == name,
        f"{name}: the job printed its ledger dump",
    )

# ---------------------------------------------------------------------------
print("\nSettings come from the pipeline defaults, then the subject, then the analysis")
check(setting("test-simple-pipeline", "sampler", "sampler") == "testsampler",
      "the project's default sampler for the pipeline is used")
check(setting("test-simple-pipeline", "waveform", "approximant") == "DefaultApproximant",
      "... and its default approximant")
check(setting("test-simple-pipeline", "data", "segment length") == "4",
      "the subject's segment length is used")
check(setting("test-simple-pipeline", "effective settings", "likelihood.minimum frequency.H1") == "20",
      "the subject's minimum frequency is used")
check(setting("test-simple-override", "waveform", "approximant") == "IMRPhenomXPHM",
      "an analysis's approximant overrides the pipeline default")
check(setting("test-simple-override", "effective settings", "likelihood.minimum frequency.H1") == "25",
      "an analysis's minimum frequency overrides the subject's")
check(setting("test-simple-override", "sampler", "sampler") == "testsampler",
      "... and what it does not override is still inherited")
check(setting("test-simple-unreviewed", "waveform", "approximant") == "DefaultApproximant",
      "the override does not leak into other analyses")
check(setting("test-subject-pipeline", "effective settings", "sampler.sampler") != "testsampler",
      "another pipeline does not get the simple pipeline's defaults")

# ---------------------------------------------------------------------------
print("\nA rerun with changed priors gets them, and the original keeps its own")
check(setting("test-simple-rerun", "priors", "chirp mass.minimum") == "25.0",
      "the rerun has the new chirp mass minimum")
check(setting("test-simple-rerun", "priors", "chirp mass.maximum") == "35.0",
      "... and the new maximum")
check(setting("test-simple-rerun", "priors", "amplitude order") == "1",
      "... and the priors it did not change")
check(setting("test-simple-pipeline", "priors", "chirp mass.minimum") == "21.418182160215295",
      "the original keeps its chirp mass minimum")
check(setting("test-simple-pipeline", "priors", "chirp mass.maximum") == "41.97447913941358",
      "... and its maximum")
rerun_visible = visible(dumps.get("test-simple-rerun", {"visible analyses": []}))
check(rerun_visible.get("test-simple-pipeline", {}).get("dependency") is True,
      "the rerun depends on the original")

# ---------------------------------------------------------------------------
print("\nasimov apply --update reaches the configuration of later analyses only")
check(setting("test-simple-after-update", "data", "segment length") == "8",
      "the analysis added afterwards has the new segment length")
check(setting("test-simple-pipeline", "data", "segment length") == "4",
      "the existing analysis's configuration still has the old one")

# ---------------------------------------------------------------------------
print("\nCombining analyses list what they combine in their configuration")
check(setting("test-subject-approved", "analyses", "count") == "1",
      "the subject analysis combines one analysis")
check(setting("test-subject-approved", "analyses", f"{FIRST}/test-simple-pipeline") is not None,
      "... the approved one")
check(setting("test-project-approved", "subjects", "names") == f"{FIRST}, {SECOND}",
      "the project analysis lists both events")
check(setting("test-project-approved", "analyses", "count") == "2",
      "... and combines two analyses")
for label in (f"{FIRST}/test-simple-pipeline", f"{SECOND}/test-simple-second-event"):
    check(setting("test-project-approved", "analyses", label) is not None, f"... including {label}")

print()
if failures:
    print(f"FAIL: {len(failures)} checks failed")
    sys.exit(1)
print("All ledger dump, configuration and job output checks passed")
