"""Test matrix strategy expansion functionality."""

import unittest
import os
import shutil
from copy import deepcopy

import asimov.event
from asimov.cli.project import make_project
from asimov.ledger import YAMLLedger
from asimov.utils import expand_strategy, set_nested_value


class StrategyExpansionTests(unittest.TestCase):
    """Tests for the expand_strategy function."""

    def test_no_strategy(self):
        """Test that productions without strategy are returned unchanged."""
        production = {
            'name': 'Prod0',
            'pipeline': 'bilby',
            'waveform': {'approximant': 'IMRPhenomXPHM'}
        }
        result = expand_strategy(production)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], 'Prod0')

    def test_simple_matrix(self):
        """Test simple matrix expansion with a single parameter."""
        production = {
            'name': 'Prod',
            'pipeline': 'bilby',
            'strategy': {
                'matrix': {
                    'waveform.approximant': ['IMRPhenomXPHM', 'SEOBNRv4PHM', 'IMRPhenomD']
                }
            }
        }
        result = expand_strategy(production)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]['name'], 'Prod-0')
        self.assertEqual(result[1]['name'], 'Prod-1')
        self.assertEqual(result[2]['name'], 'Prod-2')
        self.assertEqual(result[0]['waveform']['approximant'], 'IMRPhenomXPHM')
        self.assertEqual(result[1]['waveform']['approximant'], 'SEOBNRv4PHM')
        self.assertEqual(result[2]['waveform']['approximant'], 'IMRPhenomD')

    def test_multiple_matrix_parameters(self):
        """Test matrix expansion with multiple parameters."""
        production = {
            'name': 'Prod',
            'pipeline': 'bilby',
            'strategy': {
                'matrix': {
                    'waveform.approximant': ['IMRPhenomXPHM', 'SEOBNRv4PHM'],
                    'sampler.sampler': ['dynesty', 'nestle']
                }
            }
        }
        result = expand_strategy(production)
        # Should generate 2 x 2 = 4 combinations
        self.assertEqual(len(result), 4)
        
        # Check all combinations are present
        expected_combinations = [
            ('IMRPhenomXPHM', 'dynesty'),
            ('IMRPhenomXPHM', 'nestle'),
            ('SEOBNRv4PHM', 'dynesty'),
            ('SEOBNRv4PHM', 'nestle'),
        ]
        
        actual_combinations = [
            (r['waveform']['approximant'], r['sampler']['sampler'])
            for r in result
        ]
        
        self.assertEqual(sorted(actual_combinations), sorted(expected_combinations))

    def test_top_level_parameter(self):
        """Test matrix expansion with a top-level parameter."""
        production = {
            'name': 'Prod',
            'pipeline': 'bilby',
            'strategy': {
                'matrix': {
                    'status': ['ready', 'wait']
                }
            }
        }
        result = expand_strategy(production)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['status'], 'ready')
        self.assertEqual(result[1]['status'], 'wait')

    def test_nested_existing_values(self):
        """Test that matrix expansion preserves existing nested values."""
        production = {
            'name': 'Prod',
            'pipeline': 'bilby',
            'waveform': {
                'approximant': 'IMRPhenomXPHM',
                'mode_array': [[2, 2], [3, 3]]
            },
            'strategy': {
                'matrix': {
                    'sampler.sampler': ['dynesty', 'nestle']
                }
            }
        }
        result = expand_strategy(production)
        self.assertEqual(len(result), 2)
        # Check that the existing waveform values are preserved
        self.assertEqual(result[0]['waveform']['approximant'], 'IMRPhenomXPHM')
        self.assertEqual(result[0]['waveform']['mode_array'], [[2, 2], [3, 3]])
        self.assertEqual(result[1]['waveform']['approximant'], 'IMRPhenomXPHM')

    def test_single_value_in_matrix(self):
        """Test that single values in matrix work correctly."""
        production = {
            'name': 'Prod',
            'pipeline': 'bilby',
            'strategy': {
                'matrix': {
                    'waveform.approximant': 'IMRPhenomXPHM'  # Single value, not a list
                }
            }
        }
        result = expand_strategy(production)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['waveform']['approximant'], 'IMRPhenomXPHM')

    def test_three_parameter_matrix(self):
        """Test matrix expansion with three parameters."""
        production = {
            'name': 'TestProd',
            'pipeline': 'bilby',
            'strategy': {
                'matrix': {
                    'waveform.approximant': ['IMRPhenomXPHM', 'SEOBNRv4PHM'],
                    'sampler.nlive': [1000, 2000],
                    'sampler.walks': [50, 100]
                }
            }
        }
        result = expand_strategy(production)
        # Should generate 2 x 2 x 2 = 8 combinations
        self.assertEqual(len(result), 8)
        
        # Check all productions have unique names
        names = [r['name'] for r in result]
        self.assertEqual(len(names), len(set(names)))

    def test_strategy_without_matrix(self):
        """Test that strategy without matrix field is handled gracefully."""
        production = {
            'name': 'Prod',
            'pipeline': 'bilby',
            'strategy': {}
        }
        result = expand_strategy(production)
        self.assertEqual(len(result), 1)
        self.assertNotIn('strategy', result[0])


