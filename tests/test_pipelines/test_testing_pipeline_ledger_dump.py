"""
Tests for the ledger dumps written by asimov's bundled testing pipelines.

Each testing pipeline writes ``ledger_dump.json`` into its run directory when
its DAG is built. These tests check what that dump contains, and use it to
check that asimov hands analyses the right information:

* ``asimov apply --update`` must change what *later* analyses see without
  changing what analyses that already exist see;
* subject and project analyses must encompass exactly the analyses their
  ``needs:``/``analyses:`` filters select, across several events and several
  analyses per event.

Everything runs against both the YAML and the (default) SQLite ledgers.
"""

import json
import os
import shutil
import tempfile
import unittest
from copy import deepcopy

import yaml
from click.testing import CliRunner

from asimov.cli import project
from asimov.cli.application import apply_page
from asimov.pipelines.testing._dump import DUMP_FILENAME, ledger_dump
from asimov.project import Project
from asimov.review import ReviewMessage

BLUEPRINTS = os.path.join(os.path.dirname(__file__), "..", "test_blueprints")

SUBJECT = "GW150914_095045"


def event_blueprint(name=SUBJECT, **overrides):
    """The bundled GWOSC event blueprint, renamed and with settings overridden."""
    with open(os.path.join(BLUEPRINTS, "gwosc_event.yaml")) as handle:
        blueprint = yaml.safe_load(handle)
    blueprint["name"] = name
    blueprint["data"]["segment length"] = overrides.get("segment length", 4)
    blueprint["likelihood"]["reference frequency"] = overrides.get(
        "reference frequency", 20
    )
    return yaml.safe_dump(blueprint)


def analysis_blueprint(name, pipeline="simpletestpipeline", **extra):
    blueprint = {
        "kind": "analysis",
        "name": name,
        "pipeline": pipeline,
        "status": "ready",
    }
    blueprint.update(extra)
    return yaml.safe_dump(blueprint)


def assert_unchanged(test, before, after, path=""):
    """
    Assert every value in ``before`` is still present, unchanged, in ``after``.

    ``after`` may have gained keys: ``apply --update`` freezes the old
    event-level settings into existing analyses, which adds keys but must not
    alter any existing value.
    """
    if isinstance(before, dict):
        test.assertIsInstance(after, dict, path)
        for key, value in before.items():
            test.assertIn(key, after, f"{path}.{key} disappeared")
            assert_unchanged(test, value, after[key], f"{path}.{key}")
    else:
        test.assertEqual(before, after, f"{path} changed")


