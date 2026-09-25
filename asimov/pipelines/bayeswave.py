"""BayesWave Pipeline specification."""

import configparser
import glob
import os
import re
import shutil
import subprocess
from shutil import copyfile, copytree

import numpy as np
from gwpy.frequencyseries import FrequencySeries

from asimov import config
from asimov.utils import set_directory

from ..git import AsimovFileNotFound
from ..pipeline import Pipeline, PipelineException, PipelineLogger
from ..storage import AlreadyPresentException, Store


class BayesWave(Pipeline):
    """
    The BayesWave Pipeline.

    Parameters
    ----------
    production : :class:`asimov.Production`
       The production object.
    category : str, optional
        The category of the job.
        Defaults to "C01_offline".
    """

    name = "BayesWave"
    STATUS = {"wait", "stuck", "stopped", "running", "finished"}

    def __init__(self, production, category=None):
        super(BayesWave, self).__init__(production, category)
        self.logger.info("Using the Bayeswave pipeline")
        if not production.pipeline.lower() == "bayeswave":
            raise PipelineException

        try:
            self.category = config.get("general", "calibration_directory")
        except configparser.NoOptionError:
            self.category = "C01_offline"
            self.logger.info("Assuming C01_offline calibration.")

        if not production.meta.get("quality", {}).get("lowest minimum frequency", None):
            production.meta["quality"]["lowest minimum frequency"] = self.flow

    def build_dag(self, user=None, dryrun=False):
        """
        Construct a DAG file in order to submit a production to the
        condor scheduler using bayeswave_pipe

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
        """
        if self.production.event.repository:
            try:
                gps_file = self.production.get_timefile()
            except AsimovFileNotFound:
                if "event time" in self.production.meta:
                    gps_time = self.production.get_meta("event time")
                    with set_directory(
                        os.path.join(
                            self.production.event.repository.directory, self.category
                        )
                    ):
                        with open("gpstime.txt", "w") as f:
                            f.write(str(gps_time))
                            gps_file = os.path.join(
                                f"{self.production.category}", "gpstime.txt"
                            )
                            self.production.event.repository.add_file(
                                "gpstime.txt", gps_file
                            )
                else:
                    raise PipelineException("Cannot find the event time.")
        else:
            gps_time = self.production.get_meta("event time")
            with open("gpstime.txt", "w") as f:
                f.write(str(gps_time))
                gps_file = os.path.join("gpstime.txt")

        if self.production.event.repository:
            ini = self.production.get_configuration()
            if not user:
                if self.production.get_meta("user"):
                    user = self.production.get_meta("user")
                else:
                    user = ini._get_user()

            ini.update_accounting(user)

            if "queue" in self.production.meta:
                queue = self.production.meta["queue"]
            else:
                queue = "Priority_PE"

            ini.set_queue(queue)

            ini.save()

            ini = ini.ini_loc

        else:
            ini = f"{self.production.name}.ini"

        if self.production.rundir:
            rundir = self.production.rundir
        else:
            rundir = os.path.join(
                config.get("general", "rundir_default"),
                self.production.event.name,
                self.production.name,
            )
            self.production.rundir = rundir

        gps_time = self.production.get_meta("event time")

        default_executable = os.path.join(
            config.get("pipelines", "environment"), "bin", "bayeswave_pipe"
        )
        executable = self.production.meta.get("executable", default_executable)
        if (executable := shutil.which(executable)) is not None:
            pass
        elif (executable := shutil.which("bayeswave_pipe")) is not None:
            pass
        else:
            raise PipelineException(
                "Cannot find bayeswave_pipe executable",
                production=self.production.name,
            )

        command = [
            executable,
            # "-l", f"{gps_file}",
            f"--trigger-time={gps_time}",
        ]

        if "cache files" in self.production.meta["data"]:
            if len(self.production.meta["data"]["cache files"]) > 0:
                # Skip the datafind step if the data is already provided.
                command += ["--skip-datafind"]

        if "copy frames" in self.production.meta["scheduler"]:
            if self.production.meta["scheduler"]["copy frames"]:
                command += ["--copy-frames"]

        if "osg" in self.production.meta["scheduler"]:
            if self.production.meta["scheduler"]["osg"]:
                command += ["--transfer-files"]

                if "copy frames" not in self.production.meta["scheduler"]:
                    command += ["--igwn-pool"]
                if "copy frames" in self.production.meta["scheduler"]:
                    if not self.production.meta["scheduler"]["copy frames"]:
                        command += ["--igwn-pool"]

        command += [
            "-r",
            self.production.rundir,
            ini,
        ]

        self.logger.info(" ".join(command))

        if dryrun:
            print(" ".join(command))
            self.logger.info(" ".join(command))
        else:

            pipe = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            )
            out, err = pipe.communicate()
            if "To submit:" not in str(out):
                self.production.status = "stuck"
                self.logger.error("Could not create a DAG file")
                self.logger.info(f"{command}")
                self.logger.debug(out)
                self.logger.debug(err)
                raise PipelineException("The DAG file could not be created.")
            else:
                self.logger.info("DAG file created")
                self.logger.debug(out)

    def _original_psds(self):
        psds = {}
        results_dir = glob.glob(f"{self.production.rundir}/trigtime_*")[0]
        for det in self.production.meta["interferometers"]:
            asset = os.path.join(
                results_dir, "post", "clean", f"glitch_median_PSD_forLI_{det}.dat"
            )
            if os.path.exists(asset):
                psds[det] = asset
        return psds

    def detect_completion(self):
        psds = self._original_psds()
        if len(list(psds.values())) > 0:
            return True
        else:
            self.logger.info("Bayeswave job completion was not detected.")
            return False

    def _convert_psd(self, ascii_format, ifo):
        """
        Convert an ascii format PSD to XML.

        Parameters
        ----------
        ascii_format : str
           The location of the ascii format file.
        ifo : str
           The IFO which this PSD is for.
        """
        command = [
            "convert_psd_ascii2xml",
            "--fname-psd-ascii",
            f"{ascii_format}",
            "--conventional-postfix",
            "--ifo",
            f"{ifo}",
        ]
        self.logger.info(" ".join(command))
        pipe = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        out, err = pipe.communicate()

        if err:
            self.production.status = "stuck"
            if hasattr(self.production.event, "issue_object"):
                raise Exception(
                    f"An XML format PSD could not be created.\n{command}\n{out}\n\n{err}",
                )
            else:
                raise Exception(
                    f"An XML format PSD could not be created.\n{command}\n{out}\n\n{err} ",
                )
        else:
            asset = f"{ifo.upper()}-psd.xml.gz"
            git_location = os.path.join(
                self.production.category,
                "psds",
                f"{self.production.meta['likelihood']['sample rate']}",
            )
            self.production.event.repository.add_file(
                asset,
                os.path.join(git_location, f"{ifo}-psd.xml.gz"),
                commit_message=f"Added the xml format PSD for {ifo}.",
            )

    def after_completion(self):
        """
        Collect the outputs of the pipeline so that they can be used
        in subsequent analyses.
        
        Stages:

        - Collect PSDs from the working directory.
        - Apply suppression if required.
        - Convert the (possibly suppressed) PSDs to XML format.
        - Add the PSDs to the event data repository.
        """
        self.logger.error("BW complete")

        psds = self._original_psds()

        if "supress" in self.production.meta["quality"]:
            self.logger.warning("suppressing PSD")
            sample_rate = self.production.meta["likelihood"]["sample rate"]
            for ifo in self.production.meta["quality"]["supress"]:
                if ifo in self.production.meta["interferometers"]:
                    ranges = self.production.meta["quality"]["supress"][ifo]
                    if isinstance(ranges, dict):
                        ranges = [ranges]
                    self.supress_psd(ifo, ranges, psds[ifo])
                    repo_psd = os.path.join(
                        self.production.event.repository.directory,
                        self.category,
                        "psds",
                        str(sample_rate),
                        f"{ifo}-psd.dat",
                    )
                    psds[ifo] = repo_psd

        try:
            for ifo, psd in psds.items():
                self.logger.warning(f"Converting the PSD for {ifo} to XML")
                self._convert_psd(ascii_format=psd, ifo=ifo)
        except Exception as e:
            self.logger.error("Failed to convert the PSDs to XML")
            self.logger.exception(e)

        try:
            self.collect_pages()
        except FileNotFoundError:
            PipelineLogger(
                message=b"Failed to copy megaplot pages.",
                production=self.production.name,
            )

        try:
            self.collect_assets()
            self.store_assets()
        except Exception:
            PipelineLogger(
                message=b"Failed to store PSDs.",
                issue=self.production.event.issue_object,
                production=self.production.name,
            )

        self.production.status = "uploaded"

    @property
    def flow(self):
        """
        Calculate the lower frequency for the bayeswave job.

        This is required as bayeswave needs to be passed the lowest
        minimum frequency from the list of interferometer
        lower frequencies.
        """
        return min(self.production.meta["quality"]["minimum frequency"].values())

    def before_submit(self):
        """
        Horribly hack the sub files to add `request_disk`
        """
        sub_files = glob.glob(f"{self.production.rundir}/*.sub")
        for sub_file in sub_files:
            with open(sub_file, "r") as f_handle:
                original = f_handle.read()
            with open(sub_file, "w") as f_handle:
                self.logger.info(f"Adding request_disk = {64000} to {sub_file}")
                f_handle.write(f"request_disk = {64000}\n" + original)
        python_files = glob.glob(f"{self.production.rundir}/*.py")
        for py_file in python_files:
            with open(py_file, "r") as f_handle:
                original = f_handle.read()
            with open(py_file, "w") as f_handle:
                self.logger.info("Fixing shebang")
                path = os.path.join(
                    config.get("pipelines", "environment"), "bin", "python"
                )
                f_handle.write(f"#! {path}\n" + original)

    def submit_dag(self, dryrun=False):
        """
        Submit a DAG file to the condor cluster.

        Parameters
        ----------
        dryrun: bool
           If True then the DAG will not be submitted but all of the
           commands will be printed to stdout.

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
        self.before_submit()

        command = [
            "condor_submit_dag",
            "-batch-name",
            f"bwave/{self.production.event.name}/{self.production.name}",
            f"{self.production.name}.dag",
        ]

        if dryrun:
            print(" ".join(command))

        else:
            with set_directory(self.production.rundir):
                try:
                    dagman = subprocess.Popen(
                        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
                    )
                except FileNotFoundError as e:
                    self.logger.exception(e)
                    raise PipelineException(
                        "It looks like condor isn't installed on this system.\n"
                        f"""I wanted to run {" ".join(command)}."""
                    ) from e

                stdout, stderr = dagman.communicate()

            if "submitted to cluster" in str(stdout):
                cluster = re.search(
                    r"submitted to cluster ([\d]+)", str(stdout)
                ).groups()[0]
                self.production.status = "running"
                self.production.job_id = int(cluster)
                self.logger.info(
                    f"Successfully submitted to cluster {self.production.job_id}"
                )
                self.logger.debug(stdout)
                return (int(cluster),)
            else:
                self.logger.info(stdout)
                self.logger.error(stderr)
                raise PipelineException(
                    f"The DAG file could not be submitted.\n\n{stdout}\n\n{stderr}",
                )

    def upload_assets(self):
        """
        Upload the PSDs from this job.
        """
        sample = self.production.meta["likelihood"]["sample rate"]
        git_location = os.path.join(self.category, "psds")

        for detector, asset in self._original_psds().items():
            self.production.event.repository.add_file(
                asset,
                os.path.join(git_location, str(sample), f"{detector}-psd.dat"),
                commit_message=f"Added the PSD for {detector}.",
            )

    def store_assets(self):
        """
        Add the assets to the store.
        """

        sample_rate = self.production.meta["likelihood"]["sample rate"]
        self.logger.info(self.collect_assets())
        for detector, asset in self.collect_assets()["psds"].items():
            store = Store(root=config.get("storage", "directory"))
            try:
                store.add_file(
                    self.production.event.name,
                    self.production.name,
                    file=asset,
                    new_name=f"{detector}-{sample_rate}-psd.dat",
                )
            except AlreadyPresentException:
                self.logger.warning(
                    f"Attempted to add a PSD for {detector} which already exists."
                )
            except Exception as e:
                self.logger.error(
                    f"There was a problem committing the PSD for {detector} to the store."
                )
                self.logger.exception(e)

    def collect_logs(self):
        """
        Collect all of the log files which have been produced by this production and
        return their contents as a dictionary.
        """
        messages = {}

        logfile = os.path.join(
            config.get("logging", "directory"),
            self.production.event.name,
            self.production.name,
            "asimov.log",
        )
        with open(logfile, "r") as log_f:
            message = log_f.read()
            messages["production"] = message

        logs = glob.glob(f"{self.production.rundir}/logs/*.err") + glob.glob(
            f"{self.production.rundir}/*.err"
        )
        for log in logs:
            with open(log, "r") as log_f:
                message = log_f.read()
                messages[log.split("/")[-1]] = message
        return messages

    def collect_assets(self):
        """
        Collect the assets for this job and commit them to the event repository.
        Since this job also generates the PSDs these should be added to the production ledger.
        """
        outputs = {}

        xml_psds = {}
        psds = {}
        for det in self.production.meta["interferometers"]:
            for extension, container in [("dat", psds), ("xml.gz", xml_psds)]:
                asset = os.path.join(
                    self.production.event.repository.directory,
                    self.production.category,
                    "psds",
                    f"{self.production.meta['likelihood']['sample rate']}",
                    f"{det.upper()}-psd.{extension}",
                )
                if os.path.exists(asset):
                    container[det] = os.path.abspath(asset)

        outputs["xml psds"] = xml_psds
        outputs["psds"] = psds

        return outputs

    def supress_psd(self, ifo, ranges, psd_file):
        """
        Suppress portions of a PSD.

        Applies one or more frequency-range notches to the PSD for a given
        interferometer, writing and committing the result once.

        Author: Carl-Johan Haster - August 2020
        (Updated for asimov by Daniel Williams - November 2020)
        (Multi-range support added April 2026)

        Parameters
        ----------
        ifo : str
            The interferometer name (e.g. ``"H1"``).
        ranges : list of dict
            Each dict must have ``"lower"`` and ``"upper"`` keys specifying
            the frequency band (in Hz) to suppress.  A single dict is also
            accepted for backwards compatibility.
        """
        if isinstance(ranges, dict):
            ranges = [ranges]

        store = Store(root=config.get("storage", "directory"))
        sample_rate = self.production.meta["likelihood"]["sample rate"]
        orig_PSD_file = FrequencySeries.read(psd_file, format="txt")

        self.logger.info("PSD supression has been set")

        freq = orig_PSD_file.frequencies.value

        for r in ranges:
            fmin, fmax = r["lower"], r["upper"]
            self.logger.info(
                f"{ifo}-psd.dat will be supressed between {fmin}-Hz and {fmax}-Hz"
            )
            suppression_region = np.logical_and(
                np.greater_equal(freq, fmin), np.less_equal(freq, fmax)
            )
            orig_PSD_file[suppression_region] = 1.0

        asset = f"{ifo}-psd.dat"
        orig_PSD_file.write(asset, format="txt")

        destination = os.path.join(
            self.category, "psds", str(sample_rate), f"{ifo}-psd.dat"
        )

        for r in ranges:
            self.logger.info(
                f"{ifo}-psd.dat has been supressed between {r['lower']}-Hz and {r['upper']}-Hz"
            )

        try:
            self.production.event.repository.add_file(
                asset, destination
            )  # , message=f"Added the supresed {ifo} PSD")
        except Exception as e:
            self.logger.error(
                "The supressed PSD could not be committed to the repository"
            )
            self.logger.exception(e)

        copyfile(asset, f"{ifo}-{sample_rate}-psd.dat")
        try:
            store.add_file(
                self.production.event.name,
                self.production.name,
                file=f"{ifo}-{sample_rate}-psd.dat",
            )
        except AlreadyPresentException:
            self.logger.warning(
                "Attempted to add a supressed PSD which already exists."
            )

    def resurrect(self):
        """
        Attempt to ressurrect a failed job.
        """
        count = len(glob.glob(os.path.join(self.production.rundir, "*.dag.rescue*")))

        if (count < 5) and (count > 0):
            self.submit_dag()
            self.logger.info(f"Bayeswave job was resurrected for the {count} time.")
        else:
            self.logger.error(
                "Bayeswave resurrection not completed as there have already been 5 attempts"
            )

    def html(self):
        """Return the HTML representation of this pipeline."""
        pages_dir = os.path.join(self.production.event.name, self.production.name)
        out = ""
        if self.production.status in {"finished", "uploaded"}:
            out += """<div class="asimov-pipeline">"""
            out += (
                f"""<p><a href="{pages_dir}/index.html">Full Megaplot output</a></p>"""
            )
            out += f"""<img height=200 src="{pages_dir}/plots/clean_whitened_residual_histograms.png"</src>"""

            out += """</div>"""

        return out

    def collect_pages(self):
        """Collect the HTML output of the pipeline."""
        results_dir = glob.glob(f"{self.production.rundir}/trigtime_*")[0]
        pages_dir = os.path.join(
            config.get("general", "webroot"),
            self.production.event.name,
            self.production.name,
        )
        os.makedirs(pages_dir, exist_ok=True)
        copyfile(
            os.path.join(results_dir, "index.html"),
            os.path.join(pages_dir, "index.html"),
        )
        copytree(
            os.path.join(results_dir, "html"),
            os.path.join(pages_dir, "html"),
            dirs_exist_ok=True,
        )
        copytree(
            os.path.join(results_dir, "plots"),
            os.path.join(pages_dir, "plots"),
            dirs_exist_ok=True,
        )
