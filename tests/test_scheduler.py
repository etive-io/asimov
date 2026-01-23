"""Tests for the scheduler abstraction layer."""

import unittest
import os
import tempfile
from unittest.mock import Mock, patch, MagicMock

from asimov.scheduler import (
    Scheduler,
    HTCondor,
    Slurm,
    Job,
    JobList,
    JobDescription,
    get_scheduler,
)


class JobDescriptionTests(unittest.TestCase):
    """Test the JobDescription class."""

    def test_to_htcondor(self):
        """Test conversion to HTCondor submit description."""
        job = JobDescription(
            executable="/bin/echo",
            output="out.log",
            error="err.log",
            log="job.log",
            cpus=4,
            memory="8GB",
            disk="10GB",
        )

        htcondor_dict = job.to_htcondor()

        self.assertEqual(htcondor_dict["executable"], "/bin/echo")
        self.assertEqual(htcondor_dict["output"], "out.log")
        self.assertEqual(htcondor_dict["error"], "err.log")
        self.assertEqual(htcondor_dict["log"], "job.log")
        self.assertEqual(htcondor_dict["request_cpus"], 4)
        self.assertEqual(htcondor_dict["request_memory"], "8GB")
        self.assertEqual(htcondor_dict["request_disk"], "10GB")

    def test_to_slurm(self):
        """Test conversion to Slurm submit description."""
        job = JobDescription(
            executable="/bin/echo",
            output="out.log",
            error="err.log",
            log="job.log",
            cpus=4,
            memory="8GB",
            batch_name="test-job",
        )

        slurm_dict = job.to_slurm()

        self.assertEqual(slurm_dict["executable"], "/bin/echo")
        self.assertEqual(slurm_dict["output"], "out.log")
        self.assertEqual(slurm_dict["error"], "err.log")
        self.assertEqual(slurm_dict["log"], "job.log")
        self.assertEqual(slurm_dict["cpus"], 4)
        self.assertEqual(slurm_dict["memory"], "8GB")
        self.assertEqual(slurm_dict["batch_name"], "test-job")

    def test_to_htcondor_defaults(self):
        """Test that HTCondor defaults are set correctly."""
        job = JobDescription(
            executable="/bin/echo",
            output="out.log",
            error="err.log",
            log="job.log",
        )

        htcondor_dict = job.to_htcondor()

        # Check defaults
        self.assertEqual(htcondor_dict["request_cpus"], 1)
        self.assertEqual(htcondor_dict["request_memory"], "1GB")
        self.assertEqual(htcondor_dict["request_disk"], "1GB")


class JobTests(unittest.TestCase):
    """Test the Job class."""

    def test_job_creation(self):
        """Test creating a Job object."""
        job = Job(
            job_id=12345,
            command="/bin/echo",
            hosts=1,
            status=2,
            name="test-job",
        )

        self.assertEqual(job.job_id, 12345)
        self.assertEqual(job.command, "/bin/echo")
        self.assertEqual(job.hosts, 1)
        self.assertEqual(job._status, 2)
        self.assertEqual(job.name, "test-job")

    def test_job_status_htcondor(self):
        """Test HTCondor status code conversion."""
        status_map = {
            0: "Unexplained",
            1: "Idle",
            2: "Running",
            3: "Removed",
            4: "Completed",
            5: "Held",
            6: "Submission error",
        }

        for code, expected_status in status_map.items():
            job = Job(job_id=1, command="test", hosts=0, status=code)
            self.assertEqual(job.status, expected_status)

    def test_job_string_status(self):
        """Test that string status is returned as-is."""
        job = Job(job_id=1, command="test", hosts=0, status="RUNNING")
        self.assertEqual(job.status, "RUNNING")

    def test_job_subjobs(self):
        """Test adding subjobs to a job."""
        parent = Job(job_id=1, command="parent", hosts=0, status=2)
        child = Job(job_id=2, command="child", hosts=0, status=2, dag_id=1)

        parent.add_subjob(child)

        self.assertEqual(len(parent.subjobs), 1)
        self.assertEqual(parent.subjobs[0], child)

    def test_job_to_dict(self):
        """Test converting a job to a dictionary."""
        job = Job(
            job_id=12345,
            command="/bin/echo",
            hosts=1,
            status=2,
            name="test-job",
        )

        job_dict = job.to_dict()

        self.assertEqual(job_dict["id"], 12345)
        self.assertEqual(job_dict["command"], "/bin/echo")
        self.assertEqual(job_dict["hosts"], 1)
        self.assertEqual(job_dict["status"], 2)
        self.assertEqual(job_dict["name"], "test-job")


