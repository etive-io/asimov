"""Defines the interface with generic analysis pipelines."""

import configparser

import os
import subprocess
import time

import asimov.analysis

from asimov import utils  # NoQA
from asimov import config, logger, logging, LOGGER_LEVEL  # NoQA

import otter  # NoQA
from .storage import Store  # NoQA


class PipelineException(Exception):
    """Exception for pipeline problems."""

    def __init__(self, message, issue=None, production=None):
        super(PipelineException, self).__init__(message)
        self.message = message
        self.issue = issue
        self.production = production

    def __repr__(self):
        text = f"""
An error was detected when assembling the pipeline for a production on this event.
Please fix the error and then remove the `pipeline-error` label from this issue.
<p>
  <details>
     <summary>Click for details of the error</summary>
     <p><b>Production</b>: {self.production}</p>
     <p>{self.message}</p>
  </details>
</p>

- [ ] Resolved
"""
        return text


class PipelineLogger:
    """Log things for pipelines."""

    def __init__(self, message, issue=None, production=None):
        self.message = message  # .decode()
        self.issue = issue
        self.production = production

    def __repr__(self):
        text = f"""
One of the productions ({self.production}) produced a log message.
It is copied below.
<p>
  <details>
     <summary>Click for details of the message</summary>
     <p><b>Production</b>: {self.production}</p>
     <p>{self.message}</p>
  </details>
</p>
"""
        return text

    def submit_comment(self):
        """
        Submit this exception as a comment on the gitlab
        issue for the event.
        """
        if self.issue:
            self.issue.add_note(self.__repr__())


