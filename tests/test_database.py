"""
Database interface tests
"""

import unittest
import os
import tempfile
import shutil
from unittest.mock import Mock, patch

from asimov.database import AsimovSQLDatabase, AsimovTinyDatabase
from asimov.models import EventModel, ProductionModel, ProjectAnalysisModel
from asimov.ledger import DatabaseLedger
from asimov.event import Event


class TestAsimovSQLDatabase(unittest.TestCase):
    """Tests for SQLAlchemy database backend."""

    def setUp(self):
        """Create a temporary database for testing."""
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_ledger.db")
        self.db_url = f"sqlite:///{self.db_path}"
        self.db = AsimovSQLDatabase(database_url=self.db_url)
        self.db.create_tables()

    def tearDown(self):
        """Clean up test database."""
        if hasattr(self, 'test_dir') and os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_create_tables(self):
        """Test that tables are created successfully."""
        # Tables should be created in setUp
        # Verify by trying to query
        with self.db.get_session() as session:
            events = session.query(EventModel).all()
            self.assertEqual(len(events), 0)

    def test_insert_event(self):
        """Test inserting an event."""
        event_data = {
            "name": "GW150914",
            "repository": "https://git.ligo.org/test",
            "working_directory": "/tmp/test",
            "meta": {"gps": 1126259462.4, "interferometers": ["H1", "L1"]},
        }
        
        event = self.db.insert_event(event_data)
        self.assertIsNotNone(event.id)
        self.assertEqual(event.name, "GW150914")
        self.assertEqual(event.repository, "https://git.ligo.org/test")
        self.assertEqual(event.meta["gps"], 1126259462.4)

    def test_insert_production(self):
        """Test inserting a production."""
        # First create an event
        event_data = {
            "name": "GW150914",
            "repository": None,
            "working_directory": "/tmp/test",
            "meta": {},
        }
        self.db.insert_event(event_data)

        # Now add a production
        production_data = {
            "name": "bilby-test",
            "event_name": "GW150914",
            "pipeline": "bilby",
            "status": "ready",
            "comment": "Test production",
            "meta": {"sampler": "dynesty"},
        }
        
        production = self.db.insert_production(production_data)
        self.assertIsNotNone(production.id)
        self.assertEqual(production.name, "bilby-test")
        self.assertEqual(production.pipeline, "bilby")
        self.assertEqual(production.status, "ready")

    def test_query_events(self):
        """Test querying events."""
        # Insert multiple events
        for i in range(3):
            self.db.insert_event({
                "name": f"GW15091{i}",
                "repository": None,
                "working_directory": None,
                "meta": {},
            })

        # Query all events
        events = self.db.query_events()
        self.assertEqual(len(events), 3)

        # Query specific event
        events = self.db.query_events(filters={"name": "GW150910"})
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].name, "GW150910")

    def test_query_productions_with_filters(self):
        """Test querying productions with filters."""
        # Create event
        self.db.insert_event({
            "name": "GW150914",
            "repository": None,
            "working_directory": None,
            "meta": {},
        })

        # Insert multiple productions
        for i, status in enumerate(["ready", "running", "finished"]):
            self.db.insert_production({
                "name": f"prod-{i}",
                "event_name": "GW150914",
                "pipeline": "bilby" if i < 2 else "lalinference",
                "status": status,
                "meta": {},
            })

        # Query by event
        prods = self.db.query_productions(filters={"event_name": "GW150914"})
        self.assertEqual(len(prods), 3)

        # Query by status
        prods = self.db.query_productions(filters={"status": "ready"})
        self.assertEqual(len(prods), 1)
        self.assertEqual(prods[0].name, "prod-0")

        # Query by pipeline
        prods = self.db.query_productions(filters={"pipeline": "bilby"})
        self.assertEqual(len(prods), 2)

        # Multiple filters
        prods = self.db.query_productions(filters={
            "event_name": "GW150914",
            "pipeline": "bilby",
            "status": "running"
        })
        self.assertEqual(len(prods), 1)
        self.assertEqual(prods[0].name, "prod-1")

    def test_update_event(self):
        """Test updating an event."""
        # Create event
        self.db.insert_event({
            "name": "GW150914",
            "repository": "old_repo",
            "working_directory": None,
            "meta": {"test": "old"},
        })

        # Update event
        success = self.db.update_event("GW150914", {
            "repository": "new_repo",
            "meta": {"test": "new", "gps": 1126259462.4},
        })
        self.assertTrue(success)

        # Verify update
        events = self.db.query_events(filters={"name": "GW150914"})
        self.assertEqual(events[0].repository, "new_repo")
        self.assertEqual(events[0].meta["test"], "new")
        self.assertEqual(events[0].meta["gps"], 1126259462.4)

    def test_update_production(self):
        """Test updating a production."""
        # Create event and production
        self.db.insert_event({
            "name": "GW150914",
            "repository": None,
            "working_directory": None,
            "meta": {},
        })
        self.db.insert_production({
            "name": "test-prod",
            "event_name": "GW150914",
            "pipeline": "bilby",
            "status": "ready",
            "meta": {},
        })

        # Update production
        success = self.db.update_production("GW150914", "test-prod", {
            "status": "running",
            "meta": {"job_id": "12345"},
        })
        self.assertTrue(success)

        # Verify update
        prods = self.db.query_productions(filters={
            "event_name": "GW150914",
            "name": "test-prod"
        })
        self.assertEqual(prods[0].status, "running")
        self.assertEqual(prods[0].meta["job_id"], "12345")

    def test_delete_event(self):
        """Test deleting an event."""
        # Create event
        self.db.insert_event({
            "name": "GW150914",
            "repository": None,
            "working_directory": None,
            "meta": {},
        })

        # Verify it exists
        events = self.db.query_events(filters={"name": "GW150914"})
        self.assertEqual(len(events), 1)

        # Delete it
        success = self.db.delete_event("GW150914")
        self.assertTrue(success)

        # Verify it's gone
        events = self.db.query_events(filters={"name": "GW150914"})
        self.assertEqual(len(events), 0)

    def test_cascade_delete(self):
        """Test that deleting an event also deletes its productions."""
        # Create event and productions
        self.db.insert_event({
            "name": "GW150914",
            "repository": None,
            "working_directory": None,
            "meta": {},
        })
        for i in range(3):
            self.db.insert_production({
                "name": f"prod-{i}",
                "event_name": "GW150914",
                "pipeline": "bilby",
                "status": "ready",
                "meta": {},
            })

        # Verify productions exist
        prods = self.db.query_productions(filters={"event_name": "GW150914"})
        self.assertEqual(len(prods), 3)

        # Delete event
        self.db.delete_event("GW150914")

        # Verify productions are also deleted
        prods = self.db.query_productions(filters={"event_name": "GW150914"})
        self.assertEqual(len(prods), 0)

    def test_transaction_rollback(self):
        """Test that transactions are rolled back on error."""
        # Create an event
        self.db.insert_event({
            "name": "GW150914",
            "repository": None,
            "working_directory": None,
            "meta": {},
        })

        # Try to create a duplicate (should fail and rollback)
        with self.assertRaises(Exception):
            self.db.insert_event({
                "name": "GW150914",  # Duplicate name
                "repository": None,
                "working_directory": None,
                "meta": {},
            })

        # Verify only one event exists
        events = self.db.query_events()
        self.assertEqual(len(events), 1)

    def test_json_metadata_storage(self):
        """Test that complex metadata is stored correctly as JSON."""
        complex_meta = {
            "interferometers": ["H1", "L1", "V1"],
            "calibration": {
                "H1": "/path/to/H1.dat",
                "L1": "/path/to/L1.dat",
            },
            "data": {
                "channels": ["STRAIN"],
                "sample_rate": 4096,
            },
            "nested": {
                "level1": {
                    "level2": {
                        "value": 123
                    }
                }
            }
        }

        self.db.insert_event({
            "name": "GW150914",
            "repository": None,
            "working_directory": None,
            "meta": complex_meta,
        })

        # Retrieve and verify
        events = self.db.query_events(filters={"name": "GW150914"})
        retrieved_meta = events[0].meta
        
        self.assertEqual(retrieved_meta["interferometers"], ["H1", "L1", "V1"])
        self.assertEqual(retrieved_meta["calibration"]["H1"], "/path/to/H1.dat")
        self.assertEqual(retrieved_meta["data"]["sample_rate"], 4096)
        self.assertEqual(retrieved_meta["nested"]["level1"]["level2"]["value"], 123)

    def test_insert_project_analysis(self):
        """Test inserting a project analysis."""
        analysis_data = {
            "name": "population-study",
            "pipeline": "pesummary",
            "status": "ready",
            "comment": "Population analysis",
            "meta": {"events": ["GW150914", "GW151226"]},
        }
        
        analysis = self.db.insert_project_analysis(analysis_data)
        self.assertIsNotNone(analysis.id)
        self.assertEqual(analysis.name, "population-study")
        self.assertEqual(analysis.pipeline, "pesummary")

    def test_query_project_analyses(self):
        """Test querying project analyses."""
        # Insert multiple project analyses
        for i in range(3):
            self.db.insert_project_analysis({
                "name": f"analysis-{i}",
                "pipeline": "pesummary" if i < 2 else "bilby",
                "status": "ready",
                "meta": {},
            })

        # Query all
        analyses = self.db.query_project_analyses()
        self.assertEqual(len(analyses), 3)

        # Query by pipeline
        analyses = self.db.query_project_analyses(filters={"pipeline": "pesummary"})
        self.assertEqual(len(analyses), 2)

    def test_to_dict_conversion(self):
        """Test that models convert to dictionaries correctly."""
        # Create event
        event_data = {
            "name": "GW150914",
            "repository": "https://test.com",
            "working_directory": "/tmp/test",
            "meta": {"gps": 1126259462.4},
        }
        event = self.db.insert_event(event_data)
        
        # Convert to dict
        event_dict = event.to_dict()
        self.assertEqual(event_dict["name"], "GW150914")
        self.assertEqual(event_dict["repository"], "https://test.com")
        self.assertEqual(event_dict["gps"], 1126259462.4)
        # Note: productions are not included in to_dict to avoid lazy loading

    def test_backward_compatible_query(self):
        """Test backward-compatible query method."""
        # Create test data
        self.db.insert_event({
            "name": "GW150914",
            "repository": None,
            "working_directory": None,
            "meta": {},
        })

        # Use old-style query
        results = self.db.query("event", "name", "GW150914")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "GW150914")
        # Note: productions are not included in to_dict by default

    def test_query_supports_falsy_values(self):
        """Test that query() applies filters for falsy values."""
        self.db.insert_event({
            "name": "GW150914",
            "repository": None,
            "working_directory": None,
            "meta": {},
        })
        self.db.insert_production({
            "name": "prod-empty-status",
            "event_name": "GW150914",
            "pipeline": "bilby",
            "status": "",
            "meta": {},
        })

        results = self.db.query("production", "status", "")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "prod-empty-status")

    def test_update_event_with_flat_metadata(self):
        """Test updating event metadata when metadata fields are flattened."""
        self.db.insert_event({
            "name": "GW150914",
            "repository": "old_repo",
            "working_directory": None,
            "meta": {"existing": "value"},
        })

        self.db.update_event("GW150914", {"gps": 1126259462.4})
        event = self.db.query_events(filters={"name": "GW150914"})[0]
        self.assertEqual(event.meta["existing"], "value")
        self.assertEqual(event.meta["gps"], 1126259462.4)

    def test_init_uses_database_url_from_config(self):
        """Test SQLAlchemy URLs from config are not rewritten as sqlite paths."""
        with patch("asimov.database.config") as mock_config:
            mock_config.get.return_value = "postgresql://user:pass@host/dbname"
            with patch("asimov.database.create_engine") as mock_create_engine:
                mock_create_engine.return_value = Mock()
                AsimovSQLDatabase()
                self.assertEqual(
                    mock_create_engine.call_args.args[0],
                    "postgresql://user:pass@host/dbname",
                )

    def test_get_config_empty_by_default(self):
        """Test that get_config() returns {} before anything has been saved."""
        self.assertEqual(self.db.get_config(), {})

    def test_save_and_get_config_round_trips(self):
        """Test that save_config() persists and get_config() reads it back."""
        self.db.save_config({"project": {"name": "test"}, "labellers": {"a": "b"}})
        self.assertEqual(
            self.db.get_config(),
            {"project": {"name": "test"}, "labellers": {"a": "b"}},
        )

    def test_save_config_overwrites_previous_value(self):
        """Test that a second save_config() call replaces, not merges."""
        self.db.save_config({"project": {"name": "test"}})
        self.db.save_config({"quality": {"L1": "foo"}})
        self.assertEqual(self.db.get_config(), {"quality": {"L1": "foo"}})

    def test_config_survives_a_fresh_connection(self):
        """Test config is read back correctly by a brand new AsimovSQLDatabase
        instance pointed at the same URL (not just cached in-process)."""
        self.db.save_config({"pipelines": {"bilby": {"scheduler": "condor"}}})
        second = AsimovSQLDatabase(database_url=self.db_url)
        self.assertEqual(
            second.get_config(), {"pipelines": {"bilby": {"scheduler": "condor"}}}
        )

    def test_merge_config_preserves_untouched_keys(self):
        """Test merge_config() adds/overwrites only the keys it's given,
        leaving whatever else is already persisted alone."""
        self.db.save_config({"project": {"name": "test"}, "quality": {"L1": "old"}})
        result = self.db.merge_config({"labellers": {"interesting": "x"}})
        self.assertEqual(
            result,
            {
                "project": {"name": "test"},
                "quality": {"L1": "old"},
                "labellers": {"interesting": "x"},
            },
        )
        self.assertEqual(self.db.get_config(), result)

    def test_merge_config_on_empty_store_behaves_like_save(self):
        """Test merge_config() works correctly with nothing stored yet."""
        result = self.db.merge_config({"project": {"name": "brand-new"}})
        self.assertEqual(result, {"project": {"name": "brand-new"}})
        self.assertEqual(self.db.get_config(), result)

    def test_merge_config_persists_a_change_to_an_existing_nested_key(self):
        """Test merge_config() actually persists a change to a key that
        already exists as a dict, not just a brand-new key.

        Regression test: merge_config() used to build its merged result via
        `dict(row.data)` (a *shallow* copy) and then mutate nested values
        in place, which - for an update touching only already-existing
        keys - left the merged result structurally equal to row.data's
        prior value by the time SQLAlchemy checked whether anything had
        changed. SQLAlchemy would then skip the UPDATE entirely, silently
        dropping the merge, while merge_config()'s in-memory return value
        still (incorrectly) reported success. A fresh connection is used
        here specifically so the assertion can't be satisfied by an
        in-memory object that was mutated without ever being persisted.
        """
        self.db.save_config({"quality": {"L1": "old"}})
        result = self.db.merge_config({"quality": {"L1": "new"}})
        self.assertEqual(result, {"quality": {"L1": "new"}})

        fresh = AsimovSQLDatabase(database_url=self.db_url)
        self.assertEqual(fresh.get_config(), {"quality": {"L1": "new"}})


