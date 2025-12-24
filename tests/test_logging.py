"""
Tests for the logging interface improvements.
"""
import unittest
import os
import shutil
import tempfile
from click.testing import CliRunner
from asimov.cli import project
from asimov.olivaw import olivaw


class TestLogging(unittest.TestCase):
    """Test the logging interface improvements."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        # Reset the global file handler to ensure test isolation
        import asimov
        asimov._file_handler = None
        
    def tearDown(self):
        """Clean up test environment."""
        os.chdir(self.original_cwd)
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_help_does_not_create_log(self):
        """Test that --help does not create a log file."""
        os.chdir(self.test_dir)
        runner = CliRunner()
        result = runner.invoke(olivaw, ['--help'])
        
        # Check that no asimov.log file was created
        self.assertFalse(os.path.exists('asimov.log'), 
                        "asimov.log should not be created for --help command")
        self.assertEqual(result.exit_code, 0)
    
    def test_version_does_not_create_log(self):
        """Test that --version does not create a log file."""
        os.chdir(self.test_dir)
        runner = CliRunner()
        result = runner.invoke(olivaw, ['--version'])
        
        # Check that no asimov.log file was created
        self.assertFalse(os.path.exists('asimov.log'), 
                        "asimov.log should not be created for --version command")
        self.assertEqual(result.exit_code, 0)
    
    def test_init_creates_log_in_logs_directory(self):
        """Test that init command creates log in the logs directory."""
        os.chdir(self.test_dir)
        runner = CliRunner()
        result = runner.invoke(project.init, ['Test Project', '--root', self.test_dir])
        
        # Check that log was created in logs directory, not current directory
        self.assertFalse(os.path.exists('asimov.log'),
                        "asimov.log should not be in current directory")
        self.assertTrue(os.path.exists(os.path.join('logs', 'asimov.log')),
                       "asimov.log should be in logs directory")
        self.assertEqual(result.exit_code, 0)
        
        # Verify the log contains expected content
        with open(os.path.join('logs', 'asimov.log'), 'r') as f:
            log_content = f.read()
            self.assertIn('A new project was created', log_content)
            self.assertIn('[INFO]', log_content)


if __name__ == '__main__':
    unittest.main()
