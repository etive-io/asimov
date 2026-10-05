"""
Applying an analysis (or project analysis) which already exists in the ledger
must be refused, whichever ledger backend is in use, and must leave the
existing analysis exactly as it was.

The database ledger used to insert a second row with the same name: it
reported success, and the duplicate was then hidden when the event was loaded.
"""

import os
import shutil
import tempfile
import unittest

import yaml
from click.testing import CliRunner

from asimov.cli import project
from asimov.cli.application import apply_page
from asimov.project import Project
from asimov.review import ReviewMessage

BLUEPRINTS = os.path.join(os.path.dirname(__file__), "test_blueprints")
SUBJECT = "GW150914_095045"


def analysis_blueprint(name="first", **extra):
    blueprint = {
        "kind": "analysis",
        "name": name,
        "pipeline": "simpletestpipeline",
        "status": "ready",
    }
    blueprint.update(extra)
    return yaml.safe_dump(blueprint)


class ReapplyTestCase(unittest.TestCase):
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
        self._ledgers = []
        apply_page(
            os.path.join(BLUEPRINTS, "gwosc_event.yaml"), ledger=self.ledger()
        )

    def tearDown(self):
        for ledger in self._ledgers:
            if hasattr(ledger, "close"):
                ledger.close()
        os.chdir(self.cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def ledger(self):
        ledger = Project.load(self.test_dir).ledger
        self._ledgers.append(ledger)
        return ledger

    def apply(self, text, event=SUBJECT, **kwargs):
        """Apply a blueprint, returning what asimov printed."""
        self._files += 1
        path = os.path.join(self.test_dir, f"blueprint-{self._files}.yaml")
        with open(path, "w") as handle:
            handle.write(text)
        runner_output = []
        import click

        original = click.echo

        def capture(message=None, *args, **kw):
            runner_output.append(click.unstyle(str(message)))
            return original(message, *args, **kw)

        click.echo = capture
        try:
            apply_page(path, event=event, ledger=self.ledger(), **kwargs)
        finally:
            click.echo = original
        return "\n".join(runner_output)

    def analyses(self):
        return self.ledger().get_event(SUBJECT)[0].productions

    def names(self):
        return [analysis.name for analysis in self.analyses()]


class ReapplyAnalysis(ReapplyTestCase):
    def test_reapplying_an_existing_analysis_is_refused(self):
        self.apply(analysis_blueprint("first"))
        output = self.apply(analysis_blueprint("first"))

        self.assertIn("already exists", output)
        self.assertNotIn("Successfully applied", output)
        self.assertEqual(self.names(), ["first"])

    def test_existing_analysis_is_left_untouched(self):
        self.apply(analysis_blueprint("first", comment="original"))
        ledger = self.ledger()
        event = ledger.get_event(SUBJECT)[0]
        analysis = event.productions[0]
        analysis.status = "finished"
        analysis.job_id = 4242
        analysis.meta["note"] = "important"
        analysis.review.add(
            ReviewMessage(message="ok", status="approved", production=analysis)
        )
        ledger.update_event(event)

        self.apply(
            analysis_blueprint(
                "first", comment="replacement", waveform={"approximant": "other"}
            )
        )

        (analysis,) = self.analyses()
        self.assertEqual(analysis.status, "finished")
        self.assertEqual(analysis.job_id, 4242)
        self.assertEqual(analysis.review.status, "APPROVED")
        self.assertEqual(analysis.meta["note"], "important")
        self.assertNotEqual(analysis.meta["waveform"].get("approximant"), "other")

    def test_a_different_name_is_still_accepted(self):
        self.apply(analysis_blueprint("first"))
        self.apply(analysis_blueprint("second"))
        self.assertEqual(sorted(self.names()), ["first", "second"])

    def test_the_same_name_on_another_event_is_accepted(self):
        second = yaml.safe_load(
            open(os.path.join(BLUEPRINTS, "second_event.yaml")).read()
        )
        self.apply(yaml.safe_dump(second), event=None)
        self.apply(analysis_blueprint("first"))
        self.apply(analysis_blueprint("first"), event=second["name"])
        other = self.ledger().get_event(second["name"])[0]
        self.assertEqual([a.name for a in other.productions], ["first"])

    def test_iterate_picks_the_next_free_name(self):
        """Used to raise AttributeError on the database ledger."""
        self.apply(analysis_blueprint("first"))
        self.apply(analysis_blueprint("first"), iterate=True)
        self.assertEqual(sorted(self.names()), ["first", "first-2"])

    def test_name_override_is_accepted(self):
        """Used to raise AttributeError on the database ledger."""
        self.apply(analysis_blueprint("first"))
        self.apply(analysis_blueprint("first"), name="renamed")
        self.assertEqual(sorted(self.names()), ["first", "renamed"])


class ReapplyAnalysisSQLite(ReapplyAnalysis):
    engine = "sqlite"

    def rows(self):
        ledger = self.ledger()
        return [
            row for row in ledger.db.query("production", "event_name", SUBJECT)
        ]

    def insert_legacy_duplicate(self, original):
        """Add a second row of the same name, as an older asimov could."""
        from asimov.models import ProductionModel

        ledger = self.ledger()
        with ledger.db.get_session() as session:
            session.add(
                ProductionModel(
                    name=original.name,
                    event_name=original.event_name,
                    pipeline=original.pipeline,
                    status="ready",
                    comment=None,
                    meta=original.meta,
                )
            )

    def insert_unloadable(self, name):
        """A stored analysis which cannot be loaded (its pipeline is unknown)."""
        self.ledger().db.insert_production(
            {
                "name": name,
                "event_name": SUBJECT,
                "pipeline": "nosuchpipeline",
                "status": "ready",
                "comment": None,
                "meta": {},
            }
        )

    def test_the_database_itself_refuses_a_duplicate(self):
        """The check is made in the insert's own transaction, not only before it."""
        self.apply(analysis_blueprint("first"))
        (original,) = self.ledger().db.query_productions({"event_name": SUBJECT})
        with self.assertRaises(ValueError):
            self.ledger().db.insert_production(
                {
                    "name": "first",
                    "event_name": SUBJECT,
                    "pipeline": original.pipeline,
                    "status": "ready",
                    "comment": None,
                    "meta": {},
                }
            )
        self.assertEqual([row["name"] for row in self.rows()], ["first"])

    def test_iterate_counts_analyses_which_fail_to_load(self):
        """The name of a stored but unloadable analysis must not be reused."""
        self.insert_unloadable("first")
        self.assertEqual(self.names(), [])  # skipped when the event is loaded

        self.apply(analysis_blueprint("first"), iterate=True)

        self.assertEqual(self.names(), ["first-2"])
        self.assertEqual(
            sorted(row["name"] for row in self.rows()), ["first", "first-2"]
        )

    def test_reapplying_an_analysis_which_fails_to_load_is_refused(self):
        self.insert_unloadable("first")
        output = self.apply(analysis_blueprint("first"))
        self.assertIn("already exists", output)
        self.assertEqual([row["name"] for row in self.rows()], ["first"])

    def test_rows_are_read_oldest_first(self):
        for name in ("c", "a", "b"):
            self.apply(analysis_blueprint(name))
        ids = [row.id for row in self.ledger().db.query_productions({"event_name": SUBJECT})]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(
            [row["name"] for row in self.rows()], ["c", "a", "b"]
        )

    def test_no_duplicate_row_is_stored(self):
        self.apply(analysis_blueprint("first"))
        self.apply(analysis_blueprint("first"))
        self.assertEqual([row["name"] for row in self.rows()], ["first"])

    def test_updates_go_to_the_oldest_row_if_duplicates_already_exist(self):
        """Ledgers which already hold a duplicate (from before this was
        refused) keep loading, and updating, the original."""
        self.apply(analysis_blueprint("first", comment="original"))
        ledger = self.ledger()
        (original,) = ledger.db.query_productions({"event_name": SUBJECT})
        self.insert_legacy_duplicate(original)

        ledger = self.ledger()
        event = ledger.get_event(SUBJECT)[0]
        event.productions[0].status = "finished"
        ledger.update_event(event)

        rows = self.ledger().db.query_productions({"event_name": SUBJECT})
        self.assertEqual(
            sorted((row.id, row.status) for row in rows),
            [(original.id, "finished"), (original.id + 1, "ready")],
        )
        self.assertEqual(self.analyses()[0].status, "finished")


class ReapplyProjectAnalysis(ReapplyTestCase):
    PROJECT_ANALYSIS = yaml.safe_dump(
        {
            "kind": "projectanalysis",
            "name": "population",
            "pipeline": "projecttestpipeline",
            "status": "ready",
            "subjects": [SUBJECT],
        }
    )

    def test_reapplying_a_project_analysis_is_refused(self):
        self.apply(self.PROJECT_ANALYSIS, event=None)
        output = self.apply(self.PROJECT_ANALYSIS, event=None)

        self.assertIn("already exists", output)
        self.assertEqual(
            [a.name for a in self.ledger().project_analyses], ["population"]
        )


class ReapplyProjectAnalysisSQLite(ReapplyProjectAnalysis):
    engine = "sqlite"


if __name__ == "__main__":
    unittest.main()
