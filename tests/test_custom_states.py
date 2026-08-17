"""
Unit tests for custom monitor states.
"""

import unittest
from unittest.mock import Mock, patch

from asimov.custom_states import (
    ReviewState,
    ReviewedState,
    UploadingState,
    UploadedState,
    RestartState,
    WaitState,
    CancelledState,
    ManualState,
    register_custom_states,
)
from asimov.monitor_context import MonitorContext


class TestCustomStates(unittest.TestCase):
    """Test custom state handlers."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.analysis = Mock()
        self.analysis.name = "test_analysis"
        self.analysis.pipeline = Mock()
        
        self.context = Mock(spec=MonitorContext)
        self.context.analysis = self.analysis
        self.context.update_ledger = Mock()
        self.context.has_condor_job = Mock(return_value=False)
    
    @patch('asimov.custom_states.click.echo')
    def test_review_state(self, mock_echo):
        """Test ReviewState handler."""
        state = ReviewState()
        self.assertEqual(state.state_name, "review")
        
        # Test with no review
        result = state.handle(self.context)
        self.assertTrue(result)
        
        # Test with approved review
        self.analysis.review = Mock()
        self.analysis.review.status = "approved"
        result = state.handle(self.context)
        self.assertTrue(result)
        self.assertEqual(self.analysis.status, "reviewed")
    
    @patch('asimov.custom_states.click.echo')
    def test_reviewed_state(self, mock_echo):
        """Test ReviewedState handler."""
        state = ReviewedState()
        self.assertEqual(state.state_name, "reviewed")
        
        result = state.handle(self.context)
        self.assertTrue(result)
    
    @patch('asimov.custom_states.click.echo')
    def test_uploading_state(self, mock_echo):
        """Test UploadingState handler."""
        state = UploadingState()
        self.assertEqual(state.state_name, "uploading")
        
        # Test without pipeline
        self.analysis.pipeline = None
        result = state.handle(self.context)
        self.assertFalse(result)
        
        # Test with pipeline
        self.analysis.pipeline = Mock()
        self.analysis.pipeline.detect_upload_completion = Mock(return_value=True)
        result = state.handle(self.context)
        self.assertTrue(result)
        self.assertEqual(self.analysis.status, "uploaded")
    
    @patch('asimov.custom_states.click.echo')
    def test_uploaded_state(self, mock_echo):
        """Test UploadedState handler."""
        state = UploadedState()
        self.assertEqual(state.state_name, "uploaded")
        
        result = state.handle(self.context)
        self.assertTrue(result)
    
    @patch('asimov.custom_states.click.echo')
    def test_restart_state(self, mock_echo):
        """Test RestartState handler."""
        state = RestartState()
        self.assertEqual(state.state_name, "restart")
        
        # Test without pipeline
        self.analysis.pipeline = None
        result = state.handle(self.context)
        self.assertFalse(result)
        
        # Test with pipeline
        self.analysis.pipeline = Mock()
        result = state.handle(self.context)
        self.assertTrue(result)
        self.assertEqual(self.analysis.status, "ready")
    
    @patch('asimov.custom_states.click.echo')
    def test_wait_state(self, mock_echo):
        """Test WaitState handler."""
        state = WaitState()
        self.assertEqual(state.state_name, "wait")
        
        # Mock _needs attribute as an empty list
        self.analysis._needs = []
        
        result = state.handle(self.context)
        self.assertTrue(result)
    
    @patch('asimov.custom_states.click.echo')
    def test_wait_state_with_dependencies(self, mock_echo):
        """Test WaitState handler with dependencies."""
        state = WaitState()
        
        # Mock _needs attribute with some dependencies
        self.analysis._needs = ["dep1", "dep2"]
        
        result = state.handle(self.context)
        self.assertTrue(result)
    
    @patch('asimov.custom_states.click.echo')
    def test_cancelled_state(self, mock_echo):
        """Test CancelledState handler."""
        state = CancelledState()
        self.assertEqual(state.state_name, "cancelled")
        
        result = state.handle(self.context)
        self.assertTrue(result)
    
    @patch('asimov.custom_states.click.echo')
    def test_manual_state(self, mock_echo):
        """Test ManualState handler."""
        state = ManualState()
        self.assertEqual(state.state_name, "manual")
        
        result = state.handle(self.context)
        self.assertTrue(result)
    
    @patch('asimov.custom_states.register_state')
    def test_register_custom_states(self, mock_register):
        """Test that all custom states are registered."""
        register_custom_states()
        
        # Should register 8 states
        self.assertEqual(mock_register.call_count, 8)


class TestCustomStateIntegration(unittest.TestCase):
    """Test integration of custom states with state registry."""
    
    def test_custom_states_in_registry(self):
        """Test that custom states are available in registry."""
        from asimov.monitor_states import get_state_handler
        
        # Test a few custom states
        review_handler = get_state_handler("review")
        self.assertIsInstance(review_handler, ReviewState)
        
        uploaded_handler = get_state_handler("uploaded")
        self.assertIsInstance(uploaded_handler, UploadedState)
        
        restart_handler = get_state_handler("restart")
        self.assertIsInstance(restart_handler, RestartState)


if __name__ == '__main__':
    unittest.main()
