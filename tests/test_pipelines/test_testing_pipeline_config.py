"""
Tests for the configuration files asimov's bundled testing pipelines render.

Each testing pipeline puts a ``config.ini`` into its run directory when its
DAG is built, rendered from its template in ``asimov/configs``, and its job
prints that file and the ledger dump. These tests check that the file shows
what asimov should have given the analysis:

* settings come from the project's defaults for the pipeline, then the
  subject, then the analysis, each overriding the one before;
* a second analysis with the same pipeline but changed priors (a rerun) gets
  the new priors, and the first analysis's configuration does not change;
* subject and project analyses list the analyses they combine;
* the file ``asimov manage build`` made is the one the job gets.

Everything runs against both the YAML and the (default) SQLite ledgers.
"""

import configparser
import os
import subprocess
import unittest
from unittest.mock import patch

import yaml
from click.testing import CliRunner

from asimov.cli import manage
from asimov.pipelines.testing._config import CONFIG_FILENAME, UNSET

from .test_testing_pipeline_ledger_dump import (
    SUBJECT,
    LedgerDumpTestCase,
    analysis_blueprint,
    event_blueprint,
)

#: Project defaults for the simple testing pipeline only.
PIPELINE_DEFAULTS = yaml.safe_dump(
    {
        "kind": "configuration",
        "pipelines": {
            "simpletestpipeline": {
                "sampler": {"sampler": "testsampler"},
                "waveform": {"approximant": "DefaultApproximant"},
            }
        },
    }
)

#: Settings an analysis gives itself, overriding the subject's.
OVERRIDES = {
    "waveform": {"approximant": "IMRPhenomXPHM"},
    "likelihood": {"minimum frequency": {"H1": 25}},
}


def read_config(analysis):
    parser = configparser.ConfigParser(interpolation=None, delimiters=("=",))
    parser.optionxform = str
    with open(os.path.join(analysis.rundir, CONFIG_FILENAME)) as handle:
        parser.read_file(handle)
    return parser


def config_bytes(analysis):
    with open(os.path.join(analysis.rundir, CONFIG_FILENAME), "rb") as handle:
        return handle.read()


class ConfigTestCase(LedgerDumpTestCase):
    def build_config(self, analysis):
        analysis.pipeline.build_dag()
        return read_config(analysis)


# ---------------------------------------------------------------------------


class Precedence(ConfigTestCase):
    """Pipeline defaults, then the subject, then the analysis."""

    def setUp(self):
        super().setUp()
        self.apply(PIPELINE_DEFAULTS)
        self.apply(event_blueprint())

    def test_inherited_settings(self):
        self.apply(analysis_blueprint("plain"), event=SUBJECT)
        config = self.build_config(self.analysis(SUBJECT, "plain"))

        self.assertEqual(config["analysis"]["name"], "plain")
        self.assertEqual(config["analysis"]["subject"], SUBJECT)
        self.assertEqual(config["analysis"]["pipeline"], "SimpleTestPipeline")
        # From the project's defaults for this pipeline.
        self.assertEqual(config["sampler"]["sampler"], "testsampler")
        self.assertEqual(config["waveform"]["approximant"], "DefaultApproximant")
        # From the subject.
        self.assertEqual(config["data"]["segment length"], "4")
        self.assertEqual(config["data"]["interferometers"], "H1")
        self.assertEqual(config["likelihood"]["minimum frequency"], "H1: 20")
        self.assertEqual(config["priors"]["chirp mass.minimum"], "21.418182160215295")
        # Settings nobody gave are marked, not left out or rendered as None.
        self.assertEqual(config["data"]["channels"], UNSET)

    def test_analysis_settings_override_the_subject(self):
        self.apply(analysis_blueprint("override", **OVERRIDES), event=SUBJECT)
        config = self.build_config(self.analysis(SUBJECT, "override"))

        self.assertEqual(config["waveform"]["approximant"], "IMRPhenomXPHM")
        self.assertEqual(config["likelihood"]["minimum frequency"], "H1: 25")
        self.assertEqual(
            config["effective settings"]["likelihood.minimum frequency.H1"], "25"
        )
        # What it does not override is still inherited.
        self.assertEqual(config["data"]["segment length"], "4")
        self.assertEqual(config["sampler"]["sampler"], "testsampler")

    def test_overrides_do_not_leak_into_other_analyses(self):
        self.apply(analysis_blueprint("override", **OVERRIDES), event=SUBJECT)
        self.apply(analysis_blueprint("plain"), event=SUBJECT)
        self.build_config(self.analysis(SUBJECT, "override"))
        config = self.build_config(self.analysis(SUBJECT, "plain"))

        self.assertEqual(config["waveform"]["approximant"], "DefaultApproximant")
        self.assertEqual(config["likelihood"]["minimum frequency"], "H1: 20")

    def test_other_pipelines_do_not_get_these_defaults(self):
        self.apply(analysis_blueprint("other", "simpletestpipelineb"), event=SUBJECT)
        dump = self.build(self.analysis(SUBJECT, "other"))
        effective = dump["analysis"]["effective settings"]
        self.assertNotEqual((effective.get("sampler") or {}).get("sampler"), "testsampler")
        self.assertNotEqual(
            (effective.get("waveform") or {}).get("approximant"), "DefaultApproximant"
        )


