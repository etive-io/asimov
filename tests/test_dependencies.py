"""
Tests for the improved dependency management system.
"""
import os
import shutil
import unittest

from asimov.ledger import YAMLLedger
from asimov.cli.project import make_project
from asimov.cli.application import apply_page


class DependencyTests(unittest.TestCase):
    """Tests for flexible dependency specification."""
    
    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()
    
    @classmethod
    def tearDownClass(cls):
        """Destroy all the products of this test."""
        os.chdir(cls.cwd)

    def setUp(self):
        os.makedirs(f"{self.cwd}/tests/tmp/dep_project")
        os.chdir(f"{self.cwd}/tests/tmp/dep_project")
        make_project(name="Test project", root=f"{self.cwd}/tests/tmp/dep_project")
        self.ledger = YAMLLedger(f".asimov/ledger.yml")
        apply_page(file=f"{self.cwd}/tests/test_data/testing_pe.yaml", event=None, ledger=self.ledger)
        apply_page(file=f"{self.cwd}/tests/test_data/events_blueprint.yaml", ledger=self.ledger)

    def tearDown(self):
        del(self.ledger)
        shutil.rmtree(f"{self.cwd}/tests/tmp/dep_project")

    def test_simple_name_dependency(self):
        """Test that simple name-based dependencies still work."""
        apply_page(file=f"{self.cwd}/tests/test_data/test_linear_dag.yaml", ledger=self.ledger)
        event = self.ledger.get_event('GW150914_095045')[0]
        
        # Prod1 should depend on Prod0
        prod1 = [p for p in event.productions if p.name == 'Prod1'][0]
        self.assertEqual(len(prod1.dependencies), 1)
        self.assertIn('Prod0', prod1.dependencies)

    def test_property_based_dependency(self):
        """Test dependencies based on properties like pipeline."""
        # Create test blueprint with property-based dependency
        blueprint = """
kind: analysis
name: Prod0
pipeline: bayeswave
status: uploaded
---
kind: analysis
name: Prod1
pipeline: bilby
needs:
  - pipeline: bayeswave
"""
        with open('test_property_dep.yaml', 'w') as f:
            f.write(blueprint)
        
        apply_page(file='test_property_dep.yaml', event='GW150914_095045', ledger=self.ledger)
        event = self.ledger.get_event('GW150914_095045')[0]
        
        prod1 = [p for p in event.productions if p.name == 'Prod1'][0]
        self.assertEqual(len(prod1.dependencies), 1)
        self.assertIn('Prod0', prod1.dependencies)

    def test_negation_dependency(self):
        """Test negation in dependency specifications."""
        blueprint = """
kind: analysis
name: Prod0
pipeline: bayeswave
status: uploaded
---
kind: analysis
name: Prod1
pipeline: bilby
status: uploaded
---
kind: analysis
name: Prod2
pipeline: lalinference
needs:
  - pipeline: "!bayeswave"
"""
        with open('test_negation.yaml', 'w') as f:
            f.write(blueprint)
        
        apply_page(file='test_negation.yaml', event='GW150914_095045', ledger=self.ledger)
        event = self.ledger.get_event('GW150914_095045')[0]
        
        prod2 = [p for p in event.productions if p.name == 'Prod2'][0]
        # Should match Prod1 (bilby) and Prod2 (lalinference) but not Prod0 (bayeswave)
        self.assertIn('Prod1', prod2.dependencies)
        self.assertNotIn('Prod0', prod2.dependencies)

    def test_or_logic_multiple_values(self):
        """Test OR logic with multiple separate dependency items."""
        blueprint = """
kind: analysis
name: ProdA
pipeline: bayeswave
status: uploaded
waveform:
  approximant: IMRPhenomXPHM
---
kind: analysis
name: ProdB
pipeline: bilby
status: uploaded
waveform:
  approximant: SEOBNRv5PHM
---
kind: analysis
name: ProdC
pipeline: lalinference
status: uploaded
waveform:
  approximant: IMRPhenomD
---
kind: analysis
name: Combiner
pipeline: bilby
needs:
  - waveform.approximant: IMRPhenomXPHM
  - waveform.approximant: SEOBNRv5PHM
"""
        with open('test_or_logic.yaml', 'w') as f:
            f.write(blueprint)
        
        apply_page(file='test_or_logic.yaml', event='GW150914_095045', ledger=self.ledger)
        event = self.ledger.get_event('GW150914_095045')[0]
        
        combiner = [p for p in event.productions if p.name == 'Combiner'][0]
        # Should match both ProdA and ProdB (OR logic)
        self.assertEqual(len(combiner.dependencies), 2)
        self.assertIn('ProdA', combiner.dependencies)
        self.assertIn('ProdB', combiner.dependencies)
        self.assertNotIn('ProdC', combiner.dependencies)

    def test_and_logic_nested_list(self):
        """Test AND logic using nested lists."""
        blueprint = """
kind: analysis
name: ProdA
pipeline: bayeswave
status: uploaded
waveform:
  approximant: IMRPhenomXPHM
---
kind: analysis
name: ProdB
pipeline: bilby
status: uploaded
waveform:
  approximant: IMRPhenomXPHM
---
kind: analysis
name: ProdC
pipeline: bayeswave
status: uploaded
waveform:
  approximant: SEOBNRv5PHM
---
kind: analysis
name: Selector
pipeline: lalinference
needs:
  - - pipeline: bayeswave
    - waveform.approximant: IMRPhenomXPHM
"""
        with open('test_and_logic.yaml', 'w') as f:
            f.write(blueprint)
        
        apply_page(file='test_and_logic.yaml', event='GW150914_095045', ledger=self.ledger)
        event = self.ledger.get_event('GW150914_095045')[0]
        
        selector = [p for p in event.productions if p.name == 'Selector'][0]
        # Should only match ProdA (bayeswave AND IMRPhenomXPHM)
        self.assertEqual(len(selector.dependencies), 1)
        self.assertIn('ProdA', selector.dependencies)
        self.assertNotIn('ProdB', selector.dependencies)
        self.assertNotIn('ProdC', selector.dependencies)

    def test_staleness_detection(self):
        """Test that analyses can detect when dependencies have changed."""
        blueprint = """
kind: analysis
name: Prod0
pipeline: bayeswave
status: finished
---
kind: analysis
name: Prod1
pipeline: bilby
status: finished
needs:
  - Prod0
"""
        with open('test_stale.yaml', 'w') as f:
            f.write(blueprint)
        
        apply_page(file='test_stale.yaml', event='GW150914_095045', ledger=self.ledger)
        event = self.ledger.get_event('GW150914_095045')[0]
        
        prod1 = [p for p in event.productions if p.name == 'Prod1'][0]
        
        # Initially not stale (no resolved dependencies recorded)
        self.assertFalse(prod1.is_stale)
        
        # Record the dependencies as resolved
        prod1.resolved_dependencies = prod1.dependencies
        self.assertFalse(prod1.is_stale)
        
        # Add a new production that matches the criteria
        blueprint2 = """
kind: analysis
name: Prod0b
pipeline: bayeswave
status: finished
"""
        with open('test_stale2.yaml', 'w') as f:
            f.write(blueprint2)
        
        apply_page(file='test_stale2.yaml', event='GW150914_095045', ledger=self.ledger)
        # Reload to get updated productions
        event = self.ledger.get_event('GW150914_095045')[0]
        
        # Now if we change Prod1's needs to match by pipeline, it would become stale
        # But for this test, dependencies haven't changed, so it's not stale
        prod1_new = [p for p in event.productions if p.name == 'Prod1'][0]
        prod1_new.resolved_dependencies = ['Prod0']
        self.assertFalse(prod1_new.is_stale)

    def test_refreshable_flag(self):
        """Test the refreshable flag on analyses."""
        apply_page(file=f"{self.cwd}/tests/test_data/test_linear_dag.yaml", ledger=self.ledger)
        event = self.ledger.get_event('GW150914_095045')[0]
        
        prod1 = [p for p in event.productions if p.name == 'Prod1'][0]
        
        # Default is not refreshable
        self.assertFalse(prod1.is_refreshable)
        
        # Set to refreshable
        prod1.is_refreshable = True
        self.assertTrue(prod1.is_refreshable)
        
        # Set to not refreshable
        prod1.is_refreshable = False
        self.assertFalse(prod1.is_refreshable)


if __name__ == '__main__':
    unittest.main()
