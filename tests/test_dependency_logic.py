"""
Unit tests for dependency resolution logic without requiring full project setup.
"""
import unittest
from unittest.mock import Mock, MagicMock
from asimov.analysis import Analysis


class MockAnalysis(Analysis):
    """Mock analysis for testing dependency logic."""
    
    def __init__(self, name, **kwargs):
        self.name = name
        self.meta = kwargs.get('meta', {})
        self._needs = kwargs.get('needs', [])
        self.event = kwargs.get('event', None)
        self.status_str = kwargs.get('status', 'ready')
        self._reviews = MagicMock()
        self._reviews.status = kwargs.get('review_status', 'none')
    
    @property
    def review(self):
        return self._reviews


class DependencyLogicTests(unittest.TestCase):
    """Tests for core dependency resolution logic."""
    
    def setUp(self):
        """Create mock event with mock analyses."""
        self.event = Mock()
        
        # Create some mock analyses with different properties
        self.analysis1 = MockAnalysis(
            'Prod1', 
            meta={'pipeline': 'bayeswave', 'waveform': {'approximant': 'IMRPhenomXPHM'}},
            status='finished',
            review_status='approved'
        )
        self.analysis2 = MockAnalysis(
            'Prod2',
            meta={'pipeline': 'bilby', 'waveform': {'approximant': 'SEOBNRv5PHM'}},
            status='finished',
            review_status='approved'
        )
        self.analysis3 = MockAnalysis(
            'Prod3',
            meta={'pipeline': 'bayeswave', 'waveform': {'approximant': 'SEOBNRv5PHM'}},
            status='ready',
            review_status='none'
        )
        
        self.event.analyses = [self.analysis1, self.analysis2, self.analysis3]
        
    def test_parse_single_dependency_simple_name(self):
        """Test parsing a simple name dependency."""
        analysis = MockAnalysis('TestAnalysis', event=self.event)
        result = analysis._parse_single_dependency('Prod1')
        self.assertEqual(result, (['name'], 'Prod1', False, False))
    
    def test_parse_single_dependency_property(self):
        """Test parsing a property-based dependency."""
        analysis = MockAnalysis('TestAnalysis', event=self.event)
        result = analysis._parse_single_dependency('pipeline: bayeswave')
        self.assertEqual(result, (['pipeline'], 'bayeswave', False, False))
    
    def test_parse_single_dependency_nested_property(self):
        """Test parsing a nested property dependency."""
        analysis = MockAnalysis('TestAnalysis', event=self.event)
        result = analysis._parse_single_dependency('waveform.approximant: IMRPhenomXPHM')
        self.assertEqual(result, (['waveform', 'approximant'], 'IMRPhenomXPHM', False, False))
    
    def test_parse_single_dependency_negated(self):
        """Test parsing a negated dependency."""
        analysis = MockAnalysis('TestAnalysis', event=self.event)
        result = analysis._parse_single_dependency('pipeline: !bayeswave')
        self.assertEqual(result, (['pipeline'], 'bayeswave', True, False))
    
    def test_matches_filter_simple_name(self):
        """Test matching by name."""
        self.assertTrue(self.analysis1.matches_filter(['name'], 'Prod1', False))
        self.assertFalse(self.analysis1.matches_filter(['name'], 'Prod2', False))
    
    def test_matches_filter_property(self):
        """Test matching by simple property."""
        self.assertTrue(self.analysis1.matches_filter(['pipeline'], 'bayeswave', False))
        self.assertFalse(self.analysis2.matches_filter(['pipeline'], 'bayeswave', False))
    
    def test_matches_filter_nested_property(self):
        """Test matching by nested property."""
        self.assertTrue(
            self.analysis1.matches_filter(['waveform', 'approximant'], 'IMRPhenomXPHM', False)
        )
        self.assertFalse(
            self.analysis2.matches_filter(['waveform', 'approximant'], 'IMRPhenomXPHM', False)
        )
    
    def test_matches_filter_status(self):
        """Test matching by status."""
        self.assertTrue(self.analysis1.matches_filter(['status'], 'finished', False))
        self.assertFalse(self.analysis3.matches_filter(['status'], 'finished', False))
    
    def test_matches_filter_review(self):
        """Test matching by review status."""
        self.assertTrue(self.analysis1.matches_filter(['review', 'status'], 'approved', False))
        self.assertFalse(self.analysis3.matches_filter(['review', 'status'], 'approved', False))
    
    def test_matches_filter_negation(self):
        """Test negated matching."""
        # Negated name match
        self.assertFalse(self.analysis1.matches_filter(['name'], 'Prod1', True))
        self.assertTrue(self.analysis1.matches_filter(['name'], 'Prod2', True))
        
        # Negated pipeline match
        self.assertFalse(self.analysis1.matches_filter(['pipeline'], 'bayeswave', True))
        self.assertTrue(self.analysis2.matches_filter(['pipeline'], 'bayeswave', True))
    
    def test_process_dependencies_simple_list(self):
        """Test processing a simple list of dependencies."""
        analysis = MockAnalysis('TestAnalysis', event=self.event, needs=['Prod1', 'Prod2'])
        result = analysis._process_dependencies(analysis._needs)
        expected = [
            (['name'], 'Prod1', False, False),
            (['name'], 'Prod2', False, False)
        ]
        self.assertEqual(result, expected)
    
    def test_process_dependencies_property_queries(self):
        """Test processing property-based dependencies."""
        analysis = MockAnalysis(
            'TestAnalysis', 
            event=self.event, 
            needs=['pipeline: bayeswave', 'waveform.approximant: IMRPhenomXPHM']
        )
        result = analysis._process_dependencies(analysis._needs)
        expected = [
            (['pipeline'], 'bayeswave', False, False),
            (['waveform', 'approximant'], 'IMRPhenomXPHM', False, False)
        ]
        self.assertEqual(result, expected)
    
    def test_process_dependencies_and_group(self):
        """Test processing AND group (nested list)."""
        analysis = MockAnalysis(
            'TestAnalysis',
            event=self.event,
            needs=[['pipeline: bayeswave', 'status: finished']]
        )
        result = analysis._process_dependencies(analysis._needs)
        expected = [
            [
                (['pipeline'], 'bayeswave', False, False),
                (['status'], 'finished', False, False)
            ]
        ]
        self.assertEqual(result, expected)
    
    def test_dependencies_simple_or_logic(self):
        """Test OR logic with multiple simple dependencies."""
        analysis = MockAnalysis(
            'TestAnalysis',
            event=self.event,
            needs=['Prod1', 'Prod2']
        )
        
        deps = analysis.dependencies
        self.assertEqual(len(deps), 2)
        self.assertIn('Prod1', deps)
        self.assertIn('Prod2', deps)
    
    def test_dependencies_property_or_logic(self):
        """Test OR logic with property-based dependencies."""
        analysis = MockAnalysis(
            'TestAnalysis',
            event=self.event,
            needs=['waveform.approximant: IMRPhenomXPHM', 'waveform.approximant: SEOBNRv5PHM']
        )
        
        deps = analysis.dependencies
        # Should match Prod1 (IMRPhenomXPHM), Prod2 (SEOBNRv5PHM), and Prod3 (SEOBNRv5PHM)
        self.assertEqual(len(deps), 3)
        self.assertIn('Prod1', deps)
        self.assertIn('Prod2', deps)
        self.assertIn('Prod3', deps)
    
    def test_dependencies_and_logic(self):
        """Test AND logic with nested list."""
        analysis = MockAnalysis(
            'TestAnalysis',
            event=self.event,
            needs=[['pipeline: bayeswave', 'waveform.approximant: IMRPhenomXPHM']]
        )
        
        deps = analysis.dependencies
        # Should only match Prod1 (bayeswave AND IMRPhenomXPHM)
        self.assertEqual(len(deps), 1)
        self.assertIn('Prod1', deps)
    
    def test_dependencies_negation(self):
        """Test negation in dependencies."""
        analysis = MockAnalysis(
            'TestAnalysis',
            event=self.event,
            needs=['pipeline: !bilby']
        )
        
        deps = analysis.dependencies
        # Should match Prod1 and Prod3 (both not bilby)
        self.assertEqual(len(deps), 2)
        self.assertIn('Prod1', deps)
        self.assertIn('Prod3', deps)
        self.assertNotIn('Prod2', deps)
    
    def test_dependencies_complex_and_or(self):
        """Test complex combination of AND and OR logic."""
        analysis = MockAnalysis(
            'TestAnalysis',
            event=self.event,
            needs=[
                ['pipeline: bayeswave', 'status: finished'],  # AND group
                'waveform.approximant: SEOBNRv5PHM'  # OR'd with the AND group
            ]
        )
        
        deps = analysis.dependencies
        # Should match:
        # - Prod1 (bayeswave AND finished)
        # - Prod2 (SEOBNRv5PHM)
        # - Prod3 (SEOBNRv5PHM)
        self.assertEqual(len(deps), 3)
        self.assertIn('Prod1', deps)
        self.assertIn('Prod2', deps)
        self.assertIn('Prod3', deps)
    
    def test_staleness_detection(self):
        """Test staleness detection."""
        analysis = MockAnalysis('TestAnalysis', event=self.event, needs=['Prod1'])
        
        # Initially not stale (no resolved dependencies)
        self.assertFalse(analysis.is_stale)
        
        # Record dependencies
        analysis.resolved_dependencies = ['Prod1']
        self.assertFalse(analysis.is_stale)
        
        # Change dependencies
        analysis._needs = ['Prod2']
        # Now dependencies changed, should be stale
        current_deps = set(analysis.dependencies)
        resolved_deps = set(analysis.resolved_dependencies)
        self.assertNotEqual(current_deps, resolved_deps)
    
    def test_refreshable_flag(self):
        """Test refreshable flag."""
        analysis = MockAnalysis('TestAnalysis', event=self.event)
        
        # Default is False
        self.assertFalse(analysis.is_refreshable)
        
        # Set to True
        analysis.is_refreshable = True
        self.assertTrue(analysis.is_refreshable)
        self.assertTrue(analysis.meta['refreshable'])
        
        # Set to False
        analysis.is_refreshable = False
        self.assertFalse(analysis.is_refreshable)
    
    def test_parse_dict_format_dependency(self):
        """Test parsing dict format (YAML without quotes)."""
        analysis = MockAnalysis('TestAnalysis', event=self.event)
        
        # Dict format as parsed by YAML when no quotes are used
        dict_need = {'waveform.approximant': 'IMRPhenomXPHM'}
        result = analysis._parse_single_dependency(dict_need)
        
        expected = (['waveform', 'approximant'], 'IMRPhenomXPHM', False, False)
        self.assertEqual(result, expected)
    
    def test_parse_dict_format_with_negation(self):
        """Test parsing dict format with negation."""
        analysis = MockAnalysis('TestAnalysis', event=self.event)
        
        dict_need = {'pipeline': '!bayeswave'}
        result = analysis._parse_single_dependency(dict_need)
        
        expected = (['pipeline'], 'bayeswave', True, False)
        self.assertEqual(result, expected)
    
    def test_self_dependency_exclusion(self):
        """Test that an analysis is never a dependency of itself."""
        # Create analyses where ProdA would match its own filter
        event = Mock()
        
        prod1 = MockAnalysis('Prod1', meta={'pipeline': 'bilby'})
        prod1.event = event
        
        prod2 = MockAnalysis('Prod2', meta={'pipeline': 'bilby'})
        prod2.event = event
        
        prodA = MockAnalysis('ProdA', meta={'pipeline': 'bilby'}, 
                            needs=[{'pipeline': 'bilby'}])
        prodA.event = event
        
        event.analyses = [prod1, prod2, prodA]
        
        deps = prodA.dependencies
        
        # Should include Prod1 and Prod2, but NOT ProdA itself
        self.assertIn('Prod1', deps)
        self.assertIn('Prod2', deps)
        self.assertNotIn('ProdA', deps)


if __name__ == '__main__':
    unittest.main()
