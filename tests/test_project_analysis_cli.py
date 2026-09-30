"""
Regression tests for the CLI handling of project analyses:

* ``manage submit`` must wait for a project analysis's ``analyses:``
  dependencies rather than submitting it (and having it marked ``stuck``).
* ``review add`` must be able to review project analyses.
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from click.testing import CliRunner

from asimov.cli import manage, project, review
from asimov.cli.application import apply_page
from asimov.ledger import YAMLLedger
from asimov.review import ReviewMessage

EVENT = "kind: event\nname: {name}\ninterferometers: [H1]\n"
ANALYSIS = (
    "kind: analysis\nname: base\npipeline: simpletestpipeline\nstatus: {status}\n"
)
PROJECT_ANALYSIS = """kind: projectanalysis
name: pa1
pipeline: simpletestpipeline
subjects: {subjects}
analyses:
- - 'pipeline: simpletestpipeline'
  - 'review: approved'
status: ready
"""


class ProjectAnalysisTestCase(unittest.TestCase):
    """Set up a scratch project with two events and a project analysis."""

    subjects = "[EvA]"
    base_status = "finished"

    def setUp(self):
        self.cwd = os.getcwd()
        self.test_dir = tempfile.mkdtemp()
        os.chdir(self.test_dir)
        result = CliRunner().invoke(
            project.init,
            ["Test Project", "--root", self.test_dir, "--engine", "yamlfile"],
        )
        assert result.exit_code == 0, result.output

        self.ledger = YAMLLedger(".asimov/ledger.yml")
        for name in ("EvA", "EvB"):
            self._write("event.yaml", EVENT.format(name=name))
            apply_page("event.yaml", ledger=self.ledger)
        self._write("analysis.yaml", ANALYSIS.format(status=self.base_status))
        apply_page("analysis.yaml", event="EvA", ledger=self.ledger)
        self._write(
            "project-analysis.yaml", PROJECT_ANALYSIS.format(subjects=self.subjects)
        )
        apply_page("project-analysis.yaml", ledger=self.ledger)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _write(self, name, text):
        with open(name, "w") as f:
            f.write(text)

    def _project_analysis(self):
        return YAMLLedger(".asimov/ledger.yml").project_analyses[0]


class TestSourceAnalysesReady(ProjectAnalysisTestCase):
    base_status = "finished"

    def test_waits_for_approval(self):
        """The base analysis has finished but not been approved yet."""
        self.assertFalse(self._project_analysis().source_analyses_ready())

    def test_ready_once_approved(self):
        ledger = YAMLLedger(".asimov/ledger.yml")
        event = ledger.get_event("EvA")[0]
        event.productions[0].review.add(
            ReviewMessage(message="ok", status="approved", production=event.productions[0])
        )
        ledger.update_event(event)
        self.assertTrue(self._project_analysis().source_analyses_ready())

    def test_unfinished_dependencies_are_not_ready(self):
        ledger = YAMLLedger(".asimov/ledger.yml")
        event = ledger.get_event("EvA")[0]
        analysis = event.productions[0]
        analysis.review.add(
            ReviewMessage(message="ok", status="approved", production=analysis)
        )
        analysis.status = "running"
        ledger.update_event(event)
        self.assertFalse(self._project_analysis().source_analyses_ready())

    def test_no_match_is_not_ready(self):
        """An analyses: spec which resolves to nothing must not count as ready."""
        analysis = self._project_analysis()
        analysis._analysis_spec = [["pipeline: nosuchpipeline"]]
        self.assertFalse(analysis.source_analyses_ready())

    def test_no_spec_is_always_ready(self):
        analysis = self._project_analysis()
        analysis._analysis_spec = {}
        self.assertTrue(analysis.source_analyses_ready())


class TestManageSubmitWaitsForDependencies(ProjectAnalysisTestCase):
    # "running" so that manage submit leaves the upstream analysis alone and
    # any build_dag call can only come from the project analysis.
    base_status = "running"

    def _submit(self):
        ledger = YAMLLedger(".asimov/ledger.yml")
        with patch("asimov.cli.manage.ledger", new=ledger), patch(
            "asimov.cli.manage.condor"
        ), patch(
            "asimov.pipelines.testing.SimpleTestPipeline.build_dag", create=True
        ) as build_dag:
            result = CliRunner().invoke(manage.submit, [])
        return result, build_dag

    def test_unmet_dependencies_are_not_submitted(self):
        result, build_dag = self._submit()
        self.assertIn("not ready to submit", result.output)
        build_dag.assert_not_called()
        # It is left waiting, not marked stuck.
        self.assertEqual(self._project_analysis().status, "ready")


class TestReviewAddProjectAnalysis(ProjectAnalysisTestCase):
    subjects = "[EvA]"

    def _review(self, *args):
        ledger = YAMLLedger(".asimov/ledger.yml")
        with patch("asimov.cli.review.current_ledger", new=ledger):
            return CliRunner().invoke(review.review, ["add", *args])

    def _messages(self):
        return [m.status for m in self._project_analysis().review.messages]

    def test_single_subject_without_other_subjects(self):
        """Previously an IndexError: no event production is called pa1."""
        result = self._review("EvA", "pa1", "approved", "-m", "looks good")
        self.assertIsNone(result.exception, result.output)
        self.assertIn("pa1 approved", result.output)
        self.assertEqual(self._messages(), ["APPROVED"])

    def test_with_pipeline_filter(self):
        result = self._review("EvA", "pa1", "approved", "-p", "simpletestpipeline")
        self.assertIsNone(result.exception, result.output)
        self.assertEqual(self._messages(), ["APPROVED"])

    def test_wrong_pipeline_is_not_found(self):
        result = self._review("EvA", "pa1", "approved", "-p", "other")
        self.assertIsNone(result.exception, result.output)
        self.assertIn("Unable to find", result.output)
        self.assertEqual(self._messages(), [])

    def test_unknown_analysis_reports_an_error(self):
        result = self._review("EvA", "nosuchanalysis", "approved")
        self.assertIsNone(result.exception, result.output)
        self.assertIn("Unable to find", result.output)

    def test_rejects_unknown_status(self):
        result = self._review("EvA", "pa1", "splorg")
        self.assertIsNone(result.exception, result.output)
        self.assertIn("Did not understand the review status", result.output)
        self.assertEqual(self._messages(), [])


class TestReviewAddMultiSubjectProjectAnalysis(ProjectAnalysisTestCase):
    subjects = "[EvA, EvB]"

    def test_other_subjects(self):
        """Previously a TypeError (unhashable Event), then an AttributeError."""
        ledger = YAMLLedger(".asimov/ledger.yml")
        with patch("asimov.cli.review.current_ledger", new=ledger):
            result = CliRunner().invoke(
                review.review,
                ["add", "EvA", "pa1", "approved", "-o_e", "EvB", "-m", "ok"],
            )
        self.assertIsNone(result.exception, result.output)
        self.assertIn("pa1 approved", result.output)
        self.assertEqual(
            [m.status for m in self._project_analysis().review.messages], ["APPROVED"]
        )


if __name__ == "__main__":
    unittest.main()