class GetSchedulerTests(unittest.TestCase):
    """Test the get_scheduler factory function."""

    def test_get_htcondor_scheduler(self):
        """Test getting an HTCondor scheduler."""
        scheduler = get_scheduler("htcondor")
        self.assertIsInstance(scheduler, HTCondor)

    def test_get_slurm_scheduler(self):
        """Test getting a Slurm scheduler."""
        scheduler = get_scheduler("slurm")
        self.assertIsInstance(scheduler, Slurm)

    def test_get_scheduler_case_insensitive(self):
        """Test that scheduler type is case-insensitive."""
        scheduler = get_scheduler("HTCondor")
        self.assertIsInstance(scheduler, HTCondor)

        scheduler = get_scheduler("SLURM")
        self.assertIsInstance(scheduler, Slurm)

    def test_get_scheduler_with_kwargs(self):
        """Test passing kwargs to scheduler constructor."""
        scheduler = get_scheduler("slurm", partition="compute")
        self.assertIsInstance(scheduler, Slurm)
        self.assertEqual(scheduler.partition, "compute")

    def test_get_scheduler_unknown_type(self):
        """Test that unknown scheduler type raises ValueError."""
        with self.assertRaises(ValueError):
            get_scheduler("unknown")


class SlurmSchedulerTests(unittest.TestCase):
    """Test the Slurm scheduler implementation."""

    def test_slurm_init(self):
        """Test Slurm scheduler initialization."""
        scheduler = Slurm()
        self.assertIsNone(scheduler.partition)

        scheduler = Slurm(partition="compute")
        self.assertEqual(scheduler.partition, "compute")

    def test_create_batch_script(self):
        """Test creating a Slurm batch script."""
        scheduler = Slurm(partition="compute")

        submit_dict = {
            "executable": "/bin/echo",
            "arguments": "Hello World",
            "output": "out.log",
            "error": "err.log",
            "cpus": 4,
            "memory": "8GB",
            "batch_name": "test-job",
            "getenv": True,
        }

        script = scheduler._create_batch_script(submit_dict)

        self.assertIn("#!/bin/bash", script)
        self.assertIn("#SBATCH --partition=compute", script)
        self.assertIn("#SBATCH --job-name=test-job", script)
        self.assertIn("#SBATCH --output=out.log", script)
        self.assertIn("#SBATCH --error=err.log", script)
        self.assertIn("#SBATCH --cpus-per-task=4", script)
        # Memory is converted from GB to MB (8GB -> 8192MB)
        self.assertIn("#SBATCH --mem=8192", script)
        self.assertIn("#SBATCH --export=ALL", script)
        self.assertIn("/bin/echo Hello World", script)

    def test_create_batch_script_memory_conversion(self):
        """Test that memory is converted correctly."""
        scheduler = Slurm()

        # Test GB to MB conversion
        submit_dict = {
            "executable": "/bin/echo",
            "output": "out.log",
            "error": "err.log",
            "memory": "8GB",
        }
        script = scheduler._create_batch_script(submit_dict)
        self.assertIn("#SBATCH --mem=8192", script)

        # Test MB (no conversion)
        submit_dict["memory"] = "4096MB"
        script = scheduler._create_batch_script(submit_dict)
        self.assertIn("#SBATCH --mem=4096", script)

    @patch("subprocess.run")
    def test_slurm_submit(self, mock_run):
        """Test Slurm job submission."""
        mock_run.return_value = Mock(
            stdout="Submitted batch job 12345\n", returncode=0
        )

        scheduler = Slurm()
        job_desc = JobDescription(
            executable="/bin/echo",
            output="out.log",
            error="err.log",
            log="job.log",
        )

        job_id = scheduler.submit(job_desc)

        self.assertEqual(job_id, 12345)
        # Verify sbatch was called
        self.assertTrue(mock_run.called)
        call_args = mock_run.call_args[0][0]
        self.assertEqual(call_args[0], "sbatch")

    @patch("subprocess.run")
    def test_slurm_delete(self, mock_run):
        """Test Slurm job deletion."""
        mock_run.return_value = Mock(stdout="", returncode=0)

        scheduler = Slurm()
        scheduler.delete(12345)

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        self.assertEqual(call_args, ["scancel", "12345"])

    @patch("subprocess.run")
    def test_slurm_query(self, mock_run):
        """Test Slurm job query."""
        mock_run.return_value = Mock(
            stdout="12345|test-job|R|node01\n", returncode=0
        )

        scheduler = Slurm()
        jobs = scheduler.query(job_id=12345)

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["JobId"], "12345")
        self.assertEqual(jobs[0]["JobName"], "test-job")
        self.assertEqual(jobs[0]["State"], "R")
        self.assertEqual(jobs[0]["NodeList"], "node01")

    @patch("subprocess.run")
    def test_slurm_query_all_jobs(self, mock_run):
        """Test querying all Slurm jobs."""
        mock_run.return_value = Mock(
            stdout="12345|test-job-1|R|node01|2\n12346|test-job-2|PD|node02|1\n",
            returncode=0,
        )

        scheduler = Slurm()
        jobs = scheduler.query_all_jobs()

        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0]["id"], 12345)
        self.assertEqual(jobs[0]["name"], "test-job-1")
        self.assertEqual(jobs[0]["status"], 2)  # Running
        self.assertEqual(jobs[0]["hosts"], 2)

        self.assertEqual(jobs[1]["id"], 12346)
        self.assertEqual(jobs[1]["name"], "test-job-2")
        self.assertEqual(jobs[1]["status"], 1)  # Idle (Pending)
        self.assertEqual(jobs[1]["hosts"], 1)

    def test_topological_sort(self):
        """Test topological sort for DAG dependencies."""
        scheduler = Slurm()

        jobs = ["A", "B", "C", "D"]
        dependencies = {
            "B": ["A"],
            "C": ["A"],
            "D": ["B", "C"],
        }

        sorted_jobs = scheduler._topological_sort(jobs, dependencies)

        # A should come before B and C
        self.assertTrue(sorted_jobs.index("A") < sorted_jobs.index("B"))
        self.assertTrue(sorted_jobs.index("A") < sorted_jobs.index("C"))
        # B and C should come before D
        self.assertTrue(sorted_jobs.index("B") < sorted_jobs.index("D"))
        self.assertTrue(sorted_jobs.index("C") < sorted_jobs.index("D"))

    def test_topological_sort_cycle_detection(self):
        """Test that circular dependencies are detected."""
        scheduler = Slurm()

        jobs = ["A", "B", "C"]
        dependencies = {
            "A": ["C"],
            "B": ["A"],
            "C": ["B"],
        }

        with self.assertRaises(RuntimeError) as context:
            scheduler._topological_sort(jobs, dependencies)

        self.assertIn("Circular dependency", str(context.exception))

    def test_parse_submit_file(self):
        """Test parsing HTCondor submit file for Slurm."""
        scheduler = Slurm()

        # Create a temporary submit file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sub", delete=False) as f:
            f.write("executable = /bin/echo\n")
            f.write('arguments = "Hello World"\n')
            submit_file = f.name

        try:
            cmd = scheduler._parse_submit_file_for_slurm(submit_file, "/tmp")
            self.assertIn("/bin/echo", cmd)
            self.assertIn("Hello World", cmd)
            self.assertIn("cd /tmp", cmd)
        finally:
            os.unlink(submit_file)

    def test_convert_dag_to_slurm(self):
        """Test converting HTCondor DAG to Slurm script."""
        scheduler = Slurm()

        # Create temporary DAG file and submit files
        with tempfile.TemporaryDirectory() as tmpdir:
            dag_file = os.path.join(tmpdir, "test.dag")
            sub_file_a = os.path.join(tmpdir, "job_a.sub")
            sub_file_b = os.path.join(tmpdir, "job_b.sub")

            # Create submit files
            with open(sub_file_a, "w") as f:
                f.write("executable = /bin/echo\n")
                f.write('arguments = "Job A"\n')

            with open(sub_file_b, "w") as f:
                f.write("executable = /bin/echo\n")
                f.write('arguments = "Job B"\n')

            # Create DAG file
            with open(dag_file, "w") as f:
                f.write(f"JOB job_a {sub_file_a}\n")
                f.write(f"JOB job_b {sub_file_b}\n")
                f.write("PARENT job_a CHILD job_b\n")

            # Convert to Slurm
            script = scheduler._convert_dag_to_slurm(dag_file, "test-dag")

            self.assertIn("#!/bin/bash", script)
            self.assertIn("#SBATCH --job-name=test-dag", script)
            self.assertIn("declare -A job_ids", script)
            self.assertIn("job_a", script)
            self.assertIn("job_b", script)
            self.assertIn("--dependency=afterok:", script)


if __name__ == "__main__":
    unittest.main()
