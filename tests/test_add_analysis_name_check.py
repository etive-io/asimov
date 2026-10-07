"""
Adding an analysis to the database ledger checks its name is unique by asking
the database about that name, not by reading every analysis already stored (#242).
"""
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from asimov.database import AsimovSQLDatabase
from asimov.event import Event, Production
from asimov.ledger import DatabaseLedger


def production_row(name, event_name):
    return {
        "name": name,
        "event_name": event_name,
        "pipeline": "simpletestpipeline",
        "status": "ready",
        "comment": None,
        "meta": {},
    }


class NameExistsTests(unittest.TestCase):
    """AsimovSQLDatabase.name_exists, and the general version it overrides."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.db = AsimovSQLDatabase(database_url=f"sqlite:///{self.tmp}/test.db")
        self.db.create_tables()
        for event in ("GW150914", "GW151226"):
            self.db.insert_event(
                {"name": event, "repository": None, "working_directory": "/tmp", "meta": {}}
            )
        self.db.insert_production(production_row("bilby", "GW150914"))
        self.db.insert_project_analysis(
            {"name": "population", "pipeline": "pesummary", "status": "ready",
             "comment": None, "meta": {}}
        )

    def test_a_production_name_is_found_within_its_event(self):
        self.assertTrue(self.db.name_exists("production", "bilby", event_name="GW150914"))

    def test_the_same_name_is_free_in_another_event(self):
        self.assertFalse(self.db.name_exists("production", "bilby", event_name="GW151226"))

    def test_an_unknown_name_is_free(self):
        self.assertFalse(self.db.name_exists("production", "rift", event_name="GW150914"))

    def test_a_project_analysis_name_is_found(self):
        self.assertTrue(self.db.name_exists("project_analysis", "population"))
        self.assertFalse(self.db.name_exists("project_analysis", "other"))

    def test_an_unknown_table_is_an_error(self):
        with self.assertRaises(ValueError):
            self.db.name_exists("event", "GW150914")

    def test_it_agrees_with_the_general_version(self):
        """The override must give the same answers as reading every record."""
        general = AsimovSQLDatabase.__mro__[1].name_exists
        for table, name, event in [
            ("production", "bilby", "GW150914"),
            ("production", "bilby", "GW151226"),
            ("production", "rift", "GW150914"),
            ("project_analysis", "population", None),
            ("project_analysis", "other", None),
        ]:
            self.assertEqual(
                self.db.name_exists(table, name, event_name=event),
                general(self.db, table, name, event_name=event),
                (table, name, event),
            )


class AddAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        db_path = os.path.join(self.tmp, "ledger.db")
        patcher = patch("asimov.database.config")
        mock_config = patcher.start()
        self.addCleanup(patcher.stop)
        mock_config.get.side_effect = lambda section, key, fallback=None: {
            ("ledger", "engine"): "sqlalchemy",
            ("ledger", "location"): db_path,
        }.get((section, key), fallback or db_path)
        self.ledger = DatabaseLedger(engine="sqlalchemy")
        self.ledger.db.create_tables()
        self.event = Event(name="S000000", ledger=self.ledger, **{"event time": 900})
        self.ledger.add_event(self.event)

    def production(self, name, event=None):
        return Production.from_dict(
            parameters={"name": name, "pipeline": "simpletestpipeline", "status": "ready"},
            subject=event or self.event,
            ledger=self.ledger,
        )

    def test_adding_analyses_does_not_read_the_existing_ones(self):
        with patch.object(
            AsimovSQLDatabase, "query_productions", wraps=self.ledger.db.query_productions
        ) as read:
            for n in range(5):
                self.ledger.add_analysis(self.production(f"a{n}"), event=self.event)
        self.assertEqual(read.call_count, 0)
        self.assertEqual(len(self.ledger.get_event("S000000")[0].productions), 5)

    def test_a_duplicate_name_is_still_rejected(self):
        self.ledger.add_analysis(self.production("a0"), event=self.event)
        with self.assertRaises(ValueError) as caught:
            self.ledger.add_analysis(self.production("a0"), event=self.event)
        self.assertIn("already exists for S000000", str(caught.exception))
        self.assertEqual(len(self.ledger.get_event("S000000")[0].productions), 1)

    def test_the_same_name_is_allowed_in_another_event(self):
        other = Event(name="S000001", ledger=self.ledger, **{"event time": 901})
        self.ledger.add_event(other)
        self.ledger.add_analysis(self.production("a0"), event=self.event)
        self.ledger.add_analysis(self.production("a0", event=other), event=other)
        self.assertEqual(len(self.ledger.get_event("S000001")[0].productions), 1)


if __name__ == "__main__":
    unittest.main()
