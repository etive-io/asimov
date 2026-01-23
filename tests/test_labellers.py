"""
Tests for the labeller plugin system.
"""

import unittest
from unittest.mock import Mock, MagicMock, patch

from asimov.labellers import (
    Labeller,
    register_labeller,
    discover_labellers,
    apply_labellers,
    get_labellers,
    LABELLER_REGISTRY,
)


class TestLabeller(Labeller):
    """Test labeller implementation."""
    
    def __init__(self, name="test_labeller", labels=None):
        self._name = name
        self._labels = labels or {"interest status": True}
    
    @property
    def name(self):
        return self._name
    
    def label(self, analysis, context=None):
        return self._labels.copy()


class ConditionalTestLabeller(Labeller):
    """Test labeller with conditional logic."""
    
    def __init__(self, condition=True):
        self.condition = condition
    
    @property
    def name(self):
        return "conditional_test"
    
    def should_label(self, analysis, context=None):
        return self.condition
    
    def label(self, analysis, context=None):
        return {"test_label": True}


class TestLabellerBase(unittest.TestCase):
    """Test the base Labeller class."""
    
    def test_labeller_is_abstract(self):
        """Test that Labeller cannot be instantiated directly."""
        with self.assertRaises(TypeError):
            Labeller()
    
    def test_custom_labeller_implementation(self):
        """Test that a custom labeller can be created."""
        labeller = TestLabeller()
        self.assertEqual(labeller.name, "test_labeller")
        
        mock_analysis = Mock()
        labels = labeller.label(mock_analysis)
        self.assertEqual(labels, {"interest status": True})
    
    def test_should_label_default(self):
        """Test that should_label returns True by default."""
        labeller = TestLabeller()
        mock_analysis = Mock()
        self.assertTrue(labeller.should_label(mock_analysis))


class TestLabellerRegistry(unittest.TestCase):
    """Test the labeller registry system."""
    
    def setUp(self):
        """Clear the registry before each test."""
        LABELLER_REGISTRY.clear()
    
    def tearDown(self):
        """Clear the registry after each test."""
        LABELLER_REGISTRY.clear()
    
    def test_register_labeller(self):
        """Test registering a labeller."""
        labeller = TestLabeller()
        register_labeller(labeller)
        
        self.assertIn("test_labeller", LABELLER_REGISTRY)
        self.assertEqual(LABELLER_REGISTRY["test_labeller"], labeller)
    
    def test_register_multiple_labellers(self):
        """Test registering multiple labellers."""
        labeller1 = TestLabeller(name="labeller1")
        labeller2 = TestLabeller(name="labeller2")
        
        register_labeller(labeller1)
        register_labeller(labeller2)
        
        self.assertEqual(len(LABELLER_REGISTRY), 2)
        self.assertIn("labeller1", LABELLER_REGISTRY)
        self.assertIn("labeller2", LABELLER_REGISTRY)
    
    def test_register_overwrites_existing(self):
        """Test that registering with same name overwrites."""
        labeller1 = TestLabeller(labels={"test": 1})
        labeller2 = TestLabeller(labels={"test": 2})
        
        register_labeller(labeller1)
        register_labeller(labeller2)
        
        # Should have only one labeller
        self.assertEqual(len(LABELLER_REGISTRY), 1)
        # Should be the second one
        labels = LABELLER_REGISTRY["test_labeller"].label(Mock())
        self.assertEqual(labels["test"], 2)
    
    def test_register_invalid_type(self):
        """Test that registering non-Labeller raises error."""
        with self.assertRaises(TypeError):
            register_labeller("not a labeller")
    
    def test_get_labellers(self):
        """Test getting all registered labellers."""
        labeller1 = TestLabeller(name="labeller1")
        labeller2 = TestLabeller(name="labeller2")
        
        register_labeller(labeller1)
        register_labeller(labeller2)
        
        labellers = get_labellers()
        self.assertEqual(len(labellers), 2)
        self.assertIn("labeller1", labellers)
        self.assertIn("labeller2", labellers)
        
        # Verify it's a copy
        labellers.clear()
        self.assertEqual(len(LABELLER_REGISTRY), 2)


