"""
Tests for example labeller implementations.
"""

import unittest
from unittest.mock import Mock

from asimov.example_labellers import (
    AlwaysInterestingLabeller,
    PipelineInterestLabeller,
    FinishedAnalysisLabeller,
    ConditionalLabeller,
    create_pipeline_labeller,
    create_conditional_labeller,
)


class TestAlwaysInterestingLabeller(unittest.TestCase):
    """Test the AlwaysInterestingLabeller."""
    
    def test_name(self):
        """Test labeller name."""
        labeller = AlwaysInterestingLabeller()
        self.assertEqual(labeller.name, "always_interesting")
    
    def test_label(self):
        """Test that all analyses are marked as interesting."""
        labeller = AlwaysInterestingLabeller()
        mock_analysis = Mock()
        
        labels = labeller.label(mock_analysis)
        
        self.assertEqual(labels, {"interesting": True})


class TestPipelineInterestLabeller(unittest.TestCase):
    """Test the PipelineInterestLabeller."""
    
    def test_name(self):
        """Test labeller name."""
        labeller = PipelineInterestLabeller()
        self.assertEqual(labeller.name, "pipeline_interest")
    
    def test_default_pipelines(self):
        """Test default interesting pipelines."""
        labeller = PipelineInterestLabeller()
        
        # bilby should be interesting by default
        mock_analysis = Mock()
        mock_analysis.pipeline = Mock()
        mock_analysis.pipeline.__str__ = Mock(return_value="bilby")
        mock_analysis.name = "test"
        
        labels = labeller.label(mock_analysis)
        self.assertTrue(labels["interesting"])
    
    def test_custom_pipelines(self):
        """Test custom interesting pipelines."""
        labeller = PipelineInterestLabeller(["RIFT", "lalinference"])
        
        # RIFT should be interesting
        mock_analysis = Mock()
        mock_analysis.pipeline = Mock()
        mock_analysis.pipeline.__str__ = Mock(return_value="RIFT")
        mock_analysis.name = "test"
        
        labels = labeller.label(mock_analysis)
        self.assertTrue(labels["interesting"])
        
        # bilby should not be interesting (not in custom list)
        mock_analysis.pipeline.__str__ = Mock(return_value="bilby")
        labels = labeller.label(mock_analysis)
        self.assertFalse(labels["interesting"])
    
    def test_case_insensitive(self):
        """Test that pipeline matching is case-insensitive."""
        labeller = PipelineInterestLabeller(["BiLbY"])
        
        mock_analysis = Mock()
        mock_analysis.pipeline = Mock()
        mock_analysis.pipeline.__str__ = Mock(return_value="bilby")
        mock_analysis.name = "test"
        
        labels = labeller.label(mock_analysis)
        self.assertTrue(labels["interesting"])
    
    def test_substring_matching(self):
        """Test that pipeline matching works with substrings."""
        labeller = PipelineInterestLabeller(["bilby"])
        
        # Should match "bilby_pipe"
        mock_analysis = Mock()
        mock_analysis.pipeline = Mock()
        mock_analysis.pipeline.__str__ = Mock(return_value="bilby_pipe")
        mock_analysis.name = "test"
        
        labels = labeller.label(mock_analysis)
        self.assertTrue(labels["interesting"])
    
    def test_no_pipeline_attribute(self):
        """Test handling analysis without pipeline attribute."""
        labeller = PipelineInterestLabeller()
        
        mock_analysis = Mock(spec=[])  # No pipeline attribute
        
        labels = labeller.label(mock_analysis)
        self.assertEqual(labels, {})


class TestFinishedAnalysisLabeller(unittest.TestCase):
    """Test the FinishedAnalysisLabeller."""
    
    def test_name(self):
        """Test labeller name."""
        labeller = FinishedAnalysisLabeller()
        self.assertEqual(labeller.name, "finished_interest")
    
    def test_should_label_finished(self):
        """Test that finished analyses should be labeled."""
        labeller = FinishedAnalysisLabeller()
        
        mock_analysis = Mock()
        mock_analysis.status = "finished"
        
        self.assertTrue(labeller.should_label(mock_analysis))
    
    def test_should_label_uploaded(self):
        """Test that uploaded analyses should be labeled."""
        labeller = FinishedAnalysisLabeller()
        
        mock_analysis = Mock()
        mock_analysis.status = "uploaded"
        
        self.assertTrue(labeller.should_label(mock_analysis))
    
    def test_should_not_label_running(self):
        """Test that running analyses should not be labeled."""
        labeller = FinishedAnalysisLabeller()
        
        mock_analysis = Mock()
        mock_analysis.status = "running"
        
        self.assertFalse(labeller.should_label(mock_analysis))
    
    def test_label(self):
        """Test that labelling returns interest status."""
        labeller = FinishedAnalysisLabeller()
        mock_analysis = Mock()
        
        labels = labeller.label(mock_analysis)
        self.assertEqual(labels, {"interesting": True})


