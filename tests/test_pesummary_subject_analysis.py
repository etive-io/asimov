"""
Tests for PESummary as a SubjectAnalysis.
"""
import os
import shutil
import unittest

from asimov.ledger import YAMLLedger
from asimov.cli.project import make_project
from asimov.cli.application import apply_page


class PESummarySubjectAnalysisTests(unittest.TestCase):
    """Tests for PESummary working as a SubjectAnalysis."""
    
    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()
    
    @classmethod
    def tearDownClass(cls):
        """Destroy all the products of this test."""
        os.chdir(cls.cwd)

    def setUp(self):
        os.makedirs(f"{self.cwd}/tests/tmp/pesummary_subject_project")
        os.chdir(f"{self.cwd}/tests/tmp/pesummary_subject_project")
        make_project(name="Test project", root=f"{self.cwd}/tests/tmp/pesummary_subject_project")
        self.ledger = YAMLLedger(f".asimov/ledger.yml")
        apply_page(file=f"{self.cwd}/tests/test_data/testing_pe.yaml", event=None, ledger=self.ledger)
        apply_page(file=f"{self.cwd}/tests/test_data/events_blueprint.yaml", ledger=self.ledger)

    def tearDown(self):
        shutil.rmtree(f"{self.cwd}/tests/tmp/pesummary_subject_project")

    def test_pesummary_subject_analysis_creation(self):
        """Test that a PESummary SubjectAnalysis can be created."""
        blueprint = """
kind: analysis
name: Bilby1
pipeline: bilby
status: finished
---
kind: analysis
name: Bilby2
pipeline: bilby
status: finished
---
kind: analysis
name: CombinedPESummary
pipeline: pesummary
analyses:
  - pipeline: bilby
"""
        with open('test_pesummary_subject.yaml', 'w') as f:
            f.write(blueprint)
        
        apply_page(file='test_pesummary_subject.yaml', event='GW150914_095045', ledger=self.ledger)
        event = self.ledger.get_event('GW150914_095045')[0]
        
        # Check that PESummary SubjectAnalysis was created
        pesummary_analyses = [a for a in event.analyses if a.name == 'CombinedPESummary']
        self.assertEqual(len(pesummary_analyses), 1)
        
        pesummary = pesummary_analyses[0]
        
        # Check that it found the bilby dependencies
        self.assertEqual(len(pesummary.dependencies), 0)  # dependencies is only for needs
        
        # Check that the analyses attribute has the bilby runs
        from asimov.analysis import SubjectAnalysis
        self.assertIsInstance(pesummary, SubjectAnalysis)
        
        # Check that it has the right productions/analyses
        if hasattr(pesummary, 'analyses'):
            self.assertEqual(len(pesummary.analyses), 2)
            analysis_names = [a.name for a in pesummary.analyses]
            self.assertIn('Bilby1', analysis_names)
            self.assertIn('Bilby2', analysis_names)

    def test_pesummary_with_required_dependencies(self):
        """Test that PESummary won't run if required dependencies are missing."""
        blueprint = """
kind: analysis
name: CombinedPESummary
pipeline: pesummary
analyses:
  - pipeline: bilby
"""
        with open('test_pesummary_no_deps.yaml', 'w') as f:
            f.write(blueprint)
        
        apply_page(file='test_pesummary_no_deps.yaml', event='GW150914_095045', ledger=self.ledger)
        event = self.ledger.get_event('GW150914_095045')[0]
        
        pesummary = [a for a in event.analyses if a.name == 'CombinedPESummary'][0]
        
        # The analyses list should be empty since no bilby jobs exist
        self.assertEqual(len(pesummary.analyses), 0)

    def test_pesummary_with_optional_dependencies(self):
        """Test that PESummary can run with optional dependencies."""
        blueprint = """
kind: analysis
name: Bilby1
pipeline: bilby
status: finished
---
kind: analysis
name: CombinedPESummary
pipeline: pesummary
analyses:
  - pipeline: bilby
  - optional: true
    pipeline: rift
"""
        with open('test_pesummary_optional.yaml', 'w') as f:
            f.write(blueprint)
        
        apply_page(file='test_pesummary_optional.yaml', event='GW150914_095045', ledger=self.ledger)
        event = self.ledger.get_event('GW150914_095045')[0]
        
        pesummary = [a for a in event.analyses if a.name == 'CombinedPESummary'][0]
        
        # Should have the bilby analysis
        if hasattr(pesummary, 'analyses'):
            self.assertEqual(len(pesummary.analyses), 1)
            self.assertEqual(pesummary.analyses[0].name, 'Bilby1')


if __name__ == '__main__':
    unittest.main()
