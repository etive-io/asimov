"""
Code for the project ledger.
"""

import yaml

import os
import shutil
from functools import reduce

import asimov
import asimov.database
from asimov import config
from asimov.analysis import ProjectAnalysis
from asimov.event import Event, Production
from asimov.utils import update, set_directory


class Ledger:
    @classmethod
    def create(cls, name=None, engine=None, location=None):
        """
        Create a ledger.
        """

        if not engine:
            engine = config.get("ledger", "engine")

        if engine == "yamlfile":
            YAMLLedger.create(location=location, name=name)

        elif engine in {"tinydb", "mongodb"}:
            DatabaseLedger.create()


class YAMLLedger(Ledger):
    def __init__(self, location=None):
        if not location:
            location = os.path.join(".asimov", "ledger.yml")
        self.location = os.path.abspath(location)
        with open(self.location, "r") as ledger_file:
            self.data = yaml.safe_load(ledger_file)

        self.data["events"] = [
            update(self.get_defaults(), event, inplace=False)
            for event in self.data["events"]
        ]

        self.events = {ev["name"]: ev for ev in self.data["events"]}
        self._all_events = [
            Event(**self.events[event], ledger=self) for event in self.events.keys()
        ]
        self.data.pop("events")

    @classmethod
    def create(cls, name, location=None):
        if not location:
            location = os.path.join(".asimov", "ledger.yml")
        data = {}
        data["asimov"] = {}
        data["asimov"]["version"] = asimov.__version__
        data["events"] = []
        data["project analyses"] = []
        data["project"] = {}
        data["project"]["name"] = name
        with open(location, "w") as ledger_file:
            ledger_file.write(yaml.dump(data, default_flow_style=False))

    def update_event(self, event):
        """
        Update an event in the ledger with a changed event object.
        """
        self.events[event.name] = event.to_dict()
        self.save()

    def update_analysis_in_project_analysis(self, analysis):
        """
        Function to update an analysis contained in the project analyses
        """
        for i in range(len(self.data["project analyses"])):
            if self.data["project analyses"][i]["name"] == analysis.name:
                dict_to_save = analysis.to_dict().copy()
                dict_to_save["status"] = analysis.status
                self.data["project analyses"][i] = dict_to_save
        self.save()

    def delete_event(self, event_name):
        """
        Remove an event from the ledger.

        Parameters
        ----------
        event_name : str
           The name of the event to remove from the ledger.
        """
        event = self.events.pop(event_name)
        if "trash" not in self.data:
            self.data["trash"] = {}
        if "events" not in self.data["trash"]:
            self.data["trash"]["events"] = {}
        self.data["trash"]["events"][event_name] = event
        self.save()

    def save(self):
        """
        Update the ledger YAML file with the data from the various events.

        Notes
        -----
        The save function checks the difference between the default values for each production and event
        before saving them, in order to attempt to reduce the duplication within the ledger.


        """
        self.data["events"] = list(self.events.values())
        with set_directory(config.get("project", "root")):
            # First produce a backup of the ledger
            shutil.copy(self.location, self.location + ".bak")
            with open(self.location + "_tmp", "w") as ledger_file:
                ledger_file.write(yaml.dump(self.data, default_flow_style=False))
                ledger_file.flush()
                # os.fsync(ledger_file.fileno())
            os.replace(self.location + "_tmp", self.location)

    def add_subject(self, subject):
        """Add a new subject to the ledger."""
        if "events" not in self.data:
            self.data["events"] = []

        self.events[subject.name] = subject.to_dict()
        self.save()

    def add_event(self, event):
        self.add_subject(subject=event)

    def add_analysis(self, analysis, event=None):
        """
        Add an analysis to the ledger.

        This method can accept any of the forms of analysis supported by asimov, and
        will determine the correct way to add them to the ledger.

        Parameters
        ----------
        analysis : `asimov.Analysis`
           The analysis to be added to the ledger.
        event : str, optional
           The name of the event which the analysis should be added to.
           This is not required for project analyses.

        Examples
        --------
        """
        if isinstance(analysis, ProjectAnalysis):
            # Ensure "project analyses" key exists for old ledgers
            if "project analyses" not in self.data:
                self.data["project analyses"] = []
            names = [ana["name"] for ana in self.data["project analyses"]]
            if analysis.name not in names:
                self.data["project analyses"].append(analysis.to_dict())
            else:
                raise ValueError(
                    "An analysis with that name already exists in the ledger."
                )
        else:
            event.add_production(analysis)
            self.events[event.name] = event.to_dict()
        self.save()

    def add_production(self, event, production):
        self.add_analysis(analysis=production, event=event)

    def get_defaults(self):
        """
        Gather project-level defaults from the ledger.

        At present data, quality, priors, and likelihood settings can all be set at a project level as defaults.
        """
        defaults = {}
        if "data" in self.data:
            defaults["data"] = self.data["data"]
        if "priors" in self.data:
            defaults["priors"] = self.data["priors"]
        if "quality" in self.data:
            defaults["quality"] = self.data["quality"]
        if "likelihood" in self.data:
            defaults["likelihood"] = self.data["likelihood"]
        if "scheduler" in self.data:
            defaults["scheduler"] = self.data["scheduler"]
        return defaults

    @property
    def project_analyses(self):
        return [
            ProjectAnalysis.from_dict(analysis, ledger=self)
            for analysis in self.data.get("project analyses", [])
        ]

    def get_event(self, event=None):
        if event:
            kwargs = self.events[event]
            kwargs.pop("ledger", None)
            return [Event(**kwargs, ledger=self)]
        else:
            return self._all_events

    def get_productions(self, event=None, filters=None):
        """Get a list of productions either for a single event or for all events.

        Parameters
        ----------
        event : str
           The name of the event to pull productions from.
           Optional; if no event is specified then all of the productions are
           returned.

        filters : dict
           A dictionary of parameters to filter on.

        Examples
        --------
        FIXME: Add docs.

        """

        if event:
            productions = self.get_event(event).productions
        else:
            productions = []
            for event_i in self.get_event():
                for production in event_i.productions:
                    productions.append(production)

        def apply_filter(productions, parameter, value):
            productions = filter(
                lambda x: (
                    x.meta[parameter] == value
                    if (parameter in x.meta)
                    else (
                        getattr(x, parameter) == value
                        if hasattr(x, parameter)
                        else False
                    )
                ),
                productions,
            )
            return productions

        if filters:
            for parameter, value in filters.items():
                productions = apply_filter(productions, parameter, value)
        return list(productions)