class PrecedenceSQLite(Precedence):
    engine = "sqlite"


# ---------------------------------------------------------------------------


class Rerun(ConfigTestCase):
    """A second analysis with the same pipeline, and changed priors."""

    NEW_PRIORS = {"chirp mass": {"minimum": 25.0, "maximum": 35.0}}

    def setUp(self):
        super().setUp()
        self.apply(event_blueprint())
        self.apply(analysis_blueprint("original"), event=SUBJECT)
        self.original = self.complete(SUBJECT, "original")
        self.original_config = config_bytes(self.original)
        self.apply(
            analysis_blueprint("rerun", needs=["original"], priors=self.NEW_PRIORS),
            event=SUBJECT,
        )

    def test_rerun_has_the_new_priors(self):
        config = self.build_config(self.analysis(SUBJECT, "rerun"))
        self.assertEqual(config["priors"]["chirp mass.minimum"], "25.0")
        self.assertEqual(config["priors"]["chirp mass.maximum"], "35.0")
        # Priors it does not change are still those of the subject.
        self.assertEqual(config["priors"]["amplitude order"], "1")

    def test_original_keeps_its_priors(self):
        self.build_config(self.analysis(SUBJECT, "rerun"))
        original = self.analysis(SUBJECT, "original")
        self.assertEqual(config_bytes(original), self.original_config)
        # Rebuilding it from the ledger gives the old priors too.
        config = self.build_config(original)
        self.assertEqual(config["priors"]["chirp mass.minimum"], "21.418182160215295")
        self.assertEqual(config["priors"]["chirp mass.maximum"], "41.97447913941358")

    def test_rerun_can_see_the_original(self):
        self.analysis(SUBJECT, "rerun").pipeline.build_dag()
        dump = self.read_dump(self.analysis(SUBJECT, "rerun"))
        visible = {item["name"]: item for item in dump["visible analyses"]}
        self.assertTrue(visible["original"]["dependency"])
        self.assertIn(CONFIG_FILENAME, [f["path"] for f in visible["original"]["files"]])


class RerunSQLite(Rerun):
    engine = "sqlite"


# ---------------------------------------------------------------------------