class TestApplyLabellers(unittest.TestCase):
    """Test applying labellers to analyses."""
    
    def setUp(self):
        """Clear the registry before each test."""
        LABELLER_REGISTRY.clear()
    
    def tearDown(self):
        """Clear the registry after each test."""
        LABELLER_REGISTRY.clear()
    
    def test_apply_single_labeller(self):
        """Test applying a single labeller."""
        labeller = TestLabeller(labels={"interest status": True})
        register_labeller(labeller)
        
        mock_analysis = Mock()
        mock_analysis.meta = {}
        mock_analysis.name = "test_analysis"
        
        labels = apply_labellers(mock_analysis)
        
        self.assertEqual(labels, {"interest status": True})
        self.assertEqual(mock_analysis.meta["interest status"], True)
    
    def test_apply_multiple_labellers(self):
        """Test applying multiple labellers."""
        labeller1 = TestLabeller(name="labeller1", labels={"label1": True})
        labeller2 = TestLabeller(name="labeller2", labels={"label2": "value"})
        
        register_labeller(labeller1)
        register_labeller(labeller2)
        
        mock_analysis = Mock()
        mock_analysis.meta = {}
        mock_analysis.name = "test_analysis"
        
        labels = apply_labellers(mock_analysis)
        
        self.assertEqual(len(labels), 2)
        self.assertTrue(labels["label1"])
        self.assertEqual(labels["label2"], "value")
        self.assertEqual(mock_analysis.meta["label1"], True)
        self.assertEqual(mock_analysis.meta["label2"], "value")
    
    def test_apply_with_context(self):
        """Test applying labellers with context."""
        labeller = TestLabeller()
        register_labeller(labeller)
        
        mock_analysis = Mock()
        mock_analysis.meta = {}
        mock_analysis.name = "test_analysis"
        mock_context = Mock()
        
        labels = apply_labellers(mock_analysis, context=mock_context)
        
        self.assertEqual(labels, {"interest status": True})
    
    def test_apply_respects_should_label(self):
        """Test that should_label is respected."""
        # Labeller that should not run
        labeller = ConditionalTestLabeller(condition=False)
        register_labeller(labeller)
        
        mock_analysis = Mock()
        mock_analysis.meta = {}
        mock_analysis.name = "test_analysis"
        
        labels = apply_labellers(mock_analysis)
        
        # Should return empty since should_label returned False
        self.assertEqual(labels, {})
        self.assertNotIn("test_label", mock_analysis.meta)
    
    def test_apply_with_no_meta(self):
        """Test applying labellers when analysis has no meta attribute."""
        labeller = TestLabeller()
        register_labeller(labeller)
        
        mock_analysis = Mock(spec=[])  # No attributes
        mock_analysis.name = "test_analysis"
        
        labels = apply_labellers(mock_analysis)
        
        # Should create meta attribute
        self.assertTrue(hasattr(mock_analysis, 'meta'))
        self.assertEqual(mock_analysis.meta["interest status"], True)
    
    def test_apply_handles_errors(self):
        """Test that errors in labellers are handled gracefully."""
        class ErrorLabeller(Labeller):
            @property
            def name(self):
                return "error_labeller"
            
            def label(self, analysis, context=None):
                raise ValueError("Test error")
        
        register_labeller(ErrorLabeller())
        
        mock_analysis = Mock()
        mock_analysis.meta = {}
        mock_analysis.name = "test_analysis"
        
        # Should not raise, just log warning
        labels = apply_labellers(mock_analysis)
        self.assertEqual(labels, {})
    
    def test_apply_empty_registry(self):
        """Test applying labellers with empty registry."""
        mock_analysis = Mock()
        mock_analysis.meta = {}
        mock_analysis.name = "test_analysis"
        
        labels = apply_labellers(mock_analysis)
        
        self.assertEqual(labels, {})


class TestDiscoverLabellers(unittest.TestCase):
    """Test labeller discovery via entry points."""
    
    def setUp(self):
        """Clear the registry before each test."""
        LABELLER_REGISTRY.clear()
    
    def tearDown(self):
        """Clear the registry after each test."""
        LABELLER_REGISTRY.clear()
    
    @patch('asimov.labellers.entry_points')
    def test_discover_labellers(self, mock_entry_points):
        """Test discovering labellers via entry points."""
        # Create mock entry point
        mock_ep = MagicMock()
        mock_ep.name = "test_labeller"
        mock_ep.value = "test.module:TestLabeller"
        mock_ep.load.return_value = TestLabeller
        
        mock_entry_points.return_value = [mock_ep]
        
        discover_labellers()
        
        # Should have discovered and registered the labeller
        self.assertIn("test_labeller", LABELLER_REGISTRY)
        mock_entry_points.assert_called_once_with(group="asimov.labellers")
    
    @patch('asimov.labellers.entry_points')
    def test_discover_labellers_instance(self, mock_entry_points):
        """Test discovering labellers that return instances."""
        # Create mock entry point that returns an instance
        labeller_instance = TestLabeller(name="instance_labeller")
        
        mock_ep = MagicMock()
        mock_ep.name = "instance_labeller"
        mock_ep.value = "test.module:labeller_instance"
        mock_ep.load.return_value = labeller_instance
        
        mock_entry_points.return_value = [mock_ep]
        
        discover_labellers()
        
        # Should have registered the instance
        self.assertIn("instance_labeller", LABELLER_REGISTRY)
        self.assertEqual(LABELLER_REGISTRY["instance_labeller"], labeller_instance)
    
    @patch('asimov.labellers.entry_points')
    def test_discover_labellers_error_handling(self, mock_entry_points):
        """Test error handling in labeller discovery."""
        mock_ep = MagicMock()
        mock_ep.name = "broken_labeller"
        mock_ep.load.side_effect = ImportError("Cannot import")
        
        mock_entry_points.return_value = [mock_ep]
        
        # Should not raise, just log warning
        discover_labellers()
        
        # Should not have registered anything
        self.assertEqual(len(LABELLER_REGISTRY), 0)


if __name__ == '__main__':
    unittest.main()