class DatabaseLedger(Ledger):
    """
    Use a document database to store the ledger.
    """

    def __init__(self):
        if config.get("ledger", "engine") == "tinydb":
            self.db = asimov.database.AsimovTinyDatabase()
        else:
            self.db = asimov.database.AsimovTinyDatabase()

    @classmethod
    def create(cls):
        ledger = cls()
        ledger.db._create()
        return ledger

    def _insert(self, payload):
        """
        Store the payload in the correct database table.
        """

        if isinstance(payload, Event):
            id_number = self.db.insert("event", payload.to_dict(productions=False))
        elif isinstance(payload, Production):
            id_number = self.db.insert("production", payload.to_dict(event=False))

        return id_number

    @property
    def events(self):
        """
        Return all of the events in the ledger.
        """
        return [Event.from_dict(page) for page in self.db.tables["event"].all()]

    def get_defaults(self):
        raise NotImplementedError

    def get_event(self, event=None):
        """
        Find a specific event in the ledger and return it.
        """
        event_dict = self.db.query("event", "name", event)[0]
        return Event.from_dict(event_dict)

    def get_productions(self, event, filters=None, query=None):
        """
        Get all of the productions for a given event.
        """

        if not filters and not query:
            productions = self.db.query("production", "event", event)

        else:
            queries_1 = self.db.Q["event"] == event
            queries = [
                self.db.Q[parameter] == value for parameter, value in filters.items()
            ]
            productions = self.db.tables["production"].search(
                queries_1 & reduce(lambda x, y: x & y, queries)
            )

        event = self.get_event(event)
        return [
            Production.from_dict(dict(production), event) for production in productions
        ]
