"""Tests for the testing pipelines."""

import unittest
import shutil
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from asimov.pipelines.testing import (
    SimpleTestPipeline,
    SubjectTestPipeline,
    ProjectTestPipeline
)
from asimov.analysis import SimpleAnalysis, SubjectAnalysis, ProjectAnalysis

from asimov.ledger import YAMLLedger

from asimov.cli.application import apply_page

from click.testing import CliRunner
from asimov.cli import project


class TestingPipelineTests(unittest.TestCase):
    """Test the testing pipelines."""

    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()

    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()
        os.chdir(self.test_dir)

        runner = CliRunner()
        result = runner.invoke(
            project.init,
            ['Test Project', '--root', self.test_dir]
        )
        self.assertEqual(result.exit_code, 0)
        self.ledger = YAMLLedger(f"{self.test_dir}/.asimov/ledger.yml")

    def tearDown(self):
        """Clean up test environment."""
        os.chdir(self.cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_simple_pipeline_instantiation(self):
        """Test that SimpleTestPipeline can be instantiated."""
        # Load test data
        apply_page(
            file=f"{self.cwd}/tests/test_data/testing_pe.yaml",
            event=None,
            ledger=self.ledger
        )
        apply_page(
            file=f"{self.cwd}/tests/test_data/testing_events.yaml",
            ledger=self.ledger
        )

        # Create a test event and analysis
        event = self.ledger.get_event("GW150914_095045")[0]

        # Create a simple analysis with the test pipeline
        analysis = SimpleAnalysis(
            subject=event,
            name="test-simple",
            pipeline="simpletestpipeline",
            status="ready",
            ledger=self.ledger
        )

        # Check the pipeline was created correctly
        self.assertIsInstance(analysis.pipeline, SimpleTestPipeline)
        self.assertEqual(analysis.pipeline.name, "SimpleTestPipeline")

    @patch('subprocess.run')
    def test_simple_pipeline_submit(self, mock_run):
        """Test that SimpleTestPipeline can submit a job."""
        # Mock condor_submit_dag response
        mock_result = MagicMock()
        mock_result.stdout = "1 job(s) submitted to cluster 12345."
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        apply_page(
            file=f"{self.cwd}/tests/test_data/testing_pe.yaml",
            event=None,
            ledger=self.ledger
        )
        apply_page(
            file=f"{self.cwd}/tests/test_data/testing_events.yaml",
            ledger=self.ledger
        )

        event = self.ledger.get_event("GW150914_095045")[0]

        analysis = SimpleAnalysis(
            subject=event,
            name="test-simple",
            pipeline="simpletestpipeline",
            status="ready",
            ledger=self.ledger,
            rundir=os.path.join(self.test_dir, "simple_run")
        )

        # Submit the job
        job_id = analysis.pipeline.submit_dag(dryrun=False)

        # Check job was submitted
        self.assertEqual(job_id, 12345)
        self.assertTrue(os.path.exists(analysis.rundir))
        self.assertTrue(
            os.path.exists(os.path.join(analysis.rundir, "test_job.sh"))
        )

    def test_simple_pipeline_completion(self):
        """Test that SimpleTestPipeline can detect completion."""
        apply_page(
            file=f"{self.cwd}/tests/test_data/testing_pe.yaml",
            event=None,
            ledger=self.ledger
        )
        apply_page(
            file=f"{self.cwd}/tests/test_data/testing_events.yaml",
            ledger=self.ledger
        )

        event = self.ledger.get_event("GW150914_095045")[0]

        analysis = SimpleAnalysis(
            subject=event,
            name="test-simple",
            pipeline="simpletestpipeline",
            status="ready",
            ledger=self.ledger,
            rundir=os.path.join(self.test_dir, "simple_run")
        )

        # Initially not complete
        self.assertFalse(analysis.pipeline.detect_completion())

        # Create results file
        Path(analysis.rundir).mkdir(parents=True, exist_ok=True)
        with open(os.path.join(analysis.rundir, "results.dat"), "w") as f:
            f.write("test results\n")

        # Now should be complete
        self.assertTrue(analysis.pipeline.detect_completion())

    def test_simple_pipeline_samples(self):
        """Test that SimpleTestPipeline can generate sample files."""
        apply_page(
            file=f"{self.cwd}/tests/test_data/testing_pe.yaml",
            event=None,
            ledger=self.ledger
        )
        apply_page(
            file=f"{self.cwd}/tests/test_data/testing_events.yaml",
            ledger=self.ledger
        )

        event = self.ledger.get_event("GW150914_095045")[0]

        analysis = SimpleAnalysis(
            subject=event,
            name="test-simple",
            pipeline="simpletestpipeline",
            status="ready",
            ledger=self.ledger,
            rundir=os.path.join(self.test_dir, "simple_run")
        )

        # Get samples (should create file)
        samples = analysis.pipeline.samples(absolute=True)

        self.assertEqual(len(samples), 1)
        self.assertTrue(os.path.exists(samples[0]))
        self.assertTrue("posterior_samples.dat" in samples[0])

    def test_pipeline_names(self):
        """Test that all testing pipelines have the correct names."""
        apply_page(
            file=f"{self.cwd}/tests/test_data/testing_pe.yaml",
            event=None,
            ledger=self.ledger
        )
        apply_page(
            file=f"{self.cwd}/tests/test_data/testing_events.yaml",
            ledger=self.ledger
        )

        event = self.ledger.get_event("GW150914_095045")[0]

        # Test SimpleTestPipeline
        simple = SimpleAnalysis(
            subject=event,
            name="test-simple",
            pipeline="simpletestpipeline",
            status="ready",
            ledger=self.ledger
        )
        self.assertEqual(simple.pipeline.name, "SimpleTestPipeline")

        # Test SubjectTestPipeline
        subject = SubjectAnalysis(
            subject=event,
            name="test-subject",
            pipeline="subjecttestpipeline",
            status="ready"
        )
        self.assertEqual(subject.pipeline.name, "SubjectTestPipeline")

        # Test ProjectTestPipeline
        project_analysis = ProjectAnalysis(
            name="test-project",
            pipeline="projecttestpipeline",
            status="ready",
            subjects=["GW150914_095045"],
            ledger=self.ledger
        )
        self.assertEqual(project_analysis.pipeline.name, "ProjectTestPipeline")


class SubjectPipelineTests(unittest.TestCase):
    """Test the SubjectTestPipeline specifically."""

    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()

    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()
        os.chdir(self.test_dir)

        runner = CliRunner()
        result = runner.invoke(
            project.init,
            ['Test Project', '--root', self.test_dir]
        )
        self.assertEqual(result.exit_code, 0)
        self.ledger = YAMLLedger(f"{self.test_dir}/.asimov/ledger.yml")

    def tearDown(self):
        """Clean up test environment."""
        os.chdir(self.cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    @patch('subprocess.run')
    def test_subject_pipeline_submit(self, mock_run):
        """Test that SubjectTestPipeline can submit a job."""
        # Mock condor_submit_dag response
        mock_result = MagicMock()
        mock_result.stdout = "1 job(s) submitted to cluster 23456."
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        apply_page(
            file=f"{self.cwd}/tests/test_data/testing_pe.yaml",
            event=None,
            ledger=self.ledger
        )
        apply_page(
            file=f"{self.cwd}/tests/test_data/testing_events.yaml",
            ledger=self.ledger
        )

        event = self.ledger.get_event("GW150914_095045")[0]

        analysis = SubjectAnalysis(
            subject=event,
            name="test-subject",
            pipeline="subjecttestpipeline",
            status="ready",
            rundir=os.path.join(self.test_dir, "subject_run")
        )

        # Submit the job
        job_id = analysis.pipeline.submit_dag(dryrun=False)

        # Check job was submitted
        self.assertEqual(job_id, 23456)
        self.assertTrue(os.path.exists(analysis.rundir))
        self.assertTrue(
            os.path.exists(os.path.join(analysis.rundir, "test_subject_job.sh"))
        )


class ProjectPipelineTests(unittest.TestCase):
    """Test the ProjectTestPipeline specifically."""

    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()

    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()
        os.chdir(self.test_dir)

        runner = CliRunner()
        result = runner.invoke(
            project.init,
            ['Test Project', '--root', self.test_dir]
        )
        self.assertEqual(result.exit_code, 0)
        self.ledger = YAMLLedger(f"{self.test_dir}/.asimov/ledger.yml")

    def tearDown(self):
        """Clean up test environment."""
        os.chdir(self.cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    @patch('subprocess.run')
    def test_project_pipeline_submit(self, mock_run):
        """Test that ProjectTestPipeline can submit a job."""
        # Mock condor_submit_dag response
        mock_result = MagicMock()
        mock_result.stdout = "1 job(s) submitted to cluster 34567."
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        apply_page(
            file=f"{self.cwd}/tests/test_data/testing_pe.yaml",
            event=None,
            ledger=self.ledger
        )
        apply_page(
            file=f"{self.cwd}/tests/test_data/testing_events.yaml",
            ledger=self.ledger
        )

        analysis = ProjectAnalysis(
            name="test-project",
            pipeline="projecttestpipeline",
            status="ready",
            subjects=["GW150914_095045"],
            ledger=self.ledger,
            working_directory=os.path.join(self.test_dir, "project_run")
        )

        # Submit the job
        job_id = analysis.pipeline.submit_dag(dryrun=False)

        # Check job was submitted
        self.assertEqual(job_id, 34567)
        self.assertTrue(os.path.exists(analysis.rundir))
        self.assertTrue(
            os.path.exists(os.path.join(analysis.rundir, "test_project_job.sh"))
        )


if __name__ == '__main__':
    unittest.main()
