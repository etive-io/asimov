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
from filelock import FileLock


class Ledger:
    @classmethod
    def create(cls, name=None, engine=None, location=None):
        """
        Create a ledger.

        Parameters
        ----------
        name : str, optional
            Project name (for YAML ledgers).
        engine : str, optional
            Ledger engine ('yamlfile', 'tinydb', 'sqlalchemy', 'sqlite', 'postgresql').
            If not provided, uses config value.
        location : str, optional
            Ledger file location.

        Returns
        -------
        Ledger
            The created ledger instance.
        """
        if not engine:
            engine = config.get("ledger", "engine")

        if engine == "yamlfile":
            YAMLLedger.create(location=location, name=name)

        elif engine in {"tinydb", "mongodb", "sqlalchemy", "sqlite", "postgresql", "mysql"}:
            DatabaseLedger.create(engine=engine)


class YAMLLedger(Ledger):
    def __init__(self, location=None):
        if not location:
            location = os.path.join(".asimov", "ledger.yml")
        self.location = location
        lock_timeout = int(os.getenv("ASIMOV_LEDGER_FILELOCK_TIMEOUT", "60"))
        self.lock = FileLock(f"{self.location}.lock", timeout=lock_timeout)
        with open(location, "r") as ledger_file:
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

    def __getstate__(self):
        """
        Custom pickle support to exclude the FileLock object.
        FileLock contains thread-local state that cannot be pickled.
        """
        state = self.__dict__.copy()
        # Remove the unpicklable FileLock object
        state.pop('lock', None)
        return state

    def __setstate__(self, state):
        """
        Custom unpickle support to recreate the FileLock object.
        """
        self.__dict__.update(state)
        # Recreate the FileLock with the same configuration
        lock_timeout = int(os.getenv("ASIMOV_LEDGER_FILELOCK_TIMEOUT", "60"))
        self.lock = FileLock(f"{self.location}.lock", timeout=lock_timeout)

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
        with self.lock:  # Acquire exclusive lock for thread-safe saving
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
    Use a database to store the ledger with transaction support.

    This ledger implementation provides:
    - ACID transactions for data integrity
    - Thread-safe operations
    - Advanced querying capabilities
    - Support for concurrent access
    """

    def __init__(self, engine=None):
        """
        Initialize the database ledger.

        Parameters
        ----------
        engine : str, optional
            Database engine ('tinydb', 'sqlalchemy', 'mongodb').
            Defaults to the value in the config.
        """
        if engine is None:
            engine = config.get("ledger", "engine")

        if engine == "tinydb":
            self.db = asimov.database.AsimovTinyDatabase()
        elif engine in {"sqlalchemy", "sqlite", "postgresql", "mysql"}:
            self.db = asimov.database.AsimovSQLDatabase()
        else:
            # Default to SQL database
            self.db = asimov.database.AsimovSQLDatabase()

    @classmethod
    def create(cls, engine=None):
        """
        Create a new database ledger.

        Parameters
        ----------
        engine : str, optional
            Database engine to use.

        Returns
        -------
        DatabaseLedger
            Initialized ledger instance.
        """
        ledger = cls(engine=engine)
        ledger.db._create()
        return ledger

    def _insert(self, payload):
        """
        Store the payload in the correct database table.

        Parameters
        ----------
        payload : Event or Production or ProjectAnalysis
            The object to insert.

        Returns
        -------
        int
            The ID of the inserted record.
        """
        from asimov.analysis import ProjectAnalysis

        if isinstance(payload, Event):
            data = payload.to_dict(productions=False)
            id_number = self.db.insert("event", data)
        elif isinstance(payload, Production):
            data = payload.to_dict(event=False)
            # Ensure event_name is set for SQL database
            if "event" not in data and hasattr(payload, "event"):
                data["event_name"] = payload.event.name
            id_number = self.db.insert("production", data)
        elif isinstance(payload, ProjectAnalysis):
            data = payload.to_dict()
            id_number = self.db.insert("project_analysis", data)
        else:
            raise ValueError(f"Unknown payload type: {type(payload)}")

        return id_number

    @property
    def events(self):
        """
        Return all of the events in the ledger.

        Returns
        -------
        list of Event
            All events.
        """
        return [Event.from_dict(event_dict, ledger=self) for event_dict in self.db.query("event")]

    @property
    def project_analyses(self):
        """
        Return all project analyses in the ledger.

        Returns
        -------
        list of ProjectAnalysis
            All project analyses.
        """
        from asimov.analysis import ProjectAnalysis

        return [
            ProjectAnalysis.from_dict(analysis, ledger=self)
            for analysis in self.db.query("project_analysis")
        ]

    def get_defaults(self):
        """
        Get project-level defaults from the ledger.

        Note: For database ledgers, defaults should be stored in configuration
        rather than the database. This method is kept for compatibility.

        Returns
        -------
        dict
            Default settings (empty for database ledger).
        """
        # For database backend, defaults are in config, not in the database
        # This keeps the database focused on analysis data
        return {}

    def get_event(self, event=None):
        """
        Find a specific event in the ledger and return it.

        Parameters
        ----------
        event : str, optional
            Event name. If None, returns all events.

        Returns
        -------
        Event or list of Event
            The requested event(s).
        """
        if event:
            event_dicts = self.db.query("event", "name", event)
            if not event_dicts:
                raise ValueError(f"Event '{event}' not found in ledger")
            event_dict = event_dicts[0]
            return Event.from_dict(event_dict, ledger=self)
        else:
            return self.events

    def get_productions(self, event=None, filters=None):
        """
        Get productions, optionally filtered.

        Parameters
        ----------
        event : str, optional
            Event name to filter by.
        filters : dict, optional
            Additional filters (e.g., {'status': 'ready', 'pipeline': 'bilby'}).

        Returns
        -------
        list of Production
            Matching productions.

        Examples
        --------
        >>> ledger.get_productions(event='GW150914')
        >>> ledger.get_productions(event='GW150914', filters={'status': 'ready'})
        >>> ledger.get_productions(filters={'pipeline': 'bilby', 'status': 'finished'})
        """
        # Build combined filters
        query_filters = {}
        if event:
            query_filters["event"] = event
        if filters:
            query_filters.update(filters)

        # Query the database
        if isinstance(self.db, asimov.database.AsimovSQLDatabase):
            # Use advanced query capabilities
            production_models = self.db.query_productions(query_filters)
            production_dicts = [p.to_dict() for p in production_models]
        else:
            # Fallback for TinyDB
            if event:
                production_dicts = self.db.query("production", "event", event)
            else:
                production_dicts = self.db.query("production")

            # Apply additional filters manually for TinyDB
            if filters:
                def matches_filters(prod_dict):
                    for key, value in filters.items():
                        if prod_dict.get(key) != value:
                            return False
                    return True

                production_dicts = [p for p in production_dicts if matches_filters(p)]

        # Get the parent event
        if event:
            event_obj = self.get_event(event)
        else:
            event_obj = None

        # Convert to Production objects
        productions = []
        for prod_dict in production_dicts:
            if not event_obj and "event" in prod_dict:
                event_obj = self.get_event(prod_dict["event"])
            productions.append(Production.from_dict(prod_dict, event_obj, ledger=self))

        return productions

    def add_event(self, event):
        """
        Add an event to the ledger.

        Parameters
        ----------
        event : Event
            The event to add.
        """
        self._insert(event)

    def add_subject(self, subject):
        """
        Add a subject (event) to the ledger.

        Parameters
        ----------
        subject : Event
            The subject to add.
        """
        self.add_event(subject)

    def add_production(self, event, production):
        """
        Add a production to an event.

        Parameters
        ----------
        event : Event
            The parent event.
        production : Production
            The production to add.
        """
        self.add_analysis(analysis=production, event=event)

    def add_analysis(self, analysis, event=None):
        """
        Add an analysis to the ledger.

        Parameters
        ----------
        analysis : Production or ProjectAnalysis
            The analysis to add.
        event : Event, optional
            Parent event (required for Productions).
        """
        from asimov.analysis import ProjectAnalysis

        if isinstance(analysis, ProjectAnalysis):
            self._insert(analysis)
        else:
            # It's a Production
            if event is None:
                raise ValueError("Event is required for Production analyses")
            # Set the event reference
            analysis.event = event
            self._insert(analysis)

    def update_event(self, event):
        """
        Update an event in the ledger.

        Parameters
        ----------
        event : Event
            The event to update.
        """
        if isinstance(self.db, asimov.database.AsimovSQLDatabase):
            data = event.to_dict(productions=False)
            self.db.update_event(event.name, data)
        else:
            # For TinyDB, need to implement update logic
            raise NotImplementedError("Update not implemented for TinyDB backend")

    def update_analysis_in_project_analysis(self, analysis):
        """
        Update a project analysis in the ledger.

        Parameters
        ----------
        analysis : ProjectAnalysis
            The analysis to update.
        """
        if isinstance(self.db, asimov.database.AsimovSQLDatabase):
            data = analysis.to_dict()
            # Need to implement project analysis update
            raise NotImplementedError("Project analysis update not yet implemented")
        else:
            raise NotImplementedError("Update not implemented for TinyDB backend")

    def delete_event(self, event_name):
        """
        Delete an event from the ledger.

        Parameters
        ----------
        event_name : str
            The name of the event to delete.
        """
        if isinstance(self.db, asimov.database.AsimovSQLDatabase):
            self.db.delete_event(event_name)
        else:
            raise NotImplementedError("Delete not implemented for TinyDB backend")

    def save(self):
        """
        Save changes to the ledger.

        For database ledgers, this is typically a no-op since changes
        are committed immediately in transactions.
        """
        # Database transactions are handled automatically
        pass
