"""
Tests for the Project Python API.
"""

import unittest
import os
import shutil
import tempfile
from asimov.project import Project
from asimov.event import Event


class TestProject(unittest.TestCase):
    """Test the Project class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp()
        self.project_name = "Test Project"
    
    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
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
        
        # Check that the ledger was created
        ledger_path = os.path.join(self.test_dir, ".asimov", "ledger.yml")
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
                pipeline="bilby",
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
    
    def test_context_manager_exception_handling(self):
        """Test that ledger is not saved when an exception occurs in context."""
        project = Project(self.project_name, location=self.test_dir)
        
        # Try to add a subject but raise an exception
        with self.assertRaises(ValueError):
            with project:
                project.add_subject(name="GW150914")
                # Raise an exception before exiting context
                raise ValueError("Test exception")
        
        # Verify that the subject was not saved
        events = project.get_event()
        self.assertEqual(len(events), 0)


if __name__ == "__main__":
    unittest.main()
