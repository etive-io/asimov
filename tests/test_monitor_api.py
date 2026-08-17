"""
Unit tests for the programmatic monitor API.
"""

import unittest
from unittest.mock import Mock, patch

from asimov.monitor_api import (
    run_monitor,
    get_analysis_status,
    list_active_analyses,
)


class TestMonitorAPI(unittest.TestCase):
    """Test the programmatic monitor API."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_ledger = Mock()
        self.mock_ledger.project_analyses = []
        self.mock_ledger.get_event = Mock(return_value=[])
    
    @patch('asimov.monitor_api.condor')
    @patch('asimov.monitor_api.ledger')
    @patch('asimov.monitor_api.monitor_analysis')
    def test_run_monitor_basic(self, mock_monitor_analysis, mock_ledger, mock_condor):
        """Test basic run_monitor call."""
        # Mock condor job list
        mock_job_list = Mock()
        mock_condor.CondorJobList.return_value = mock_job_list
        
        # Mock ledger
        mock_ledger.project_analyses = []
        mock_ledger.get_event.return_value = []
        
        # Run monitor
        results = run_monitor()
        
        # Check results
        self.assertIsInstance(results, dict)
        self.assertIn('total', results)
        self.assertIn('project_analyses', results)
        self.assertIn('event_analyses', results)
        self.assertEqual(results['total'], 0)
    
    @patch('asimov.monitor_api.condor')
    @patch('asimov.monitor_api.ledger')
    @patch('asimov.monitor_api.monitor_analysis')
    def test_run_monitor_with_analyses(self, mock_monitor_analysis, mock_ledger, mock_condor):
        """Test run_monitor with active analyses."""
        # Mock condor
        mock_job_list = Mock()
        mock_condor.CondorJobList.return_value = mock_job_list
        
        # Mock analyses
        mock_analysis = Mock()
        mock_analysis.name = "test_analysis"
        mock_analysis.status = "running"
        mock_analysis.pipeline = "bilby"
        
        mock_ledger.project_analyses = [mock_analysis]
        mock_ledger.get_event.return_value = []
        
        # Run monitor
        results = run_monitor()
        
        # Check that monitor_analysis was called
        mock_monitor_analysis.assert_called_once()
        self.assertEqual(results['project_analyses'], 1)
        self.assertEqual(results['total'], 1)
    
    @patch('asimov.monitor_api.condor')
    def test_run_monitor_no_condor(self, mock_condor):
        """Test run_monitor raises error when condor not available."""
        # Mock condor error - use the class without instantiation
        mock_condor.htcondor.HTCondorLocateError = Exception
        mock_condor.CondorJobList.side_effect = Exception
        
        # Should raise RuntimeError
        with self.assertRaises(RuntimeError):
            run_monitor()
    
    @patch('asimov.monitor_api.ledger')
    def test_get_analysis_status(self, mock_ledger):
        """Test get_analysis_status function."""
        # Mock analyses
        mock_analysis = Mock()
        mock_analysis.name = "test_analysis"
        mock_analysis.status = "running"
        
        mock_ledger.project_analyses = [mock_analysis]
        mock_ledger.get_event.return_value = []
        
        # Get statuses
        statuses = get_analysis_status()
        
        # Check results
        self.assertIsInstance(statuses, dict)
        self.assertIn("project_analyses/test_analysis", statuses)
        self.assertEqual(statuses["project_analyses/test_analysis"], "running")
    
    @patch('asimov.monitor_api.ledger')
    def test_get_analysis_status_filtered(self, mock_ledger):
        """Test get_analysis_status with filter."""
        # Mock analyses
        mock_analysis1 = Mock()
        mock_analysis1.name = "test_analysis_1"
        mock_analysis1.status = "running"
        
        mock_analysis2 = Mock()
        mock_analysis2.name = "test_analysis_2"
        mock_analysis2.status = "finished"
        
        mock_ledger.project_analyses = [mock_analysis1, mock_analysis2]
        mock_ledger.get_event.return_value = []
        
        # Get status for specific analysis
        statuses = get_analysis_status(analysis_name="test_analysis_1")
        
        # Should only have one
        self.assertEqual(len(statuses), 1)
        self.assertIn("project_analyses/test_analysis_1", statuses)
    
    @patch('asimov.monitor_api.ledger')
    def test_list_active_analyses(self, mock_ledger):
        """Test list_active_analyses function."""
        # Mock analyses
        mock_analysis = Mock()
        mock_analysis.name = "test_analysis"
        mock_analysis.status = "running"
        mock_analysis.pipeline = "bilby"
        
        mock_ledger.project_analyses = [mock_analysis]
        mock_ledger.get_event.return_value = []
        
        # List analyses
        analyses = list_active_analyses()
        
        # Check results
        self.assertIsInstance(analyses, list)
        self.assertEqual(len(analyses), 1)
        self.assertEqual(analyses[0]['name'], "test_analysis")
        self.assertEqual(analyses[0]['status'], "running")
        self.assertEqual(analyses[0]['type'], "project")
    
    @patch('asimov.monitor_api.ledger')
    def test_list_active_analyses_with_events(self, mock_ledger):
        """Test list_active_analyses with event analyses."""
        # Mock event
        mock_event = Mock()
        mock_event.name = "GW150914"
        
        mock_production = Mock()
        mock_production.name = "bilby_prod"
        mock_production.status = "running"
        mock_production.pipeline = "bilby"
        
        mock_event.productions = [mock_production]
        
        mock_ledger.project_analyses = []
        mock_ledger.get_event.return_value = [mock_event]
        
        # List analyses
        analyses = list_active_analyses()
        
        # Check results
        self.assertEqual(len(analyses), 1)
        self.assertEqual(analyses[0]['name'], "bilby_prod")
        self.assertEqual(analyses[0]['type'], "event")
        self.assertEqual(analyses[0]['event'], "GW150914")


if __name__ == '__main__':
    unittest.main()
