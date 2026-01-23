"""
Minimal testing pipeline for SimpleAnalysis.

This pipeline is designed to be used for testing asimov's infrastructure
without requiring a real gravitational wave analysis pipeline.
It provides a minimal implementation that completes quickly, making it
ideal for end-to-end testing and as a template for pipeline developers.
"""

import os

from pathlib import Path

from ...pipeline import Pipeline


class SimpleTestPipeline(Pipeline):
    """
    A minimal testing pipeline for SimpleAnalysis.
    
    This pipeline implements the minimum required functionality for testing
    asimov's infrastructure. It creates dummy output files and completes
    quickly without performing any actual analysis.
    
    This pipeline serves two purposes:
    1. Testing asimov's infrastructure without running real analyses
    2. Providing a template for developers creating new pipelines
    
    Parameters
    ----------
    production : :class:`asimov.analysis.SimpleAnalysis`
        The production/analysis object.
    category : str, optional
        The category of the job.
        
    Examples
    --------
    To use this pipeline in a ledger configuration:
    
    .. code-block:: yaml
    
        kind: analysis
        name: test-simple
        pipeline: simpletestpipeline
        status: ready
        
    Notes
    -----
    This pipeline creates a simple output file in the run directory
    to simulate a completed analysis.
    """
    
    name = "SimpleTestPipeline"
    STATUS = {"wait", "stuck", "stopped", "running", "finished"}
    
    def __init__(self, production, category=None):
        """
        Initialize the SimpleTestPipeline.
        
        Parameters
        ----------
        production : :class:`asimov.analysis.SimpleAnalysis`
            The production object this pipeline will run for.
        category : str, optional
            The category of the job (e.g., calibration version).
        """
        super().__init__(production, category)
        self.logger.info("Using the SimpleTestPipeline for testing")
    
    def _ensure_rundir(self):
        """
        Ensure the run directory exists.
        
        Returns
        -------
        bool
            True if rundir exists or was created, False if no rundir is configured.
        """
        if not self.production.rundir:
            return False
        Path(self.production.rundir).mkdir(parents=True, exist_ok=True)
        return True
    
    def build_dag(self, user=None, dryrun=False):
        """
        Build the DAG for this pipeline.
        
        Creates a HTCondor submit file and DAG file that will run a simple
        test job on the scheduler.
        
        Parameters
        ----------
        user : str, optional
            The user account for job submission.
        dryrun : bool, optional
            If True, only simulate the build without creating files.
            
        Returns
        -------
        None
        """
        if not dryrun:
            if self._ensure_rundir():
                # Create a simple job script that will create results
                job_script = os.path.join(self.production.rundir, "test_job.sh")
                results_file = os.path.join(self.production.rundir, "results.dat")
                with open(job_script, "w") as f:
                    f.write("#!/bin/bash\n")
                    f.write("# Simple test pipeline job\n")
                    f.write("set -e\n")
                    f.write("echo 'Test job running'\n")
                    f.write(f"echo 'Working directory: {self.production.rundir}'\n")
                    f.write("echo 'Current directory:' $(pwd)\n")
                    f.write("sleep 2\n")
                    f.write("# Create the results file with absolute path\n")
                    f.write(f"cat > {results_file} << 'EOF'\n")
                    f.write("# Test pipeline results\n")
                    f.write("test_parameter: 1.0\n")
                    f.write("test_error: 0.1\n")
                    f.write("EOF\n")
                    f.write(f"echo 'Test job complete - {results_file} created'\n")
                    f.write("ls -la\n")
                
                # Make script executable
                os.chmod(job_script, 0o755)
                
                # Create HTCondor submit file
                submit_file = os.path.join(self.production.rundir, "test_job.sub")
                with open(submit_file, "w") as f:
                    f.write("# HTCondor submit file for SimpleTestPipeline\n")
                    f.write("universe = vanilla\n")
                    f.write(f"executable = {job_script}\n")
                    f.write(f"initialdir = {self.production.rundir}\n")
                    f.write("output = test_job.out\n")
                    f.write("error = test_job.err\n")
                    f.write("log = test_job.log\n")
                    f.write("getenv = True\n")
                    f.write("queue 1\n")
                
                # Create a minimal DAG file
                dag_file = os.path.join(self.production.rundir, "test.dag")
                with open(dag_file, "w") as f:
                    f.write("# Simple test pipeline DAG\n")
                    f.write("JOB test_job test_job.sub\n")
                    
                self.logger.info(f"Built test DAG in {self.production.rundir}")
            else:
                self.logger.warning("No run directory specified, cannot build DAG")
        else:
            self.logger.info("Dry run: would build test DAG")
        
    def submit_dag(self, dryrun=False):
        """
        Submit the pipeline job to HTCondor.

        This submits the DAG file to HTCondor so the job actually runs
        on the scheduler and creates the results file.

        Parameters
        ----------
        dryrun : bool, optional
            If True, only simulate the submission without actually submitting.
            Default is False.

        Returns
        -------
        int
            The HTCondor cluster ID.
        """
        import subprocess
        import re

        if not self.production.rundir:
            self.logger.warning("No run directory specified, cannot submit job")
            return None

        # Build the DAG first
        self.build_dag(dryrun=dryrun)

        self.before_submit(dryrun=dryrun)
        
        dag_file = "test.dag"
        
        command = [
            "condor_submit_dag",
            "-batch-name",
            f"test/{self.production.event.name}/{self.production.name}",
            dag_file
        ]
        
        self.logger.info(f"Submitting DAG: {' '.join(command)}")
        
        if dryrun:
            print(f"Would run: {' '.join(command)}")
            return 12345
        else:
            # Change to run directory before submitting
            original_dir = os.getcwd()
            os.chdir(self.production.rundir)
            
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    check=True
                )
                
                self.logger.info(f"DAG submitted successfully")
                self.logger.debug(f"Output: {result.stdout}")
                
                # Extract cluster ID from output
                match = re.search(r'submitted to cluster (\d+)', result.stdout)
                if match:
                    cluster_id = int(match.group(1))
                    self.logger.info(f"Cluster ID: {cluster_id}")
                    return cluster_id
                else:
                    self.logger.warning("Could not extract cluster ID from condor_submit_dag output")
                    return None
                    
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to submit DAG: {e}")
                self.logger.error(f"stderr: {e.stderr}")
                raise
            finally:
                os.chdir(original_dir)
        
    def detect_completion(self):
        """
        Check if the pipeline has completed.
        
        This checks for the existence of a results file that would be
        created by a completed job.
        
        Returns
        -------
        bool
            True if the job has completed, False otherwise.
        """
        if not self.production.rundir:
            return False
            
        # Check for a completion marker file
        completion_file = os.path.join(self.production.rundir, "results.dat")
        return os.path.exists(completion_file)
        
    def before_submit(self, dryrun=False):
        """
        Prepare the job before submission.
        
        This creates the run directory and any necessary setup files.
        
        Parameters
        ----------
        dryrun : bool, optional
            If True, only simulate the preparation.
        """
        if not dryrun and self._ensure_rundir():
            self.logger.info(f"Prepared run directory: {self.production.rundir}")
            
    def after_completion(self):
        """
        Post-processing after job completion.
        
        This creates a simple results file and updates the status.
        """
        if self.production.rundir:
            # Create a dummy results file
            results_file = os.path.join(self.production.rundir, "results.dat")
            if not os.path.exists(results_file):
                with open(results_file, "w") as f:
                    f.write("# Test pipeline results\n")
                    f.write("test_parameter: 1.0\n")
                    f.write("test_error: 0.1\n")
                    
        super().after_completion()
        
    def samples(self, absolute=False):
        """
        Return the location of output samples.
        
        Parameters
        ----------
        absolute : bool, optional
            If True, return absolute paths.
            
        Returns
        -------
        list
            List of paths to sample files (dummy file for testing).
        """
        if not self.production.rundir:
            return []
        
        # Ensure directory exists
        self._ensure_rundir()
        
        samples_file = os.path.join(self.production.rundir, "posterior_samples.dat")
        
        # Create dummy samples file if it doesn't exist
        if not os.path.exists(samples_file):
            with open(samples_file, "w") as f:
                f.write("# parameter1 parameter2\n")
                f.write("1.0 2.0\n")
                f.write("1.1 2.1\n")
                
        if absolute:
            return [os.path.abspath(samples_file)]
        else:
            return [samples_file]
            
    def collect_assets(self):
        """
        Collect analysis assets for version control.
        
        Returns
        -------
        dict
            Dictionary of assets produced by this pipeline.
        """
        assets = {}
        if self.production.rundir:
            results = os.path.join(self.production.rundir, "results.dat")
            if os.path.exists(results):
                assets['results'] = results
        return assets
