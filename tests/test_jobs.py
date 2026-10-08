"""
Tests for running build and submit in a separate process (#68).
"""

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from asimov import jobs
from asimov.cli import manage
from asimov.cli.application import apply_page
from asimov.cli.project import make_project
from asimov.context import ProjectContext
from asimov.principal import Principal, acting_as

DATA = os.path.join(os.path.dirname(__file__), "test_data")
ENGINES = ("yamlfile", "sqlite")


class JobTestCase(unittest.TestCase):
    engine = "yamlfile"

    def setUp(self):
        self.origin = os.getcwd()
        self.addCleanup(os.chdir, self.origin)
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        make_project(name="T", root=self.root, engine=self.engine)
        os.chdir(self.origin)
        self.context = ProjectContext.from_directory(self.root)
        self.addCleanup(self.context.reload_ledger)
        with self.context.activate():
            apply_page(os.path.join(DATA, "testing_pe.yaml"), ledger=self.context.ledger)
            apply_page(os.path.join(DATA, "test_event.yaml"), ledger=self.context.ledger)

    def start(self, action="build", **kwargs):
        agent = Principal.agent("tester", acting_for=Principal.person("dw"))
        with self.context.activate(), acting_as(agent):
            return jobs.start_job(self.context, action, **kwargs)

    def wait(self, job_id, seconds=60):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            job = jobs.get_job(self.root, job_id)
            if not job.active:
                return job
            time.sleep(0.1)
        self.fail("the job did not finish")


class TestWorker(JobTestCase):
    def test_a_real_worker_builds_and_finishes(self):
        job = self.start("build")
        self.assertIn(job.status, ("queued", "running"))
        done = self.wait(job.id)
        self.assertEqual(done.status, "succeeded", done.error)
        self.assertIsNone(jobs._locked_by(self.root))
        self.assertIn("Building", jobs.read_log(self.root, job.id))

    def test_the_job_runs_as_the_caller(self):
        job = self.start("build")
        self.assertEqual(job.principal["identifier"], "tester")
        self.assertEqual(job.principal["acting for"]["identifier"], "dw")

    def test_the_start_is_audited(self):
        job = self.start("submit", dryrun=True)
        self.wait(job.id)
        with self.context.activate():
            records = self.context.ledger.audit_log(kind="job")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].action, "submit")
        self.assertEqual(records[0].content["job"], job.id)
        self.assertEqual(records[0].principal_obj.identifier, "tester")

    def test_a_dry_submit_submits_nothing(self):
        done = self.wait(self.start("submit", dryrun=True).id)
        self.assertEqual(done.status, "succeeded", done.error)
        self.assertEqual(done.result, {"submitted": 0})

    def test_unknown_action(self):
        with self.assertRaises(jobs.JobError):
            self.start("delete")

    def test_failure_is_recorded(self):
        with patch.object(manage, "build_analyses", side_effect=RuntimeError("no scheduler")):
            job = self.start("build", command=[sys.executable, "-c", "pass"])
            done = jobs.run_job(self.root, job.id)
        self.assertEqual(done.status, "failed")
        self.assertIn("no scheduler", done.error)
        self.assertIsNone(jobs._locked_by(self.root))


class TestLock(JobTestCase):
    SLEEP = [sys.executable, "-c", "import time; time.sleep(60)"]

    def tearDown(self):
        for job in jobs.list_jobs(self.root):
            if job.active and job.pid and job.pid != os.getpid():
                try:
                    os.kill(job.pid, 9)
                except OSError:
                    pass

    def test_a_second_job_is_refused_while_one_runs(self):
        first = self.start("build", command=self.SLEEP)
        with self.assertRaises(jobs.JobBusy) as raised:
            self.start("submit")
        self.assertEqual(raised.exception.job_id, first.id)
        self.assertIn(first.id, str(raised.exception))

    def test_a_dead_worker_is_noticed_and_the_lock_released(self):
        job = self.start("build", command=[sys.executable, "-c", "import os; os._exit(0)"])
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and jobs.get_job(self.root, job.id).active:
            time.sleep(0.1)
        done = jobs.get_job(self.root, job.id)
        self.assertEqual(done.status, "failed")
        self.assertIn("stopped without finishing", done.error)
        self.assertIsNone(jobs._locked_by(self.root))
        # and another job can start
        self.wait(self.start("build").id)

    def test_a_stale_lock_is_taken_over(self):
        os.makedirs(jobs.jobs_dir(self.root), exist_ok=True)
        with open(jobs._lock_path(self.root), "w") as handle:
            handle.write("0" * 32)
        self.wait(self.start("build").id)

    def test_timeout_stops_the_worker(self):
        def slow(event=None, dryrun=False):
            time.sleep(30)

        with patch.object(manage, "build_analyses", slow):
            job = self.start("build", timeout=1, command=[sys.executable, "-c", "pass"])
            started = time.monotonic()
            done = jobs.run_job(self.root, job.id)
        self.assertLess(time.monotonic() - started, 15)
        self.assertEqual(done.status, "failed")
        self.assertIn("more than 1 seconds", done.error)


class TestRecords(JobTestCase):
    def test_list_newest_first_and_active_filter(self):
        a = self.wait(self.start("build").id)
        b = self.wait(self.start("build").id)
        listed = jobs.list_jobs(self.root)
        self.assertEqual([j.id for j in listed], [b.id, a.id])
        self.assertEqual(jobs.list_jobs(self.root, active=True), [])
        self.assertEqual(len(jobs.list_jobs(self.root, limit=1)), 1)

    def test_bad_ids_are_refused(self):
        for bad in ("../../etc/passwd", "", "XYZ"):
            with self.assertRaises(jobs.JobError):
                jobs.get_job(self.root, bad)

    def test_unknown_job(self):
        with self.assertRaises(jobs.JobError):
            jobs.get_job(self.root, "ab" * 16)

    def test_records_are_json(self):
        job = self.wait(self.start("build").id)
        with open(os.path.join(jobs.jobs_dir(self.root), job.id + ".json")) as handle:
            self.assertEqual(json.load(handle)["status"], "succeeded")


class TestSqlite(TestWorker, TestLock, TestRecords):
    engine = "sqlite"


if __name__ == "__main__":
    unittest.main()
