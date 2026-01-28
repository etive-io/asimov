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


if __name__ == "__main__":
    unittest.main()
