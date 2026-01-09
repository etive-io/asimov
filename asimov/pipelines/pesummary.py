"""Defines the interface with generic analysis pipelines."""

import os
import warnings

try:
    warnings.filterwarnings("ignore", module="htcondor2")
    import htcondor2 as htcondor # NoQA
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
        
        self.analysis = production
        self.event = self.subject = production.subject if hasattr(production, 'subject') else production.event

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
            self.meta = {}

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
        
        # Get config file
        try:
            configfile = self.event.repository.find_prods(
                self.production.name, self.category
            )[0]
        except (AttributeError, IndexError):  # pragma: no cover
            raise PipelineException(
                "Could not find PESummary configuration file."
            )
        
        # Determine labels and samples for PESummary
        if is_subject_analysis:
            # Multiple analyses - get labels and samples from dependencies
            labels = []
            samples_list = []
            
            # Get the analyses that are dependencies
            if hasattr(self.production, 'productions') and self.production.productions:
                source_analyses = self.production.productions
            elif hasattr(self.production, 'analyses') and self.production.analyses:
                source_analyses = self.production.analyses
            else:
                raise PipelineException(
                    "SubjectAnalysis PESummary has no source analyses to process."
                )
            
            for dep_analysis in source_analyses:
                labels.append(dep_analysis.name)
                # Get samples from the dependency
                dep_samples = dep_analysis._previous_assets().get("samples", None)
                if dep_samples:
                    samples_list.append(dep_samples)
                else:
                    self.logger.warning(f"No samples found for {dep_analysis.name}")
            
            if not samples_list:
                raise PipelineException(
                    "No samples found from any dependency analyses."
                )
            
            # For SubjectAnalysis, use first analysis for waveform/quality settings
            # or fall back to SubjectAnalysis metadata
            reference_analysis = source_analyses[0]
            if "waveform" in reference_analysis.meta:
                waveform_meta = reference_analysis.meta["waveform"]
                quality_meta = reference_analysis.meta.get("quality", {})
            else:
                waveform_meta = self.production.meta.get("waveform", {})
                quality_meta = self.production.meta.get("quality", {})
        else:
            # Single analysis mode (post-processing)
            labels = [self.production.name]
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
        if "approximant" in waveform_meta:
            command += [
                "--approximant",
                waveform_meta["approximant"],
            ]
        
        if "minimum frequency" in quality_meta:
            command += [
                "--f_low",
                str(min(quality_meta["minimum frequency"].values())),
            ]
        
        if "reference frequency" in waveform_meta:
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

        # Config file
        command += [
            "--config",
            os.path.join(
                self.event.repository.directory, self.category, configfile
            ),
        ]
        
        # Samples - handle both single and multiple analyses
        command += ["--samples"]
        if is_subject_analysis:
            # Multiple samples files
            for samples in samples_list:
                if isinstance(samples, dict):
                    # If samples is a dict (shouldn't be for pesummary), just skip
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
                # Dict or other - get the value
                command.append(str(samples))

        # PSDs - get from first dependency in SubjectAnalysis mode
        if is_subject_analysis and source_analyses:
            psds = source_analyses[0]._previous_assets().get("psds", {})
        else:
            psds = self.production._previous_assets().get("psds", {})
        
        psds = {
            ifo: os.path.abspath(psd)
            for ifo, psd in psds.items()
        }
        if len(psds) > 0:
            command += ["--psds"]
            for key, value in psds.items():
                command += [f"{key}:{value}"]

        # Calibration envelopes - get from first dependency in SubjectAnalysis mode
        if is_subject_analysis and source_analyses:
            cals = source_analyses[0]._previous_assets().get("calibration", {})
        else:
            cals = self.production._previous_assets().get("calibration", {})
        
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

        print(command)

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
            hostname_job = htcondor.Submit(submit_description)

            try:
                # There should really be a specified submit node, and if there is, use it.
                schedulers = htcondor.Collector().locate(
                    htcondor.DaemonTypes.Schedd, config.get("condor", "scheduler")
                )
                schedd = htcondor.Schedd(schedulers)
            except:  # NoQA
                # If you can't find a specified scheduler, use the first one you find
                schedd = htcondor.Schedd()
            with schedd.transaction() as txn:
                cluster_id = hostname_job.queue(txn)

        else:
            cluster_id = 0

        return cluster_id
