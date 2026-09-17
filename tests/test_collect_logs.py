"""Tests for Pipeline.collect_logs()."""

import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock

from asimov.pipeline import Pipeline


class TestCollectLogs(unittest.TestCase):
    """Tests for the default, scheduler-independent collect_logs() implementation."""

    def setUp(self):
        self.rundir = tempfile.mkdtemp()
        production = MagicMock()
        production.rundir = self.rundir
        production.event.name = "GW150914"
        production.name = "Prod0"
        production.category = None
        self.pipeline = Pipeline(production)

    def tearDown(self):
        shutil.rmtree(self.rundir, ignore_errors=True)

    def test_no_rundir(self):
        """collect_logs() returns an empty dict when there is no run directory."""
        self.pipeline.production.rundir = os.path.join(self.rundir, "does-not-exist")
        self.assertEqual(self.pipeline.collect_logs(), {})

    def test_empty_rundir(self):
        """collect_logs() returns an empty dict when the run directory has no logs."""
        self.assertEqual(self.pipeline.collect_logs(), {})

    def test_finds_condor_style_logs(self):
        """collect_logs() finds .out/.err/.log files regardless of scheduler."""
        with open(os.path.join(self.rundir, "test_job.out"), "w") as f:
            f.write("stdout content\n")
        with open(os.path.join(self.rundir, "test_job.err"), "w") as f:
            f.write("stderr content\n")
        with open(os.path.join(self.rundir, "test_job.log"), "w") as f:
            f.write("condor log content\n")

        logs = self.pipeline.collect_logs()
        self.assertEqual(logs["test_job.out"], "stdout content\n")
        self.assertEqual(logs["test_job.err"], "stderr content\n")
        self.assertEqual(logs["test_job.log"], "condor log content\n")

    def test_finds_slurm_style_logs(self):
        """collect_logs() also picks up Slurm's %j-suffixed output files."""
        with open(os.path.join(self.rundir, "slurm_12345.out"), "w") as f:
            f.write("slurm stdout\n")

        logs = self.pipeline.collect_logs()
        self.assertEqual(logs["slurm_12345.out"], "slurm stdout\n")

    def test_ignores_non_log_files(self):
        """collect_logs() only reads files matching the known log patterns."""
        with open(os.path.join(self.rundir, "config.ini"), "w") as f:
            f.write("[section]\nkey = value\n")

        self.assertEqual(self.pipeline.collect_logs(), {})

    def test_truncates_large_logs(self):
        """collect_logs() caps each file to the last _LOG_TAIL_BYTES bytes."""
        original_cap = Pipeline._LOG_TAIL_BYTES
        Pipeline._LOG_TAIL_BYTES = 100
        try:
            content = "x" * 500
            with open(os.path.join(self.rundir, "big.out"), "w") as f:
                f.write(content)

            logs = self.pipeline.collect_logs()
            self.assertIn("truncated", logs["big.out"])
            self.assertTrue(logs["big.out"].endswith("x" * 100))
        finally:
            Pipeline._LOG_TAIL_BYTES = original_cap

    def test_subclass_can_override_log_patterns(self):
        """Subclasses can widen or narrow which files count as logs."""

        class CustomPipeline(Pipeline):
            log_patterns = ["*.custom"]

        with open(os.path.join(self.rundir, "test_job.out"), "w") as f:
            f.write("should be ignored\n")
        with open(os.path.join(self.rundir, "notes.custom"), "w") as f:
            f.write("custom log\n")

        custom_pipeline = CustomPipeline(self.pipeline.production)
        logs = custom_pipeline.collect_logs()
        self.assertEqual(logs, {"notes.custom": "custom log\n"})


if __name__ == "__main__":
    unittest.main()
