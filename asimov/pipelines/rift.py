"""RIFT Pipeline specification."""


import os
import shutil
import glob
import subprocess
from ..pipeline import Pipeline, PipelineException, PipelineLogger
from ..ini import RunConfiguration
from asimov import config
from asimov import logging


class Rift(Pipeline):
    """
    The RIFT Pipeline.

    Parameters
    ----------
    production : :class:`asimov.Production`
       The production object.
    category : str, optional
        The category of the job.
        Defaults to "C01_offline".
    """

    STATUS = {"wait", "stuck", "stopped", "running", "finished"}

    def __init__(self, production, category=None):
        super(Rift, self).__init__(production, category)
        self.logger = logger = logging.AsimovLogger(event=production.event)
        if not production.pipeline.lower() == "rift":
            raise PipelineException
        
        if "bootstrap" in self.production.meta:
            self.bootstrap = self.production.meta
        else:
            self.bootstrap = False

    def _activate_environment(self):
        """
        Activate the python virtual environment for the pipeline.
        """
        env = config.get("rift", "environment")
        command = ["/bin/bash", "-c", "source", f"{env}/bin/activate"]

        pipe = subprocess.Popen(command, 
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        out, err = pipe.communicate()

        if err:
            self.production.status = "stuck"
            if hasattr(self.production.event, "issue_object"):
                raise PipelineException(f"The virtual environment could not be initiated.\n{command}\n{out}\n\n{err}",
                                            issue=self.production.event.issue_object,
                                            production=self.production.name)
            else:
                raise PipelineException(f"The virtual environment could not be initiated.\n{command}\n{out}\n\n{err}",
                                        production=self.production.name)
        

    def _convert_psd(self, ascii_format):
        """
        Convert an ascii format PSD to XML.

        Parameters
        ----------
        ascii_format : str
           The location of the ascii format file.
        """
        self._activate_environment()
        
        
                   
        command = ["convert_psd_ascii2xml",
                   "--fname-psd-ascii", f"{ascii_format}",
                   "--conventional-postfix",
                   "--ifo",  f"{ifo}"]
            
        pipe = subprocess.Popen(command, 
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        out, err = pipe.communicate()
        if err:
            self.production.status = "stuck"
            if hasattr(self.production.event, "issue_object"):
                raise PipelineException(f"An XML format PSD could not be created.\n{command}\n{out}\n\n{err}",
                                            issue=self.production.event.issue_object,
                                            production=self.production.name)
            else:
                raise PipelineException(f"An XML format PSD could not be created.\n{command}\n{out}\n\n{err}",
                                        production=self.production.name)
            
    def before_submit(self):
        """
        Convert the text-based PSD to an XML psd if the xml doesn't exist already.
        """
        category = "C01_offline" # Fix me: this shouldn't be hard-coded
        if len(self.production.get_psds("xml"))==0:
            for ifo in self.production.meta['interferometers']:
                os.chdir(f"{event.repository.directory}/{category}")
                os.mkdir(f"psds")
                os.chdir("psds")
                self._convert_psd(self.production['psds'][ifo])
                event.repository.repo.git.add(f"{ifo.upper()}-psd.xml")
            event.repository.repo.git.commit("Added converted xml psds")
            event.repository.repo.git.push()
            

    def build_dag(self, user=None):
        """
        Construct a DAG file in order to submit a production to the
        condor scheduler using util_RIFT_pseudo_pipe.py

        Parameters
        ----------
        production : str
           The production name.
        user : str
           The user accounting tag which should be used to run the job.

        Raises
        ------
        PipelineException
           Raised if the construction of the DAG fails.

        Notes
        -----

        In order to assemble the pipeline the RIFT runner requires additional
        production metadata: at least the l_max value.
        An example RIFT production specification would then look something like:
        
        ::
           
           - Prod3:
               rundir: tests/tmp/s000000xx/Prod3
               pipeline: rift
               approximant: IMRPhenomPv3
               lmax: 2
               cip jobs: 5 # This is optional, and will default to 3
               bootstrap: Prod1
               bootstrap fmin: 20
               needs: Prod1
               comment: RIFT production run.
               status: wait

        
        """

        self._activate_environment()
        
        os.chdir(os.path.join(self.production.event.repository.directory,
                              self.category))
        gps_file = self.production.get_timefile()
        coinc_file = self.production.get_coincfile()
        
        ini = self.production.get_configuration()

        if not user:
            if self.production.get_meta("user"):
                user = self.production.get_meta("user")
        else:
            user = ini._get_user()
            self.production.set_meta("user", user)

        ini.update_accounting(user)

        try:
            calibration = config.get("general", "calibration")
        except:
            calibration = "C01"

        approximant = self.production.meta['approximant']

        ini.save()

        if self.production.rundir:
            rundir = self.production.rundir
        else:
            rundir = os.path.join(os.path.expanduser("~"),
                                  self.production.event.name,
                                  self.production.name)
            self.production.rundir = rundir

        # TODO lmax needs to be determined for each waveform (it's the maximum harmonic order)
        # for now it will be fetched from the production metadata
        lmax = self.production.meta['lmax']
        
        if "cip jobs" in self.production.meta:
            cip = self.production.meta['cip jobs']
        else:
            cip = 3
            
        
        command = [os.path.join(config.get("pipelines", "environment"), "bin", "util_RIFT_pseudo_pipe.py"),
                   "--use-coinc", os.path.join(self.production.event.repository.directory, "C01_offline",
                                               coinc_file),
                   "--l-max", f"{lmax}",
                   "--calibration", f"{calibration}",
                   "--add-extrinsic",
                   #"--archive-pesummary-label", f"{calibration}:{approximant}",
                   #"--archive-pesummary-event-label", f"{calibration}:{approximant}",
                   "--cip-explode-jobs", str(cip),
                   "--use-rundir", self.production.rundir,
                   "--use-ini", os.path.join(self.production.event.repository.directory, "C01_offline",  ini.ini_loc)
        ]
           
        # Placeholder LI grid bootstrapping; conditional on it existing and location specification
        
        if self.bootstrap:

            # Find the appropriate production in the ledger
            productions = self.production.event.productions
            bootstrap_production = [production for production in productions if production.name == self.bootstrap]

            if len(bootstrap_production) == 0:
                raise PipelineException(f"Unable to find the bootstrapping production for {self.production.name}.",
                                        issue=self.production.event.issue_object,
                                        production=self.production.name)
            else:
                bootstrap_production = bootstrap_production[0]
            
            shutil.copy(f"{bootstrap_production.rundir}/posterior_samples.dat", f"{self.production.rundir}/LI_samples.dat")
            convcmd = ["convert_output_format_inferance2ile",
                       "--posterior-samples", f"{self.production.rundir}/LI_samples.dat",
                       "--output-xml", f"bootstrap-grid.xml.gz",
                       "--fmin", f"{self.production.meta['bootstrap fmin']}"] 
            pipe = subprocess.Popen(convcmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            out,err = pipe.communicate()
            if err:
                self.production.status = "stuck"
                if hasattr(self.production.event, "issue_object"):
                    raise PipelineException(f"Unable to convert LI posterior into ILE starting grid.\n{convcmd}\n{out}\n\n{err}",
                                            issue=self.production.event.issue_object,
                                            production=self.production.name)
                else:
                    raise PipelineException(f"Unable to convert LI posterior into ILE starting grid.\n{convcmd}\n{out}\n\n{err}",
                                        production=self.production.name)
            else:
                command += ["--manual-initial-grid", os.path.join(self.production.rundir, "bootstrap-grid.xml.gz")]
        
        self.logger.info(command, production = self.production)
        pipe = subprocess.Popen(command, 
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        out, err = pipe.communicate()
        if err or "Successfully created DAG file." not in str(out):
            self.production.status = "stuck"
            if hasattr(self.production.event, "issue_object"):
                self.logger.info(out, production = self.production)
                self.logger.error(err, production = self.production)
                raise PipelineException(f"DAG file could not be created.\n{command}\n{out}\n\n{err}",
                                            issue=self.production.event.issue_object,
                                            production=self.production.name)
            else:
                self.logger.info(out, production = self.production)
                self.logger.error(err, production = self.production)
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
    
    def submit_dag(self):
         """
        Submit a DAG file to the condor cluster (using the RIFT dag name). This is an overwrite of the near identical parent function submit_dag()

        Parameters
        ----------
        category : str, optional
           The category of the job.
           Defaults to "C01_offline".
        production : str
           The production name.

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
        """

        os.chdir(self.production.rundir)

        self.before_submit()
        
        try:
            command = ["condor_submit_dag",
                                   os.path.join(self.production.rundir, "marginalize_intrinsic_parameters_BasicIterationWorkflow.dag")]
            dagman = subprocess.Popen(command,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT)
        except FileNotFoundError as error:
            raise PipelineException("It looks like condor isn't installed on this system.\n"
                                    f"""I wanted to run {" ".join(command)}.""")

        stdout, stderr = dagman.communicate()

        if "submitted to cluster" in str(stdout):
            cluster = re.search("submitted to cluster ([\d]+)", str(stdout)).groups()[0]
            self.production.status = "running"
            self.production.job_id = cluster
            return cluster, PipelineLogger(stdout)
        else:
            raise PipelineException(f"The DAG file could not be submitted.\n\n{stdout}\n\n{stderr}",
                                    issue=self.production.event.issue_object,
                                    production=self.production.name)

