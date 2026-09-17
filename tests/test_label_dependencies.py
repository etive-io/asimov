"""
Tests for label-based dependency resolution.
"""

import unittest
from unittest.mock import Mock


class TestLabelDependencies(unittest.TestCase):
    """Test label-based dependency resolution."""
    
    def _create_test_analysis(self, labels=None):
        """Create a minimal Analysis instance for testing."""
        # Import here to avoid module-level import issues
        from asimov.analysis import Analysis
        
        analysis = Mock(spec=Analysis)
        analysis.meta = {'labels': labels or {}}
        analysis.review = Mock()
        analysis.review.status = 'none'
        analysis.status = 'ready'
        analysis.name = 'test'
        # Use the real implementation from Analysis
        analysis._matches_label = Analysis._matches_label.__get__(analysis, type(analysis))
        analysis.matches_filter = Analysis.matches_filter.__get__(analysis, type(analysis))
        return analysis
    
    def test_label_dependency_simple(self):
        """Test simple label dependency without comparison."""
        analysis = self._create_test_analysis({'interesting': True})
        
        # Test simple label check (label exists and is truthy)
        result = analysis._matches_label('interesting')
        self.assertTrue(result)
    
    def test_label_dependency_false_value(self):
        """Test label dependency with False value."""
        analysis = self._create_test_analysis({'interesting': False})
        
        # Should return False since label value is False
        result = analysis._matches_label('interesting')
        self.assertFalse(result)
    
    def test_label_dependency_missing(self):
        """Test label dependency when label doesn't exist."""
        analysis = self._create_test_analysis({})
        
        result = analysis._matches_label('interesting')
        self.assertFalse(result)
    
    def test_label_dependency_greater_than(self):
        """Test label dependency with > operator."""
        analysis = self._create_test_analysis({'priority': 10})
        
        result = analysis._matches_label('priority>5')
        self.assertTrue(result)
        
        result = analysis._matches_label('priority>15')
        self.assertFalse(result)
    
    def test_label_dependency_greater_equal(self):
        """Test label dependency with >= operator."""
        analysis = self._create_test_analysis({'priority': 10})
        
        result = analysis._matches_label('priority>=10')
        self.assertTrue(result)
        
        result = analysis._matches_label('priority>=11')
        self.assertFalse(result)
    
    def test_label_dependency_less_than(self):
        """Test label dependency with < operator."""
        analysis = self._create_test_analysis({'priority': 5})
        
        result = analysis._matches_label('priority<10')
        self.assertTrue(result)
        
        result = analysis._matches_label('priority<5')
        self.assertFalse(result)
    
    def test_label_dependency_less_equal(self):
        """Test label dependency with <= operator."""
        analysis = self._create_test_analysis({'priority': 5})
        
        result = analysis._matches_label('priority<=5')
        self.assertTrue(result)
        
        result = analysis._matches_label('priority<=4')
        self.assertFalse(result)
    
    def test_label_dependency_equals(self):
        """Test label dependency with == operator."""
        analysis = self._create_test_analysis({'priority': 5})
        
        result = analysis._matches_label('priority==5')
        self.assertTrue(result)
        
        result = analysis._matches_label('priority==10')
        self.assertFalse(result)
    
    def test_label_dependency_not_equals(self):
        """Test label dependency with != operator."""
        analysis = self._create_test_analysis({'priority': 5})
        
        result = analysis._matches_label('priority!=10')
        self.assertTrue(result)
        
        result = analysis._matches_label('priority!=5')
        self.assertFalse(result)
    
    def test_label_dependency_string_comparison(self):
        """Test label dependency with string values."""
        analysis = self._create_test_analysis({'status': 'complete'})
        
        result = analysis._matches_label('status==complete')
        self.assertTrue(result)
        
        result = analysis._matches_label('status!=pending')
        self.assertTrue(result)
        
        result = analysis._matches_label('status==pending')
        self.assertFalse(result)
    
    def test_label_dependency_boolean_as_number(self):
        """Test label dependency with boolean converted to number."""
        analysis = self._create_test_analysis({'interesting': True})
        
        # True should be treated as 1
        result = analysis._matches_label('interesting>=1')
        self.assertTrue(result)
        
        result = analysis._matches_label('interesting==1')
        self.assertTrue(result)
    
    def test_matches_filter_with_label(self):
        """Test matches_filter with label attribute."""
        analysis = self._create_test_analysis({'interesting': True})
        
        # Test label matching through matches_filter
        result = analysis.matches_filter(['label'], 'interesting')
        self.assertTrue(result)
        
        result = analysis.matches_filter(['label'], 'interesting>=1')
        self.assertTrue(result)
        
        result = analysis.matches_filter(['label'], 'nonexistent')
        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
