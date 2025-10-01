"""Defines the interface with generic analysis pipelines."""

import os
import warnings

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
    """

    executable = os.path.join(
        config.get("pipelines", "environment"), "bin", "summarypages"
    )
    name = "PESummary"

    def __init__(self, production, category=None):
        self.production = production

        self.category = category if category else production.category
        self.logger = logger
        self.meta = self.production.meta["postprocessing"][self.name.lower()]

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
            self.subject.name,
        )

        self.outputs = os.path.join(self.outputs, self.production.name)
        self.outputs = os.path.join(self.outputs, "pesummary")

        metafile = os.path.join(self.outputs, "samples", "posterior_samples.h5")

        return dict(metafile=metafile)

    def submit_dag(self, dryrun=False):
        """
        Run PESummary on the results of this job.
        """

        configfile = self.production.event.repository.find_prods(
            self.production.name, self.category
        )[0]
        label = str(self.production.name)

        command = [
            "--webdir",
            os.path.join(
                config.get("project", "root"),
                config.get("general", "webroot"),
                self.production.event.name,
                self.production.name,
                "pesummary",
            ),
            "--labels",
            label,
        ]

        command += ["--gw"]
        command += [
            "--approximant",
            self.production.meta["waveform"]["approximant"],
        ]

        command += [
            "--f_low",
            str(min(self.production.meta["quality"]["minimum frequency"].values())),
            "--f_ref",
            str(self.production.meta["waveform"]["reference frequency"]),
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

        if "nrsur" in self.production.meta["waveform"]["approximant"].lower():
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
                self.production.event.repository.directory, self.category, configfile
            ),
        ]
        # Samples
        command += ["--samples"]
        command += [self.production._previous_assets().get("samples", {})]

        # PSDs
        psds = {
            ifo: os.path.abspath(psd)
            for ifo, psd in self.production._previous_assets().get("psds", {}).items()
        }
        if len(psds) > 0:
            command += ["--psds"]
            for key, value in psds.items():
                command += [f"{key}:{value}"]

        # Calibration envelopes
        cals = {
            ifo: os.path.abspath(psd)
            for ifo, psd in self.production._previous_assets()
            .get("calibration", {})
            .items()
        }
        if len(cals) > 0:
            command += ["--calibration"]
            for key, value in cals.items():
                command += [f"{key}:{value}"]

        with utils.set_directory(self.subject.work_dir):
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
            "output": f"{self.subject.work_dir}/pesummary.out",
            "error": f"{self.subject.work_dir}/pesummary.err",
            "log": f"{self.subject.work_dir}/pesummary.log",
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
