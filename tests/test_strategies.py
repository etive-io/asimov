"""
Tests for strategy expansion functionality.
"""

import unittest
from copy import deepcopy

from asimov.strategies import expand_strategy, set_nested_value


class TestSetNestedValue(unittest.TestCase):
    """Tests for the set_nested_value helper function."""
    
    def test_simple_path(self):
        """Test setting a simple (non-nested) value."""
        d = {}
        set_nested_value(d, "key", "value")
        self.assertEqual(d, {"key": "value"})
    
    def test_nested_path(self):
        """Test setting a nested value."""
        d = {}
        set_nested_value(d, "waveform.approximant", "IMRPhenomXPHM")
        self.assertEqual(d, {"waveform": {"approximant": "IMRPhenomXPHM"}})
    
    def test_deeply_nested_path(self):
        """Test setting a deeply nested value."""
        d = {}
        set_nested_value(d, "a.b.c.d", "value")
        self.assertEqual(d, {"a": {"b": {"c": {"d": "value"}}}})
    
    def test_existing_structure(self):
        """Test setting a value in an existing structure."""
        d = {"waveform": {"other": "data"}}
        set_nested_value(d, "waveform.approximant", "IMRPhenomXPHM")
        self.assertEqual(d, {"waveform": {"other": "data", "approximant": "IMRPhenomXPHM"}})