class TestAsimovTinyDatabase(unittest.TestCase):
    """Tests for TinyDB backend (for backward compatibility)."""

    def setUp(self):
        """Create a temporary database for testing."""
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_ledger.json")
        
        # Mock config to return our test path
        self.config_patcher = patch('asimov.database.config')
        self.mock_config = self.config_patcher.start()
        self.mock_config.get.return_value = self.db_path
        
        self.db = AsimovTinyDatabase()

    def tearDown(self):
        """Clean up test database."""
        self.config_patcher.stop()
        if hasattr(self, 'test_dir') and os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_insert_and_query(self):
        """Test basic insert and query operations."""
        # Insert an event
        event_data = {"name": "GW150914", "meta": {}}
        doc_id = self.db.insert("event", event_data)
        self.assertIsNotNone(doc_id)

        # Query it back
        results = self.db.query("event", "name", "GW150914")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "GW150914")

    def test_query_all(self):
        """Test querying all rows from a table."""
        self.db.insert("event", {"name": "GW150914", "meta": {}})
        self.db.insert("event", {"name": "GW151226", "meta": {}})
        results = self.db.query("event")
        self.assertEqual(len(results), 2)

    def test_get_config_empty_by_default(self):
        """Test that get_config() returns {} before anything has been saved."""
        self.assertEqual(self.db.get_config(), {})

    def test_save_and_get_config_round_trips(self):
        """Test that save_config() persists and get_config() reads it back."""
        self.db.save_config({"project": {"name": "test"}})
        self.assertEqual(self.db.get_config(), {"project": {"name": "test"}})

    def test_save_config_overwrites_previous_value(self):
        """Test that a second save_config() call replaces, not merges."""
        self.db.save_config({"project": {"name": "test"}})
        self.db.save_config({"quality": {"L1": "foo"}})
        self.assertEqual(self.db.get_config(), {"quality": {"L1": "foo"}})

    def test_merge_config_preserves_untouched_keys(self):
        """Test merge_config() adds/overwrites only the keys it's given,
        leaving whatever else is already persisted alone."""
        self.db.save_config({"project": {"name": "test"}, "quality": {"L1": "old"}})
        result = self.db.merge_config({"labellers": {"interesting": "x"}})
        self.assertEqual(
            result,
            {
                "project": {"name": "test"},
                "quality": {"L1": "old"},
                "labellers": {"interesting": "x"},
            },
        )
        self.assertEqual(self.db.get_config(), result)

    def test_merge_config_persists_a_change_to_an_existing_nested_key(self):
        """Test merge_config() actually persists a change to a key that
        already exists as a dict, not just a brand-new key - see the
        matching AsimovSQLDatabase test for why this is the case that
        exposes the shallow-copy-then-mutate-in-place bug this guards
        against. A fresh AsimovTinyDatabase against the same path is used
        so the assertion can't be satisfied by TinyDB's own in-memory
        cache having been mutated without the write ever reaching disk.
        """
        self.db.save_config({"quality": {"L1": "old"}})
        result = self.db.merge_config({"quality": {"L1": "new"}})
        self.assertEqual(result, {"quality": {"L1": "new"}})

        fresh = AsimovTinyDatabase(database_path=self.db_path)
        self.assertEqual(fresh.get_config(), {"quality": {"L1": "new"}})

    def test_explicit_database_path_overrides_config(self):
        """Test that an explicit database_path is honored instead of the
        (mocked) config value, matching AsimovSQLDatabase's database_url."""
        other_path = os.path.join(self.test_dir, "other_ledger.json")
        db = AsimovTinyDatabase(database_path=other_path)
        db.save_config({"project": {"name": "explicit-path"}})

        # The mocked config still points at self.db_path; a database opened
        # against that path should NOT see the write made via other_path.
        self.assertEqual(self.db.get_config(), {})
        self.assertTrue(os.path.exists(other_path))

        # Re-opening the explicit path directly should see the write.
        reopened = AsimovTinyDatabase(database_path=other_path)
        self.assertEqual(
            reopened.get_config(), {"project": {"name": "explicit-path"}}
        )