class SetNestedValueTests(unittest.TestCase):
    """Tests for the set_nested_value helper function."""

    def test_single_level(self):
        """Test setting a top-level value."""
        d = {}
        set_nested_value(d, 'key', 'value')
        self.assertEqual(d, {'key': 'value'})

    def test_two_levels(self):
        """Test setting a two-level nested value."""
        d = {}
        set_nested_value(d, 'level1.level2', 'value')
        self.assertEqual(d, {'level1': {'level2': 'value'}})

    def test_three_levels(self):
        """Test setting a three-level nested value."""
        d = {}
        set_nested_value(d, 'level1.level2.level3', 'value')
        self.assertEqual(d, {'level1': {'level2': {'level3': 'value'}}})

    def test_update_existing(self):
        """Test updating an existing nested value."""
        d = {'level1': {'level2': 'old_value', 'other': 'preserved'}}
        set_nested_value(d, 'level1.level2', 'new_value')
        self.assertEqual(d, {'level1': {'level2': 'new_value', 'other': 'preserved'}})


class EventStrategyIntegrationTests(unittest.TestCase):
    """Integration tests for strategy expansion with Event class."""

    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()

    def setUp(self):
        """Set up a test environment with a project."""
        os.makedirs(f"{self.cwd}/tests/tmp/strategy_test")
        os.chdir(f"{self.cwd}/tests/tmp/strategy_test")
        make_project(name="Strategy Test", root=f"{self.cwd}/tests/tmp/strategy_test")
        self.ledger = YAMLLedger(f".asimov/ledger.yml")

    def tearDown(self):
        """Clean up the test environment."""
        os.chdir(self.cwd)
        shutil.rmtree(f"{self.cwd}/tests/tmp/strategy_test")

    def test_event_with_strategy_production(self):
        """Test creating an event with a production that uses strategy."""
        event_data = {
            'name': 'GW150914_095045',
            'interferometers': ['H1', 'L1'],
            'working directory': f'{self.cwd}/tests/tmp/strategy_test/events',
            'data': {
                'channels': {'H1': 'H1:DCS-CALIB_STRAIN_C02', 'L1': 'L1:DCS-CALIB_STRAIN_C02'}
            },
            'productions': [
                {
                    'name': 'WaveformTest',
                    'pipeline': 'bilby',
                    'strategy': {
                        'matrix': {
                            'waveform.approximant': ['IMRPhenomXPHM', 'SEOBNRv4PHM', 'IMRPhenomD']
                        }
                    }
                }
            ]
        }
        
        event = asimov.event.Event.from_dict(event_data, ledger=self.ledger)
        
        # Should have 3 productions (one for each waveform)
        self.assertEqual(len(event.productions), 3)
        
        # Check production names
        production_names = [p.name for p in event.productions]
        self.assertIn('WaveformTest-0', production_names)
        self.assertIn('WaveformTest-1', production_names)
        self.assertIn('WaveformTest-2', production_names)
        
        # Check that each production has a different waveform approximant
        approximants = [p.meta['waveform']['approximant'] for p in event.productions]
        self.assertEqual(sorted(approximants), sorted(['IMRPhenomXPHM', 'SEOBNRv4PHM', 'IMRPhenomD']))

    def test_event_with_multiple_parameter_strategy(self):
        """Test creating an event with a production that uses multi-parameter strategy."""
        event_data = {
            'name': 'GW150914_095045',
            'interferometers': ['H1', 'L1'],
            'working directory': f'{self.cwd}/tests/tmp/strategy_test/events',
            'data': {
                'channels': {'H1': 'H1:DCS-CALIB_STRAIN_C02', 'L1': 'L1:DCS-CALIB_STRAIN_C02'}
            },
            'productions': [
                {
                    'name': 'ComparisonTest',
                    'pipeline': 'bilby',
                    'strategy': {
                        'matrix': {
                            'waveform.approximant': ['IMRPhenomXPHM', 'SEOBNRv4PHM'],
                            'sampler.sampler': ['dynesty', 'nestle']
                        }
                    }
                }
            ]
        }
        
        event = asimov.event.Event.from_dict(event_data, ledger=self.ledger)
        
        # Should have 4 productions (2 waveforms x 2 samplers)
        self.assertEqual(len(event.productions), 4)

    def test_event_with_mixed_productions(self):
        """Test creating an event with both strategy and non-strategy productions."""
        event_data = {
            'name': 'GW150914_095045',
            'interferometers': ['H1', 'L1'],
            'working directory': f'{self.cwd}/tests/tmp/strategy_test/events',
            'data': {
                'channels': {'H1': 'H1:DCS-CALIB_STRAIN_C02', 'L1': 'L1:DCS-CALIB_STRAIN_C02'}
            },
            'productions': [
                {
                    'name': 'SingleProd',
                    'pipeline': 'bilby',
                    'waveform': {'approximant': 'IMRPhenomXPHM'}
                },
                {
                    'name': 'StrategyProd',
                    'pipeline': 'bilby',
                    'strategy': {
                        'matrix': {
                            'waveform.approximant': ['SEOBNRv4PHM', 'IMRPhenomD']
                        }
                    }
                }
            ]
        }
        
        event = asimov.event.Event.from_dict(event_data, ledger=self.ledger)
        
        # Should have 3 productions (1 single + 2 from strategy)
        self.assertEqual(len(event.productions), 3)
        
        # Check production names
        production_names = [p.name for p in event.productions]
        self.assertIn('SingleProd', production_names)
        self.assertIn('StrategyProd-0', production_names)
        self.assertIn('StrategyProd-1', production_names)


if __name__ == '__main__':
    unittest.main()