class TestExpandStrategy(unittest.TestCase):
    """Tests for the expand_strategy function."""
    
    def test_no_strategy(self):
        """Test that blueprints without a strategy are returned unchanged."""
        blueprint = {
            "kind": "analysis",
            "name": "test-analysis",
            "pipeline": "bilby"
        }
        result = expand_strategy(blueprint)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], blueprint)
    
    def test_single_parameter_strategy(self):
        """Test strategy with a single parameter."""
        blueprint = {
            "kind": "analysis",
            "name": "bilby-{waveform.approximant}",
            "pipeline": "bilby",
            "strategy": {
                "waveform.approximant": ["IMRPhenomXPHM", "SEOBNRv4PHM"]
            }
        }
        result = expand_strategy(deepcopy(blueprint))
        
        # Should create 2 analyses
        self.assertEqual(len(result), 2)
        
        # Check first analysis
        self.assertEqual(result[0]["name"], "bilby-IMRPhenomXPHM")
        self.assertEqual(result[0]["pipeline"], "bilby")
        self.assertEqual(result[0]["waveform"]["approximant"], "IMRPhenomXPHM")
        self.assertNotIn("strategy", result[0])
        
        # Check second analysis
        self.assertEqual(result[1]["name"], "bilby-SEOBNRv4PHM")
        self.assertEqual(result[1]["pipeline"], "bilby")
        self.assertEqual(result[1]["waveform"]["approximant"], "SEOBNRv4PHM")
        self.assertNotIn("strategy", result[1])
    
    def test_multi_parameter_strategy_matrix(self):
        """Test strategy with multiple parameters (matrix/cross-product)."""
        blueprint = {
            "kind": "analysis",
            "name": "bilby-{waveform.approximant}-{sampler.sampler}",
            "pipeline": "bilby",
            "strategy": {
                "waveform.approximant": ["IMRPhenomXPHM", "SEOBNRv4PHM"],
                "sampler.sampler": ["dynesty", "emcee"]
            }
        }
        result = expand_strategy(deepcopy(blueprint))
        
        # Should create 4 analyses (2 x 2)
        self.assertEqual(len(result), 4)
        
        # Check that all combinations are created
        combinations = [
            ("IMRPhenomXPHM", "dynesty"),
            ("IMRPhenomXPHM", "emcee"),
            ("SEOBNRv4PHM", "dynesty"),
            ("SEOBNRv4PHM", "emcee")
        ]
        
        for i, (waveform, sampler) in enumerate(combinations):
            self.assertEqual(result[i]["waveform"]["approximant"], waveform)
            self.assertEqual(result[i]["sampler"]["sampler"], sampler)
            self.assertEqual(result[i]["name"], f"bilby-{waveform}-{sampler}")
    
    def test_strategy_with_numeric_values(self):
        """Test strategy with numeric parameter values."""
        blueprint = {
            "kind": "analysis",
            "name": "bilby-fref-{waveform.frequency}",
            "pipeline": "bilby",
            "strategy": {
                "waveform.frequency": [20, 50, 100]
            }
        }
        result = expand_strategy(deepcopy(blueprint))
        
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["waveform"]["frequency"], 20)
        self.assertEqual(result[1]["waveform"]["frequency"], 50)
        self.assertEqual(result[2]["waveform"]["frequency"], 100)
    
    def test_strategy_preserves_other_fields(self):
        """Test that strategy expansion preserves other blueprint fields."""
        blueprint = {
            "kind": "analysis",
            "name": "bilby-{waveform.approximant}",
            "pipeline": "bilby",
            "event": "GW150914",
            "comment": "Test analysis",
            "needs": ["generate-psd"],
            "likelihood": {
                "sample rate": 4096
            },
            "strategy": {
                "waveform.approximant": ["IMRPhenomXPHM", "SEOBNRv4PHM"]
            }
        }
        result = expand_strategy(deepcopy(blueprint))
        
        self.assertEqual(len(result), 2)
        
        for analysis in result:
            self.assertEqual(analysis["pipeline"], "bilby")
            self.assertEqual(analysis["event"], "GW150914")
            self.assertEqual(analysis["comment"], "Test analysis")
            self.assertEqual(analysis["needs"], ["generate-psd"])
            self.assertEqual(analysis["likelihood"]["sample rate"], 4096)
    
    def test_name_without_template(self):
        """Test that names without templates work correctly."""
        blueprint = {
            "kind": "analysis",
            "name": "bilby-analysis",
            "pipeline": "bilby",
            "strategy": {
                "waveform.approximant": ["IMRPhenomXPHM", "SEOBNRv4PHM"]
            }
        }
        result = expand_strategy(deepcopy(blueprint))
        
        # Both should have the same name (this might create a conflict,
        # but we let the user handle that)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "bilby-analysis")
        self.assertEqual(result[1]["name"], "bilby-analysis")
    
    def test_strategy_with_single_value(self):
        """Test strategy with only one value (edge case)."""
        blueprint = {
            "kind": "analysis",
            "name": "bilby-{waveform.approximant}",
            "pipeline": "bilby",
            "strategy": {
                "waveform.approximant": ["IMRPhenomXPHM"]
            }
        }
        result = expand_strategy(deepcopy(blueprint))
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "bilby-IMRPhenomXPHM")
        self.assertEqual(result[0]["waveform"]["approximant"], "IMRPhenomXPHM")
    
    def test_complex_nested_values(self):
        """Test strategy with complex nested parameter paths."""
        blueprint = {
            "kind": "analysis",
            "name": "test",
            "pipeline": "bilby",
            "strategy": {
                "likelihood.marginalisation.distance": [True, False]
            }
        }
        result = expand_strategy(deepcopy(blueprint))
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["likelihood"]["marginalisation"]["distance"], True)
        self.assertEqual(result[1]["likelihood"]["marginalisation"]["distance"], False)
    
    def test_boolean_values_in_name(self):
        """Test that boolean values are converted to lowercase in names."""
        blueprint = {
            "kind": "analysis",
            "name": "test-{likelihood.marginalisation.distance}",
            "pipeline": "bilby",
            "strategy": {
                "likelihood.marginalisation.distance": [True, False]
            }
        }
        result = expand_strategy(deepcopy(blueprint))
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "test-true")
        self.assertEqual(result[1]["name"], "test-false")
    
    def test_empty_strategy(self):
        """Test that an empty strategy raises an error."""
        blueprint = {
            "kind": "analysis",
            "name": "test",
            "pipeline": "bilby",
            "strategy": {}
        }
        with self.assertRaises(ValueError) as context:
            expand_strategy(deepcopy(blueprint))
        self.assertIn("empty", str(context.exception).lower())
    
    def test_empty_parameter_list(self):
        """Test that empty parameter lists raise an error."""
        blueprint = {
            "kind": "analysis",
            "name": "test",
            "pipeline": "bilby",
            "strategy": {
                "waveform.approximant": []
            }
        }
        with self.assertRaises(ValueError) as context:
            expand_strategy(deepcopy(blueprint))
        self.assertIn("empty", str(context.exception).lower())
        self.assertIn("waveform.approximant", str(context.exception))
    
    def test_non_list_parameter_value(self):
        """Test that non-list parameter values raise an error."""
        blueprint = {
            "kind": "analysis",
            "name": "test",
            "pipeline": "bilby",
            "strategy": {
                "waveform.approximant": "IMRPhenomXPHM"  # Should be a list
            }
        }
        with self.assertRaises(TypeError) as context:
            expand_strategy(deepcopy(blueprint))
        self.assertIn("must be a list", str(context.exception))
        self.assertIn("waveform.approximant", str(context.exception))
    
    def test_set_nested_value_with_non_dict_intermediate(self):
        """Test that set_nested_value raises error for non-dict intermediate values."""
        d = {"waveform": "some_string"}
        with self.assertRaises(TypeError) as context:
            set_nested_value(d, "waveform.approximant", "IMRPhenomXPHM")
        self.assertIn("intermediate key", str(context.exception).lower())
        self.assertIn("waveform", str(context.exception))


if __name__ == "__main__":
    unittest.main()
