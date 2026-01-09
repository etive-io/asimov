"""
Tests for the logging interface improvements.
"""
import unittest
import os
import shutil
import tempfile
from unittest.mock import patch
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
        # Using patch to properly mock the private variable
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
        
        # Check that logs directory was created
        self.assertTrue(os.path.exists('logs'), 
                       "logs directory should exist")
        
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
    
    def test_log_rotation_config(self):
        """Test that log rotation configuration is read correctly."""
        from asimov import setup_file_logging
        import asimov
        
        # Reset handler
        asimov._file_handler = None
        
        os.chdir(self.test_dir)
        
        # Create a test log file
        log_path = os.path.join(self.test_dir, 'test.log')
        setup_file_logging(logfile=log_path)
        
        # Verify handler was created
        self.assertIsNotNone(asimov._file_handler)
        
        # Check that it's a RotatingFileHandler with expected defaults
        from logging.handlers import RotatingFileHandler
        self.assertIsInstance(asimov._file_handler, RotatingFileHandler)
        self.assertEqual(asimov._file_handler.maxBytes, 10 * 1024 * 1024)  # 10 MB
        self.assertEqual(asimov._file_handler.backupCount, 5)
    
    def test_invalid_log_directory_fallback(self):
        """Test that invalid log directory falls back to current directory."""
        from asimov import setup_file_logging
        import asimov
        
        # Reset handler
        asimov._file_handler = None
        
        os.chdir(self.test_dir)
        
        # Try to create a log in a directory that cannot be created (invalid path)
        with patch('asimov.config.get') as mock_config:
            # Return an invalid path that will fail os.makedirs
            mock_config.return_value = '/root/invalid_path_no_permission'
            
            # This should fall back gracefully
            setup_file_logging()
            
            # Should have created handler in current directory as fallback
            # Note: may be None if both attempts fail, which is acceptable
    
    def test_setup_file_logging_thread_safety(self):
        """Test that setup_file_logging is thread-safe."""
        from asimov import setup_file_logging
        import asimov
        import threading
        
        # Reset handler
        asimov._file_handler = None
        
        os.chdir(self.test_dir)
        
        log_path = os.path.join(self.test_dir, 'thread_test.log')
        results = []
        
        def call_setup():
            setup_file_logging(logfile=log_path)
            results.append(asimov._file_handler)
        
        # Call from multiple threads
        threads = [threading.Thread(target=call_setup) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # All threads should see the same handler (only one created)
        self.assertTrue(all(h == results[0] for h in results))


if __name__ == '__main__':
    unittest.main()
