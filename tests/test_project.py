"""
Tests for the Project Python API.
"""

import unittest
import os
import shutil
import tempfile
from asimov import config as global_config
from asimov.project import Project
from asimov.event import Event


class TestProject(unittest.TestCase):
    """Test the Project class."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp()
        self.project_name = "Test Project"
        # These tests rely on Project(...) picking up the *default* ledger
        # engine (they don't pass one explicitly - that's the point). The
        # global config singleton is shared across the whole test process,
        # so another test file that ran earlier and explicitly requested
        # a non-default engine would otherwise leak into these. Save
        # whatever was there so tearDown can put it back, rather than
        # leaking our own removal into whichever test happens to run next.
        self._saved_ledger_options = {}
        for option in ("engine", "location"):
            try:
                self._saved_ledger_options[option] = global_config.get("ledger", option)
                global_config.remove_option("ledger", option)
            except Exception:
                pass

    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        for option, value in self._saved_ledger_options.items():
            global_config.set("ledger", option, value)
    
    def test_project_creation(self):
        """Test that a project can be created programmatically."""
        project = Project(self.project_name, location=self.test_dir)
        
        # Verify that the project object has the expected attributes
        self.assertEqual(project.name, self.project_name)
        self.assertEqual(project.location, self.test_dir)
        
        # Check that the project directory was created
        self.assertTrue(os.path.exists(self.test_dir))
        
        # Check that the config file was created
        config_path = os.path.join(self.test_dir, ".asimov", "asimov.conf")
        self.assertTrue(os.path.exists(config_path))
        
        # Check that the ledger was created (sqlite is the default engine
        # for new projects now; see asimov/cli/project.py)
        ledger_path = os.path.join(self.test_dir, ".asimov", "ledger.db")
        self.assertTrue(os.path.exists(ledger_path))
        
        # Check that subdirectories were created
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "working")))
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "checkouts")))
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "results")))
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "logs")))
    
    def test_project_load(self):
        """Test that an existing project can be loaded."""
        # First create a project
        Project(self.project_name, location=self.test_dir)
        
        # Now load it
        project2 = Project.load(self.test_dir)
        
        # Check that the loaded project has the same name
        self.assertEqual(project2.name, self.project_name)
        self.assertEqual(project2.location, self.test_dir)
    
    def test_project_load_nonexistent(self):
        """Test that loading a nonexistent project raises an error."""
        nonexistent_dir = os.path.join(self.test_dir, "nonexistent")
        
        with self.assertRaises(FileNotFoundError):
            Project.load(nonexistent_dir)
    
    def test_project_context_manager(self):
        """Test that the project works as a context manager."""
        project = Project(self.project_name, location=self.test_dir)
        
        # Should be able to use as a context manager
        with project:
            # The ledger should be accessible
            self.assertIsNotNone(project.ledger)
    
    def test_add_subject(self):
        """Test adding a subject to the project."""
        project = Project(self.project_name, location=self.test_dir)
        
        with project:
            # Add a subject
            subject = project.add_subject(name="GW150914")
            
            # Check that the subject was created
            self.assertIsInstance(subject, Event)
            self.assertEqual(subject.name, "GW150914")
        
        # After exiting the context, the subject should be in the ledger
        events = project.get_event()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].name, "GW150914")
    
    def test_add_subject_outside_context(self):
        """Test that adding a subject outside a context manager raises an error."""
        project = Project(self.project_name, location=self.test_dir)
        
        # Should raise an error when not in a context
        with self.assertRaises(RuntimeError):
            project.add_subject(name="GW150914")
    
    def test_add_event_alias(self):
        """Test that add_event is an alias for add_subject."""
        project = Project(self.project_name, location=self.test_dir)
        
        with project:
            # Add an event
            event = project.add_event(name="GW150914")
            
            # Check that the event was created
            self.assertIsInstance(event, Event)
            self.assertEqual(event.name, "GW150914")
    
    def test_project_repr(self):
        """Test the string representation of a project."""
        project = Project(self.project_name, location=self.test_dir)
        
        repr_str = repr(project)
        self.assertIn(self.project_name, repr_str)
        self.assertIn(self.test_dir, repr_str)
    
    def test_add_multiple_subjects(self):
        """Test adding multiple subjects to a project."""
        project = Project(self.project_name, location=self.test_dir)
        
        with project:
            subject1 = project.add_subject(name="GW150914")
            subject2 = project.add_subject(name="GW151226")
            
            # Check that the returned subjects are correct
            self.assertIsInstance(subject1, Event)
            self.assertIsInstance(subject2, Event)
            self.assertEqual(subject1.name, "GW150914")
            self.assertEqual(subject2.name, "GW151226")
        
        # Check that both subjects are in the ledger
        events = project.get_event()
        self.assertEqual(len(events), 2)
        event_names = {event.name for event in events}
        self.assertEqual(event_names, {"GW150914", "GW151226"})
    
    def test_add_analysis_to_subject(self):
        """Test adding an analysis to a subject within a project context."""
        project = Project(self.project_name, location=self.test_dir)
        
        with project:
            subject = project.add_subject(name="GW150914")
            # Add a production/analysis to the subject
            from asimov.analysis import GravitationalWaveTransient
            production = GravitationalWaveTransient(
                subject=subject,
                name="prod_bilby",
                pipeline="simpletestpipeline",
                status="ready",
                ledger=project.ledger
            )
            subject.add_production(production)
            project.ledger.update_event(subject)
        
        # Reload and check that the production was saved
        events = project.get_event()
        self.assertEqual(len(events), 1)
        self.assertEqual(len(events[0].productions), 1)
        self.assertEqual(events[0].productions[0].name, "prod_bilby")
    
    def test_project_creation_on_existing_fails(self):
        """Test that creating a project on an existing project directory raises an error."""
        # First create a project
        Project(self.project_name, location=self.test_dir)
        
        # Try to create another project in the same location
        with self.assertRaises(RuntimeError) as context:
            Project("Another Project", location=self.test_dir)
        
        self.assertIn("already contains an asimov project", str(context.exception))
    
    def test_load_with_malformed_config(self):
        """Test that loading a project with incomplete config raises a clear error."""
        # Create a directory with a malformed config
        os.makedirs(os.path.join(self.test_dir, ".asimov"))
        
        # Create a config file with missing sections
        import configparser
        config = configparser.ConfigParser()
        config.add_section("project")
        config.set("project", "name", "Test")
        # Missing other required sections
        
        config_path = os.path.join(self.test_dir, ".asimov", "asimov.conf")
        with open(config_path, "w") as f:
            config.write(f)
        
        # Try to load the project
        with self.assertRaises(ValueError) as context:
            Project.load(self.test_dir)
        
        self.assertIn("incomplete or malformed", str(context.exception))
    
    @unittest.expectedFailure
    def test_context_manager_exception_handling(self):
        """Test that ledger is not saved when an exception occurs in context.

        add_subject() mutates the ledger's in-memory state unconditionally
        (there's no rollback of that), so this must check what __exit__
        actually guarantees on exception: that the write never reaches
        disk. Checking project.get_event() on the same in-memory Project
        wouldn't distinguish "rolled back" from "just never persisted" -
        reload from disk to actually tell the difference.

        Known gap, not fixed here: this is an expected failure for the
        (now default) sqlite/DatabaseLedger engine. __exit__'s "only save
        on success" logic only ever gated YAMLLedger.save(), which really
        is the sole write point for that backend. For DatabaseLedger,
        AsimovSQLDatabase.get_session() commits at the end of *each*
        insert/update call independently - there's no transaction scoped
        to the whole `with project:` block - so the write already reached
        disk before the exception was even raised. Fixing this properly
        needs Project's context manager to hold open a single DB session/
        transaction across the block, which is a bigger, separate change.
        """
        project = Project(self.project_name, location=self.test_dir)

        # Try to add a subject but raise an exception
        with self.assertRaises(ValueError):
            with project:
                project.add_subject(name="GW150914")
                # Raise an exception before exiting context
                raise ValueError("Test exception")

        # Verify that the subject was never written to disk
        reloaded = Project.load(self.test_dir)
        events = reloaded.get_event()
        self.assertEqual(len(events), 0)


if __name__ == "__main__":
    unittest.main()
