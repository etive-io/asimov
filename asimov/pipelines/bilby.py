"""Bilby Pipeline specification."""

import configparser
import glob
import os
import re
import shutil
import subprocess
import time

from typing import Dict, Any

from .. import config

from ..pipeline import Pipeline, PipelineException, PipelineLogger
from .. import auth
from .pesummary import PESummary
from ..priors import PriorInterface


class BilbyPriorInterface(PriorInterface):
    """
    Prior interface for the Bilby pipeline.
    
    Converts asimov prior specifications into bilby prior_dict format.
    """
    
    def convert(self) -> Dict[str, Any]:
        """
        Convert asimov priors to bilby prior_dict format.
        
        Returns
        -------
        dict
            Dictionary suitable for bilby's prior-dict config option
        """
        if self.prior_dict is None:
            return {}
        
        # Return the dictionary representation
        # The actual rendering to bilby format happens in the template
        return self.prior_dict.to_dict()
    
    def get_default_prior(self) -> str:
        """
        Get the default prior set for bilby.
        
        Returns
        -------
        str
            The default prior class name (e.g., "BBHPriorDict")
        """
        if self.prior_dict is None or self.prior_dict.default is None:
            return "BBHPriorDict"
        return self.prior_dict.default
    
    def to_prior_dict_string(self) -> str:
        """
        Generate a string representation of the prior_dict for bilby.
        
        This method creates a complete Python dictionary string that can be
        directly inserted into the bilby configuration file, providing
        maximum flexibility for prior specifications.
        
        Returns
        -------
        str
            String representation of the prior dictionary for bilby
        """
        if self.prior_dict is None:
            # Return default priors if none specified
            return self._get_default_prior_dict_string()
        
        priors = self.prior_dict.to_dict()
        prior_lines = []
        
        # Process each prior specification
        for param_name, param_spec in priors.items():
            if param_name == 'default':
                # Skip the default key as it's handled separately
                continue
            
            if not isinstance(param_spec, dict):
                # Skip non-dict values
                continue
            
            # Generate the prior string for this parameter
            prior_str = self._format_prior(param_name, param_spec)
            if prior_str:
                prior_lines.append(prior_str)
        
        # Add default fixed priors for sky location and polarization,
        # but only if they have not been specified by the user.
        default_sky_priors = {
            "dec": "dec = Cosine(name='dec')",
            "ra": "ra = Uniform(name='ra', minimum=0, maximum=2 * np.pi, boundary='periodic')",
            "theta_jn": "theta_jn = Sine(name='theta_jn')",
            "psi": "psi = Uniform(name='psi', minimum=0, maximum=np.pi, boundary='periodic')",
            "phase": "phase = Uniform(name='phase', minimum=0, maximum=2 * np.pi, boundary='periodic')",
        }

        # Determine which parameters have been explicitly specified in the prior dict
        specified_params = {name for name in priors.keys() if name != "default"}

        # Only append defaults for parameters that are not explicitly specified
        for param_name, prior_str in default_sky_priors.items():
            if param_name not in specified_params:
                prior_lines.append(prior_str)
        
        # Join all lines with proper indentation
        return "{\n   " + ",\n   ".join(prior_lines) + "}"
    
    def _format_prior(self, param_name: str, param_spec: Dict[str, Any]) -> str:
        """
        Format a single prior specification as a string.
        
        Parameters
        ----------
        param_name : str
            The parameter name
        param_spec : dict
            The prior specification
            
        Returns
        -------
        str
            Formatted prior string
        """
        # Map parameter names to bilby parameter names
        name_map = {
            'chirp mass': 'chirp_mass',
            'mass ratio': 'mass_ratio',
            'total mass': 'total_mass',
            'mass 1': 'mass_1',
            'mass 2': 'mass_2',
            'spin 1': 'a_1',
            'spin 2': 'a_2',
            'tilt 1': 'tilt_1',
            'tilt 2': 'tilt_2',
            'phi 12': 'phi_12',
            'phi jl': 'phi_jl',
            'lambda 1': 'lambda_1',
            'lambda 2': 'lambda_2',
            'luminosity distance': 'luminosity_distance',
            'geocentric time': 'geocent_time'
        }
        
        bilby_name = name_map.get(param_name, param_name.replace(' ', '_'))
        
        # Get prior type and parameters
        prior_type = param_spec.get('type')
        minimum = param_spec.get('minimum')
        maximum = param_spec.get('maximum')
        boundary = param_spec.get('boundary')
        
        # Whitelist of allowed prior types to prevent code injection
        allowed_prior_types = {
            'Uniform', 'LogUniform', 'PowerLaw', 'Gaussian', 'TruncatedGaussian',
            'Sine', 'Cosine', 'Interped', 'FromFile',
            'DeltaFunction', 'Constraint',
            'bilby.gw.prior.UniformInComponentsChirpMass',
            'bilby.gw.prior.UniformInComponentsMassRatio',
            'bilby.gw.prior.AlignedSpin',
            'bilby.gw.prior.UniformComovingVolume',
            'bilby.gw.prior.UniformSourceFrame',
            'bilby.core.prior.Uniform',
            'bilby.core.prior.LogUniform',
            'bilby.core.prior.PowerLaw',
            'bilby.core.prior.Gaussian',
            'bilby.core.prior.TruncatedGaussian',
            'bilby.core.prior.Sine',
            'bilby.core.prior.Cosine',
            'bilby.core.prior.Interped',
            'bilby.core.prior.FromFile',
            'bilby.core.prior.DeltaFunction',
            'bilby.core.prior.Constraint'
        }
        
        # Default prior types for common parameters
        default_types = {
            'chirp_mass': 'bilby.gw.prior.UniformInComponentsChirpMass',
            'mass_ratio': 'bilby.gw.prior.UniformInComponentsMassRatio',
            'mass_1': 'Constraint',
            'mass_2': 'Constraint',
            'total_mass': 'Constraint',
            'a_1': 'Uniform',
            'a_2': 'Uniform',
            'tilt_1': 'Sine',
            'tilt_2': 'Sine',
            'phi_12': 'Uniform',
            'phi_jl': 'Uniform',
            'lambda_1': 'Uniform',
            'lambda_2': 'Uniform',
            'luminosity_distance': 'PowerLaw',
            'geocent_time': 'Uniform'
        }
        
        if prior_type is None:
            prior_type = default_types.get(bilby_name, 'Uniform')
        else:
            # Validate that the prior type is in the whitelist
            if prior_type not in allowed_prior_types:
                raise ValueError(
                    f"Prior type '{prior_type}' for parameter '{bilby_name}' is not in the "
                    f"allowed list. This prevents potential code injection. "
                    f"Allowed types: {sorted(allowed_prior_types)}"
                )
        
        # Build the prior string
        parts = [f"name='{bilby_name}'"]
        
        # Add minimum and maximum if present
        if minimum is not None:
            parts.append(f"minimum={minimum}")
        elif bilby_name in ['a_1', 'a_2', 'phi_12', 'phi_jl', 'lambda_1', 'lambda_2']:
            parts.append("minimum=0")
        elif bilby_name in ['mass_1', 'mass_2']:
            parts.append("minimum=1")
        
        if maximum is not None:
            parts.append(f"maximum={maximum}")
        elif bilby_name in ['a_1', 'a_2']:
            parts.append("maximum=0.99")
        elif bilby_name in ['phi_12', 'phi_jl']:
            parts.append("maximum=2 * np.pi")
        elif bilby_name in ['lambda_1', 'lambda_2']:
            parts.append("maximum=5000")
        elif bilby_name in ['mass_1', 'mass_2']:
            parts.append("maximum=1000")
        
        # Add boundary condition if present
        if boundary:
            parts.append(f"boundary='{boundary}'")
        elif bilby_name in ['phi_12', 'phi_jl']:
            parts.append("boundary='periodic'")
        
        # Add unit for mass parameters
        if bilby_name == 'chirp_mass':
            parts.append("unit='$M_{\\odot}$'")
        elif bilby_name == 'luminosity_distance':
            parts.append("unit='Mpc'")
        
        # Add any other parameters from the spec
        for key, value in param_spec.items():
            if key not in ['type', 'minimum', 'maximum', 'boundary'] and value is not None:
                key_name = key.replace(' ', '_')
                if isinstance(value, str):
                    parts.append(f"{key_name}='{value}'")
                else:
                    parts.append(f"{key_name}={value}")
        
        return f"{bilby_name} = {prior_type}({', '.join(parts)})"
    
    def _get_default_prior_dict_string(self) -> str:
        """
        Get the default prior dictionary string when no priors are specified.
        
        Returns
        -------
        str
            Default prior dictionary string
        """
        return """{
   chirp_mass = bilby.gw.prior.UniformInComponentsChirpMass(name='chirp_mass', minimum=1, maximum=100, unit='$M_{\\odot}$'),
   mass_ratio = bilby.gw.prior.UniformInComponentsMassRatio(name='mass_ratio', minimum=0.05, maximum=1.0),
   mass_1 = Constraint(name='mass_1', minimum=1, maximum=1000),
   mass_2 = Constraint(name='mass_2', minimum=1, maximum=1000),
   a_1 = Uniform(name='a_1', minimum=0, maximum=0.99),
   a_2 = Uniform(name='a_2', minimum=0, maximum=0.99),
   tilt_1 = Sine(name='tilt_1'),
   tilt_2 = Sine(name='tilt_2'),
   phi_12 = Uniform(name='phi_12', minimum=0, maximum=2 * np.pi, boundary='periodic'),
   phi_jl = Uniform(name='phi_jl', minimum=0, maximum=2 * np.pi, boundary='periodic'),
   luminosity_distance = PowerLaw(name='luminosity_distance', unit='Mpc'),
   dec = Cosine(name='dec'),
   ra = Uniform(name='ra', minimum=0, maximum=2 * np.pi, boundary='periodic'),
   theta_jn = Sine(name='theta_jn'),
   psi = Uniform(name='psi', minimum=0, maximum=np.pi, boundary='periodic'),
   phase = Uniform(name='phase', minimum=0, maximum=2 * np.pi, boundary='periodic')
}"""