class Pipeline:
    """
    Factory class for pipeline specification.
    """

    name = "Asimov Pipeline"

    available_outputs = []
    """Data products this pipeline can produce (e.g. ``["posterior_samples", "psd"]``)."""

    required_inputs = []
    """Data products this pipeline needs to run (e.g. ``["psd", "calibration"]``)."""

    def __init__(self, production, category=None):
        self.production = production

        try:
            self.category = production.category
        except AttributeError:
            self.category = None

        if isinstance(production, asimov.analysis.ProjectAnalysis):
            full_name = f"ProjectAnalysis/{production.name}"
        else:
            full_name = f"analysis.{production.event.name}/{production.name}"

        self.logger = logger.getChild(full_name)
        self.logger.setLevel(LOGGER_LEVEL)
        
        # Initialize scheduler instance (lazy-loaded via property)
        self._scheduler = None
        
        # Initialize prior interface
        self._prior_interface = None

    @property
    def scheduler(self):
        """
        Get the configured scheduler instance for this pipeline.
        
        The scheduler is lazy-loaded on first access and cached for reuse.
        
        Returns
        -------
        Scheduler
            A configured scheduler instance
        """
        if self._scheduler is None:
            from asimov.scheduler_utils import get_configured_scheduler
            self._scheduler = get_configured_scheduler()
        return self._scheduler


    def __repr__(self):
        return self.name.lower()

    def detect_completion(self):
        """
        Check to see if the job has in fact completed.
        """
        pass

    def before_config(self, dryrun=False):
        """
        Define a hook to run before the config file for the pipeline is generated.
        """
        pass

    def before_build(self, dryrun=False):
        """
        Define a hook to be run before the DAG is built.
        """
        pass

    def before_submit(self, dryrun=False):
        """
        Define a hook to run before the DAG file is generated and submitted.

        Note, this method should be over-written in the specific pipeline implementation
        if required.
        It allows the `dryrun` option to be specified in order to only print the commands
        rather than run them.
        """
        pass

    def after_completion(self):
        """
        Define a hook to run after the DAG has completed execution successfully.

        Note, this method should take no arguments, and should be over-written in the
        specific pipeline implementation if required.
        """
        self.production.status = "finished"

        # Need to determine the correct list of post-processing jobs here

        # self.production.meta.pop("job id")

    def collect_assets(self):
        """
        Add the various analysis assets from the run directory to the git repository.
        """
        repo = self.production.event.repository

        for asset in self.assets:
            repo.add_file(asset[0], asset[1])

    def collect_logs(self):
        return {}

    def store_results(self):
        """
        Store the PE Summary results
        """
        # Prefer absolute webroot; if relative, join to project root
        webroot = config.get("general", "webroot")
        if not os.path.isabs(webroot):
            webroot = os.path.join(config.get("project", "root"), webroot)

        files = [
            f"{self.production.name}_pesummary.dat",
            "posterior_samples.h5",
            f"{self.production.name}_skymap.fits",
        ]

        for filename in files:
            results = os.path.join(
                webroot,
                self.production.event.name,
                self.production.name,
                "pesummary",
                "samples",
                filename,
            )
            if os.path.exists(results):
                try:
                    store = Store(root=config.get("storage", "directory"))
                    store.add_file(
                        self.production.event.name, self.production.name, file=results
                    )
                except (OSError, IOError) as e:
                    self.logger.warning("Failed to store result %s: %s", results, e)
            else:
                self.logger.debug("Result not found, skipping: %s", results)

    def detect_completion_processing(self):
        """
        Detect that PESummary post-processing outputs exist and are valid.

        For SubjectAnalysis productions, validates that the HDF5 file contains
        all expected analyses as datasets. For regular analyses, just checks
        that the file exists and is readable.
        """
        webroot = config.get("general", "webroot")
        if not os.path.isabs(webroot):
            webroot = os.path.join(config.get("project", "root"), webroot)

        base = os.path.join(webroot, self.production.event.name, self.production.name, "pesummary")

        # Posterior file is the primary completion criterion
        posterior = os.path.join(base, "samples", "posterior_samples.h5")
        if os.path.exists(posterior):
            # Validate HDF5 file is readable and contains expected content
            try:
                import h5py
                with h5py.File(posterior, 'r') as f:
                    # For SubjectAnalysis, verify all expected analyses are present as datasets
                    from asimov.analysis import SubjectAnalysis
                    if isinstance(self.production, SubjectAnalysis):
                        # Get the list of analyses that should be in the file
                        # Use resolved_dependencies if available (what was actually processed)
                        # Otherwise fall back to current analyses list
                        expected_analyses = getattr(self.production, 'resolved_dependencies', None)
                        if not expected_analyses and hasattr(self.production, 'analyses'):
                            expected_analyses = [a.name for a in self.production.analyses]

                        if expected_analyses:
                            # Check if all expected analyses have datasets in the HDF5 file
                            # PESummary stores each analysis as a top-level group
                            available_keys = list(f.keys())
                            missing = [name for name in expected_analyses if name not in available_keys]

                            if missing:
                                self.logger.warning(
                                    f"HDF5 file exists but is missing expected analyses: {missing}. "
                                    f"Available: {available_keys}"
                                )
                                return False

                            self.logger.debug(f"HDF5 file validated with all expected analyses: {expected_analyses}")
                    else:
                        # For regular analysis, just verify the file has some content
                        if len(f.keys()) == 0:
                            self.logger.warning("HDF5 file exists but is empty")
                            return False

                    return True

            except (OSError, IOError) as e:
                self.logger.warning(f"HDF5 file exists but is not readable: {e}")
                return False
            except ImportError:
                # h5py not available, fall back to simple existence check
                self.logger.warning("h5py not available, cannot validate HDF5 contents")
                return True
            except Exception as e:
                self.logger.warning(f"Error validating HDF5 file: {e}")
                return False

        # Legacy sentinel
        legacy = os.path.join(base, "samples", f"{self.production.name}_pesummary.dat")
        if os.path.exists(legacy):
            return True

        return False

    def after_processing(self):
        """
        Run the after processing jobs.
        """
        try:
            self.store_results()
        except Exception as e:
            # Do not block upload on storage failures; log and continue
            self.logger.warning("Post-processing storage error: %s", e)
        self.production.status = "uploaded"
    
    def get_prior_interface(self):
        """
        Get the prior interface for this pipeline.
        
        This method should be overridden by pipeline-specific implementations
        to return their custom prior interface.
        
        Returns
        -------
        PriorInterface
            The prior interface for this pipeline
        """
        from asimov.priors import PriorInterface
        
        if self._prior_interface is None:
            priors = self.production.priors
            self._prior_interface = PriorInterface(priors)
        return self._prior_interface

    def get_actual_outputs(self, production):
        """
        Return the list of data products this specific production will generate.

        By default returns :attr:`available_outputs`.  Override in a subclass
        to add conditional outputs that depend on the production configuration.

        Parameters
        ----------
        production : :class:`asimov.analysis.Analysis`
            The analysis for which outputs are being queried.

        Returns
        -------
        list of str
            Names of data products produced by this production.
        """
        return list(self.available_outputs)

    def get_actual_inputs(self, production):
        """
        Return the list of data products required by this specific production.

        By default returns :attr:`required_inputs`.  Override in a subclass
        to add conditional inputs that depend on the production configuration.

        Parameters
        ----------
        production : :class:`asimov.analysis.Analysis`
            The analysis for which inputs are being queried.

        Returns
        -------
        list of str
            Names of data products required by this production.
        """
        return list(self.required_inputs)

    def eject_job(self):
        """
        Remove a job from the cluster.
        """
        command = ["condor_rm", f"{self.production.meta['job id']}"]
        try:
            dagman = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            )

        except FileNotFoundError as error:
            raise PipelineException(
                "It looks like condor isn't installed on this system.\n"
                f"""I wanted to run {" ".join(command)}."""
            ) from error

        stdout, stderr = dagman.communicate()
        if not stderr:
            time.sleep(20)
            self.production.meta.pop("job id")

    def clean(self, dryrun=False):
        """
        Remove all of the artefacts from a job from the working directory.
        """
        pass

    def submit_dag(self):
        """
        Submit the DAG for this pipeline.
        """
        raise NotImplementedError

    def resurrect(self):
        pass

    def while_running(self):
        """
        Define a hook to run while the job is running.
        
        This method is called during each monitor cycle while the analysis
        is in the 'running' state. It can be used to collect intermediate
        results, update progress information, etc.
        
        Note, this method should take no arguments, and should be over-written
        in the specific pipeline implementation if required.
        """
        pass

    def get_state_handlers(self):
        """
        Get pipeline-specific state handlers.
        
        This method allows pipelines to define their own custom state handlers
        that override or extend the default state handlers. This enables
        pipeline-specific behavior for different analysis states.
        
        Returns
        -------
        dict or None
            A dictionary mapping state names (str) to MonitorState instances,
            or None to use only default state handlers.
            
        Examples
        --------
        Override the running state handler:
        
        >>> from asimov.monitor_states import MonitorState
        >>> 
        >>> class CustomRunningState(MonitorState):
        ...     @property
        ...     def state_name(self):
        ...         return "running"
        ...     def handle(self, context):
        ...         # Custom running logic for this pipeline
        ...         return True
        >>> 
        >>> class MyPipeline(Pipeline):
        ...     def get_state_handlers(self):
        ...         return {
        ...             "running": CustomRunningState(),
        ...         }
        
        Note
        ----
        Pipeline-specific handlers take precedence over default handlers.
        If a state is not defined in the pipeline's handlers, the default
        handler will be used.
        """
        return None

    @classmethod
    def read_ini(cls, filepath):
        """
        Read and parse a pipeline configuration file.

        Parameters
        ----------
        filepath: str
           The path to the ini file.
        """

        with open(filepath, "r") as f:
            file_content = f.read()

        config_parser = configparser.RawConfigParser()
        config_parser.read_string(file_content)

        return config_parser

    def check_progress(self):
        pass

    def html(self):
        """
        Return an HTML representation of this pipeline object.
        """

        out = ""
        out += """<div class="asimov-pipeline">"""
        out += f"""<p class="asimov-pipeline-name">{self.name}</p>"""
        out += """</div>"""

        return out

    def collect_pages(self):
        pass

    def build(self):
        pass

    def build_report(self, reportformat="html"):
        """
        Build an entire report on this pipeline, including logs and configs.
        """
        webdir = config.get("general", "webroot")
        if reportformat == "html":
            # report = otter.Otter(
            #     f"{webdir}/{self.production.event.name}/{self.production.name}/index.html",
            #     author="Asimov",
            #     title="Asimov analysis report",
            # )
            report_logs = otter.Otter(
                f"{webdir}/{self.production.event.name}/{self.production.name}/logs.html",
                author="Asimov",
                title="Asimov analysis logs",
            )
            # report_config = otter.Otter(
            #     f"{webdir}/{self.production.event.name}/{self.production.name}/config.html",
            #     author="Asimov",
            #     title="Asimov analysis configuration",
            # )
            with report_logs:
                for log in self.collect_logs().values():
                    for message in log.split("\n"):
                        report_logs + message
            # with report_config:
            #     report_config + self.