class TestConditionalLabeller(unittest.TestCase):
    """Test the ConditionalLabeller."""
    
    def test_default_name(self):
        """Test default labeller name."""
        labeller = ConditionalLabeller()
        self.assertEqual(labeller.name, "conditional")
    
    def test_custom_name(self):
        """Test custom labeller name."""
        labeller = ConditionalLabeller(labeller_name="custom")
        self.assertEqual(labeller.name, "custom")
    
    def test_default_condition(self):
        """Test default condition (always True)."""
        labeller = ConditionalLabeller()
        mock_analysis = Mock()
        
        labels = labeller.label(mock_analysis)
        self.assertTrue(labels["interesting"])
    
    def test_custom_condition_true(self):
        """Test custom condition that returns True."""
        def condition(analysis):
            return analysis.test_attr == "interesting"
        
        labeller = ConditionalLabeller(condition_func=condition)
        
        mock_analysis = Mock()
        mock_analysis.test_attr = "interesting"
        
        labels = labeller.label(mock_analysis)
        self.assertTrue(labels["interesting"])
    
    def test_custom_condition_false(self):
        """Test custom condition that returns False."""
        def condition(analysis):
            return analysis.test_attr == "interesting"
        
        labeller = ConditionalLabeller(condition_func=condition)
        
        mock_analysis = Mock()
        mock_analysis.test_attr = "boring"
        
        labels = labeller.label(mock_analysis)
        self.assertFalse(labels["interesting"])
    
    def test_condition_error_handling(self):
        """Test that errors in condition are handled gracefully."""
        def bad_condition(analysis):
            raise ValueError("Test error")
        
        labeller = ConditionalLabeller(condition_func=bad_condition)
        mock_analysis = Mock()
        
        # Should not raise, just return empty dict
        labels = labeller.label(mock_analysis)
        self.assertEqual(labels, {})
    
    def test_condition_with_complex_logic(self):
        """Test condition with complex logic."""
        def high_mass_condition(analysis):
            if hasattr(analysis, 'meta') and 'mass' in analysis.meta:
                return analysis.meta['mass'] > 50
            return False
        
        labeller = ConditionalLabeller(condition_func=high_mass_condition)
        
        # High mass analysis
        mock_analysis = Mock()
        mock_analysis.meta = {'mass': 60}
        labels = labeller.label(mock_analysis)
        self.assertTrue(labels["interesting"])
        
        # Low mass analysis
        mock_analysis.meta = {'mass': 30}
        labels = labeller.label(mock_analysis)
        self.assertFalse(labels["interesting"])


class TestFactoryFunctions(unittest.TestCase):
    """Test factory functions for creating labellers."""
    
    def test_create_pipeline_labeller(self):
        """Test creating a pipeline labeller."""
        labeller = create_pipeline_labeller(["RIFT", "bilby"])
        
        self.assertIsInstance(labeller, PipelineInterestLabeller)
        self.assertEqual(labeller.interesting_pipelines, ["rift", "bilby"])
    
    def test_create_conditional_labeller(self):
        """Test creating a conditional labeller."""
        def test_condition(analysis):
            return True
        
        labeller = create_conditional_labeller(test_condition, "test")
        
        self.assertIsInstance(labeller, ConditionalLabeller)
        self.assertEqual(labeller.name, "test")
        
        mock_analysis = Mock()
        labels = labeller.label(mock_analysis)
        self.assertTrue(labels["interesting"])
    
    def test_create_conditional_labeller_default_name(self):
        """Test creating conditional labeller with default name."""
        labeller = create_conditional_labeller(lambda a: True)
        self.assertEqual(labeller.name, "conditional")


if __name__ == '__main__':
    unittest.main()
