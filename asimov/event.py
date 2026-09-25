"""
Trigger handling code.
"""

import glob
import os
import pathlib
from copy import deepcopy
import configparser
import subprocess

import networkx as nx
import yaml
from ligo.gracedb.rest import GraceDb, HTTPError
from liquid import Liquid

from asimov import config, logger, LOGGER_LEVEL
from asimov.pipelines import known_pipelines
from asimov.storage import Store
from asimov.utils import update, diff_dict

from .git import EventRepo
from .ini import RunConfiguration
from .review import Review

status_map = {
    "cancelled": "light",
    "finished": "success",
    "uploaded": "success",
    "processing": "primary",
    "running": "primary",
    "stuck": "warning",
    "restart": "secondary",
    "ready": "secondary",
    "wait": "light",
    "stop": "danger",
    "manual": "light",
    "stopped": "light",
}


class DescriptionException(Exception):
    """Exception for event description problems."""

    def __init__(self, message, issue=None, production=None):
        super(DescriptionException, self).__init__(message)
        self.message = message
        self.issue = issue
        self.production = production

    def __repr__(self):
        text = f"""
An error was detected with the YAML markup in this issue.
Please fix the error and then remove the `yaml-error` label from this issue.
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

    def submit_comment(self):
        """
        Submit this exception as a comment on the gitlab
        issue for the event.
        """
        if self.issue:
            self.issue.add_label("yaml-error", state=False)
            self.issue.add_note(self.__repr__())
        else:
            print(self.__repr__())


class Event:
    """
    A specific gravitational wave event or trigger.
    """

    def __init__(self, name, repository=None, update=False, **kwargs):
        """
        Parameters
        ----------
        update : bool
           Flag to determine if the event repo should be updated
           when it is loaded. Defaults to False.
        """
        self.name = name

        self.logger = logger.getChild("event").getChild(f"{self.name}")
        self.logger.setLevel(LOGGER_LEVEL)

        # pathlib.Path(os.path.join(config.get("logging", "directory"), name)).mkdir(
        #    parents=True, exist_ok=True
        # )
        # logfile = os.path.join(config.get("logging", "directory"), name, "asimov.log")

        # fh = logging.FileHandler(logfile)
        # formatter = logging.Formatter("%(asctime)s - %(message)s", "%Y-%m-%d %H:%M:%S")
        # fh.setFormatter(formatter)
        # self.logger.addHandler(fh)

        if "working_directory" in kwargs:
            self.work_dir = kwargs["working_directory"]
        else:
            self.work_dir = os.path.join(
                config.get("general", "rundir_default"), self.name
            )
        if not os.path.exists(self.work_dir):
            os.makedirs(self.work_dir)

        if "ledger" in kwargs:
            if kwargs["ledger"]:
                self.ledger = kwargs["ledger"]
        else:
            self.ledger = None

        if repository:
            if "git@" in repository or "https://" in repository:
                self.repository = EventRepo.from_url(
                    repository, self.name, directory=None, update=update
                )
            else:
                self.repository = EventRepo(repository)
        elif not repository:
            # If the repository isn't set you'll need to make one
            location = config.get("general", "git_default")
            location = os.path.join(location, self.name)
            self.repository = EventRepo.create(location)

        else:
            self.repository = repository

        if "psds" in kwargs:
            self.psds = kwargs["psds"]
        else:
            self.psds = {}

        self.meta = kwargs

        self.issue_object = None
        if "issue" in kwargs:
            if kwargs["issue"]:
                self.issue_object = kwargs.pop("issue")
                self.from_notes()
        else:
            self.issue_object = None

        self.productions = []
        self.graph = nx.DiGraph()

        if "productions" in kwargs:
            for production in kwargs["productions"]:
                try:
                    self.add_production(
                        Production.from_dict(
                            production, event=self, issue=self.issue_object
                        )
                    )
                except DescriptionException as error:
                    error.submit_comment()

        self.productions = []
        self.graph = nx.DiGraph()

        if "productions" in kwargs:
            for production in kwargs["productions"]:
                try:
                    self.add_production(
                        Production.from_dict(
                            production, event=self, issue=self.issue_object
                        )
                    )
                except DescriptionException as error:
                    error.submit_comment()

        self._check_required()

        if (
            ("interferometers" in self.meta)
            and ("calibration" in self.meta)
            and ("data" in self.meta)
        ):
            try:
                self._check_calibration()
            except DescriptionException:
                pass

    def __eq__(self, other):
        if isinstance(other, Event):
            if other.name == self.name:
                return True
            else:
                return False
        else:
            return False

    def update_data(self):
        if self.ledger:
            self.ledger.update_event(self)
        pass

    def _check_required(self):
        """
        Find all of the required metadata is provided.
        """
        return True

    def _check_calibration(self):
        """
        Find the calibration envelope locations.
        """

        if "calibration" not in self.meta["data"]:
            self.logger.warning("There are no calibration envelopes for this event.")

        elif ("calibration" in self.meta["data"]) and (
            set(self.meta["interferometers"]).issubset(
                set(self.meta["data"]["calibration"].keys())
            )
        ):
            pass

        else:
            self.logger.warning(
                f"""Some of the calibration envelopes are missing from this event. """
                f"""{set(self.meta['interferometers']) - set(self.meta['data']['calibration'].keys())} are absent."""
            )

    def _check_psds(self):
        """
        Find the psd locations.
        """
        if ("calibration" in self.meta) and (
            set(self.meta["interferometers"]) == set(self.psds.keys())
        ):
            pass
        else:
            raise DescriptionException(
                "Some of the required psds are missing from this issue. "
                f"{set(self.meta['interferometers']) - set(self.meta['calibration'].keys())}"
            )

    @property
    def webdir(self):
        """
        Get the web directory for this event.
        """
        if "webdir" in self.meta:
            return self.meta["webdir"]
        else:
            return None

    def add_production(self, production):
        """
        Add an additional production to this event.
        """

        if production.name in [production_o.name for production_o in self.productions]:
            raise ValueError(
                f"A production with this name already exists for {self.name}. New productions must have unique names."
            )

        self.productions.append(production)
        self.graph.add_node(production)

        if production.dependencies:
            dependencies = production.dependencies
            dependencies = [
                production
                for production in self.productions
                if production.name in dependencies
            ]
            for dependency in dependencies:
                self.graph.add_edge(dependency, production)

    def __repr__(self):
        return f"<Event {self.name}>"

    @classmethod
    def from_dict(cls, data, issue=None, update=False, ledger=None):
        """
        Convert a dictionary representation of the event object to an Event object.
        """
        event = cls(**data, issue=issue, update=update, ledger=ledger)
        if ledger:
            ledger.add_event(event)
        return event

    @classmethod
    def from_yaml(cls, data, issue=None, update=False, repo=True, ledger=None):
        """
        Parse YAML to generate this event.

        Parameters
        ----------
        data : str
           YAML-formatted event specification.
        issue : int
           The gitlab issue which stores this event.
        update : bool
           Flag to determine if the repository is updated when loaded.
           Defaults to False.
        ledger : `asimov.ledger.Ledger`
           An asimov ledger which the event should be included in.

        Returns
        -------
        Event
           An event.
        """
        data = yaml.safe_load(data)
        if "kind" in data:
            data.pop("kind")
        if (
            not {
                "name",
            }
            <= data.keys()
        ):
            raise DescriptionException(
                "Some of the required parameters are missing from this issue."
            )

        try:
            calibration = data["data"]["calibration"]
        except KeyError:
            calibration = {}

        if "productions" in data:
            if isinstance(data["productions"], type(None)):
                data["productions"] = []
        else:
            data["productions"] = []

        if "interferometers" in data and "event time" in data:

            if calibration.keys() != data["interferometers"]:
                # We need to fetch the calibration data
                from asimov.utils import find_calibrations

                try:
                    data["data"]["calibration"] = find_calibrations(data["event time"])
                except ValueError:
                    logger.warning(
                        f"Could not find calibration files for {data['name']}"
                    )

        if "working directory" not in data:
            data["working directory"] = os.path.join(
                config.get("general", "rundir_default"), data["name"]
            )

        if not repo and "repository" in data:
            data.pop("repository")
        event = cls.from_dict(data, issue=issue, update=update, ledger=ledger)

        if issue:
            event.issue_object = issue
            event.from_notes()

        return event

    @classmethod
    def from_issue(cls, issue, update=False, repo=True):
        """
        Parse an issue description to generate this event.


        Parameters
        ----------
        update : bool
           Flag to determine if the repository is updated when loaded.
           Defaults to False.
        """

        text = issue.text.split("---")

        event = cls.from_yaml(text[1], issue, update=update, repo=repo)
        event.text = text
        # event.from_notes()

        return event

    def from_notes(self):
        """
        Update the event data from information in the issue comments.

        Uses nested dictionary update code from
        https://stackoverflow.com/questions/3232943/update-value-of-a-nested-dictionary-of-varying-depth#3233356
        """

        notes_data = self.issue_object.parse_notes()
        for note in notes_data:
            update(self.meta, note)

    def get_gracedb(self, gfile, destination):
        """
        Get a file from Gracedb, and store it in the event repository.

        Parameters
        ----------
        gfile : str
           The name of the gracedb file, e.g. `coinc.xml`.
        destination : str
           The location in the repository for this file.
        """

        if "preferred event" in self.meta.get("ligo", {}):
            gid = self.meta["ligo"]["preferred event"]
        else:
            raise ValueError("No preferred event GID is included in this event's metadata.")

        try:
            client = GraceDb(service_url=config.get("gracedb", "url"))
            file_obj = client.files(gid, gfile)

            with open("download.file", "w") as dest_file:
                dest_file.write(file_obj.read().decode())

            if "xml" in gfile:
                # Convert to the new xml format
                command = ["ligolw_no_ilwdchar", "download.file"]
                pipe = subprocess.Popen(
                    command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
                )
                out, err = pipe.communicate()

            self.repository.add_file(
                "download.file",
                destination,
                commit_message=f"Downloaded {gfile} from GraceDB",
            )
            self.logger.info(f"Fetched {gfile} from GraceDB")
        except HTTPError as e:
            self.logger.error(
                f"Unable to connect to GraceDB when attempting to download {gfile}. {e}"
            )
            raise HTTPError(e)

    def to_dict(self, productions=True):
        data = {}
        data["name"] = self.name

        if self.repository.url:
            data["repository"] = self.repository.url
        else:
            data["repository"] = self.repository.directory

        for key, value in self.meta.items():
            data[key] = value
        # try:
        #    data['repository'] = self.repository.url
        # except AttributeError:
        #    pass
        if productions:
            data["productions"] = []
            for production in self.productions:
                # Remove duplicate data
                prod_dict = production.to_dict()[production.name]
                dupes = []
                prod_names = []
                for key, value in prod_dict.items():
                    if production.name in prod_names:
                        continue
                    if key in data:
                        if data[key] == value:
                            dupes.append(key)
                for dupe in dupes:
                    prod_dict.pop(dupe)
                prod_names.append(production.name)
                data["productions"].append({production.name: prod_dict})
        data["working directory"] = self.work_dir
        if "issue" in data:
            data.pop("issue")
        if "ledger" in data:
            data.pop("ledger")
        if "pipelines" in data:
            data.pop("pipelines")
        return data

    def to_yaml(self):
        """Serialise this object as yaml"""
        data = self.to_dict()

        return yaml.dump(data, default_flow_style=False)

    def to_issue(self):
        self.text[1] = "\n" + self.to_yaml()
        return "---".join(self.text)

    def draw_dag(self):
        """
        Draw the dependency graph for this event.
        """
        return nx.draw(self.graph, labelled=True)

    def get_all_latest(self):
        """
        Get all of the jobs which are not blocked by an unfinished job
        further back in their history.

        Returns
        -------
        set
            A set of independent jobs which are not finished execution.
        """
        unfinished = self.graph.subgraph(
            [
                production
                for production in self.productions
                if production.finished is False
            ]
        )
        ends = [
            x
            for x in unfinished.reverse().nodes()
            if unfinished.reverse().out_degree(x) == 0
        ]
        return set(ends)  # only want to return one version of each production!

    def build_report(self):
        for production in self.productions:
            production.build_report()

    def html(self):
        card = f"""
        <div class="card event-data" id="card-{self.name}">
        <div class="card-body">
        <h3 class="card-title">{self.name}</h3>
        """

        card += "<h4>Analyses</h4>"
        card += """<div class="list-group">"""

        for production in self.productions:
            card += production.html()

        card += """</div>"""

        # card += """
        # </div></div>
        # """

        return card


