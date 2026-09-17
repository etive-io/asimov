"""Tests for asimov.scheduler_utils."""

import unittest

from asimov.scheduler import JobDescription
from asimov.scheduler_utils import create_job_from_dict


class CreateJobFromDictTests(unittest.TestCase):
    """Test the create_job_from_dict conversion helper."""

    def test_maps_request_gpus_to_gpus(self):
        job_dict = {
            "executable": "/bin/echo",
            "output": "out.log",
            "error": "err.log",
            "log": "job.log",
            "request_cpus": "4",
            "request_memory": "8GB",
            "request_gpus": "2",
        }

        job = create_job_from_dict(job_dict)

        self.assertIsInstance(job, JobDescription)
        self.assertEqual(job.kwargs["gpus"], "2")
        self.assertNotIn("request_gpus", job.kwargs)
        # The input dictionary must be left untouched
        self.assertIn("request_gpus", job_dict)

    def test_no_gpus_key_when_not_requested(self):
        job_dict = {
            "executable": "/bin/echo",
            "output": "out.log",
            "error": "err.log",
            "log": "job.log",
        }

        job = create_job_from_dict(job_dict)

        self.assertNotIn("gpus", job.kwargs)


if __name__ == "__main__":
    unittest.main()
