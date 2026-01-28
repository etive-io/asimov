"""
Unit tests for the monitor helper functions.
"""

import unittest
from unittest.mock import Mock, patch

from asimov.monitor_helpers import monitor_analysis, monitor_analyses_list



class TestMonitorAnalysis(unittest.TestCase):
    """Test the monitor_analysis function."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.analysis = Mock()
        self.analysis.name = "test_analysis"
        self.analysis.status = "running"
        self.analysis.pipeline = "bilby"
        self.analysis.event = Mock()
        self.analysis.event.name = "GW150914"
        
        self.job_list = Mock()
        self.job_list.jobs = {}
        
        self.ledger = Mock()
        self.ledger.update_event = Mock()
        self.ledger.save = Mock()
    
    @patch('asimov.monitor_helpers.get_state_handler')
    @patch('asimov.monitor_helpers.click.echo')
    def test_monitor_analysis_success(self, mock_echo, mock_get_handler):
        """Test successful monitoring of an analysis."""
        # Mock state handler
        mock_handler = Mock()
        mock_handler.handle = Mock(return_value=True)
        mock_get_handler.return_value = mock_handler
        
        result = monitor_analysis(
            self.analysis,
            self.job_list,
            self.ledger,
            dry_run=False
        )
        
        self.assertTrue(result)
        mock_handler.handle.assert_called_once()
    
    @patch('asimov.monitor_helpers.get_state_handler')
    @patch('asimov.monitor_helpers.click.echo')
    def test_monitor_analysis_with_path(self, mock_echo, mock_get_handler):
        """Test monitoring with explicit analysis path."""
        mock_handler = Mock()
        mock_handler.handle = Mock(return_value=True)
        mock_get_handler.return_value = mock_handler
        
        result = monitor_analysis(
            self.analysis,
            self.job_list,
            self.ledger,
            analysis_path="custom/path"
        )
        
        self.assertTrue(result)
    
    @patch('asimov.monitor_helpers.get_state_handler')
    @patch('asimov.monitor_helpers.click.echo')
    def test_monitor_analysis_inactive_skipped(self, mock_echo, mock_get_handler):
        """Test that inactive analyses are skipped."""
        self.analysis.status = "cancelled"  # Not in ACTIVE_STATES
        
        result = monitor_analysis(
            self.analysis,
            self.job_list,
            self.ledger
        )
        
        # Should still return True (successfully skipped)
        self.assertTrue(result)
        mock_get_handler.assert_not_called()
    
    @patch('asimov.monitor_helpers.get_state_handler')
    @patch('asimov.monitor_helpers.click.echo')
    def test_monitor_analysis_unknown_state(self, mock_echo, mock_get_handler):
        """Test handling of unknown state."""
        mock_get_handler.return_value = None  # No handler found
        
        result = monitor_analysis(
            self.analysis,
            self.job_list,
            self.ledger
        )
        
        self.assertFalse(result)
    
    @patch('asimov.monitor_helpers.get_state_handler')
    @patch('asimov.monitor_helpers.click.echo')
    @patch('asimov.monitor_helpers.logger')
    def test_monitor_analysis_handler_exception(self, mock_logger, mock_echo, mock_get_handler):
        """Test handling of exception in state handler."""
        mock_handler = Mock()
        mock_handler.handle = Mock(side_effect=Exception("Test error"))
        mock_get_handler.return_value = mock_handler
        
        result = monitor_analysis(
            self.analysis,
            self.job_list,
            self.ledger
        )
        
        self.assertFalse(result)
        mock_logger.exception.assert_called_once()
    
    @patch('asimov.monitor_helpers.get_state_handler')
    @patch('asimov.monitor_helpers.click.echo')
    def test_monitor_project_analysis(self, mock_echo, mock_get_handler):
        """Test monitoring a project analysis (no event attribute)."""
        # Remove event attribute to simulate ProjectAnalysis
        delattr(self.analysis, 'event')
        
        mock_handler = Mock()
        mock_handler.handle = Mock(return_value=True)
        mock_get_handler.return_value = mock_handler
        
        result = monitor_analysis(
            self.analysis,
            self.job_list,
            self.ledger
        )
        
        self.assertTrue(result)
    
    @patch('asimov.monitor_helpers.get_state_handler')
    @patch('asimov.monitor_helpers.click.echo')
    def test_monitor_analysis_with_pipeline_states(self, mock_echo, mock_get_handler):
        """Test that pipeline is passed to get_state_handler."""
        mock_handler = Mock()
        mock_handler.handle = Mock(return_value=True)
        mock_get_handler.return_value = mock_handler
        
        # Create a mock pipeline
        mock_pipeline = Mock()
        self.analysis.pipeline = mock_pipeline
        
        monitor_analysis(
            self.analysis,
            self.job_list,
            self.ledger
        )
        
        # Verify get_state_handler was called with pipeline
        mock_get_handler.assert_called_once()
        call_kwargs = mock_get_handler.call_args[1]
        self.assertEqual(call_kwargs.get('pipeline'), mock_pipeline)


class TestMonitorAnalysesList(unittest.TestCase):
    """Test the monitor_analyses_list function."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.job_list = Mock()
        self.ledger = Mock()
    
    @patch('asimov.monitor_helpers.monitor_analysis')
    def test_monitor_empty_list(self, mock_monitor):
        """Test monitoring an empty list of analyses."""
        stats = monitor_analyses_list([], self.job_list, self.ledger)
        
        self.assertEqual(stats["total"], 0)
        mock_monitor.assert_not_called()
    
    @patch('asimov.monitor_helpers.monitor_analysis')
    def test_monitor_multiple_analyses(self, mock_monitor):
        """Test monitoring multiple analyses."""
        mock_monitor.return_value = True
        
        analyses = [
            Mock(name=f"analysis_{i}", status="running")
            for i in range(3)
        ]
        
        stats = monitor_analyses_list(
            analyses,
            self.job_list,
            self.ledger,
            label="test_analyses"
        )
        
        self.assertEqual(stats["total"], 3)
        self.assertEqual(mock_monitor.call_count, 3)
    
    @patch('asimov.monitor_helpers.monitor_analysis')
    def test_monitor_mixed_states(self, mock_monitor):
        """Test monitoring analyses in different states."""
        mock_monitor.return_value = True
        
        analyses = [
            Mock(name="running_1", status="running"),
            Mock(name="stuck_1", status="stuck"),
            Mock(name="ready_1", status="ready"),
            Mock(name="finished_1", status="finished"),
            Mock(name="running_2", status="running"),
        ]
        
        stats = monitor_analyses_list(analyses, self.job_list, self.ledger)
        
        self.assertEqual(stats["total"], 5)
        self.assertEqual(stats["running"], 2)
        self.assertEqual(stats["stuck"], 1)
        self.assertEqual(stats["ready"], 1)
        self.assertEqual(stats["finished"], 1)
    
    @patch('asimov.monitor_helpers.monitor_analysis')
    def test_monitor_skips_inactive(self, mock_monitor):
        """Test that inactive analyses are skipped."""
        analyses = [
            Mock(name="active", status="running"),
            Mock(name="cancelled", status="cancelled"),
            Mock(name="manual", status="manual"),
        ]
        
        stats = monitor_analyses_list(analyses, self.job_list, self.ledger)
        
        # Only the active one should be monitored
        self.assertEqual(stats["total"], 1)
        mock_monitor.assert_called_once()


if __name__ == '__main__':
    unittest.main()
