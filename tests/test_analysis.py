"""
Test suites for the implementation of analyses.

Analyses replace and generalise the earlier notion of a "production" from v0.3 and earlier.
"""

import unittest

from importlib import reload
from unittest.mock import patch

import os
import io
import shutil
import contextlib

from click.testing import CliRunner
import asimov
from asimov.event import Production
from asimov.cli.application import apply_page
from asimov.cli import manage, project
from asimov.ledger import YAMLLedger
from asimov.pipeline import PipelineException

from asimov.cli.application import apply_page


class TestBaseAnalysis(unittest.TestCase):

    EVENTS = ["GW150914_095045", "GW151226_033853", "GW170814_103043"]
    
    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()

    @classmethod
    def tearDownClass(self):
        os.chdir(self.cwd)
        try:
            shutil.rmtree(f"{self.cwd}/tests/tmp/")
        except FileNotFoundError:
            pass

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(f"{self.cwd}/tests/tmp/")

    def setUp(self):
        reload(asimov)
        reload(manage)
        os.makedirs(f"{self.cwd}/tests/tmp/project")
        os.chdir(f"{self.cwd}/tests/tmp/project")
        runner = CliRunner()
        result = runner.invoke(
            project.init, ["Test Project", "--root", f"{self.cwd}/tests/tmp/project"]
        )
        assert result.exit_code == 0
        assert result.output == "● New project created successfully!\n"
        self.ledger = YAMLLedger(".asimov/ledger.yml")

        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            apply_page(
                file=f"{self.cwd}/tests/test_data/testing_pe.yaml",
                event=None,
                ledger=self.ledger,
            )
            apply_page(
                file=f"{self.cwd}/tests/test_data/testing_events.yaml",
                ledger=self.ledger,
            )


class TestSimpleAnalysis(TestBaseAnalysis):
    pass


class TestSubjectAnalysis(TestBaseAnalysis):
    """
    Tests for subject analysis code.
    """

    pipelines = {"bayeswave"}
    EVENTS = ["GW150914_095045", "GW151226_033853", "GW170814_103043"]

    def setUp(self):
        super().setUp()

    def test_all_events_present(self):
        """Test that all of the expected events are in the ledger."""
        self.assertEqual(list(self.ledger.events.keys()), self.EVENTS)

    def test_that_analyses_are_matched(self):
        pass


# class TestProjectAnalysis(TestBaseAnalysis):
#     """
#     Tests for Project Analysis code.
#     """

#     def setUp(self):
#         super().setUp()
#         apply_page(
#             file=f"{self.cwd}/tests/test_data/test_joint_analysis.yaml",
#             ledger=self.ledger,
#         )

#     def test_that_subjects_are_accessible(self):
#         """Test that it is possible to get a list of subjects from a project analysis."""
#         self.assertTrue(
#             self.ledger.project_analyses[0].subjects
#             == ["GW150914_095045", "GW151226_033853"]
#         )
#         self.assertTrue(
#             self.ledger.project_analyses[0].events
#             == ["GW150914_095045", "GW151226_033853"]
#         )

#     def test_that_all_waveform_analyses_are_returned(self):
#         """Test that the query returns all of the jobs specifying a specific waveform."""

#         apply_page(
#             file=f"{self.cwd}/tests/test_data/test_analyses.yaml",
#             ledger=self.ledger,
#         )
#         self.assertEqual(len(self.ledger.events), 3)
        
#         p_analysis = self.ledger.project_analyses

#         print(p_analysis[1]._analysis_spec)
        
#         analyses = p_analysis[1].analyses
        
#         self.assertEqual(len(analyses), 3)

#     def test_that_all_uploaded_analyses_are_returned(self):
#         """Test that the query returns all of the jobs specifying a specific waveform."""

#         apply_page(
#             file=f"{self.cwd}/tests/test_data/test_analyses.yaml",
#             ledger=self.ledger,
#         )
#         p_analysis = self.ledger.project_analyses

#         analyses = p_analysis[2].analyses
#         self.assertEqual(len(analyses), 3)

#     def test_that_all_reviewed_analyses_are_returned(self):
#         """Test that the query returns all of the jobs with a specific review state."""

#         apply_page(
#             file=f"{self.cwd}/tests/test_data/test_analyses.yaml",
#             ledger=self.ledger,
#         )
#         p_analysis = self.ledger.project_analyses
        
#         analyses = p_analysis[3].analyses
#         self.assertEqual(len(analyses), 2)

#     def test_mutliple_filters(self):
#         """Test that the query returns all of the jobs with a specific review state."""

#         apply_page(
#             file=f"{self.cwd}/tests/test_data/test_analyses.yaml",
#             ledger=self.ledger,
#         )
#         p_analysis = self.ledger.project_analyses
        
#         analyses = p_analysis[4].analyses
#         self.assertEqual(len(analyses), 1)
#         for analysis in analyses:
#             self.assertTrue(str(analysis.pipeline).lower() == "lalinference")
#             self.assertTrue(str(analysis.meta['waveform']['approximant']).lower() == "imrphenomxphm")
