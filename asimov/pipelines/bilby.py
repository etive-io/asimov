"""Bilby Pipeline specification."""

import os
import glob
import os
import re
import subprocess

from asimov.utils import update

from ..pipeline import Pipeline, PipelineException, PipelineLogger
from ..ini import RunConfiguration
from .. import config, logger
import re
import numpy as np

from liquid import Liquid
import htcondor

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
    name = "Bilby"
    STATUS = {"wait", "stuck", "stopped", "running", "finished"}

    def __init__(self, production, category=None):
        super(Bilby, self).__init__(production, category)
        self.logger = logger
        if not production.pipeline.lower() == "bilby":
            raise PipelineException

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

    def before_submit(self):
        """
        Pre-submit hook.
        """
        self.logger.info("Running the before_submit hook")
        sub_files = glob.glob(f"{self.production.rundir}/submit/*.submit")
        for sub_file in sub_files:
            if "dag" in sub_file:
                continue
            with open(sub_file, "r") as f_handle:
                original = f_handle.read()
            with open(sub_file, "w") as f_handle:
                self.logger.info(f"Adding preserve_relative_paths to {sub_file}")
                f_handle.write("preserve_relative_paths = True\n" + original)

    def _determine_prior(self):
        """
        Determine the correct choice of prior file for this production.
        """

        self.logger.info("Determining the prior file for this production")

        if "prior file" in self.production.meta:
            self.logger.info("A prior file has already been specified.")
            self.logger.info(f"{self.production.meta['prior file']}")
            return self.production.meta["prior file"]
        else:
            duration = int(self.production.meta['data']['segment length'])
            scale_factor = 1 # Check this
            template = None

            prior_parameters = {}
            
            if "event type" in self.production.meta:
                event_type = self.production.meta["event type"].lower()
            else:
                event_type = "bbh"
                self.production.meta["event type"] = event_type

                if self.production.event.issue_object:
                    self.production.event.issue_object.update_data()

            if template is None:
                template_filename = f"{event_type}.prior.template"
                self.logger.info(
                    f"[bilby] Constructing a prior using {event_type}.prior.template."
                )
                try:
                    template = os.path.join(
                        config.get("bilby", "priors"), template_filename
                    )
                except (configparser.NoOptionError, configparser.NoSectionError):
                    from pkg_resources import resource_filename

            #with open(template, "r") as old_prior:
            #    prior_string = old_prior.read().format(**prior_parameters)

            priors = {}
            priors = update(priors, self.production.event.ledger.data['priors'])
            priors = update(priors, self.production.event.meta['priors'])
            priors = update(priors, self.production.meta['priors'])
            
            liq = Liquid(template)
            rendered = liq.render(priors=priors, config=config)
            
            prior_name = f"{self.production.name}.prior"
            prior_file = os.path.join(os.getcwd(), prior_name)
            self.logger.info(f"Saving the new prior file as {prior_file}")
            with open(prior_file, "w") as new_prior:
                new_prior.write(rendered)
                
            repo = self.production.event.repository
            try:
                repo.add_file(prior_file, os.path.join("C01_offline", prior_name))
                os.remove(prior_file)
            except:
                pass
            return os.path.join(self.production.event.repository.directory, "C01_offline", prior_name)

        
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

        self.logger.info(f"[bilby] Working in {cwd}")

        if self.production.event.repository:
            ini = self.production.event.repository.find_prods(
                self.production.name,
                self.category)[0]
            ini = os.path.join(cwd, ini)
            gps_file = self.production.get_timefile()
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

        prior_file = self._determine_prior()
        
        command = [os.path.join(config.get("pipelines", "environment"), "bin", "bilby_pipe"),
                   ini,
                   "--label", job_label,
                   "--outdir", f"{cwd}/{self.production.rundir}",
                   "--accounting", f"{self.production.meta['scheduler']['accounting group']}"
        ]

        if dryrun:
            print(" ".join(command))
        else:
            self.logger.info(" ".join(command))
            pipe = subprocess.Popen(command, 
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT)
            out, err = pipe.communicate()
            self.logger.info(out)
            self.logger.error(err)
            #os.chdir(cwd)
            if err or "DAG generation complete, to submit jobs" not in str(out):
                self.production.status = "stuck"
                if hasattr(self.production.event, "issue_object"):
                    raise PipelineException(f"DAG file could not be created.\n{command}\n{out}\n\n{err}",
                                                issue=self.production.event.issue_object,
                                                production=self.production.name)
                else:
                    raise PipelineException(f"DAG file could not be created.\n{command}\n{out}\n\n{err}",
                                            production=self.production.name)
            else:
                if hasattr(self.production.event, "issue_object"):
                    return PipelineLogger(message=out,
                                          issue=self.production.event.issue_object,
                                          production=self.production.name)
                else:
                    return PipelineLogger(message=out,
                                          production=self.production.name)


    def submit_dag(self, dryrun=False):
        """
        Submit a DAG file to the condor cluster.

        Parameters
        ----------
        dryrun : bool
           If set to true the DAG will not be submitted, but all commands will be printed to standard output instead. Defaults to False.

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
        its DAG files in a different location
        """
        #os.chdir(self.production.event.meta['working directory'])   
        #os.chdir(os.path.join(self.production.event.repository.directory,
        #                      self.category))

        cwd = os.getcwd()
        self.logger.info(f"Working in {cwd}")

        self.before_submit()

        try:
            # to do: Check that this is the correct name of the output DAG file for billby (it
            # probably isn't)
            if "job label" in self.production.meta:
                job_label = self.production.meta["job label"]
            else:
                job_label = self.production.name
            dag_filename = f"dag_{job_label}.submit"
            command = [
                #"ssh", f"{config.get('scheduler', 'server')}",
                "condor_submit_dag",
                       "-batch-name", f"bilby/{self.production.event.name}/{self.production.name}",
                                   os.path.join(self.production.rundir, "submit", dag_filename)]

            if dryrun:
                print(" ".join(command))
            else:
                dagman = subprocess.Popen(command,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT)

                stdout, stderr = dagman.communicate()

                if "submitted to cluster" in str(stdout):
                    cluster = re.search("submitted to cluster ([\d]+)", str(stdout)).groups()[0]
                    self.production.status = "running"
                    self.production.job_id = int(cluster)
                    return cluster, PipelineLogger(stdout)
                else:
                    raise PipelineException(f"The DAG file could not be submitted.\n\n{stdout}\n\n{stderr}",
                                            issue=self.production.event.issue_object,
                                            production=self.production.name)
        except FileNotFoundError as error:
            raise PipelineException("It looks like condor isn't installed on this system.\n"
                                    f"""I wanted to run {" ".join(command)}.""")

        
    def collect_assets(self):
        """
        Gather all of the results assets for this job.
        """
        return {"samples": self.samples()}

    def samples(self, absolute=False):
        """
        Collect the combined samples file for PESummary.
        """
        return glob.glob(os.path.join(self.production.rundir, "result", "*_merge*_result.*"))
        
    def after_completion(self):
        post_pipeline = PESummaryPipeline(production=self.production)
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
                messages[
                    log.split("/")[-1]
                ] = "There was a problem opening this log file."
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
                messages[
                    log.split("/")[-1]
                ] = "There was a problem opening this log file."
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
        pages_dir = os.path.join(self.production.event.name, self.production.name)
        out = ""
        out += """<div class="asimov-pipeline bilby">"""
        out += """<ul>"""
        out += f"""<li><a href="{pages_dir}/overview.html">Overview pages</a></li>"""
        if self.production.status in {"finished", "uploaded"}:
            if self.production.status == "uploaded":
                out += f"""<li><a href="{pages_dir}/pesummary/home.html">Summary pages</a></li>"""
        out += """</ul>"""

        image_card = """<div class="card" style="width: 18rem;">
<img class="card-img-top" src="{0}" alt="Card image cap">
  <div class="card-body">
    <p class="card-text">{1}</p>
  </div>
</div>
        """

        plots = [
            [
                f"{pages_dir}/pesummary/plots/{self.production.name}_1d_posterior_luminosity_distance.png",
                "luminosity distance",
            ],
            [
                f"{pages_dir}/pesummary/plots/{self.production.name}_skymap.png",
                "skymap",
            ],
        ]

        out += """<div class="card-group">"""
        for plot in plots:
            if self.production.status in {"finished", "uploaded"}:
                out += image_card.format(plot[0], plot[1])

        out += """</div>"""  # Closes card-group
        out += """</div>"""  # Closes the bilby div
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
