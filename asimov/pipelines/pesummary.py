"""Defines the interface with generic analysis pipelines."""

import configparser
import os
import warnings

try:
    warnings.filterwarnings("ignore", module="htcondor2")
    import htcondor2 as htcondor  # NoQA
except ImportError:
    warnings.filterwarnings("ignore", module="htcondor")
    import htcondor  # NoQA
from asimov import utils  # NoQA
from asimov import config, logger, logging, LOGGER_LEVEL  # NoQA

import otter  # NoQA
from ..storage import Store  # NoQA
from ..pipeline import Pipeline, PipelineException, PipelineLogger  # NoQA


class PESummary(Pipeline):
    """
    A postprocessing pipeline add-in using PESummary.
    
    This pipeline can work in two modes:
    1. Post-processing hook: Called after a single analysis completes (legacy mode)
    2. SubjectAnalysis: Processes results from multiple analyses as dependencies
    """

    executable = os.path.join(
        config.get("pipelines", "environment"), "bin", "summarypages"
    )
    name = "PESummary"

    def __init__(self, production, category=None):
        """
        Initialize PESummary pipeline.
        
        Parameters
        ----------
        production : Analysis
            The analysis this pipeline is attached to. Can be a SimpleAnalysis 
            (for post-processing hook mode) or SubjectAnalysis (for multi-analysis mode)
        category : str, optional
            The category for file locations
        """
        # Call parent constructor
        super().__init__(production, category)
        # Resolve executable, prefer explicit [pesummary] executable if provided
        try:
            pes_exec = config.get("pesummary", "executable")
            if pes_exec:
                self.executable = pes_exec
        except (configparser.NoSectionError, configparser.NoOptionError):
            # Fall back to pipelines environment path
            pass
        
        self.analysis = production
        
        # Get subject/event - handle different analysis types
        if hasattr(production, 'subject'):
            self.event = self.subject = production.subject
        elif hasattr(production, 'event'):
            self.event = self.subject = production.event
        else:
            raise PipelineException(
                "Production must have either 'subject' or 'event' attribute"
            )

        # Set category appropriately
        if category:
            self.category = category
        elif hasattr(production, 'category'):
            self.category = production.category
        else:
            self.category = config.get("general", "calibration_directory")

        # Get metadata - check different locations based on analysis type
        if "postprocessing" in production.meta and self.name.lower() in production.meta["postprocessing"]:
            self.meta = production.meta["postprocessing"][self.name.lower()]
        elif hasattr(production, 'subject') and "postprocessing" in production.subject.meta:
            # For SimpleAnalysis, check subject metadata
            if self.name.lower() in production.subject.meta["postprocessing"]:
                self.meta = production.subject.meta["postprocessing"][self.name.lower()]
            else:
                self.meta = {}
        else:
            self.meta = production.meta

    def collect_assets(self):
        """
        Gather all of the results assets for this job.

        For PESummary SubjectAnalysis jobs, this returns the combined results.
        For PESummary post-processing jobs, this returns the samples and config.

        Returns
        -------
        dict
            A dictionary of assets with keys like 'samples', 'config', etc.
        """
        # For PESummary as a SubjectAnalysis, return the combined samples
        webroot = config.get("general", "webroot")
        if not os.path.isabs(webroot):
            webroot = os.path.join(config.get("project", "root"), webroot)

        # Path to the combined posterior samples file
        samples_file = os.path.join(
            webroot,
            self.subject.name,
            self.production.name,
            "pesummary",
            "samples",
            "posterior_samples.h5"
        )

        assets = {}

        # Add samples if they exist
        if os.path.exists(samples_file):
            assets["samples"] = samples_file

        # For post-processing mode, also include the config
        from asimov.analysis import SubjectAnalysis
        if not isinstance(self.production, SubjectAnalysis):
            try:
                config_file = self.event.repository.find_prods(
                    self.production.name, self.category
                )[0]
                assets["config"] = config_file
            except (AttributeError, IndexError):
                # If the event or repository is missing, or no production config
                # is found, skip adding a config asset but continue without error.
                logger.debug(
                    "PESummary.collect_assets: no config found for production %s "
                    "in category %s",
                    getattr(self.production, "name", "<unknown>"),
                    getattr(self, "category", "<none>"),
                )

        return assets

    def results(self):
        """
        Fetch the results file from this post-processing step.

        A dictionary of results will be returned with the description
        of each results file as the key.  These may be nested if it
        makes sense for the output, for example skymaps.

        For example

        {'metafile': '/home/asimov/working/samples/metafile.hd5',
         'skymaps': {'H1': '/another/file/path', ...}
        }

        Returns
        -------
        dict
           A dictionary of the results.
        """
        self.outputs = os.path.join(
            config.get("project", "root"),
            config.get("general", "webroot"),
            self.name,
        )

        self.outputs = os.path.join(self.outputs, self.name, "pesummary")

        metafile = os.path.join(self.outputs, "samples", "posterior_samples.h5")

        return dict(metafile=metafile)

    def build_dag(self, user=None, dryrun=False):
        """
        Prepare the PESummary job for submission.
        
        For PESummary, there's no DAG file to build since it runs as a single job.
        This method exists to satisfy the Pipeline interface.
        
        Parameters
        ----------
        user : str, optional
            The user accounting tag (not used by PESummary)
        dryrun : bool, optional
            If True, don't actually build anything
        """
        # PESummary doesn't need a DAG file - it runs as a single condor job
        # The actual job configuration is done in submit_dag
        pass

    def submit_dag(self, dryrun=False):
        """
        Run PESummary on the results of this job.
        
        Supports two modes:
        1. Post-processing a single analysis (SimpleAnalysis)
        2. Combining multiple analyses (SubjectAnalysis)
        """
        # Determine if this is a SubjectAnalysis or SimpleAnalysis
        from asimov.analysis import SubjectAnalysis
        is_subject_analysis = isinstance(self.production, SubjectAnalysis)
        
        # Get config file(s)
        # For SubjectAnalysis, configs are collected from dependencies above
        # For SimpleAnalysis (post-processing hook), get the config from the production
        configfile = None  # Initialize to avoid unbound variable
        if not is_subject_analysis:
            try:
                configfile = self.event.repository.find_prods(
                    self.production.name, self.category
                )[0]
            except (AttributeError, IndexError):  # pragma: no cover
                raise PipelineException(
                    "Could not find PESummary configuration file."
                )

        # Prefer assets from the current production; fall back to dependency assets
        current_assets = {}
        if not is_subject_analysis:
            try:
                current_assets = self.production.pipeline.collect_assets()
            except (AttributeError, PipelineException):
                # If the production has no pipeline or the pipeline fails in an
                # expected way, fall back to using no current assets.
                current_assets = {}
        
        # Determine labels and samples for PESummary
        if is_subject_analysis:
            # Multiple analyses - get labels and samples from dependencies
            labels = []
            samples_list = []
            config_list = []
            approximants = []
            f_lows = []
            f_refs = []
            
            # Get the analyses that are dependencies
            # Prefer the current analyses list; fall back to productions if needed
            if hasattr(self.production, 'analyses') and self.production.analyses:
                source_analyses = self.production.analyses
            elif hasattr(self.production, 'productions') and self.production.productions:
                source_analyses = self.production.productions
            else:
                raise PipelineException(
                    "SubjectAnalysis PESummary has no source analyses to process."
                )
            
            for dep_analysis in source_analyses:
                # Get samples and config directly from this analysis
                dep_assets = dep_analysis.pipeline.collect_assets()
                if not isinstance(dep_assets, dict):
                    self.logger.warning(
                        f"collect_assets for {dep_analysis.name} returned "
                        f"{type(dep_assets).__name__}, expected dict; skipping this analysis."
                    )
                    continue
                dep_samples = dep_assets.get("samples", None)
                dep_config = dep_assets.get("config", None)
                if dep_samples:
                    labels.append(dep_analysis.name)
                    samples_list.append(dep_samples)
                    
                    # Collect waveform parameters for this analysis
                    if "waveform" in dep_analysis.meta:
                        if "approximant" in dep_analysis.meta["waveform"]:
                            approximants.append(dep_analysis.meta["waveform"]["approximant"])
                        if "reference frequency" in dep_analysis.meta["waveform"]:
                            f_refs.append(str(dep_analysis.meta["waveform"]["reference frequency"]))
                    
                    if "quality" in dep_analysis.meta:
                        if "minimum frequency" in dep_analysis.meta["quality"]:
                            f_lows.append(str(min(dep_analysis.meta["quality"]["minimum frequency"].values())))
                    
                    # Config file should be added for each analysis that has samples
                    if dep_config:
                        # Convert to absolute path if needed
                        if isinstance(dep_config, str):
                            config_path = os.path.join(
                                self.event.repository.directory,
                                dep_analysis.category if hasattr(dep_analysis, 'category') else self.category,
                                dep_config
                            )
                            config_list.append(config_path)
                        elif isinstance(dep_config, list):
                            # If it's a list, handle each config file
                            for cfg in dep_config:
                                config_path = os.path.join(
                                    self.event.repository.directory,
                                    dep_analysis.category if hasattr(dep_analysis, 'category') else self.category,
                                    cfg
                                )
                                config_list.append(config_path)
                        else:
                            config_list.append(dep_config)
                    else:
                        self.logger.warning(f"No config found for {dep_analysis.name}")
                else:
                    self.logger.warning(f"No samples found for {dep_analysis.name}")
            
            if not samples_list:
                raise PipelineException(
                    "No samples found from any dependency analyses."
                )
            
            # Persist resolved dependencies so we can detect staleness later
            try:
                self.production.resolved_dependencies = labels
                self.logger.info(f"Stored resolved dependencies: {labels}")
            except Exception as e:
                self.logger.error(f"Failed to store resolved_dependencies: {e}")
                raise PipelineException(f"Could not store resolved dependencies: {e}") from e

            # Ensure that the run directory exists (race-free)
            os.makedirs(self.production.rundir, exist_ok=True)

            # For SubjectAnalysis, use metadata from the production itself
            # Individual analysis waveform settings are collected above
            waveform_meta = self.production.meta.get("waveform", {})
            quality_meta = self.production.meta.get("quality", {})
        else:
            # Single analysis mode (post-processing)
            labels = [self.production.name]
            if "samples" in current_assets and current_assets["samples"]:
                samples_list = [current_assets["samples"]]
            else:
                samples_list = [self.production._previous_assets().get("samples", {})]
            waveform_meta = self.production.meta.get("waveform", {})
            quality_meta = self.production.meta.get("quality", {})

        command = [
            "--webdir",
            os.path.join(
                config.get("project", "root"),
                config.get("general", "webroot"),
                self.subject.name,
                self.production.name,
                "pesummary",
            ),
            "--labels",
        ]
        command.extend(labels)

        command += ["--gw"]
        
        # Add waveform settings if available
        # For SubjectAnalysis with multiple approximants, pass them as a list
        if is_subject_analysis and approximants:
            command += ["--approximant"]
            command.extend(approximants)
        elif "approximant" in waveform_meta:
            command += [
                "--approximant",
                waveform_meta["approximant"],
            ]
        
        # f_low - use per-analysis values if available, otherwise use global
        if is_subject_analysis and f_lows:
            # If we have per-analysis f_low values, use them
            command += ["--f_low"]
            command.extend(f_lows)
        elif "minimum frequency" in quality_meta:
            command += [
                "--f_low",
                str(min(quality_meta["minimum frequency"].values())),
            ]
        
        # f_ref - use per-analysis values if available, otherwise use global
        if is_subject_analysis and f_refs:
            command += ["--f_ref"]
            command.extend(f_refs)
        elif "reference frequency" in waveform_meta:
            command += [
                "--f_ref",
                str(waveform_meta["reference frequency"]),
            ]

        if "cosmology" in self.meta:
            command += [
                "--cosmology",
                self.meta["cosmology"],
            ]
        if "redshift" in self.meta:
            command += ["--redshift_method", self.meta["redshift"]]
        if "skymap samples" in self.meta:
            command += [
                "--nsamples_for_skymap",
                str(self.meta["skymap samples"]),
            ]

        if "evolve spins" in self.meta:
            if "forwards" in self.meta["evolve spins"]:
                command += ["--evolve_spins_fowards", "True"]
            if "backwards" in self.meta["evolve spins"]:
                command += ["--evolve_spins_backwards", "precession_averaged"]

        if "nrsur" in waveform_meta.get("approximant", "").lower():
            command += ["--NRSur_fits"]

        if "multiprocess" in self.meta:
            command += ["--multi_process", str(self.meta["multiprocess"])]

        if "regenerate" in self.meta:
            command += ["--regenerate", " ".join(self.meta["regenerate posteriors"])]

        if "calculate" in self.meta:
            if "precessing snr" in self.meta["calculate"]:
                command += ["--calculate_precessing_snr"]

        # Handle additional arguments - supports both flags and options with values
        # This allows passing arbitrary PESummary command-line arguments via the blueprint.
        #
        # Supported formats in the blueprint:
        #
        # 1. Dictionary format (for options with values):
        #    additional arguments:
        #      nsamples: 1000
        #      seed: 42
        #      custom_option: "some_value"
        #    Result: --nsamples 1000 --seed 42 --custom_option some_value
        #
        # 2. List format (for flags without values):
        #    additional arguments: ["disable_prior_sampling", "no_ligo_skymap"]
        #    Result: --disable_prior_sampling --no_ligo_skymap
        #
        # 3. Mixed list format (flags and options):
        #    additional arguments:
        #      - "disable_prior_sampling"  # flag
        #      - {nsamples: 1000}          # option with value
        #      - "no_ligo_skymap"          # flag
        #      - {seed: 42}                # option with value
        #    Result: --disable_prior_sampling --nsamples 1000 --no_ligo_skymap --seed 42
        #
        # Note: Options with None or empty string values will only add the flag without a value.
        if "additional arguments" in self.meta:
            additional_args = self.meta["additional arguments"]
            
            # If it's a dictionary, treat keys as options and values as their arguments
            if isinstance(additional_args, dict):
                for key, value in additional_args.items():
                    command += [f"--{key}"]
                    if value is not None and value != "":
                        # Only add the value if it's not None or empty string
                        command += [str(value)]
            
            # If it's a list, each item can be a flag (string) or option (dict)
            elif isinstance(additional_args, list):
                for arg in additional_args:
                    if isinstance(arg, str):
                        # Simple flag
                        command += [f"--{arg}"]
                    elif isinstance(arg, dict):
                        # Option with value(s)
                        for key, value in arg.items():
                            command += [f"--{key}"]
                            if value is not None and value != "":
                                command += [str(value)]

        # Samples - handle both single and multiple analyses
        command += ["--samples"]
        if is_subject_analysis:
            # Multiple samples files
            for samples in samples_list:
                if isinstance(samples, dict):
                    # If samples is a dict, log a warning and skip
                    self.logger.warning(
                        f"Unexpected dict format for samples in SubjectAnalysis: {samples}"
                    )
                    continue
                elif isinstance(samples, list):
                    command.extend(samples)
                else:
                    command.append(samples)
        else:
            # Single samples file
            samples = samples_list[0]
            if isinstance(samples, list):
                command.extend(samples)
            elif isinstance(samples, str):
                command.append(samples)
            else:
                # Dict or other - try to convert to string
                self.logger.warning(
                    f"Unexpected format for samples: {type(samples)}, converting to string"
                )
                command.append(str(samples))

        # Config files - handle both single and multiple analyses
        command += ["--config"]
        if is_subject_analysis:
            # Multiple config files from dependencies
            if config_list:
                command.extend(config_list)
            else:
                self.logger.warning("No config files found from dependency analyses")
        else:
            # Single config file for post-processing mode
            if configfile is not None:
                command.append(
                    os.path.join(
                        self.event.repository.directory, self.category, configfile
                    )
                )
            else:
                raise PipelineException("No config file available for PESummary")

        # PSDs - get from first analysis in SubjectAnalysis mode or from this production
        if is_subject_analysis and source_analyses:
            psds = source_analyses[0].pipeline.collect_assets().get("psds", {})
        else:
            psds = current_assets.get("psds", {}) or self.production._previous_assets().get("psds", {})
        
        psds = {
            ifo: os.path.abspath(psd)
            for ifo, psd in psds.items()
        }
        if len(psds) > 0:
            command += ["--psds"]
            for key, value in psds.items():
                command += [f"{key}:{value}"]

        # Calibration envelopes - get from first analysis in SubjectAnalysis mode or from this production
        if is_subject_analysis and source_analyses:
            cals = source_analyses[0].pipeline.collect_assets().get("calibration", {})
        else:
            cals = current_assets.get("calibration", {}) or self.production._previous_assets().get("calibration", {})
        
        cals = {
            ifo: os.path.abspath(cal)
            for ifo, cal in cals.items()
        }
        if len(cals) > 0:
            command += ["--calibration"]
            for key, value in cals.items():
                command += [f"{key}:{value}"]

        with utils.set_directory(self.production.rundir):
            with open("pesummary.sh", "w") as bash_file:
                bash_file.write(f"{self.executable} " + " ".join(command))

        self.logger.info(
            f"PE summary command: {self.executable} {' '.join(command)}",
        )
        
        if dryrun:
            print("PESUMMARY COMMAND")
            print("-----------------")
            print(" ".join(command))
        self.subject = self.production.event
        submit_description = {
            "executable": self.executable,
            "arguments": " ".join(command),
            "output": f"{self.production.rundir}/pesummary.out",
            "error": f"{self.production.rundir}/pesummary.err",
            "log": f"{self.production.rundir}/pesummary.log",
            "request_cpus": self.meta["multiprocess"],
            "getenv": "true",
            "batch_name": f"Summary Pages/{self.subject.name}/{self.production.name}",
            "request_memory": "8192MB",
            "should_transfer_files": "YES",
            "request_disk": "8192MB",
        }
        if "accounting group" in self.meta:
            submit_description["accounting_group_user"] = config.get("condor", "user")
            submit_description["accounting_group"] = self.meta["accounting group"]

        if dryrun:
            print("SUBMIT DESCRIPTION")
            print("------------------")
            print(submit_description)

        if not dryrun:
            job = htcondor.Submit(submit_description)

            try:
                schedulers = htcondor.Collector().locate(
                    htcondor.DaemonTypes.Schedd, config.get("condor", "scheduler")
                )
            except (configparser.NoOptionError, configparser.NoSectionError):
                schedulers = htcondor.Collector().locate(htcondor.DaemonTypes.Schedd)

            schedd = htcondor.Schedd(schedulers)
            
            result = schedd.submit(job)
            cluster_id = result.cluster()
            self.logger.info(f"Submitted {cluster_id} to htcondor job queue.")

        else:
            cluster_id = 0

        return cluster_id