class Combined(ConfigTestCase):
    """Subject and project analyses list what they combine."""

    A = "EventA"
    B = "EventB"

    def setUp(self):
        super().setUp()
        self.apply(event_blueprint(self.A))
        self.apply(event_blueprint(self.B))
        for subject, name, review in [
            (self.A, "a-approved", "approved"),
            (self.A, "a-rejected", "rejected"),
            (self.B, "b-approved", "approved"),
        ]:
            self.apply(analysis_blueprint(name), event=subject)
            self.complete(subject, name)
            self.review(subject, name, review)

    def test_subject_analysis(self):
        self.apply(
            analysis_blueprint(
                "combine", "subjecttestpipeline", analyses=["review: approved"]
            ),
            event=self.A,
        )
        config = self.build_config(self.analysis(self.A, "combine"))

        self.assertEqual(config["analysis"]["subject"], self.A)
        self.assertEqual(config["analyses"]["count"], "1")
        self.assertIn(f"{self.A}/a-approved", config["analyses"])
        self.assertIn("review: APPROVED", config["analyses"][f"{self.A}/a-approved"])
        self.assertNotIn(f"{self.A}/a-rejected", config["analyses"])

    def test_project_analysis(self):
        self.apply(
            yaml.safe_dump(
                {
                    "kind": "projectanalysis",
                    "name": "population",
                    "pipeline": "projecttestpipeline",
                    "status": "ready",
                    "subjects": [self.A, self.B],
                    "analyses": ["review: approved"],
                }
            )
        )
        config = self.build_config(self.project_analysis("population"))

        self.assertEqual(config["subjects"]["names"], f"{self.A}, {self.B}")
        self.assertEqual(config["analyses"]["count"], "2")
        self.assertEqual(
            sorted(key for key in config["analyses"] if key != "count"),
            [f"{self.A}/a-approved", f"{self.B}/b-approved"],
        )


class CombinedSQLite(Combined):
    engine = "sqlite"


# ---------------------------------------------------------------------------


class JobOutput(ConfigTestCase):
    """The job prints its configuration and the ledger dump."""

    def setUp(self):
        super().setUp()
        self.apply(event_blueprint())
        self.apply(analysis_blueprint("first", **OVERRIDES), event=SUBJECT)

    def test_job_prints_config_and_dump(self):
        analysis = self.analysis(SUBJECT, "first")
        analysis.pipeline.build_dag()
        result = subprocess.run(
            ["bash", "test_job.sh"],
            cwd=analysis.rundir,
            capture_output=True,
            text=True,
            check=True,
        )
        out = result.stdout
        for marker in ("config.ini", "ledger_dump.json"):
            self.assertIn(f"===== BEGIN {marker} =====", out)
            self.assertIn(f"===== END {marker} =====", out)
        config = out.split("===== BEGIN config.ini =====")[1].split("===== END")[0]
        self.assertIn("approximant = IMRPhenomXPHM", config)
        dump = out.split("===== BEGIN ledger_dump.json =====")[1].split("===== END")[0]
        self.assertIn('"approximant": "IMRPhenomXPHM"', dump)
        self.assertTrue(os.path.exists(os.path.join(analysis.rundir, "results.dat")))

    def test_dryrun_writes_no_config(self):
        analysis = self.analysis(SUBJECT, "first")
        analysis.pipeline.build_dag(dryrun=True)
        self.assertFalse(os.path.exists(os.path.join(analysis.rundir, CONFIG_FILENAME)))


class ManageBuild(ConfigTestCase):
    """The configuration ``asimov manage build`` made is the one staged."""

    def setUp(self):
        super().setUp()
        self.apply(event_blueprint())
        self.apply(analysis_blueprint("first", **OVERRIDES), event=SUBJECT)

    def test_built_config_is_staged(self):
        with patch("asimov.cli.manage.ledger", new=self.ledger()):
            result = CliRunner().invoke(manage.build, [])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Production config first created", result.output)

        analysis = self.analysis(SUBJECT, "first")
        built = analysis.event.repository.find_prods(analysis.name, analysis.category)[0]
        self.assertTrue(os.path.exists(built), built)

        analysis.pipeline.build_dag()
        with open(built, "rb") as handle:
            self.assertEqual(config_bytes(analysis), handle.read())
        with open(os.path.join(analysis.rundir, "test_job.sh")) as handle:
            self.assertIn(f"# source: {built}", handle.read())
        self.assertEqual(read_config(analysis)["waveform"]["approximant"], "IMRPhenomXPHM")


class ManageBuildSQLite(ManageBuild):
    engine = "sqlite"


if __name__ == "__main__":
    unittest.main()
