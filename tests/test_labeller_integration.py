"""
Integration tests for labeller system with monitor.
"""

import unittest
from unittest.mock import Mock, patch

from asimov.labellers import register_labeller, apply_labellers, LABELLER_REGISTRY
from asimov.example_labellers import PipelineInterestLabeller
from asimov.monitor_helpers import monitor_analysis
from asimov.monitor_context import MonitorContext


class TestLabellerMonitorIntegration(unittest.TestCase):
    """Test integration of labellers with monitor system."""
    
    def setUp(self):
        """Clear labeller registry before each test."""
        LABELLER_REGISTRY.clear()
    
    def tearDown(self):
        """Clear labeller registry after each test."""
        LABELLER_REGISTRY.clear()
    
    def test_labeller_applied_during_monitoring(self):
        """Test that labellers are applied when monitoring an analysis."""
        # Register a labeller
        labeller = PipelineInterestLabeller(["bilby"])
        register_labeller(labeller)
        
        # Create mock analysis
        mock_analysis = Mock()
        mock_analysis.name = "test_analysis"
        mock_analysis.status = "ready"
        mock_analysis.pipeline = Mock()
        mock_analysis.pipeline.__str__ = Mock(return_value="bilby")
        mock_analysis.meta = {}
        
        # Create mock job list and ledger
        mock_job_list = Mock()
        mock_ledger = Mock()
        
        # Monitor the analysis (with mocked state handler)
        with patch('asimov.monitor_helpers.get_state_handler') as mock_get_handler:
            mock_handler = Mock()
            mock_handler.handle.return_value = True
            mock_get_handler.return_value = mock_handler
            
            result = monitor_analysis(
                analysis=mock_analysis,
                job_list=mock_job_list,
                ledger=mock_ledger,
                dry_run=False
            )
        
        # Verify labeller was applied
        self.assertTrue(result)
        self.assertTrue(mock_analysis.meta.get("labels", {}).get("interesting"))
    
    def test_multiple_labellers_applied(self):
        """Test that multiple labellers are all applied."""
        from asimov.labellers import Labeller
        
        class TestLabeller1(Labeller):
            @property
            def name(self):
                return "labeller1"
            
            def label(self, analysis, context=None):
                return {"label1": "value1"}
        
        class TestLabeller2(Labeller):
            @property
            def name(self):
                return "labeller2"
            
            def label(self, analysis, context=None):
                return {"label2": "value2"}
        
        register_labeller(TestLabeller1())
        register_labeller(TestLabeller2())
        
        # Create mock analysis
        mock_analysis = Mock()
        mock_analysis.name = "test_analysis"
        mock_analysis.status = "ready"
        mock_analysis.meta = {}
        
        # Create context
        mock_context = Mock()
        
        # Apply labellers
        labels = apply_labellers(mock_analysis, mock_context)
        
        # Verify both labellers were applied
        self.assertIn("label1", labels)
        self.assertIn("label2", labels)
        self.assertEqual(mock_analysis.meta["labels"]["label1"], "value1")
        self.assertEqual(mock_analysis.meta["labels"]["label2"], "value2")
    
    def test_labeller_with_monitor_context(self):
        """Test that labellers receive the monitor context."""
        from asimov.labellers import Labeller
        
        class ContextAwareLabeller(Labeller):
            def __init__(self):
                self.received_context = None
            
            @property
            def name(self):
                return "context_aware"
            
            def label(self, analysis, context=None):
                self.received_context = context
                if context is not None:
                    return {"has_context": True}
                return {"has_context": False}
        
        labeller = ContextAwareLabeller()
        register_labeller(labeller)
        
        # Create mock analysis and context
        mock_analysis = Mock()
        mock_analysis.name = "test"
        mock_analysis.meta = {}
        
        mock_job_list = Mock()
        mock_ledger = Mock()
        
        context = MonitorContext(
            analysis=mock_analysis,
            job_list=mock_job_list,
            ledger=mock_ledger,
            dry_run=False,
            analysis_path="test/analysis"
        )
        
        # Apply labellers with context
        labels = apply_labellers(mock_analysis, context)
        
        # Verify labeller received context
        self.assertIsNotNone(labeller.received_context)
        self.assertTrue(labels.get("has_context"))
    
    def test_labeller_error_doesnt_break_monitoring(self):
        """Test that errors in labellers don't break monitoring."""
        from asimov.labellers import Labeller
        
        class ErrorLabeller(Labeller):
            @property
            def name(self):
                return "error_labeller"
            
            def label(self, analysis, context=None):
                raise ValueError("Test error")
        
        register_labeller(ErrorLabeller())
        
        # Create mock analysis
        mock_analysis = Mock()
        mock_analysis.name = "test_analysis"
        mock_analysis.status = "ready"
        mock_analysis.meta = {}
        
        # Apply labellers - should not raise
        labels = apply_labellers(mock_analysis)
        
        # Should return empty labels, not crash
        self.assertEqual(labels, {})
    
    def test_labeller_interest_status_used_in_workflow(self):
        """Test that interest status set by labeller can be used."""
        # Register a labeller that marks analyses as interesting
        labeller = PipelineInterestLabeller(["bilby"])
        register_labeller(labeller)
        
        # Create mock bilby analysis
        mock_analysis = Mock()
        mock_analysis.name = "bilby_prod1"
        mock_analysis.pipeline = Mock()
        mock_analysis.pipeline.__str__ = Mock(return_value="bilby")
        mock_analysis.meta = {}
        
        # Apply labellers
        apply_labellers(mock_analysis)
        
        # Verify interest status was set
        self.assertTrue(mock_analysis.meta.get("labels", {}).get("interesting"))
        
        # Simulate checking interest status in workflow
        if mock_analysis.meta.get("labels", {}).get("interesting"):
            # This analysis would be prioritized
            pass
        
        self.assertTrue(True)  # Test completed successfully


if __name__ == '__main__':
    unittest.main()
