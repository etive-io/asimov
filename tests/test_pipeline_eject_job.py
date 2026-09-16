"""Tests for Pipeline.eject_job()."""

import unittest
from unittest.mock import patch, MagicMock

from asimov.pipeline import Pipeline


class FakeProduction:
    """A minimal stand-in mirroring Analysis.job_id's storage location."""

    def __init__(self):
        self.meta = {}

    @property
    def job_id(self):
        if "scheduler" in self.meta and "job id" in self.meta["scheduler"]:
            return self.meta["scheduler"]["job id"]
        return None

    @job_id.setter
    def job_id(self, value):
        self.meta.setdefault("scheduler", {})["job id"] = value


class EjectJobTests(unittest.TestCase):
    def _make_pipeline(self, production):
        pipeline = Pipeline.__new__(Pipeline)
        pipeline.production = production
        return pipeline

    @patch("asimov.pipeline.subprocess.Popen")
    def test_eject_job_reads_job_id_property(self, mock_popen):
        production = FakeProduction()
        production.job_id = 12345

        mock_process = MagicMock()
        # stderr=subprocess.STDOUT means communicate() always returns None
        # for the stderr half, regardless of success or failure.
        mock_process.communicate.return_value = (b"", None)
        mock_process.returncode = 0
        mock_popen.return_value = mock_process

        pipeline = self._make_pipeline(production)
        with patch("asimov.pipeline.time.sleep"):
            pipeline.eject_job()

        command = mock_popen.call_args[0][0]
        self.assertEqual(command, ["condor_rm", "12345"])
        self.assertIsNone(production.job_id)

    @patch("asimov.pipeline.subprocess.Popen")
    def test_eject_job_leaves_job_id_on_nonzero_exit(self, mock_popen):
        """A failed condor_rm (non-zero exit) must not discard the job ID,
        even though stderr is always None due to the STDOUT redirect."""
        production = FakeProduction()
        production.job_id = 12345

        mock_process = MagicMock()
        mock_process.communicate.return_value = (b"some error output", None)
        mock_process.returncode = 1
        mock_popen.return_value = mock_process

        pipeline = self._make_pipeline(production)
        with patch("asimov.pipeline.time.sleep"):
            pipeline.eject_job()

        self.assertEqual(production.job_id, 12345)


if __name__ == "__main__":
    unittest.main()