class LedgerDumpTestCase(unittest.TestCase):
    """A scratch project, driven the way the CLI drives it."""

    engine = "yamlfile"

    def setUp(self):
        self.cwd = os.getcwd()
        self.test_dir = tempfile.mkdtemp()
        os.chdir(self.test_dir)
        result = CliRunner().invoke(
            project.init,
            ["Test Project", "--root", self.test_dir, "--engine", self.engine],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self._files = 0

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -- helpers ---------------------------------------------------------

    def ledger(self):
        """A freshly loaded ledger, as a new asimov process would see it."""
        return Project.load(self.test_dir).ledger

    def apply(self, text, event=None, update=False):
        self._files += 1
        path = os.path.join(self.test_dir, f"blueprint-{self._files}.yaml")
        with open(path, "w") as handle:
            handle.write(text)
        apply_page(path, event=event, ledger=self.ledger(), update_page=update)

    def analysis(self, subject, name):
        for candidate in self.ledger().get_event(subject)[0].productions:
            if candidate.name == name:
                return candidate
        self.fail(f"no analysis {name} on {subject}")

    def project_analysis(self, name):
        for candidate in self.ledger().project_analyses:
            if candidate.name == name:
                return candidate
        self.fail(f"no project analysis {name}")

    def build(self, analysis):
        """Build the analysis's DAG and return its parsed ledger dump."""
        analysis.pipeline.build_dag()
        return self.read_dump(analysis)

    def read_dump(self, analysis):
        with open(os.path.join(analysis.rundir, DUMP_FILENAME)) as handle:
            return json.load(handle)

    def dump_bytes(self, analysis):
        with open(os.path.join(analysis.rundir, DUMP_FILENAME), "rb") as handle:
            return handle.read()

    def complete(self, subject, name):
        """Run an analysis to completion, so it leaves outputs behind."""
        analysis = self.analysis(subject, name)
        analysis.pipeline.build_dag()
        analysis.pipeline.after_completion()
        self.ledger_update(subject, analysis)
        return analysis

    def ledger_update(self, subject, analysis):
        ledger = self.ledger()
        event = ledger.get_event(subject)[0]
        for index, existing in enumerate(event.productions):
            if existing.name == analysis.name:
                event.productions[index].status = analysis.status
        ledger.update_event(event)

    def review(self, subject, name, status):
        ledger = self.ledger()
        event = ledger.get_event(subject)[0]
        analysis = [a for a in event.productions if a.name == name][0]
        analysis.review.add(
            ReviewMessage(message="test", status=status, production=analysis)
        )
        ledger.update_event(event)

    @staticmethod
    def names(analyses):
        return sorted(item["name"] for item in analyses)


# ---------------------------------------------------------------------------


class DumpContents(LedgerDumpTestCase):
    def setUp(self):
        super().setUp()
        self.apply(event_blueprint())

    def test_simple_analysis_dump(self):
        self.apply(analysis_blueprint("first"), event=SUBJECT)
        dump = self.build(self.analysis(SUBJECT, "first"))

        self.assertEqual(dump["analysis"]["name"], "first")
        self.assertEqual(dump["analysis"]["pipeline"], "SimpleTestPipeline")
        # The analysis's own ledger entry, with the settings it inherits.
        self.assertIn("first", dump["analysis"]["ledger entry"])
        effective = dump["analysis"]["effective settings"]
        self.assertEqual(effective["data"]["segment length"], 4)
        self.assertEqual(effective["waveform"]["reference frequency"], 20)
        # The subject it belongs to.
        self.assertEqual(dump["subjects"][0]["name"], SUBJECT)
        self.assertEqual(dump["subjects"][0]["settings"]["data"]["segment length"], 4)
        # Nothing to see yet, and a simple analysis encompasses nothing.
        self.assertEqual(dump["visible analyses"], [])
        self.assertNotIn("encompassed analyses", dump)

    def test_dump_lists_outputs_of_previous_analyses(self):
        self.apply(analysis_blueprint("first"), event=SUBJECT)
        self.complete(SUBJECT, "first")
        self.apply(analysis_blueprint("second", needs=["first"]), event=SUBJECT)
        self.apply(analysis_blueprint("unrelated"), event=SUBJECT)

        dump = self.build(self.analysis(SUBJECT, "second"))
        visible = {item["name"]: item for item in dump["visible analyses"]}

        self.assertEqual(set(visible), {"first", "unrelated"})
        self.assertEqual(dump["analysis"]["dependencies"], ["first"])
        self.assertTrue(visible["first"]["dependency"])
        self.assertFalse(visible["unrelated"]["dependency"])
        self.assertIn("results.dat", [f["path"] for f in visible["first"]["files"]])
        self.assertIn("results", visible["first"]["assets"])
        # It has not run, so there is nothing to see from it yet.
        self.assertEqual(
            [f["path"] for f in visible["unrelated"]["files"]], []
        )

    def test_dump_does_not_list_itself(self):
        self.apply(analysis_blueprint("first"), event=SUBJECT)
        analysis = self.analysis(SUBJECT, "first")
        self.build(analysis)
        rebuilt = self.build(analysis)
        self.assertNotIn(
            DUMP_FILENAME, [f["path"] for f in rebuilt["analysis"].get("files", [])]
        )
        self.assertEqual(rebuilt["visible analyses"], [])

    def test_dryrun_writes_nothing(self):
        self.apply(analysis_blueprint("first"), event=SUBJECT)
        analysis = self.analysis(SUBJECT, "first")
        analysis.pipeline.build_dag(dryrun=True)
        self.assertFalse(
            os.path.exists(os.path.join(analysis.rundir, DUMP_FILENAME))
        )


class DumpContentsSQLite(DumpContents):
    engine = "sqlite"


# ---------------------------------------------------------------------------


class ApplyUpdate(LedgerDumpTestCase):
    """``asimov apply --update`` after an analysis already exists."""

    def setUp(self):
        super().setUp()
        self.apply(event_blueprint())
        self.apply(analysis_blueprint("before"), event=SUBJECT)
        self.before = self.complete(SUBJECT, "before")
        self.before_dump_bytes = self.dump_bytes(self.before)
        self.before_entry = deepcopy(self.analysis(SUBJECT, "before").to_dict())

        # Change event-level settings, then add an analysis afterwards.
        self.apply(
            event_blueprint(**{"segment length": 8, "reference frequency": 25}),
            update=True,
        )
        self.apply(analysis_blueprint("after"), event=SUBJECT)

    def test_new_analysis_sees_updated_settings(self):
        dump = self.build(self.analysis(SUBJECT, "after"))
        effective = dump["analysis"]["effective settings"]

        self.assertEqual(effective["data"]["segment length"], 8)
        self.assertEqual(effective["waveform"]["reference frequency"], 25)
        settings = dump["subjects"][0]["settings"]
        self.assertEqual(settings["data"]["segment length"], 8)
        self.assertEqual(settings["likelihood"].get("reference frequency", 25), 25)

    def test_new_analysis_still_sees_the_earlier_analysis(self):
        dump = self.build(self.analysis(SUBJECT, "after"))
        visible = {item["name"]: item for item in dump["visible analyses"]}

        self.assertEqual(list(visible), ["before"])
        self.assertIn("results.dat", [f["path"] for f in visible["before"]["files"]])

    def test_existing_analysis_is_not_mutated(self):
        """What the earlier analysis knew before the update, it still knows."""
        # Adding the later analysis and reloading must not touch it either.
        self.build(self.analysis(SUBJECT, "after"))

        now = self.analysis(SUBJECT, "before").to_dict()
        assert_unchanged(self, self.before_entry, now, "before")

        effective = ledger_dump(self.analysis(SUBJECT, "before"))["analysis"][
            "effective settings"
        ]
        self.assertEqual(effective["data"]["segment length"], 4)
        self.assertEqual(effective["waveform"]["reference frequency"], 20)

    def test_existing_analysis_dump_is_untouched(self):
        self.build(self.analysis(SUBJECT, "after"))
        self.assertEqual(
            self.dump_bytes(self.analysis(SUBJECT, "before")), self.before_dump_bytes
        )


class ApplyUpdateSQLite(ApplyUpdate):
    engine = "sqlite"


# ---------------------------------------------------------------------------


class Encompassed(LedgerDumpTestCase):
    """
    Two events; one has several analyses with different review states.

    ====== ============ ==========
    event  analysis     review
    ====== ============ ==========
    A      a-approved   approved
    A      a-rejected   rejected
    A      a-unreviewed (none)
    B      b-approved   approved
    ====== ============ ==========
    """

    A = "EventA"
    B = "EventB"

    def setUp(self):
        super().setUp()
        self.apply(event_blueprint(self.A))
        self.apply(event_blueprint(self.B))
        for subject, name, review in [
            (self.A, "a-approved", "approved"),
            (self.A, "a-rejected", "rejected"),
            (self.A, "a-unreviewed", None),
            (self.B, "b-approved", "approved"),
        ]:
            self.apply(analysis_blueprint(name), event=subject)
            self.complete(subject, name)
            if review:
                self.review(subject, name, review)

    def test_subject_analysis_needs_filters_on_review(self):
        self.apply(
            analysis_blueprint(
                "combine", "subjecttestpipeline", analyses=["review: approved"]
            ),
            event=self.A,
        )
        analysis = self.analysis(self.A, "combine")
        dump = self.build(analysis)

        self.assertEqual(self.names(dump["encompassed analyses"]), ["a-approved"])
        # Analyses on the other event are not encompassed.
        self.assertNotIn("b-approved", self.names(dump["encompassed analyses"]))
        # ... but the analyses of the subject it belongs to are all visible.
        self.assertEqual(
            self.names(dump["visible analyses"]),
            ["a-approved", "a-rejected", "a-unreviewed"],
        )
        self.assertEqual(
            {item["name"]: item["review status"] for item in dump["visible analyses"]},
            {"a-approved": "APPROVED", "a-rejected": "REJECTED", "a-unreviewed": None},
        )

    def test_needs_names_the_analyses_a_subject_pipeline_combines(self):
        """The bundled blueprint style: a plain analysis with ``needs:``."""
        self.apply(
            analysis_blueprint(
                "combine-needs", "subjecttestpipeline", needs=["review: approved"]
            ),
            event=self.A,
        )
        dump = self.build(self.analysis(self.A, "combine-needs"))
        self.assertEqual(self.names(dump["encompassed analyses"]), ["a-approved"])
        self.assertEqual(dump["analysis"]["dependencies"], ["a-approved"])

    def test_subject_analysis_with_negated_filter(self):
        self.apply(
            analysis_blueprint(
                "not-approved", "subjecttestpipeline", analyses=["review: !approved"]
            ),
            event=self.A,
        )
        dump = self.build(self.analysis(self.A, "not-approved"))
        self.assertEqual(
            self.names(dump["encompassed analyses"]), ["a-rejected", "a-unreviewed"]
        )

    def test_subject_analysis_and_group(self):
        """Nested lists are ANDed: approved *and* a matching name."""
        self.apply(
            analysis_blueprint(
                "and-group",
                "subjecttestpipeline",
                analyses=[["review: approved", "name: a-approved"]],
            ),
            event=self.A,
        )
        dump = self.build(self.analysis(self.A, "and-group"))
        self.assertEqual(self.names(dump["encompassed analyses"]), ["a-approved"])

    def test_subject_analysis_results_list_encompassed_analyses(self):
        self.apply(
            analysis_blueprint(
                "combine", "subjecttestpipeline", analyses=["review: approved"]
            ),
            event=self.A,
        )
        analysis = self.analysis(self.A, "combine")
        self.build(analysis)
        with open(os.path.join(analysis.rundir, "test_subject_job.sh")) as handle:
            script = handle.read()

        self.assertIn("# Number of analyses combined: 1", script)
        self.assertIn(f"{self.A}/a-approved", script)
        self.assertNotIn("a-rejected", script)
        self.assertNotIn("a-unreviewed", script)

    def test_project_analysis_spans_events(self):
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
        analysis = self.project_analysis("population")
        dump = self.build(analysis)

        encompassed = {
            (item["subject"], item["name"]) for item in dump["encompassed analyses"]
        }
        self.assertEqual(
            encompassed, {(self.A, "a-approved"), (self.B, "b-approved")}
        )
        self.assertEqual([s["name"] for s in dump["subjects"]], [self.A, self.B])
        # Every analysis on both events is visible; only some are encompassed.
        self.assertEqual(
            self.names(dump["visible analyses"]),
            sorted(["a-approved", "a-rejected", "a-unreviewed", "b-approved"]),
        )

        with open(os.path.join(analysis.rundir, "test_project_job.sh")) as handle:
            script = handle.read()
        self.assertIn("# Number of analyses combined: 2", script)
        self.assertIn(f"{self.A}/a-approved", script)
        self.assertIn(f"{self.B}/b-approved", script)
        self.assertNotIn("a-rejected", script)


class EncompassedSQLite(Encompassed):
    engine = "sqlite"


if __name__ == "__main__":
    unittest.main()
