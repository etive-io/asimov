"""
Tests for SubjectAnalysis, the mechanism used by combiner-style analyses
(e.g. the pesummary plugin) which aggregate multiple upstream analyses.
"""
import os
import shutil
import unittest

from asimov.ledger import YAMLLedger
from asimov.cli.project import make_project
from asimov.cli.application import apply_page


class SubjectAnalysisTests(unittest.TestCase):
    """Tests for the generic SubjectAnalysis mechanism."""

    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()

    @classmethod
    def tearDownClass(cls):
        """Destroy all the products of this test."""
        os.chdir(cls.cwd)

    def setUp(self):
        os.makedirs(f"{self.cwd}/tests/tmp/subject_analysis_project")
        os.chdir(f"{self.cwd}/tests/tmp/subject_analysis_project")
        make_project(
            name="Test project",
            root=f"{self.cwd}/tests/tmp/subject_analysis_project",
            engine="yamlfile",
        )
        self.ledger = YAMLLedger(f".asimov/ledger.yml")
        apply_page(file=f"{self.cwd}/tests/test_data/testing_pe.yaml", event=None, ledger=self.ledger)
        apply_page(file=f"{self.cwd}/tests/test_data/events_blueprint.yaml", ledger=self.ledger)

    def tearDown(self):
        shutil.rmtree(f"{self.cwd}/tests/tmp/subject_analysis_project")

    def test_subject_analysis_creation(self):
        """Test that a SubjectAnalysis can be created."""
        blueprint = """
kind: analysis
name: Analysis1
pipeline: simpletestpipeline
status: finished
---
kind: analysis
name: Analysis2
pipeline: simpletestpipeline
status: finished
---
kind: analysis
name: Combined
pipeline: subjecttestpipeline
analyses:
  - pipeline: simpletestpipeline
"""
        with open('test_subject_analysis.yaml', 'w') as f:
            f.write(blueprint)

        apply_page(file='test_subject_analysis.yaml', event='GW150914_095045', ledger=self.ledger)
        event = self.ledger.get_event('GW150914_095045')[0]

        # Check that the SubjectAnalysis was created
        combined_analyses = [a for a in event.analyses if a.name == 'Combined']
        self.assertEqual(len(combined_analyses), 1)

        combined = combined_analyses[0]

        # Check that it found the upstream dependencies
        self.assertEqual(len(combined.dependencies), 0)  # dependencies is only for needs

        # Check that the analyses attribute has the upstream runs
        from asimov.analysis import SubjectAnalysis
        self.assertIsInstance(combined, SubjectAnalysis)

        # Check that it has the right productions/analyses
        if hasattr(combined, 'analyses'):
            self.assertEqual(len(combined.analyses), 2)
            analysis_names = [a.name for a in combined.analyses]
            self.assertIn('Analysis1', analysis_names)
            self.assertIn('Analysis2', analysis_names)

    def test_subject_analysis_with_required_dependencies(self):
        """Test that a SubjectAnalysis won't run if required dependencies are missing."""
        blueprint = """
kind: analysis
name: Combined
pipeline: subjecttestpipeline
analyses:
  - pipeline: simpletestpipeline
"""
        with open('test_subject_no_deps.yaml', 'w') as f:
            f.write(blueprint)

        apply_page(file='test_subject_no_deps.yaml', event='GW150914_095045', ledger=self.ledger)
        event = self.ledger.get_event('GW150914_095045')[0]

        combined = [a for a in event.analyses if a.name == 'Combined'][0]

        # The analyses list should be empty since no upstream jobs exist
        self.assertEqual(len(combined.analyses), 0)

    def test_subject_analysis_with_optional_dependencies(self):
        """Test that a SubjectAnalysis can run with optional dependencies."""
        blueprint = """
kind: analysis
name: Analysis1
pipeline: simpletestpipeline
status: finished
---
kind: analysis
name: Combined
pipeline: subjecttestpipeline
analyses:
  - pipeline: simpletestpipeline
  - optional: true
    pipeline: simpletestpipelineb
"""
        with open('test_subject_optional.yaml', 'w') as f:
            f.write(blueprint)

        apply_page(file='test_subject_optional.yaml', event='GW150914_095045', ledger=self.ledger)
        event = self.ledger.get_event('GW150914_095045')[0]

        combined = [a for a in event.analyses if a.name == 'Combined'][0]

        # Should have the required (present) analysis, not the optional (absent) one
        if hasattr(combined, 'analyses'):
            self.assertEqual(len(combined.analyses), 1)
            self.assertEqual(combined.analyses[0].name, 'Analysis1')


if __name__ == '__main__':
    unittest.main()
