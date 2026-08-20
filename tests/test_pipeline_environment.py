"""
Integration tests for environment capture in pipelines.
"""

import unittest
import os
import json
import tempfile
import shutil
from unittest.mock import MagicMock, patch

from asimov.pipeline import Pipeline
from asimov.environment import EnvironmentCapture


class TestPipelineEnvironmentCapture(unittest.TestCase):
    """Test environment capture integration with Pipeline class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp()
        
        # Create a mock production
        self.mock_production = MagicMock()
        self.mock_production.name = "test_production"
        self.mock_production.rundir = self.test_dir
        self.mock_production.meta = {}
        
        # Create mock event
        self.mock_event = MagicMock()
        self.mock_event.name = "test_event"
        self.mock_production.event = self.mock_event
        
    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_before_config_captures_environment(self):
        """Test that before_config captures environment."""
        pipeline = Pipeline(self.mock_production)
        
        # Call before_config
        pipeline.before_config(dryrun=False)
        
        # Check that environment files were created
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, 'environment.json')))
        
        # Check that metadata was updated
        self.assertIn('environment', self.mock_production.meta)
        self.assertIn('files', self.mock_production.meta['environment'])
        self.assertTrue(self.mock_production.meta['environment']['captured_at'])
    
    def test_before_config_dryrun_does_not_capture(self):
        """Test that before_config in dryrun mode doesn't capture environment."""
        pipeline = Pipeline(self.mock_production)
        
        # Call before_config in dryrun mode
        pipeline.before_config(dryrun=True)
        
        # Check that no environment files were created
        self.assertFalse(os.path.exists(os.path.join(self.test_dir, 'environment.json')))
        
        # Check that metadata was not updated
        self.assertNotIn('environment', self.mock_production.meta)
    
    def test_capture_environment_creates_files(self):
        """Test that _capture_environment creates the expected files."""
        pipeline = Pipeline(self.mock_production)
        
        # Call the internal method
        pipeline._capture_environment()
        
        # Check that environment.json was created
        json_file = os.path.join(self.test_dir, 'environment.json')
        self.assertTrue(os.path.exists(json_file))
        
        # Verify JSON content
        with open(json_file, 'r') as f:
            metadata = json.load(f)
            self.assertIn('timestamp', metadata)
            self.assertIn('environment_type', metadata)
            self.assertIn('python_version', metadata)
    
    def test_capture_environment_handles_missing_rundir(self):
        """Test that capture handles missing rundir gracefully."""
        self.mock_production.rundir = None
        pipeline = Pipeline(self.mock_production)
        
        # Should not raise an exception
        try:
            pipeline._capture_environment()
        except Exception as e:
            self.fail(f"_capture_environment raised exception: {e}")
        
        # No environment metadata should be added
        self.assertNotIn('environment', self.mock_production.meta)
    
    def test_capture_environment_with_conda(self):
        """Test environment capture in a conda environment."""
        with patch.dict(os.environ, {'CONDA_DEFAULT_ENV': 'test-env'}):
            with patch.object(EnvironmentCapture, 'capture_conda_environment', 
                            return_value='numpy=1.0\npandas=2.0\n'):
                pipeline = Pipeline(self.mock_production)
                pipeline._capture_environment()
                
                # Check that conda file was created
                conda_file = os.path.join(self.test_dir, 'environment-conda.txt')
                self.assertTrue(os.path.exists(conda_file))
                
                # Verify content
                with open(conda_file, 'r') as f:
                    content = f.read()
                    self.assertIn('numpy', content)
                    self.assertIn('pandas', content)
    
    def test_store_environment_files_with_no_environment(self):
        """Test that _store_environment_files handles missing environment gracefully."""
        pipeline = Pipeline(self.mock_production)
        
        # Should not raise an exception when no environment was captured
        try:
            pipeline._store_environment_files()
        except Exception as e:
            self.fail(f"_store_environment_files raised exception: {e}")
    
    def test_environment_files_recorded_in_metadata(self):
        """Test that environment file paths are recorded in metadata."""
        pipeline = Pipeline(self.mock_production)
        pipeline._capture_environment()
        
        # Check metadata structure
        env_meta = self.mock_production.meta['environment']
        self.assertIn('files', env_meta)
        self.assertIsInstance(env_meta['files'], dict)
        
        # Check that at least metadata file is recorded
        self.assertIn('metadata', env_meta['files'])
        
        # Verify the path points to an actual file
        metadata_path = env_meta['files']['metadata']
        self.assertTrue(os.path.exists(metadata_path))


if __name__ == '__main__':
    unittest.main()