class Bilby(Pipeline):
    """
    The Bilby Pipeline.

    Parameters
    ----------
    production : :class:`asimov.Production`
       The production object.
    category : str, optional
        The category of the job.
        Defaults to "analyses".
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
    
    def get_prior_interface(self):
        """
        Get the bilby-specific prior interface.
        
        Returns
        -------
        BilbyPriorInterface
            The prior interface for bilby
        """
        if self._prior_interface is None:
            priors = self.production.priors
            self._prior_interface = BilbyPriorInterface(priors)
        return self._prior_interface

    def detect_completion(self):
        """
        Check for the production of the posterior file to signal that the job has completed.
        """
        self.logger.info("Checking if the bilby job has completed")
        results_dir = glob.glob(f"{self.production.rundir}/final_result")
        if len(results_dir) > 0:  # dynesty_merge_result.json
            results_files = glob.glob(
                os.path.join(results_dir[0], "*.hdf5")
            )
            results_files += glob.glob(
                os.path.join(results_dir[0], "*.json")
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

    def get_sampler_kwargs(self):
        defaults = self.production.meta.get("sampler", {}).get("sampler kwargs", {})
        if self.production.dependencies:
            productions = {}
            for production in self.production.event.productions:
                productions[production.name] = production
            for previous_job in self.production.dependencies:
                if "samples" in productions[previous_job].pipeline.collect_assets():
                    posterior_file = productions[previous_job].pipeline.collect_assets()['samples']
                    defaults['initial_result_file'] = posterior_file[0]
        return defaults

    def get_additional_files(self):
        defaults = self.production.meta.get("scheduler", {}).get("additional files", [])
        if self.production.dependencies:
            productions = {}
            for production in self.production.event.productions:
                productions[production.name] = production
            for previous_job in self.production.dependencies:
                if "samples" in productions[previous_job].pipeline.collect_assets():
                    posterior_file = productions[previous_job].pipeline.collect_assets()['samples']
                    defaults.append(posterior_file[0])
        return defaults

    
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

        if not dryrun:
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
        else:
            executable = "bilby_pipe"
            
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
            os.path.join(rundir, "final_result", "*.hdf5")
        ) + glob.glob(os.path.join(rundir, "final_result", "*.json"))

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