class Production:
    """
    A specific production run.

    Parameters
    ----------
    event : `asimov.event`
        The event this production is running on.
    name : str
        The name of this production.
    status : str
        The status of this production.
    pipeline : str
        This production's pipeline.
    comment : str
        A comment on this production.
    """

    def __init__(self, event, name, status, pipeline, comment=None, **kwargs):
        self.event = event if isinstance(event, Event) else event[0]
        self.subject = self.event
        self.name = name

        pathlib.Path(
            os.path.join(config.get("logging", "directory"), self.event.name, name)
        ).mkdir(parents=True, exist_ok=True)

        self.logger = logger.getChild("analysis").getChild(
            f"{self.event.name}/{self.name}"
        )
        self.logger.setLevel(LOGGER_LEVEL)

        # fh = logging.FileHandler(logfile)
        # formatter = logging.Formatter("%(asctime)s - %(message)s", "%Y-%m-%d %H:%M:%S")
        # fh.setFormatter(formatter)
        # self.logger.addHandler(fh)

        self.category = config.get("general", "calibration_directory")

        if status:
            self.status_str = status.lower()
        else:
            self.status_str = "none"
        self.comment = comment

        # Start by adding pipeline defaults
        if "pipelines" in self.event.ledger.data:
            if pipeline in self.event.ledger.data["pipelines"]:
                self.meta = deepcopy(self.event.ledger.data["pipelines"][pipeline])
            else:
                self.meta = {}
        else:
            self.meta = {}

        if "postprocessing" in self.event.ledger.data:
            self.meta["postprocessing"] = deepcopy(
                self.event.ledger.data["postprocessing"]
            )

        # Update with the event and project defaults
        if "ledger" in self.event.meta:
            self.event.meta.pop("ledger")
        self.meta = update(self.meta, deepcopy(self.event.meta))
        if "productions" in self.meta:
            self.meta.pop("productions")

        self.meta = update(self.meta, kwargs)

        if "sampler" not in self.meta:
            self.meta["sampler"] = {}
        if "cip jobs" in self.meta:
            # TODO: Should probably raise a deprecation warning
            self.meta["sampler"]["cip jobs"] = self.meta["cip jobs"]

        if "scheduler" not in self.meta:
            self.meta["scheduler"] = {}

        if "likelihood" not in self.meta:
            self.meta["likelihood"] = {}
        if "marginalization" not in self.meta["likelihood"]:
            self.meta["likelihood"]["marginalization"] = {}

        if "data" not in self.meta:
            self.meta["data"] = {}
        if "data files" not in self.meta["data"]:
            self.meta["data"]["data files"] = {}

        if "lmax" in self.meta:
            # TODO: Should probably raise a deprecation warning
            self.meta["sampler"]["lmax"] = self.meta["lmax"]

        self.pipeline = pipeline
        self.pipeline = known_pipelines[pipeline.lower()](self)

        if "review" in self.meta:
            self.review = Review.from_dict(self.meta["review"], production=self)
            self.meta.pop("review")
        else:
            self.review = Review()

        # Check that the upper frequency is included, otherwise calculate it
        if (
            "quality" in self.meta
            and ("maximum frequency" not in self.meta["quality"])
            and ("sample rate" in self.meta["likelihood"])
            and len(self.meta["interferometers"]) > 0
        ) or (
            list(self.meta.get("quality", {}).get("maximum frequency", {}).keys())
            != self.meta.get("interferometers")
            and ("sample rate" in self.meta["likelihood"])
        ):
            if "maximum frequency" not in self.meta["quality"]:
                self.meta["quality"]["maximum frequency"] = {}
            # Account for the PSD roll-off with the 0.875 factor
            for ifo in self.meta["interferometers"]:
                psd_rolloff = self.meta.get("likelihood", {}).get(
                    "roll off factor", 0.875
                )
                if ifo not in self.meta["quality"]["maximum frequency"]:
                    self.meta["quality"]["maximum frequency"][ifo] = int(
                        psd_rolloff * self.meta["likelihood"]["sample rate"] / 2
                    )

        # Add a warning about roll-offs
        if not ("roll off time" in self.meta["likelihood"]):
            self.logger.warning(
                "Using the default roll off settings (0.4-seconds); note that these may result in spectral leakage."
            )

        # Get the data quality recommendations
        if "quality" in self.event.meta:
            self.quality = self.event.meta["quality"]
        else:
            self.quality = {}

        if "quality" in self.meta:
            if "quality" in kwargs:
                self.meta["quality"].update(kwargs["quality"])
            self.quality = self.meta["quality"]

        if ("quality" in self.meta) and ("event time" in self.meta):
            if ("segment start" not in self.meta["quality"]) and (
                "segment length" in self.meta["data"]
            ):
                self.meta["likelihood"]["segment start"] = (
                    self.meta["event time"]
                    - self.meta["data"]["segment length"]
                    + self.meta.get("likelihood", {}).get("post trigger time", 2)
                )
                # self.event.meta['likelihood']['segment start'] = self.meta['data']['segment start']

        # Update waveform data
        if "waveform" not in self.meta:
            self.logger.info("Didn't find waveform information in the metadata")
            self.meta["waveform"] = {}
        if "approximant" in self.meta:
            self.logger.warn(
                "Found deprecated approximant information, "
                "moving to waveform area of ledger"
            )
            approximant = self.meta.pop("approximant")
            self.meta["waveform"]["approximant"] = approximant
        if "reference frequency" in self.meta["likelihood"]:
            self.logger.warning(
                "Found deprecated ref freq information, "
                "moving to waveform area of ledger"
            )
            ref_freq = self.meta["likelihood"].pop("reference frequency")
            self.meta["waveform"]["reference frequency"] = ref_freq

        # Gather the PSDs for the job
        self.psds = self._collect_psds()

        # Gather the appropriate prior data for this production
        if "priors" in self.meta:
            self.priors = self.meta["priors"]
            if (
                "amplitude order" in self.meta["priors"]
                and "pn amplitude order" not in self.meta["waveform"]
            ):
                self.meta["waveform"]["pn amplitude order"] = self.meta["priors"][
                    "amplitude order"
                ]

    def __hash__(self):
        return int(f"{hash(self.name)}{abs(hash(self.event.name))}")

    def __eq__(self, other):
        return (self.name == other.name) & (self.event == other.event)

    def _process_dependencies(self, needs):
        """
        Process the dependencies list for this production.
        """
        return needs

    @property
    def dependencies(self):
        if "needs" in self.meta:
            return self._process_dependencies(self.meta["needs"])
        else:
            return None

    def results(self, filename=None, handle=False, hash=None):
        store = Store(root=config.get("storage", "results_store"))
        if not filename:
            try:
                items = store.manifest.list_resources(self.event.name, self.name)
                return items
            except KeyError:
                return None
        elif handle:
            return open(
                store.fetch_file(self.event.name, self.name, filename, hash), "r"
            )
        else:
            return store.fetch_file(self.event.name, self.name, filename, hash=hash)

    @property
    def rel_psds(self):
        """
        Return the relative path to a PSD for a given event repo.
        """
        rels = {}
        for ifo, psds in self.psds.items():
            psd = self.psds[ifo]
            psd = psd.split("/")
            rels[ifo] = "/".join(psd[-3:])
        return rels

    @property
    def reference_frame(self):
        """
        Calculate the appropriate reference frame.
        """
        ifos = self.meta["interferometers"]
        if len(ifos) == 1:
            return ifos[0]
        else:
            return "".join(ifos[:2])

    def get_meta(self, key):
        """
        Get the value of a metadata attribute, or return None if it doesn't
        exist.
        """
        if key in self.meta:
            return self.meta[key]
        else:
            return None

    def set_meta(self, key, value):
        """
        Set a metadata attribute which doesn't currently exist.
        """
        if key not in self.meta:
            self.meta[key] = value
            self.event.ledger.update_event(self.event)
        else:
            raise ValueError

    @property
    def finished(self):
        finished_states = ["uploaded"]
        return self.status in finished_states

    @property
    def status(self):
        return self.status_str.lower()

    @status.setter
    def status(self, value):
        self.status_str = value.lower()
        self.event.ledger.update_event(self.event)

    @property
    def job_id(self):
        if "job id" in self.meta:
            return self.meta["job id"]
        else:
            return None

    @job_id.setter
    def job_id(self, value):
        self.meta["job id"] = value
        if self.event.issue_object:
            self.event.issue_object.update_data()

    def to_dict(self, event=True):
        """
        Return this production as a dictionary.

        Parameters
        ----------
        event : bool
           If set to True the output is designed to be included nested within an event.
           The event name is not included in the representation, and the production name is provided as a key.
        """
        dictionary = deepcopy(self.meta)
        if not event:
            dictionary["event"] = self.event.name
            dictionary["name"] = self.name

        dictionary["status"] = self.status
        dictionary["pipeline"] = self.pipeline.name.lower()
        dictionary["comment"] = self.comment

        dictionary["review"] = self.review.to_dicts()

        if "data" in self.meta:
            dictionary["data"] = self.meta["data"]
        if "likelihood" in self.meta:
            dictionary["likelihood"] = self.meta["likelihood"]
        if "quality" in self.meta:
            dictionary["quality"] = self.meta["quality"]
        if "priors" in self.meta:
            dictionary["priors"] = self.meta["priors"]
        if "waveform" in self.meta:
            dictionary["waveform"] = self.meta["waveform"]
        dictionary["needs"] = self.dependencies
        dictionary["job id"] = self.job_id

        # Remove duplicates of pipeline defaults
        if "pipelines" in self.event.ledger.data and self.pipeline.name.lower() in self.event.ledger.data["pipelines"]:
            defaults = deepcopy(
                self.event.ledger.data["pipelines"][self.pipeline.name.lower()]
            )
        else:
            defaults = {}

        if "postprocessing" in self.event.ledger.data:
            defaults["postprocessing"] = deepcopy(
                self.event.ledger.data["postprocessing"]
            )

        if "ledger" in self.event.meta:
            self.event.meta.pop("ledger")

        defaults = update(defaults, deepcopy(self.event.meta))

        dictionary = diff_dict(defaults, dictionary)

        for key, value in self.meta.items():
            if key == "operations":
                continue
        if "repository" in self.meta:
            dictionary["repository"] = self.repository.url
        if "ledger" in dictionary:
            dictionary.pop("ledger")
        if "pipelines" in dictionary:
            dictionary.pop("pipelines")

        if "productions" in dictionary:
            dictionary.pop("productions")

        if not event:
            output = dictionary
        else:
            output = {self.name: dictionary}
        return output

    @property
    def rundir(self):
        """
        Return the run directory for this event.
        """
        if "rundir" in self.meta:
            return os.path.abspath(self.meta["rundir"])
        elif "working directory" in self.event.meta:

            value = os.path.join(self.event.meta["working directory"], self.name)
            self.meta["rundir"] = value
            return os.path.abspath(value)
        else:
            return None

    @rundir.setter
    def rundir(self, value):
        """
        Set the run directory.
        """
        if "rundir" not in self.meta:
            self.meta["rundir"] = value
            if self.event.issue_object is not None:
                self.event.issue_object.update_data()
        else:
            raise ValueError

    def get_psds(self, format="ascii", sample_rate=None):
        """
        Get the PSDs for this production.

        Parameters
        ----------
        format : {ascii, xml}
           The format of the PSD to be returned.
           Defaults to the ascii format.
        sample_rate : int
           The sample rate of the PSD to be returned.
           Defaults to None, in which case the sample rate in the event data is used.

        Returns
        -------
        list
           A list of PSD files for the production.
        """
        if sample_rate is None:
            try:
                if (
                    "likelihood" in self.meta
                    and "sample rate" in self.meta["likelihood"]
                ):
                    sample_rate = self.meta["likelihood"]["sample rate"]
                else:
                    raise DescriptionException(
                        "The sample rate for this event cannot be found.",
                        issue=self.event.issue_object,
                        production=self.name,
                    )
            except Exception as e:
                raise DescriptionException(
                    "The sample rate for this event cannot be found.",
                    issue=self.event.issue_object,
                    production=self.name,
                ) from e

        if (len(self.psds) > 0) and (format == "ascii"):
            return self.psds
        elif format == "xml":
            # TODO: This is a hack, and we need a better way to sort this.
            files = glob.glob(
                f"{self.event.repository.directory}/{self.category}/psds/{sample_rate}/*.xml.gz"
            )
            return files

    def get_timefile(self):
        """
        Find this event's time file.

        Returns
        -------
        str
           The location of the time file.
        """
        try:
            return self.event.repository.find_timefile(self.category)
        except FileNotFoundError:
            new_file = os.path.join("gps.txt")
            with open(new_file, "w") as f:
                f.write(f"{self.event.meta['event time']}")
            self.logger.info(
                f"Created a new time file in {new_file} with time {self.event.meta['event time']}"
            )
            self.event.repository.add_file(
                new_file,
                os.path.join(self.category, new_file),
                "Added a new GPS timefile.",
            )
            return new_file

    def get_coincfile(self):
        """
        Find this event's coinc.xml file.

        Returns
        -------
        str
           The location of the time file.
        """
        try:
            coinc = self.event.repository.find_coincfile(self.category)
            return coinc
        except FileNotFoundError:
            self.logger.info("Could not find a coinc.xml file")
            savepath = os.path.abspath(
                os.path.join(
                    self.event.repository.directory, self.category, "coinc.xml"
                ),
            )
            print(savepath)
            self.event.get_gracedb(
                "coinc.xml",
                savepath,
            )
            coinc = self.event.repository.find_coincfile(self.category)
            return coinc

    def get_configuration(self):
        """
        Get the configuration file contents for this event.
        """
        if "ini" in self.meta:
            ini_loc = self.meta["ini"]
        else:
            # We'll need to search the repository for it.
            try:
                ini_loc = self.event.repository.find_prods(self.name, self.category)[0]
                if not os.path.exists(ini_loc):
                    raise ValueError("Could not open the ini file.")
            except IndexError:
                raise ValueError("Could not open the ini file.")
        try:
            ini = RunConfiguration(ini_loc)
        except ValueError:
            raise ValueError("Could not open the ini file")
        except configparser.MissingSectionHeaderError:
            raise ValueError("This isn't a valid ini file")

        return ini

    @classmethod
    def from_dict(cls, parameters, event, issue=None):
        name, pars = list(parameters.items())[0]
        # Normalise None metadata (production stored as {name: null})
        if pars is None:
            pars = {}
        # Check that pars is a dictionary
        if not isinstance(pars, dict):
            if "event" in parameters:
                parameters.pop("event")

            if "status" not in parameters:
                parameters["status"] = "ready"

            return cls(event=event, **parameters)

        # Check all of the required parameters are included
        if not {"status", "pipeline"} <= pars.keys():
            raise DescriptionException(
                f"Some of the required parameters are missing from {name}", issue, name
            )
        if "comment" not in pars:
            pars["comment"] = None
        if "event" in pars:
            pars.pop(event)

        return cls(event, name, **pars)

    def __repr__(self):
        return f"<Production {self.name} for {self.event} | status: {self.status}>"

    def _collect_psds(self, format="ascii"):
        """
        Collect the required psds for this production.
        """
        psds = {}
        # If the PSDs are specifically provided in the ledger,
        # use those.

        if format == "ascii":
            keyword = "psds"
        elif format == "xml":
            keyword = "xml psds"
        else:
            raise ValueError(f"This PSD format ({format}) is not recognised.")

        if keyword in self.meta:
            # if self.meta["likelihood"]["sample rate"] in self.meta[keyword]:
            psds = self.meta[keyword]  # [self.meta["likelihood"]["sample rate"]]

        # First look through the list of the job's dependencies
        # to see if they're provided by a job there.
        elif self.dependencies:
            productions = {}
            for production in self.event.productions:
                productions[production.name] = production

            for previous_job in self.dependencies:
                try:
                    # Check if the job provides PSDs as an asset and were produced with compatible settings
                    if keyword in productions[previous_job].pipeline.collect_assets():
                        if self._check_compatible(productions[previous_job]):
                            psds = productions[previous_job].pipeline.collect_assets()[
                                keyword
                            ]
                            break
                        else:
                            self.logger.info(
                                f"The PSDs from {previous_job} are not compatible with this job."
                            )
                    else:
                        psds = {}
                except Exception:
                    psds = {}
        # Otherwise return no PSDs
        else:
            psds = {}

        for ifo, psd in psds.items():
            self.logger.debug(f"PSD-{ifo}: {psd}")

        return psds

    def _check_compatible(self, other_production):
        """
        Check that the data settings in two productions are sufficiently compatible
        that one can be used as a dependency of the other.
        """
        compatible = True

        # Check that the sample rate of this analysis is equal or less than that of the preceeding analysis
        # to ensure that PSDs have points at the correct frequencies.
        try:
            compatible = self.meta.get("likelihood", {}).get(
                "sample rate", None
            ) <= other_production.meta.get("likelihood", {}).get("sample rate", None)
        except TypeError:
            # One or more sample rates are missing so these can't be deemed compatible.
            return False
        tests = [
            ("data", "channels"),
            ("data", "frame types"),
            ("data", "segment length"),
        ]
        for test in tests:
            compatible &= self.meta.get(test[0], {}).get(
                test[1], None
            ) == other_production.meta.get(test[0], {}).get(test[1], None)
        return compatible

    def make_config(self, filename, template_directory=None, dryrun=False):
        """
        Make the configuration file for this production.

        Parameters
        ----------
        filename : str
           The location at which the config file should be saved.
        template_directory : str, optional
           The path to the directory containing the pipeline config templates.
           Defaults to the directory specified in the asimov configuration file.
        """

        self.logger.info("Creating config file.")

        self.psds = self._collect_psds()
        self.xml_psds = self._collect_psds(format="xml")

        if "template" in self.meta:
            template = f"{self.meta['template']}.ini"
        else:
            template = f"{self.pipeline.name.lower()}.ini"

        pipeline = self.pipeline
        if hasattr(pipeline, "config_template"):
            template_file = pipeline.config_template
        else:
            try:
                template_directory = config.get("templating", "directory")
                template_file = os.path.join(f"{template_directory}", template)
                if not os.path.exists(template_file):
                    raise Exception
            except Exception:
                from pkg_resources import resource_filename

                template_file = resource_filename("asimov", f"configs/{template}")

        self.logger.info(f"Using {template_file}")

        liq = Liquid(template_file)
        rendered = liq.render(production=self, config=config)

        if not dryrun:
            with open(filename, "w") as output_file:
                output_file.write(rendered)
            self.logger.info(f"Saved as {filename}")
        else:
            print(rendered)

    def build_report(self):
        if self.pipeline:
            self.pipeline.build_report()

    def html(self):
        """
        An HTML representation of this production.
        """
        production = self

        card = ""

        card += f"<div class='asimov-analysis asimov-analysis-{self.status}'>"
        card += f"<h4>{self.name}"

        if self.comment:
            card += (
                f"""  <small class="asimov-comment text-muted">{self.comment}</small>"""
            )
        card += "</h4>"
        if self.status:
            card += f"""<p class="asimov-status">
  <span class="badge badge-pill badge-{status_map[self.status]}">{self.status}</span>
</p>"""

        if self.pipeline:
            card += f"""<p class="asimov-pipeline-name">{self.pipeline.name}</p>"""

        if self.pipeline:
            # self.pipeline.collect_pages()
            card += self.pipeline.html()

        if self.rundir:
            card += f"""<p class="asimov-rundir"><code>{production.rundir}</code></p>"""
        else:
            card += """&nbsp;"""

        if "approximant" in production.meta:
            card += f"""<p class="asimov-attribute">Waveform approximant:
   <span class="asimov-approximant">{production.meta['approximant']}</span>
</p>"""

        card += """&nbsp;"""
        card += """</div>"""

        if len(self.review) > 0:
            for review in self.review:
                card += review.html()

        return card
