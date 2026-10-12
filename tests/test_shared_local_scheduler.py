"""
The local scheduler is shared within a process (#233).

It only knows the processes which it started. A pipeline submits through the
scheduler it asks for, and the list of jobs asks for another: when each was a
fresh instance, the list never had what the pipeline started, and a job that
was running was taken for one that had been evicted.
"""
import configparser
import sys
import tempfile
import unittest
import warnings
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from asimov import scheduler_utils
from asimov.cli import monitor as monitor_cli
from asimov.scheduler import JobList, LocalProcessScheduler
from asimov.scheduler_utils import get_configured_scheduler


def configured(scheduler_type):
    parser = configparser.ConfigParser()
    parser.add_section("scheduler")
    parser.set("scheduler", "type", scheduler_type)
    return parser


class SharedSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(self.clean_up)

    def clean_up(self):
        scheduler = scheduler_utils._LOCAL_SCHEDULER
        if scheduler is not None:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                for entry in scheduler.query_all_jobs():
                    scheduler.delete(entry["id"])

    def test_the_local_scheduler_is_the_same_each_time(self):
        first = get_configured_scheduler(configured("local"))
        second = get_configured_scheduler(configured("local"))
        self.assertIsInstance(first, LocalProcessScheduler)
        self.assertIs(first, second)

    def test_another_kind_is_not_shared(self):
        first = get_configured_scheduler(configured("slurm"))
        second = get_configured_scheduler(configured("slurm"))
        self.assertIsNot(first, second)

    def test_a_job_submitted_through_one_is_in_the_list_of_jobs(self):
        submitting = get_configured_scheduler(configured("local"))
        directory = tempfile.mkdtemp()
        pid = submitting.submit({
            "executable": sys.executable,
            "arguments": "-c 'import time; time.sleep(5)'",
            "output": f"{directory}/out", "error": f"{directory}/err",
        })
        listing = JobList(get_configured_scheduler(configured("local")),
                          cache_file=f"{directory}/cache.yaml", cache_time=0)
        self.assertIn(pid, listing.jobs)


class FreshJobListTests(unittest.TestCase):
    """--until-idle reads the jobs on each pass; one pass alone may use the cache."""

    def invoke(self, *arguments):
        calls = []

        def spy(cache_time=None):
            calls.append(cache_time)
            raise RuntimeError("stop here")

        with patch.object(monitor_cli, "get_job_list", spy), \
             patch.object(monitor_cli, "initialize_telemetry_sinks"), \
             patch("asimov.monitor_helpers.initialize_labellers"), \
             patch("asimov.setup_file_logging"), \
             patch.object(monitor_cli.manage.build, "callback", MagicMock()), \
             patch.object(monitor_cli.manage.submit, "callback", MagicMock(return_value=0)):
            CliRunner().invoke(monitor_cli.monitor, list(arguments))
        return calls

    def test_each_pass_of_until_idle_asks_for_the_jobs_afresh(self):
        calls = self.invoke("--chain", "--until-idle", "--max-passes", "1")
        self.assertTrue(calls)
        self.assertEqual(set(calls), {0})

    def test_a_single_pass_uses_the_cache_as_before(self):
        calls = self.invoke("--chain")
        self.assertEqual(calls, [None])


if __name__ == "__main__":
    unittest.main()
