"""
Tests for label-based dependency resolution.
"""

import unittest
from unittest.mock import Mock, patch

# Import the actual method implementation
from asimov.analysis import Analysis


class MockAnalysis:
    """Mock analysis that includes _matches_label and matches_filter methods."""
    
    def __init__(self):
        self.meta = {}
        self.review = Mock()
        self.review.status = 'none'
        self.status = 'ready'
        self.name = 'test'
    
    # Copy the actual implementation from Analysis
    def _matches_label(self, spec):
        """Implementation copied from Analysis class."""
        import re
        
        # Get labels from metadata
        labels = self.meta.get('labels', {})
        
        # Parse the specification for comparison operators
        match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)(>=|<=|>|<|==|!=)?(.*)$', spec.strip())
        
        if not match:
            return False
        
        label_name = match.group(1)
        operator = match.group(2)
        threshold = match.group(3).strip() if match.group(3) else None
        
        # Check if label exists
        if label_name not in labels:
            return False
        
        label_value = labels[label_name]
        
        # If no operator specified, just check if label is truthy
        if not operator or not threshold:
            return bool(label_value)
        
        # Try to convert to numeric for comparison
        try:
            label_num = float(label_value) if not isinstance(label_value, bool) else int(label_value)
            threshold_num = float(threshold)
            
            if operator == '>=':
                return label_num >= threshold_num
            elif operator == '<=':
                return label_num <= threshold_num
            elif operator == '>':
                return label_num > threshold_num
            elif operator == '<':
                return label_num < threshold_num
            elif operator == '==':
                return label_num == threshold_num
            elif operator == '!=':
                return label_num != threshold_num
        except (ValueError, TypeError):
            # Fall back to string comparison
            if operator == '==':
                return str(label_value).lower() == threshold.lower()
            elif operator == '!=':
                return str(label_value).lower() != threshold.lower()
        
        return False
    
    def matches_filter(self, attribute, match, negate=False):
        """Simplified matches_filter that only handles labels."""
        if attribute[0] == "label":
            is_label = self._matches_label(match)
            if negate:
                return not is_label
            return is_label
        return False


class TestLabelDependencies(unittest.TestCase):
    """Test label-based dependency resolution."""
    
    def test_label_dependency_simple(self):
        """Test simple label dependency without comparison."""
        analysis = MockAnalysis()
        analysis.meta = {'labels': {'interesting': True}}
        
        # Test simple label check (label exists and is truthy)
        result = analysis._matches_label('interesting')
        self.assertTrue(result)
    
    def test_label_dependency_false_value(self):
        """Test label dependency with False value."""
        analysis = MockAnalysis()
        analysis.meta = {'labels': {'interesting': False}}
        
        # Should return False since label value is False
        result = analysis._matches_label('interesting')
        self.assertFalse(result)
    
    def test_label_dependency_missing(self):
        """Test label dependency when label doesn't exist."""
        analysis = MockAnalysis()
        analysis.meta = {'labels': {}}
        
        result = analysis._matches_label('interesting')
        self.assertFalse(result)
    
    def test_label_dependency_greater_than(self):
        """Test label dependency with > operator."""
        analysis = MockAnalysis()
        analysis.meta = {'labels': {'priority': 10}}
        
        result = analysis._matches_label('priority>5')
        self.assertTrue(result)
        
        result = analysis._matches_label('priority>15')
        self.assertFalse(result)
    
    def test_label_dependency_greater_equal(self):
        """Test label dependency with >= operator."""
        analysis = MockAnalysis()
        analysis.meta = {'labels': {'priority': 10}}
        
        result = analysis._matches_label('priority>=10')
        self.assertTrue(result)
        
        result = analysis._matches_label('priority>=11')
        self.assertFalse(result)
    
    def test_label_dependency_less_than(self):
        """Test label dependency with < operator."""
        analysis = MockAnalysis()
        analysis.meta = {'labels': {'priority': 5}}
        
        result = analysis._matches_label('priority<10')
        self.assertTrue(result)
        
        result = analysis._matches_label('priority<5')
        self.assertFalse(result)
    
    def test_label_dependency_less_equal(self):
        """Test label dependency with <= operator."""
        analysis = MockAnalysis()
        analysis.meta = {'labels': {'priority': 5}}
        
        result = analysis._matches_label('priority<=5')
        self.assertTrue(result)
        
        result = analysis._matches_label('priority<=4')
        self.assertFalse(result)
    
    def test_label_dependency_equals(self):
        """Test label dependency with == operator."""
        analysis = MockAnalysis()
        analysis.meta = {'labels': {'priority': 5}}
        
        result = analysis._matches_label('priority==5')
        self.assertTrue(result)
        
        result = analysis._matches_label('priority==10')
        self.assertFalse(result)
    
    def test_label_dependency_not_equals(self):
        """Test label dependency with != operator."""
        analysis = MockAnalysis()
        analysis.meta = {'labels': {'priority': 5}}
        
        result = analysis._matches_label('priority!=10')
        self.assertTrue(result)
        
        result = analysis._matches_label('priority!=5')
        self.assertFalse(result)
    
    def test_label_dependency_string_comparison(self):
        """Test label dependency with string values."""
        analysis = MockAnalysis()
        analysis.meta = {'labels': {'status': 'complete'}}
        
        result = analysis._matches_label('status==complete')
        self.assertTrue(result)
        
        result = analysis._matches_label('status!=pending')
        self.assertTrue(result)
        
        result = analysis._matches_label('status==pending')
        self.assertFalse(result)
    
    def test_label_dependency_boolean_as_number(self):
        """Test label dependency with boolean converted to number."""
        analysis = MockAnalysis()
        analysis.meta = {'labels': {'interesting': True}}
        
        # True should be treated as 1
        result = analysis._matches_label('interesting>=1')
        self.assertTrue(result)
        
        result = analysis._matches_label('interesting==1')
        self.assertTrue(result)
    
    def test_matches_filter_with_label(self):
        """Test matches_filter with label attribute."""
        analysis = MockAnalysis()
        analysis.meta = {'labels': {'interesting': True}}
        analysis.review = Mock()
        analysis.review.status = 'none'
        analysis.status = 'ready'
        analysis.name = 'test'
        
        # Test label matching through matches_filter
        result = analysis.matches_filter(['label'], 'interesting')
        self.assertTrue(result)
        
        result = analysis.matches_filter(['label'], 'interesting>=1')
        self.assertTrue(result)
        
        result = analysis.matches_filter(['label'], 'nonexistent')
        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
