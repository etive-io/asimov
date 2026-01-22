"""
Minimal testing pipeline for ProjectAnalysis.

This pipeline is designed to test asimov's ProjectAnalysis infrastructure,
which operates across multiple events/subjects. It provides a minimal
implementation ideal for testing and as a template for population analyses.
"""

import os

from pathlib import Path

from ...pipeline import Pipeline


class ProjectTestPipeline(Pipeline):
    """
    A minimal testing pipeline for ProjectAnalysis.
    
    This pipeline implements the minimum required functionality for testing
    asimov's ProjectAnalysis infrastructure. ProjectAnalyses operate across
    multiple subjects (events), making them suitable for population analyses,
    catalog studies, or any analysis requiring data from multiple events.
    
    This pipeline serves two purposes:
    1. Testing asimov's ProjectAnalysis infrastructure
    2. Providing a template for developers creating population or catalog
       analysis pipelines
    
    Parameters
    ----------
    production : :class:`asimov.analysis.ProjectAnalysis`
        The project analysis object.
    category : str, optional
        The category of the job.
        
    Examples
    --------
    To use this pipeline in a ledger configuration:
    
    .. code-block:: yaml
    
        kind: project_analysis
        name: test-population
        pipeline: projecttestpipeline
        status: ready
        subjects:
          - Event1
          - Event2
        analyses:
          - status:finished
        
    Notes
    -----
    This pipeline creates a combined output file that references all
    subjects and their analyses, simulating a population study.
    """
    
    name = "ProjectTestPipeline"
    STATUS = {"wait", "stuck", "stopped", "running", "finished"}
    
    def __init__(self, production, category=None):
        """
        Initialize the ProjectTestPipeline.
        
        Parameters
        ----------
        production : :class:`asimov.analysis.ProjectAnalysis`
            The project analysis object this pipeline will run for.
        category : str, optional
            The category of the job.
        """
        super().__init__(production, category)
        self.logger.info("Using the ProjectTestPipeline for testing")
    
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
        Build the DAG for this project analysis pipeline.
        
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
                job_script = os.path.join(self.production.rundir, "test_project_job.sh")
                results_file = os.path.join(self.production.rundir, "population_results.dat")
                with open(job_script, "w") as f:
                    f.write("#!/bin/bash\n")
                    f.write("# Project analysis test pipeline job\n")
                    f.write("set -e\n")
                    f.write("echo 'Processing analyses across multiple subjects'\n")
                    f.write(f"echo 'Working directory: {self.production.rundir}'\n")
                    f.write("echo 'Current directory:' $(pwd)\n")
                    f.write("sleep 2\n")
                    f.write("# Create the results file with absolute path\n")
                    f.write(f"cat > {results_file} << 'EOF'\n")
                    f.write("# Project analysis test pipeline results\n")
                    f.write("# Population/catalog analysis\n")
                    f.write("population_rate: 10.5\n")
                    f.write("rate_uncertainty: 2.3\n")
                    f.write("selection_effects: 0.85\n")
                    f.write("EOF\n")
                    f.write(f"echo 'Project analysis complete - {results_file} created'\n")
                    f.write("ls -la\n")
                
                # Make script executable
                os.chmod(job_script, 0o755)
                
                # Create HTCondor submit file
                submit_file = os.path.join(self.production.rundir, "test_project_job.sub")
                with open(submit_file, "w") as f:
                    f.write("# HTCondor submit file for ProjectTestPipeline\n")
                    f.write("universe = vanilla\n")
                    f.write(f"executable = {job_script}\n")
                    f.write(f"initialdir = {self.production.rundir}\n")
                    f.write("output = test_project_job.out\n")
                    f.write("error = test_project_job.err\n")
                    f.write("log = test_project_job.log\n")
                    f.write("getenv = True\n")
                    f.write("queue 1\n")
                
                # Create a minimal DAG file
                dag_file = os.path.join(self.production.rundir, "test_project.dag")
                with open(dag_file, "w") as f:
                    f.write("# Project test pipeline DAG\n")
                    f.write("JOB test_project_job test_project_job.sub\n")
                    
                self.logger.info(f"Built project test DAG in {self.production.rundir}")
            else:
                self.logger.warning("No run directory specified, cannot build DAG")
        else:
            self.logger.info("Dry run: would build project test DAG")
        
    def submit_dag(self, dryrun=False):
        """
        Submit the pipeline job to HTCondor.

        This submits the DAG file to HTCondor so the job actually runs
        on the scheduler and creates the results file.

        Parameters
        ----------
        dryrun : bool, optional
            If True, only simulate the submission.

        Returns
        -------
        int
            The HTCondor cluster ID.
        """
        import subprocess
        import re

        if not self.production.rundir:
            self.logger.warning("No run directory specified")
            return None

        # Build the DAG first
        self.build_dag(dryrun=dryrun)

        self.before_submit(dryrun=dryrun)
        
        dag_file = "test_project.dag"
        
        command = [
            "condor_submit_dag",
            "-batch-name",
            f"test-project/{self.production.name}",
            dag_file
        ]
        
        self.logger.info(f"Submitting project DAG: {' '.join(command)}")
        
        if dryrun:
            print(f"Would run: {' '.join(command)}")
            return 34567
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
                
                self.logger.info(f"Project DAG submitted successfully")
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
                self.logger.error(f"Failed to submit project DAG: {e}")
                self.logger.error(f"stderr: {e.stderr}")
                raise
            finally:
                os.chdir(original_dir)
        
    def detect_completion(self):
        """
        Check if the project analysis has completed.
        
        Returns
        -------
        bool
            True if the job has completed, False otherwise.
        """
        if not self.production.rundir:
            return False
            
        completion_file = os.path.join(self.production.rundir, "population_results.dat")
        return os.path.exists(completion_file)
        
    def before_submit(self, dryrun=False):
        """
        Prepare the job before submission.
        
        This checks that required subjects and analyses are available
        and creates the run directory.
        
        Parameters
        ----------
        dryrun : bool, optional
            If True, only simulate the preparation.
        """
        if not dryrun and self._ensure_rundir():
            # Log information about subjects and analyses
            if hasattr(self.production, '_subjects'):
                self.logger.info(
                    f"Project analysis across {len(self.production._subjects)} subjects"
                )
                for subject in self.production._subjects:
                    self.logger.info(f"  - Subject: {subject}")
                    
            if hasattr(self.production, 'analyses'):
                self.logger.info(
                    f"Combining {len(self.production.analyses)} total analyses"
                )
                    
            self.logger.info(f"Prepared run directory: {self.production.rundir}")
            
    def after_completion(self):
        """
        Post-processing after job completion.
        
        This creates a population/catalog results file referencing all
        input subjects and analyses.
        """
        if self.production.rundir:
            # Create a population results file
            results_file = os.path.join(self.production.rundir, "population_results.dat")
            if not os.path.exists(results_file):
                with open(results_file, "w") as f:
                    f.write("# Project analysis test pipeline results\n")
                    f.write("# Population/catalog analysis\n")
                    
                    if hasattr(self.production, '_subjects'):
                        f.write(f"# Number of subjects: {len(self.production._subjects)}\n")
                        for i, subject in enumerate(self.production._subjects):
                            f.write(f"# Subject {i+1}: {subject}\n")
                    
                    if hasattr(self.production, 'analyses'):
                        f.write(f"# Total analyses: {len(self.production.analyses)}\n")
                    
                    f.write("population_rate: 10.5\n")
                    f.write("rate_uncertainty: 2.3\n")
                    f.write("selection_effects: 0.85\n")
                    
        super().after_completion()
        
    def samples(self, absolute=False):
        """
        Return the location of population samples.
        
        Parameters
        ----------
        absolute : bool, optional
            If True, return absolute paths.
            
        Returns
        -------
        list
            List of paths to population sample files.
        """
        if not self.production.rundir:
            return []
        
        # Ensure directory exists
        self._ensure_rundir()
        
        samples_file = os.path.join(self.production.rundir, "population_samples.dat")
        
        # Create dummy population samples file
        if not os.path.exists(samples_file):
            with open(samples_file, "w") as f:
                f.write("# rate mass_distribution\n")
                f.write("10.5 1.0\n")
                f.write("11.2 1.1\n")
                f.write("9.8 0.9\n")
                
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
            results = os.path.join(self.production.rundir, "population_results.dat")
            if os.path.exists(results):
                assets['population_results'] = results
        return assets
