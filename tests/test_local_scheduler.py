"""Tests for the LocalProcessScheduler."""

import os
import sys
import tempfile
import unittest

from asimov.scheduler import LocalProcessScheduler, JobDescription, get_scheduler


class TestLocalProcessScheduler(unittest.TestCase):
    """Tests for the LocalProcessScheduler class."""

    def setUp(self):
        self.scheduler = LocalProcessScheduler()
        self.tmpdir = tempfile.mkdtemp()

    def _out(self, name):
        return os.path.join(self.tmpdir, name)

    # ------------------------------------------------------------------
    # submit / query / delete
    # ------------------------------------------------------------------

    def test_submit_returns_pid(self):
        """submit() should return a positive integer PID."""
        pid = self.scheduler.submit(
            {
                "executable": sys.executable,
                "arguments": "-c pass",
                "output": self._out("out.txt"),
                "error": self._out("err.txt"),
            }
        )
        self.assertIsInstance(pid, int)
        self.assertGreater(pid, 0)
        # Wait for the subprocess so it does not become a zombie
        self.scheduler._processes[pid]["process"].wait()

    def test_submit_job_description(self):
        """submit() should also accept a JobDescription object."""
        job = JobDescription(
            executable=sys.executable,
            output=self._out("out2.txt"),
            error=self._out("err2.txt"),
            log=self._out("log2.txt"),
            arguments="-c pass",
        )
        pid = self.scheduler.submit(job)
        self.assertIsInstance(pid, int)
        self.scheduler._processes[pid]["process"].wait()

    def test_query_running_job(self):
        """query() should report 'running' for a long-running process."""
        pid = self.scheduler.submit(
            {
                "executable": sys.executable,
                "arguments": "-c import time; time.sleep(5)",
                "output": self._out("run_out.txt"),
                "error": self._out("run_err.txt"),
            }
        )
        results = self.scheduler.query(pid)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "running")
        # Clean up
        self.scheduler.delete(pid)

    def test_query_completed_job(self):
        """query() should report 'completed' after a process exits successfully."""
        pid = self.scheduler.submit(
            {
                "executable": sys.executable,
                "arguments": "-c pass",
                "output": self._out("done_out.txt"),
                "error": self._out("done_err.txt"),
            }
        )
        # Wait for process to finish
        self.scheduler._processes[pid]["process"].wait()
        results = self.scheduler.query(pid)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "completed")

    def test_delete_terminates_process(self):
        """delete() should terminate a running process."""
        pid = self.scheduler.submit(
            {
                "executable": sys.executable,
                "arguments": "-c import time; time.sleep(30)",
                "error": self._out("del_err.txt"),
            }
        )
        # Ensure process is actually running
        proc = self.scheduler._processes[pid]["process"]
        self.assertIsNone(proc.poll())
        # Delete it
        self.scheduler.delete(pid)
        # Process should no longer be tracked
        self.assertNotIn(pid, self.scheduler._processes)
        # And the OS process should be gone or finished
        self.assertIsNotNone(proc.poll())

    def test_query_all_jobs(self):
        """query_all_jobs() should return all tracked processes."""
        pid1 = self.scheduler.submit(
            {
                "executable": sys.executable,
                "arguments": "-c import time; time.sleep(10)",
                "output": self._out("all1_out.txt"),
                "error": self._out("all1_err.txt"),
            }
        )
        pid2 = self.scheduler.submit(
            {
                "executable": sys.executable,
                "arguments": "-c import time; time.sleep(10)",
                "output": self._out("all2_out.txt"),
                "error": self._out("all2_err.txt"),
            }
        )
        all_jobs = self.scheduler.query_all_jobs()
        pids = [j["id"] for j in all_jobs]
        self.assertIn(pid1, pids)
        self.assertIn(pid2, pids)
        # Clean up
        self.scheduler.delete(pid1)
        self.scheduler.delete(pid2)

    def test_submit_dag_raises(self):
        """submit_dag() should raise NotImplementedError."""
        with self.assertRaises(NotImplementedError):
            self.scheduler.submit_dag("dummy.dag")

    def test_submit_no_executable_raises(self):
        """submit() with no executable should raise RuntimeError."""
        with self.assertRaises((RuntimeError, KeyError, TypeError)):
            self.scheduler.submit({"arguments": "-c pass"})

    def test_stdout_written_to_file(self):
        """Output should be written to the specified output file."""
        out_file = self._out("stdout.txt")
        pid = self.scheduler.submit(
            {
                "executable": sys.executable,
                "arguments": "-c print('hello')",
                "output": out_file,
                "error": self._out("stdout_err.txt"),
            }
        )
        self.scheduler._processes[pid]["process"].wait()
        with open(out_file) as f:
            content = f.read()
        self.assertIn("hello", content)


class TestGetSchedulerLocal(unittest.TestCase):
    """Tests for the get_scheduler factory with type='local'."""

    def test_get_scheduler_local(self):
        """get_scheduler('local') should return a LocalProcessScheduler."""
        scheduler = get_scheduler("local")
        self.assertIsInstance(scheduler, LocalProcessScheduler)

    def test_get_scheduler_unknown_raises(self):
        """get_scheduler() with unknown type should raise ValueError."""
        with self.assertRaises(ValueError):
            get_scheduler("unknown_scheduler_type")


if __name__ == "__main__":
    unittest.main()
