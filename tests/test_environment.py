"""
Tests for environment capture functionality.
"""

import unittest
import os
import json
import sys
import subprocess
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

from asimov.environment import EnvironmentCapture, capture_and_save_environment


class TestEnvironmentCapture(unittest.TestCase):
    """Test the EnvironmentCapture class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_detect_environment_type(self):
        """Test environment type detection."""
        capture = EnvironmentCapture()
        # The environment type should be one of the expected values
        self.assertIn(capture.env_type, ['conda', 'virtualenv', 'venv', 'system'])
    
    def test_detect_conda_environment(self):
        """Test conda environment detection."""
        with patch.dict(os.environ, {'CONDA_DEFAULT_ENV': 'test-env'}):
            capture = EnvironmentCapture()
            self.assertEqual(capture.env_type, 'conda')
    
    def test_detect_virtualenv(self):
        """Test virtualenv detection."""
        # Mock sys.prefix and sys.base_prefix to simulate virtualenv
        with patch.object(sys, 'prefix', '/path/to/venv'):
            with patch.object(sys, 'base_prefix', '/usr'):
                capture = EnvironmentCapture()
                # Should detect as virtualenv (not system)
                self.assertIn(capture.env_type, ['virtualenv', 'conda'])
    
    def test_capture_pip_environment(self):
        """Test pip environment capture."""
        capture = EnvironmentCapture()
        pip_output = capture.capture_pip_environment()
        
        # Should return a string if pip is available
        if pip_output is not None:
            self.assertIsInstance(pip_output, str)
            # Should contain package information
            self.assertTrue(len(pip_output) > 0)
    
    def test_capture_conda_environment_when_not_conda(self):
        """Test conda capture when not in conda environment."""
        # If not in conda environment, this should handle gracefully
        with patch.dict(os.environ, {}, clear=True):
            capture = EnvironmentCapture()
            if capture.env_type != 'conda':
                # May return None if conda is not available
                conda_output = capture.capture_conda_environment()
                # Should be None or a string
                self.assertTrue(conda_output is None or isinstance(conda_output, str))
    
    def test_get_environment_info(self):
        """Test getting comprehensive environment info."""
        capture = EnvironmentCapture()
        info = capture.get_environment_info()
        
        # Check required fields are present
        self.assertIn('timestamp', info)
        self.assertIn('environment_type', info)
        self.assertIn('python_version', info)
        self.assertIn('python_executable', info)
        
        # Check timestamp is a valid ISO 8601 string
        # Just verify it contains some expected parts
        self.assertIn('T', info['timestamp'])  # Date-time separator
        
        # Check python_version matches sys.version
        self.assertEqual(info['python_version'], sys.version)
        
        # Check python_executable matches sys.executable
        self.assertEqual(info['python_executable'], sys.executable)
    
    def test_get_environment_info_conda(self):
        """Test getting environment info in conda environment."""
        with patch.dict(os.environ, {'CONDA_DEFAULT_ENV': 'test-env', 'CONDA_PREFIX': '/path/to/conda'}):
            with patch.object(EnvironmentCapture, 'capture_conda_environment', return_value='numpy=1.0\npandas=2.0\n'):
                capture = EnvironmentCapture()
                info = capture.get_environment_info()
                
                self.assertEqual(info['environment_type'], 'conda')
                self.assertEqual(info['conda_env_name'], 'test-env')
                self.assertIn('conda_environment', info)
                self.assertIn('numpy', info['conda_environment'])
    
    def test_save_environment(self):
        """Test saving environment to files."""
        capture = EnvironmentCapture()
        created_files = capture.save_environment(self.test_dir)
        
        # Check that at least metadata file was created
        self.assertIn('metadata', created_files)
        self.assertTrue(os.path.exists(created_files['metadata']))
        
        # Check metadata file content
        with open(created_files['metadata'], 'r') as f:
            metadata = json.load(f)
            self.assertIn('timestamp', metadata)
            self.assertIn('environment_type', metadata)
            self.assertIn('python_version', metadata)
        
        # Check pip file if created
        if 'pip' in created_files:
            self.assertTrue(os.path.exists(created_files['pip']))
            with open(created_files['pip'], 'r') as f:
                content = f.read()
                # Should contain some package information
                self.assertTrue(len(content) > 0)
    
    def test_save_environment_with_prefix(self):
        """Test saving environment with custom prefix."""
        capture = EnvironmentCapture()
        prefix = 'test_env'
        created_files = capture.save_environment(self.test_dir, prefix=prefix)
        
        # Check files have correct prefix
        for file_type, filepath in created_files.items():
            filename = os.path.basename(filepath)
            self.assertTrue(filename.startswith(prefix))
    
    def test_save_environment_creates_directory(self):
        """Test that save_environment creates directory if it doesn't exist."""
        new_dir = os.path.join(self.test_dir, 'subdir', 'nested')
        capture = EnvironmentCapture()
        created_files = capture.save_environment(new_dir)
        
        # Directory should have been created
        self.assertTrue(os.path.exists(new_dir))
        
        # Files should exist in the new directory
        self.assertIn('metadata', created_files)
        self.assertTrue(os.path.exists(created_files['metadata']))
    
    def test_capture_and_save_environment_convenience_function(self):
        """Test the convenience function for capturing and saving."""
        created_files = capture_and_save_environment(self.test_dir)
        
        # Should create at least the metadata file
        self.assertIn('metadata', created_files)
        self.assertTrue(os.path.exists(created_files['metadata']))
        
        # Verify the metadata file has correct content
        with open(created_files['metadata'], 'r') as f:
            metadata = json.load(f)
            self.assertIn('timestamp', metadata)
            self.assertIn('environment_type', metadata)
    
    def test_capture_pip_timeout(self):
        """Test that pip capture handles timeout gracefully."""
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('pip', 30)):
            capture = EnvironmentCapture()
            result = capture.capture_pip_environment()
            self.assertIsNone(result)
    
    def test_capture_conda_timeout(self):
        """Test that conda capture handles timeout gracefully."""
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('conda', 30)):
            capture = EnvironmentCapture()
            result = capture.capture_conda_environment()
            self.assertIsNone(result)
    
    def test_capture_pip_not_found(self):
        """Test that pip capture handles FileNotFoundError gracefully."""
        with patch('subprocess.run', side_effect=FileNotFoundError):
            capture = EnvironmentCapture()
            result = capture.capture_pip_environment()
            self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
