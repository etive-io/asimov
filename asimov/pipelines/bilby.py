"""Bilby Pipeline specification."""

import configparser
import glob
import os
import re
import shutil
import subprocess
import time

from .. import config

from ..pipeline import Pipeline, PipelineException, PipelineLogger
from .. import auth
from .pesummary import PESummary


class Bilby(Pipeline):
    """
    The Bilby Pipeline.

    Parameters
    ----------
    production : :class:`asimov.Production`
       The production object.
    category : str, optional
        The category of the job.
        Defaults to "C01_offline".
    """

    name = "bilby"
    STATUS = {"wait", "stuck", "stopped", "running", "finished"}

    def __init__(self, production, category=None):
        super(Bilby, self).__init__(production, category)
        self.logger.warning(
            "The Bilby interface built into asimov will be removed "
            "in v0.7 of asimov, and replaced with an integration from an "
            "external package."
        )
        self.logger.info("Using the bilby pipeline")

        if not production.pipeline.lower() == "bilby":
            raise PipelineException("Pipeline mismatch")

    def detect_completion(self):
        """
        Check for the production of the posterior file to signal that the job has completed.
        """
        self.logger.info("Checking if the bilby job has completed")
        results_dir = glob.glob(f"{self.production.rundir}/result")
        if len(results_dir) > 0:  # dynesty_merge_result.json
            results_files = glob.glob(
                os.path.join(results_dir[0], "*merge*_result.hdf5")
            )
            results_files += glob.glob(
                os.path.join(results_dir[0], "*merge*_result.json")
            )
            self.logger.debug(f"results files {results_files}")
            if len(results_files) > 0:
                self.logger.info("Results files found, the job is finished.")
                return True
            else:
                self.logger.info("No results files found.")
                return False
        else:
            self.logger.info("No results directory found")
            return False

    @auth.refresh_scitoken
    def before_submit(self):
        """
        Pre-submit hook.
        """
        pass

    @auth.refresh_scitoken
    def build_dag(self, psds=None, user=None, clobber_psd=False, dryrun=False):
        """
        Construct a DAG file in order to submit a production to the
        condor scheduler using bilby_pipe.

        Parameters
        ----------
        production : str
           The production name.
        psds : dict, optional
           The PSDs which should be used for this DAG. If no PSDs are
           provided the PSD files specified in the ini file will be used
           instead.
        user : str
           The user accounting tag which should be used to run the job.
        dryrun: bool
           If set to true the commands will not be run, but will be printed to standard output. Defaults to False.

        Raises
        ------
        PipelineException
           Raised if the construction of the DAG fails.
        """

        cwd = os.getcwd()

        self.logger.info(f"Working in {cwd}")

        if self.production.event.repository:
            ini = self.production.event.repository.find_prods(
                self.production.name, self.category
            )[0]
            ini = os.path.join(cwd, ini)
        else:
            ini = f"{self.production.name}.ini"

        if self.production.rundir:
            rundir = self.production.rundir
        else:
            rundir = os.path.join(
                os.path.expanduser("~"),
                self.production.event.name,
                self.production.name,
            )
            self.production.rundir = rundir

        if "job label" in self.production.meta:
            job_label = self.production.meta["job label"]
        else:
            job_label = self.production.name

        default_executable = os.path.join(
            config.get("pipelines", "environment"), "bin", "bilby_pipe"
        )
        executable = self.production.meta.get("executable", default_executable)
        if (executable := shutil.which(executable)) is not None:
            pass
        elif (executable := shutil.which("bilby_pipe")) is not None:
            pass
        else:
            raise PipelineException(
                "Cannot find bilby_pipe executable",
                production=self.production.name,
            )
        command = [
            executable,
            ini,
            "--label",
            job_label,
            "--outdir",
            f"{os.path.abspath(self.production.rundir)}",
        ]

        if "accounting group" in self.production.meta:
            command += [
                "--accounting",
                f"{self.production.meta['scheduler']['accounting group']}",
            ]
        else:
            self.logger.warning(
                "This Bilby Job does not supply any accounting"
                " information, which may prevent it running"
                " on some clusters."
            )

        if dryrun:
            print(" ".join(command))
        else:
            self.logger.info(" ".join(command))
            pipe = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            )
            out, err = pipe.communicate()
            self.logger.info(out)

            if err or "DAG generation complete, to submit jobs" not in str(out):
                self.production.status = "stuck"
                self.logger.error(err)
                raise PipelineException(
                    f"DAG file could not be created.\n{command}\n{out}\n\n{err}",
                    production=self.production.name,
                )
            else:
                time.sleep(10)
                return PipelineLogger(message=out, production=self.production.name)

    def submit_dag(self, dryrun=False):
        """
        Submit a DAG file to the scheduler.

        Parameters
        ----------
        dryrun : bool
           If set to true the DAG will not be submitted,
           but all commands will be printed to standard
           output instead. Defaults to False.

        Returns
        -------
        int
           The cluster ID assigned to the running DAG file.
        PipelineLogger
           The pipeline logger message.

        Raises
        ------
        PipelineException
           This will be raised if the pipeline fails to submit the job.

        Notes
        -----
        This overloads the default submission routine, as bilby seems to store
        its DAG files in a different location.
        
        This method now uses the scheduler API for DAG submission, making it
        scheduler-agnostic and easier to support multiple scheduling systems.
        """

        cwd = os.getcwd()
        self.logger.info(f"Working in {cwd}")

        self.before_submit()

        try:
            if "job label" in self.production.meta:
                job_label = self.production.meta["job label"]
            else:
                job_label = self.production.name
            
            dag_filename = f"dag_{job_label}.submit"
            dag_path = os.path.join(self.production.rundir, "submit", dag_filename)
            batch_name = f"bilby/{self.production.event.name}/{self.production.name}"

            if dryrun:
                print(f"Would submit DAG: {dag_path} with batch name: {batch_name}")
            else:
                self.logger.info(f"Working in {os.getcwd()}")
                self.logger.info(f"Submitting DAG: {dag_path}")

                try:
                    # Use the scheduler API to submit the DAG
                    cluster_id = self.scheduler.submit_dag(
                        dag_file=dag_path,
                        batch_name=batch_name
                    )
                    
                    self.logger.info(
                        f"Submitted successfully. Running with job id {int(cluster_id)}"
                    )
                    self.production.status = "running"
                    self.production.job_id = int(cluster_id)
                    
                    # Create a mock stdout message for compatibility
                    stdout_msg = f"DAG submitted to cluster {cluster_id}"
                    return cluster_id, PipelineLogger(stdout_msg)
                    
                except FileNotFoundError as error:
                    self.logger.error(f"DAG file not found: {dag_path}")
                    raise PipelineException(
                        f"The DAG file could not be found at {dag_path}.",
                    ) from error
                except RuntimeError as error:
                    self.logger.error("Could not submit the job to the scheduler")
                    self.logger.exception(error)
                    raise PipelineException(
                        "The DAG file could not be submitted.",
                    ) from error

        except FileNotFoundError as error:
            self.logger.exception(error)
            raise PipelineException(
                "It looks like the scheduler isn't properly configured.\n"
                f"Failed to submit DAG file: {dag_path}"
            ) from error

    def collect_assets(self):
        """
        Gather all of the results assets for this job.
        """
        return {
            "samples": self.samples(),
            "config": self.production.event.repository.find_prods(
                self.production.name, self.category
            )[0],
        }

    def samples(self, absolute=False):
        """
        Collect the combined samples file for PESummary.
        """

        if absolute:
            rundir = os.path.abspath(self.production.rundir)
        else:
            rundir = self.production.rundir
        self.logger.info(f"Rundir for samples: {rundir}")
        return glob.glob(
            os.path.join(rundir, "result", "*_merge*_result.hdf5")
        ) + glob.glob(os.path.join(rundir, "result", "*_merge*_result.json"))

    def after_completion(self):
        post_pipeline = PESummary(production=self.production)
        self.logger.info("Job has completed. Running PE Summary.")
        cluster = post_pipeline.submit_dag()
        self.production.meta["job id"] = int(cluster)
        self.production.status = "processing"
        self.production.event.update_data()

    def collect_logs(self):
        """
        Collect all of the log files which have been produced by this production and
        return their contents as a dictionary.
        """
        logs = glob.glob(f"{self.production.rundir}/submit/*.err") + glob.glob(
            f"{self.production.rundir}/log*/*.err"
        )
        logs += glob.glob(f"{self.production.rundir}/*/*.out")
        messages = {}
        for log in logs:
            try:
                with open(log, "r") as log_f:
                    message = log_f.read()
                    message = message.split("\n")
                    messages[log.split("/")[-1]] = "\n".join(message[-100:])
            except FileNotFoundError:
                messages[log.split("/")[-1]] = (
                    "There was a problem opening this log file."
                )
        return messages

    def check_progress(self):
        """
        Check the convergence progress of a job.
        """
        logs = glob.glob(f"{self.production.rundir}/log_data_analysis/*.out")
        messages = {}
        for log in logs:
            try:
                with open(log, "r") as log_f:
                    message = log_f.read()
                    message = message.split("\n")[-1]
                    p = re.compile(r"([\d]+)it")
                    iterations = p.search(message)
                    p = re.compile(r"dlogz:([\d]*\.[\d]*)")
                    dlogz = p.search(message)
                    if iterations:
                        messages[log.split("/")[-1]] = (
                            iterations.group(),
                            dlogz.group(),
                        )
            except FileNotFoundError:
                messages[log.split("/")[-1]] = (
                    "There was a problem opening this log file."
                )
        return messages

    @classmethod
    def read_ini(cls, filepath):
        """
        Read and parse a bilby configuration file.

        Note that bilby configurations are property files and not compliant ini configs.

        Parameters
        ----------
        filepath: str
           The path to the ini file.
        """

        with open(filepath, "r") as f:
            file_content = "[root]\n" + f.read()

        config_parser = configparser.RawConfigParser()
        config_parser.read_string(file_content)

        return config_parser

    def html(self):
        """Return the HTML representation of this pipeline."""
        pages_dir = os.path.join(
            self.production.event.name, self.production.name, "pesummary"
        )
        out = ""
        if self.production.status in {"uploaded"}:
            out += """<div class="asimov-pipeline">"""
            out += f"""<p><a href="{pages_dir}/home.html">Summary Pages</a></p>"""
            out += f"""<img height=200 src="{pages_dir}/plots/{self.production.name}_psd_plot.png"</src>"""
            out += f"""<img height=200 src="{pages_dir}/plots/{self.production.name}_waveform_time_domain.png"</src>"""

            out += """</div>"""

        return out

    def resurrect(self):
        """
        Attempt to ressurrect a failed job.
        """
        try:
            count = self.production.meta["resurrections"]
        except KeyError:
            count = 0
        if (count < 5) and (
            len(glob.glob(os.path.join(self.production.rundir, "submit", "*.rescue*")))
            > 0
        ):
            count += 1
            self.submit_dag()
