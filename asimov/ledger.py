"""
Code for the project ledger.
"""
import yaml

import os
import shutil

import asimov
import asimov.database
from asimov import config
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
        elif engine == "gitlab":
            raise NotImplementedError(
                "This hasn't been ported to the new interface yet. Stay tuned!"
            )


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
            Event(**self.events[event], ledger=self)
            for event in self.events.keys()
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

    def add_event(self, event):
        if "events" not in self.data:
            self.data["events"] = []

        self.events[event.name] = event.to_dict()
        self.save()

    def add_production(self, event, production):
        event.add_production(production)
        self.events[event.name] = event.to_dict()
        self.save()

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
                lambda x: x.meta[parameter] == value
                if (parameter in x.meta)
                else (
                    getattr(x, parameter) == value if hasattr(x, parameter) else False
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
                lambda x: x.meta[parameter] == value
                if (parameter in x.meta)
                else (
                    getattr(x, parameter) == value if hasattr(x, parameter) else False
                ),
                productions,
            )
            return productions

        if filters:
            for parameter, value in filters.items():
                productions = apply_filter(productions, parameter, value)
        return list(productions)