class TestDatabaseLedger(unittest.TestCase):
    """Tests for DatabaseLedger integration."""

    def setUp(self):
        """Create a temporary database for testing."""
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_ledger.db")
        
        # Mock config to return our test path and use sqlalchemy engine
        self.config_patcher = patch('asimov.database.config')
        self.mock_config = self.config_patcher.start()
        self.mock_config.get.side_effect = lambda section, key, fallback=None: {
            ("ledger", "engine"): "sqlalchemy",
            ("ledger", "location"): self.db_path,
        }.get((section, key), fallback or self.db_path)
        
        self.ledger = DatabaseLedger(engine="sqlalchemy")
        self.ledger.db.create_tables()

    def tearDown(self):
        """Clean up test database."""
        self.config_patcher.stop()
        if hasattr(self, 'test_dir') and os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_create_ledger(self):
        """Test that a database ledger can be created."""
        self.assertIsNotNone(self.ledger)
        self.assertIsNotNone(self.ledger.db)

    def test_add_and_get_event_at_db_level(self):
        """Test adding and retrieving an event at database level."""
        # Insert event data directly
        event_data = {
            "name": "GW150914",
            "repository": "https://test.com",
            "working_directory": "/tmp/test",
            "meta": {"gps": 1126259462.4},
        }
        self.ledger.db.insert_event(event_data)
        
        # Retrieve using ledger query
        events = self.ledger.db.query_events(filters={"name": "GW150914"})
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].name, "GW150914")

    def test_query_productions_with_filters(self):
        """Test querying productions with filters."""
        # Create event
        self.ledger.db.insert_event({
            "name": "GW150914",
            "repository": None,
            "working_directory": None,
            "meta": {},
        })

        # Add productions directly to database
        for i, status in enumerate(["ready", "running", "finished"]):
            self.ledger.db.insert_production({
                "name": f"prod-{i}",
                "event_name": "GW150914",
                "pipeline": "bilby" if i < 2 else "lalinference",
                "status": status,
                "meta": {},
            })

        # Query with filters using SQL database directly
        prods = self.ledger.db.query_productions(filters={
            "event_name": "GW150914",
            "status": "ready",
            "pipeline": "bilby"
        })
        
        # Should find only prod-0 which is ready and bilby
        self.assertEqual(len(prods), 1)
        self.assertEqual(prods[0].name, "prod-0")

    def test_get_event_returns_list_for_compatibility(self):
        """Test get_event returns a one-element list for compatibility."""
        self.ledger.db.insert_event({
            "name": "GW150914",
            "repository": None,
            "working_directory": None,
            "meta": {},
        })

        events = self.ledger.get_event("GW150914")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].name, "GW150914")

    def test_get_productions_maps_events_per_production(self):
        """Test get_productions resolves the parent event for each production."""
        self.ledger.db.insert_event({
            "name": "GW150914",
            "repository": None,
            "working_directory": None,
            "meta": {},
        })
        self.ledger.db.insert_event({
            "name": "GW151226",
            "repository": None,
            "working_directory": None,
            "meta": {},
        })
        self.ledger.db.insert_production({
            "name": "prod-a",
            "event_name": "GW150914",
            "pipeline": "simpletestpipeline",
            "status": "ready",
            "meta": {},
        })
        self.ledger.db.insert_production({
            "name": "prod-b",
            "event_name": "GW151226",
            "pipeline": "simpletestpipeline",
            "status": "ready",
            "meta": {},
        })

        productions = self.ledger.get_productions()
        events_by_production = {p.name: p.event.name for p in productions}
        self.assertEqual(events_by_production["prod-a"], "GW150914")
        self.assertEqual(events_by_production["prod-b"], "GW151226")

    def test_get_all_events_from_db(self):
        """Test retrieving all events."""
        # Add multiple events
        for i in range(3):
            self.ledger.db.insert_event({
                "name": f"GW15091{i}",
                "repository": None,
                "working_directory": None,
                "meta": {},
            })

        # Get all events
        events = self.ledger.db.query_events()
        self.assertEqual(len(events), 3)

    def test_update_event_via_db(self):
        """Test updating an event."""
        # Create event
        self.ledger.db.insert_event({
            "name": "GW150914",
            "repository": "old_repo",
            "working_directory": None,
            "meta": {},
        })

        # Update it
        self.ledger.db.update_event("GW150914", {
            "repository": "new_repo",
            "working_directory": "/new/path",
            "meta": {"test": "value"},
        })

        # Verify update worked
        events = self.ledger.db.query_events(filters={"name": "GW150914"})
        self.assertEqual(events[0].repository, "new_repo")
        self.assertEqual(events[0].working_directory, "/new/path")

    def test_delete_event_via_db(self):
        """Test deleting an event."""
        # Create event
        self.ledger.db.insert_event({
            "name": "GW150914",
            "repository": None,
            "working_directory": None,
            "meta": {},
        })

        # Verify it exists
        events = self.ledger.db.query_events(filters={"name": "GW150914"})
        self.assertEqual(len(events), 1)

        # Delete it
        self.ledger.db.delete_event("GW150914")

        # Verify it's gone
        events = self.ledger.db.query_events(filters={"name": "GW150914"})
        self.assertEqual(len(events), 0)

    def test_backward_compatibility_with_yaml_ledger(self):
        """Test that DatabaseLedger has same interface as YAMLLedger."""
        # Verify key methods exist
        self.assertTrue(hasattr(self.ledger, 'add_event'))
        self.assertTrue(hasattr(self.ledger, 'get_event'))
        self.assertTrue(hasattr(self.ledger, 'get_productions'))
        self.assertTrue(hasattr(self.ledger, 'add_production'))
        self.assertTrue(hasattr(self.ledger, 'update_event'))
        self.assertTrue(hasattr(self.ledger, 'delete_event'))
        self.assertTrue(hasattr(self.ledger, 'save'))
        self.assertTrue(hasattr(self.ledger, 'events'))
        self.assertTrue(hasattr(self.ledger, 'project_analyses'))

    def test_project_analyses_property(self):
        """Test project analyses support."""
        # Add a project analysis directly
        self.ledger.db.insert_project_analysis({
            "name": "population-study",
            "pipeline": "pesummary",
            "status": "ready",
            "meta": {},
        })

        # Verify it can be queried
        analyses = self.ledger.db.query_project_analyses()
        self.assertEqual(len(analyses), 1)
        self.assertEqual(analyses[0].name, "population-study")

    def test_cascade_delete_productions(self):
        """Test that deleting an event cascades to productions."""
        # Create event with productions
        self.ledger.db.insert_event({
            "name": "GW150914",
            "repository": None,
            "working_directory": None,
            "meta": {},
        })
        
        for i in range(3):
            self.ledger.db.insert_production({
                "name": f"prod-{i}",
                "event_name": "GW150914",
                "pipeline": "bilby",
                "status": "ready",
                "meta": {},
            })

        # Verify productions exist
        prods = self.ledger.db.query_productions(filters={"event_name": "GW150914"})
        self.assertEqual(len(prods), 3)

        # Delete event
        self.ledger.db.delete_event("GW150914")

        # Verify productions are also deleted
        prods = self.ledger.db.query_productions(filters={"event_name": "GW150914"})
        self.assertEqual(len(prods), 0)

    def test_data_defaults_to_minimal_dict(self):
        """Test that .data starts out matching YAMLLedger's guard expectations."""
        self.assertEqual(self.ledger.data, {"project": {}, "pipelines": {}})

    def test_data_mutation_persists_across_save(self):
        """Test the exact pattern `kind: configuration` blueprints use:
        mutate ledger.data in place, then call ledger.save() to persist it.
        This is the pattern that silently no-opped before this fix, since
        the old `.data` getter returned a fresh throwaway dict every time."""
        from asimov.utils import update as merge_update

        merge_update(self.ledger.data, {"labellers": {"interesting": "x"}})
        self.ledger.save()

        fresh = DatabaseLedger(engine="sqlalchemy", location=f"sqlite:///{self.db_path}")
        self.assertEqual(fresh.data["labellers"], {"interesting": "x"})
        # The keys from the default dict should still be present too.
        self.assertIn("project", fresh.data)
        self.assertIn("pipelines", fresh.data)

    def test_save_does_not_erase_a_concurrent_process_unrelated_change(self):
        """Test the exact scenario a blind save() used to be vulnerable to:
        a long-lived process (like `asimov monitor`, which calls
        ledger.save() after every analysis) holds a config snapshot from
        before a second, independent process added something new. When the
        long-lived process later saves for an unrelated reason, the second
        process's addition must survive - not get wiped out by the first
        process's stale snapshot."""
        db_url = f"sqlite:///{self.db_path}"

        # "monitor": a long-lived ledger that loads its cache early.
        monitor_ledger = DatabaseLedger(engine="sqlalchemy", location=db_url)
        _ = monitor_ledger.data  # trigger the cache load, before anyone else writes

        # "apply": an independent, short-lived process adds something new.
        apply_ledger = DatabaseLedger(engine="sqlalchemy", location=db_url)
        apply_ledger.data["labellers"] = {"interesting": "x"}
        apply_ledger.save()

        # "monitor" now saves for an unrelated reason (e.g. a status update),
        # without ever having touched "labellers" itself.
        monitor_ledger.data["scheduler"] = {"cron_minute": "*/5"}
        monitor_ledger.save()

        fresh = DatabaseLedger(engine="sqlalchemy", location=db_url)
        self.assertEqual(fresh.data["labellers"], {"interesting": "x"})
        self.assertEqual(fresh.data["scheduler"], {"cron_minute": "*/5"})

    def test_save_conflict_on_the_same_key_is_last_writer_wins_for_that_key_only(self):
        """Test the honest remaining limitation: if two processes both
        change the *same* top-level key, the second to save() wins for
        that key - but unlike the old blind overwrite, this no longer
        drags every *other* key down with it."""
        db_url = f"sqlite:///{self.db_path}"

        first = DatabaseLedger(engine="sqlalchemy", location=db_url)
        first.data["quality"] = {"L1": "first-value"}
        first.save()

        second = DatabaseLedger(engine="sqlalchemy", location=db_url)
        _ = second.data  # caches the state including first's "quality" write
        second.data["labellers"] = {"interesting": "x"}  # unrelated key

        first.data["quality"] = {"L1": "first-value-updated"}
        first.save()

        second.data["quality"] = {"L1": "second-value"}
        second.save()

        fresh = DatabaseLedger(engine="sqlalchemy", location=db_url)
        # Last writer (second) wins for the key it actually conflicted on...
        self.assertEqual(fresh.data["quality"], {"L1": "second-value"})
        # ...but second's unrelated addition still made it through.
        self.assertEqual(fresh.data["labellers"], {"interesting": "x"})

    def test_save_does_not_resurrect_a_stale_value_for_an_untouched_key(self):
        """Test the specific gap flagged in review on an earlier version of
        this fix: save() must not re-merge the *whole* cached snapshot, only
        what this process actually changed. A process that merely *loaded*
        an existing key (without changing it) before a second process
        updated that same key must not drag the second process's update
        back to the stale value it happened to see at load time."""
        db_url = f"sqlite:///{self.db_path}"

        seed = DatabaseLedger(engine="sqlalchemy", location=db_url)
        seed.data["quality"] = {"L1": "original"}
        seed.save()

        # "monitor": loads the cache - including "quality" - but never
        # itself changes "quality".
        monitor_ledger = DatabaseLedger(engine="sqlalchemy", location=db_url)
        self.assertEqual(monitor_ledger.data["quality"], {"L1": "original"})

        # An independent process changes "quality" concurrently.
        other_ledger = DatabaseLedger(engine="sqlalchemy", location=db_url)
        other_ledger.data["quality"] = {"L1": "updated-by-someone-else"}
        other_ledger.save()

        # "monitor" now saves for an unrelated reason, without ever having
        # touched "quality" itself.
        monitor_ledger.data["scheduler"] = {"cron_minute": "*/5"}
        monitor_ledger.save()

        fresh = DatabaseLedger(engine="sqlalchemy", location=db_url)
        self.assertEqual(fresh.data["quality"], {"L1": "updated-by-someone-else"})
        self.assertEqual(fresh.data["scheduler"], {"cron_minute": "*/5"})

    def test_data_returns_same_object_on_repeat_access(self):
        """Test .data is cached (same object identity), not reloaded/rebuilt
        on every access, matching update()'s in-place-mutation contract."""
        self.assertIs(self.ledger.data, self.ledger.data)

    def test_create_seeds_project_name(self):
        """Test that DatabaseLedger.create(name=...) seeds
        data["project"]["name"], matching YAMLLedger.create(). Real CLI
        callers (make_project() in asimov/cli/project.py) always pass
        `name`, and `asimov monitor`/`asimov report` read
        ledger.data["project"]["name"] unconditionally from project
        creation onward - not only once a `kind: configuration` blueprint
        happens to set it."""
        other_path = os.path.join(self.test_dir, "seeded_ledger.db")
        other_url = f"sqlite:///{other_path}"
        ledger = DatabaseLedger.create(
            name="GWTC-Test", engine="sqlalchemy", location=other_url
        )
        self.assertEqual(ledger.data["project"]["name"], "GWTC-Test")

        # And it's genuinely persisted, not just held in the returned
        # instance's cache.
        fresh = DatabaseLedger(engine="sqlalchemy", location=other_url)
        self.assertEqual(fresh.data["project"]["name"], "GWTC-Test")

    def test_tinydb_engine_honors_sqlite_prefixed_location(self):
        """Test the tinydb branch of DatabaseLedger.__init__ strips a
        sqlite:/// prefix rather than trying to open a file literally named
        "sqlite:///...". Ledger.create()'s dispatcher URL-ifies bare paths
        for every non-yaml engine, tinydb included, since that's the form
        AsimovSQLDatabase needs - tinydb has to defensively unwrap it."""
        tinydb_path = os.path.join(self.test_dir, "tiny_ledger.json")
        ledger = DatabaseLedger(engine="tinydb", location=f"sqlite:///{tinydb_path}")
        ledger.data["project"] = {"name": "tiny-test"}
        ledger.save()

        self.assertTrue(os.path.exists(tinydb_path))
        self.assertFalse(os.path.exists(f"sqlite:///{tinydb_path}"))

        reopened = DatabaseLedger(engine="tinydb", location=tinydb_path)
        self.assertEqual(reopened.data["project"]["name"], "tiny-test")


if __name__ == "__main__":
    unittest.main()
