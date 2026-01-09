"""
Tests for optional dependency handling.
"""
import os
import shutil
import unittest

from asimov.ledger import YAMLLedger
from asimov.cli.project import make_project
from asimov.cli.application import apply_page


class OptionalDependencyTests(unittest.TestCase):
    """Tests for optional dependency specifications."""
    
    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()
    
    @classmethod
    def tearDownClass(cls):
        """Destroy all the products of this test."""
        os.chdir(cls.cwd)

    def setUp(self):
        os.makedirs(f"{self.cwd}/tests/tmp/optional_dep_project")
        os.chdir(f"{self.cwd}/tests/tmp/optional_dep_project")
        make_project(name="Test project", root=f"{self.cwd}/tests/tmp/optional_dep_project")
        self.ledger = YAMLLedger(f".asimov/ledger.yml")
        apply_page(file=f"{self.cwd}/tests/test_data/testing_pe.yaml", event=None, ledger=self.ledger)
        apply_page(file=f"{self.cwd}/tests/test_data/events_blueprint.yaml", ledger=self.ledger)

    def tearDown(self):
        shutil.rmtree(f"{self.cwd}/tests/tmp/optional_dep_project")

    def test_optional_dependency_parsing(self):
        """Test that optional dependencies are correctly parsed."""
        blueprint = """
kind: analysis
name: Prod0
pipeline: bayeswave
status: finished
---
kind: analysis
name: Prod1
pipeline: bilby
needs:
  - optional: true
    pipeline: bayeswave
"""
        with open('test_optional.yaml', 'w') as f:
            f.write(blueprint)
        
        apply_page(file='test_optional.yaml', event='GW150914_095045', ledger=self.ledger)
        event = self.ledger.get_event('GW150914_095045')[0]
        
        prod1 = [p for p in event.productions if p.name == 'Prod1'][0]
        
        # Should still resolve the dependency
        self.assertEqual(len(prod1.dependencies), 1)
        self.assertIn('Prod0', prod1.dependencies)
        
        # But required dependencies should be empty
        self.assertEqual(len(prod1.required_dependencies), 0)
        
        # And required dependencies should be satisfied (vacuously true)
        self.assertTrue(prod1.has_required_dependencies_satisfied)

    def test_required_dependency_not_satisfied(self):
        """Test that an analysis recognizes when required dependencies are missing."""
        blueprint = """
kind: analysis
name: Prod1
pipeline: bilby
needs:
  - pipeline: bayeswave
"""
        with open('test_required_missing.yaml', 'w') as f:
            f.write(blueprint)
        
        apply_page(file='test_required_missing.yaml', event='GW150914_095045', ledger=self.ledger)
        event = self.ledger.get_event('GW150914_095045')[0]
        
        prod1 = [p for p in event.productions if p.name == 'Prod1'][0]
        
        # Should have no resolved dependencies
        self.assertEqual(len(prod1.dependencies), 0)
        
        # Should have required dependencies spec
        self.assertGreater(len(prod1.required_dependencies), 0)
        
        # Required dependencies should NOT be satisfied
        self.assertFalse(prod1.has_required_dependencies_satisfied)

    def test_required_dependency_satisfied(self):
        """Test that an analysis recognizes when required dependencies are present."""
        blueprint = """
kind: analysis
name: Prod0
pipeline: bayeswave
status: finished
---
kind: analysis
name: Prod1
pipeline: bilby
needs:
  - pipeline: bayeswave
"""
        with open('test_required_present.yaml', 'w') as f:
            f.write(blueprint)
        
        apply_page(file='test_required_present.yaml', event='GW150914_095045', ledger=self.ledger)
        event = self.ledger.get_event('GW150914_095045')[0]
        
        prod1 = [p for p in event.productions if p.name == 'Prod1'][0]
        
        # Should have resolved dependencies
        self.assertEqual(len(prod1.dependencies), 1)
        
        # Should have required dependencies spec
        self.assertGreater(len(prod1.required_dependencies), 0)
        
        # Required dependencies should be satisfied
        self.assertTrue(prod1.has_required_dependencies_satisfied)

    def test_mixed_optional_required_dependencies(self):
        """Test a mix of optional and required dependencies."""
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
---
kind: analysis
name: Combiner
pipeline: lalinference
needs:
  - pipeline: bayeswave
  - optional: true
    pipeline: rift
"""
        with open('test_mixed.yaml', 'w') as f:
            f.write(blueprint)
        
        apply_page(file='test_mixed.yaml', event='GW150914_095045', ledger=self.ledger)
        event = self.ledger.get_event('GW150914_095045')[0]
        
        combiner = [p for p in event.productions if p.name == 'Combiner'][0]
        
        # Should resolve the bayeswave dependency (required and present)
        self.assertIn('Prod0', combiner.dependencies)
        
        # Should have 1 required dependency
        self.assertEqual(len(combiner.required_dependencies), 1)
        
        # Required dependencies should be satisfied (bayeswave is present)
        self.assertTrue(combiner.has_required_dependencies_satisfied)
        
        # Should NOT have the rift dependency (optional and not present)
        # Dependencies list only includes what's actually matched
        self.assertEqual(len(combiner.dependencies), 1)


if __name__ == '__main__':
    unittest.main()
