"""Tests for the LocalProcessScheduler."""

import os
import shutil
import sys
import tempfile
import unittest
import warnings

from asimov.scheduler import LocalProcessScheduler, JobDescription, get_scheduler


class TestLocalProcessScheduler(unittest.TestCase):
    """Tests for the LocalProcessScheduler class."""

    def setUp(self):
        self.scheduler = LocalProcessScheduler()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        """Terminate any remaining tracked processes and remove temporary files."""
        # Use query() to get currently tracked PIDs without accessing internals,
        # then delete each one.  Suppress the expected warning when a process
        # was already cleaned up by a previous query().
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            for entry in self.scheduler.query_all_jobs():
                self.scheduler.delete(entry["id"])
        shutil.rmtree(self.tmpdir, ignore_errors=True)

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
        self.scheduler.wait_for_job(pid)

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
        self.scheduler.wait_for_job(pid)

    def test_query_running_job(self):
        """query() should report 'running' for a long-running process."""
        pid = self.scheduler.submit(
            {
                "executable": sys.executable,
                "arguments": ["-c", "import time; time.sleep(5)"],
                "output": self._out("run_out.txt"),
                "error": self._out("run_err.txt"),
            }
        )
        results = self.scheduler.query(pid)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "running")

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
        # Wait for process to finish using the public API
        self.scheduler.wait_for_job(pid)
        results = self.scheduler.query(pid)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "completed")

    def test_query_error_exit_code(self):
        """query() should report 'error (exit N)' for a process that exits with non-zero code."""
        pid = self.scheduler.submit(
            {
                "executable": sys.executable,
                "arguments": ["-c", "import sys; sys.exit(42)"],
                "output": self._out("err_out.txt"),
                "error": self._out("err_err.txt"),
            }
        )
        self.scheduler.wait_for_job(pid)
        results = self.scheduler.query(pid)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "error (exit 42)")

    def test_query_unknown_job_id(self):
        """query() with an unknown job_id should return an empty list."""
        results = self.scheduler.query(job_id=999999999)
        self.assertEqual(results, [])

    def test_delete_terminates_process(self):
        """delete() should terminate a running process."""
        pid = self.scheduler.submit(
            {
                "executable": sys.executable,
                "arguments": ["-c", "import time; time.sleep(30)"],
                "error": self._out("del_err.txt"),
            }
        )
        # Ensure process is actually running by querying it
        results = self.scheduler.query(pid)
        self.assertEqual(results[0]["status"], "running")
        # Delete it
        self.scheduler.delete(pid)
        # Process should no longer be tracked: a second query should return nothing
        results_after = self.scheduler.query(pid)
        self.assertEqual(results_after, [])

    def test_delete_unknown_pid_warns(self):
        """delete() with an unknown PID should emit a RuntimeWarning."""
        with self.assertWarns(RuntimeWarning):
            self.scheduler.delete(999999999)

    def test_query_all_jobs(self):
        """query_all_jobs() should return all tracked processes."""
        pid1 = self.scheduler.submit(
            {
                "executable": sys.executable,
                "arguments": ["-c", "import time; time.sleep(10)"],
                "output": self._out("all1_out.txt"),
                "error": self._out("all1_err.txt"),
            }
        )
        pid2 = self.scheduler.submit(
            {
                "executable": sys.executable,
                "arguments": ["-c", "import time; time.sleep(10)"],
                "output": self._out("all2_out.txt"),
                "error": self._out("all2_err.txt"),
            }
        )
        all_jobs = self.scheduler.query_all_jobs()
        pids = [j["id"] for j in all_jobs]
        self.assertIn(pid1, pids)
        self.assertIn(pid2, pids)

    def test_submit_dag_raises(self):
        """submit_dag() should raise NotImplementedError."""
        with self.assertRaises(NotImplementedError):
            self.scheduler.submit_dag("dummy.dag")

    def test_submit_no_executable_raises(self):
        """submit() with no executable should raise RuntimeError."""
        with self.assertRaises(RuntimeError):
            self.scheduler.submit({"arguments": "-c pass"})

    def test_stdout_written_to_file(self):
        """Output should be written to the specified output file."""
        out_file = self._out("stdout.txt")
        pid = self.scheduler.submit(
            {
                "executable": sys.executable,
                "arguments": ["-c", "print('hello')"],
                "output": out_file,
                "error": self._out("stdout_err.txt"),
            }
        )
        self.scheduler.wait_for_job(pid)
        # Allow query to clean up the completed process
        self.scheduler.query(pid)
        with open(out_file) as f:
            content = f.read()
        self.assertIn("hello", content)

    def test_arguments_with_spaces_via_shlex(self):
        """Arguments containing spaces in a quoted substring are handled correctly via shlex."""
        out_file = self._out("shlex_out.txt")
        # The outer double-quotes around the Python code protect the inner space,
        # which is how shlex.split correctly handles arguments with spaces.
        pid = self.scheduler.submit(
            {
                "executable": sys.executable,
                "arguments": "-c \"print('hello world')\"",
                "output": out_file,
                "error": self._out("shlex_err.txt"),
            }
        )
        self.scheduler.wait_for_job(pid)
        self.scheduler.query(pid)
        with open(out_file) as f:
            content = f.read()
        self.assertIn("hello world", content)

    def test_completed_processes_removed_after_query(self):
        """Completed processes should be removed from tracking after query() reports them."""
        pid = self.scheduler.submit(
            {
                "executable": sys.executable,
                "arguments": "-c pass",
                "output": self._out("cleanup_out.txt"),
                "error": self._out("cleanup_err.txt"),
            }
        )
        self.scheduler.wait_for_job(pid)
        # First query should return the completed status and then remove the entry
        results = self.scheduler.query(pid)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "completed")
        # After the first query, a second query for the same PID should return nothing
        results2 = self.scheduler.query(pid)
        self.assertEqual(results2, [])

    # ------------------------------------------------------------------
    # collect_history
    # ------------------------------------------------------------------

    def test_collect_history_after_completion(self):
        """collect_history() should work once query() has observed completion."""
        pid = self.scheduler.submit(
            {
                "executable": sys.executable,
                "arguments": "-c pass",
                "output": self._out("history_out.txt"),
                "error": self._out("history_err.txt"),
            }
        )
        self.scheduler.wait_for_job(pid)
        self.scheduler.query(pid)  # moves the completed process into _history

        history = self.scheduler.collect_history(pid)
        self.assertEqual(history["cpus"], 1.0)
        self.assertEqual(history["gpus"], 0.0)
        self.assertGreaterEqual(history["runtime"], 0.0)
        self.assertTrue(history["end"])  # a YYYY-MM-DD string was produced

    def test_collect_history_unknown_pid_raises(self):
        """collect_history() for a PID that was never tracked should raise ValueError."""
        with self.assertRaises(ValueError):
            self.scheduler.collect_history(999999999)

    def test_collect_history_before_query_observes_completion_raises(self):
        """collect_history() shouldn't find a history record before query() has run."""
        pid = self.scheduler.submit(
            {
                "executable": sys.executable,
                "arguments": "-c pass",
                "output": self._out("premature_out.txt"),
                "error": self._out("premature_err.txt"),
            }
        )
        self.scheduler.wait_for_job(pid)
        # Deliberately not calling query() here - no history record exists yet.
        with self.assertRaises(ValueError):
            self.scheduler.collect_history(pid)

    def test_collect_history_error_exit_still_recorded(self):
        """A non-zero exit code should still produce a usable history record."""
        pid = self.scheduler.submit(
            {
                "executable": sys.executable,
                "arguments": ["-c", "import sys; sys.exit(3)"],
                "output": self._out("failed_out.txt"),
                "error": self._out("failed_err.txt"),
            }
        )
        self.scheduler.wait_for_job(pid)
        self.scheduler.query(pid)

        history = self.scheduler.collect_history(pid)
        self.assertTrue(history["end"])

    def test_history_is_bounded(self):
        """The history cache should evict the oldest entry once the limit is exceeded."""
        original_limit = self.scheduler._HISTORY_LIMIT
        self.scheduler._HISTORY_LIMIT = 2
        try:
            pids = []
            for _ in range(3):
                pid = self.scheduler.submit(
                    {
                        "executable": sys.executable,
                        "arguments": "-c pass",
                        "output": self._out(f"bounded_out_{_}.txt"),
                        "error": self._out(f"bounded_err_{_}.txt"),
                    }
                )
                self.scheduler.wait_for_job(pid)
                self.scheduler.query(pid)
                pids.append(pid)

            # The first submitted job's history should have been evicted.
            with self.assertRaises(ValueError):
                self.scheduler.collect_history(pids[0])
            # The most recent one should still be present.
            self.scheduler.collect_history(pids[-1])
        finally:
            self.scheduler._HISTORY_LIMIT = original_limit


class TestGetSchedulerLocal(unittest.TestCase):
    """Tests for the get_scheduler factory with type='local'."""

    def test_get_scheduler_local(self):
        """get_scheduler('local') should return a LocalProcessScheduler."""
        scheduler = get_scheduler("local")
        self.assertIsInstance(scheduler, LocalProcessScheduler)

    def test_get_scheduler_local_rejects_kwargs(self):
        """get_scheduler('local') with extra kwargs should raise TypeError."""
        with self.assertRaises(TypeError):
            get_scheduler("local", some_option="value")

    def test_get_scheduler_unknown_raises(self):
        """get_scheduler() with unknown type should raise ValueError."""
        with self.assertRaises(ValueError):
            get_scheduler("unknown_scheduler_type")


if __name__ == "__main__":
    unittest.main()
