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
    def _invalidate_events_cache(self):
        """
        Drop the cached ``events``/``get_event()`` result.

        Every write path that can change which events exist, or what a
        production's dependency graph looks like, must call this. Without
        it, events/productions read once stay stale for the lifetime of
        this ledger instance - including within a single `with project:`
        block, where a just-added event wouldn't show up in `get_event()`
        until the process reloaded the ledger from scratch.
        """
        self._events_cache = None

    def _invalidate_project_analyses_cache(self):
        """Drop the cached ``project_analyses`` result. See _invalidate_events_cache."""
        self._project_analyses_cache = None

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
            if name is None:
                name = config.get("project", "name", fallback=None)
            if name is None:
                raise ValueError("Project name is required when creating a YAML ledger")
            YAMLLedger.create(location=location, name=name)
            return YAMLLedger(location=location)

        elif engine in {"tinydb", "mongodb", "sqlalchemy", "sqlite", "postgresql", "mysql"}:
            database_url = None
            if location:
                database_url = (
                    location if "://" in location
                    else f"sqlite:///{os.path.abspath(location)}"
                )
            return DatabaseLedger.create(name=name, engine=engine, location=database_url)

        raise ValueError(f"Unsupported ledger engine: {engine}")


class YAMLLedger(Ledger):
    def __init__(self, location=None):
        if not location:
            location = os.path.join(".asimov", "ledger.yml")
        self.location = os.path.abspath(location)
        lock_timeout = int(os.getenv("ASIMOV_LEDGER_FILELOCK_TIMEOUT", "60"))
        self.lock = FileLock(f"{self.location}.lock", timeout=lock_timeout)
        with open(location, "r") as ledger_file:
            self.data = yaml.safe_load(ledger_file)

        self.data["events"] = [
            update(self.get_defaults(), event, inplace=False)
            for event in self.data["events"]
        ]

        self.events = {ev["name"]: ev for ev in self.data["events"]}
        self._events_cache = None
        self._project_analyses_cache = None
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
        self._invalidate_events_cache()
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
        self._invalidate_project_analyses_cache()
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
        self._invalidate_events_cache()
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
        self._invalidate_events_cache()
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
            self._invalidate_project_analyses_cache()
        else:
            event.add_production(analysis)
            self.events[event.name] = event.to_dict()
            self._invalidate_events_cache()
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
        if self._project_analyses_cache is None:
            self._project_analyses_cache = [
                ProjectAnalysis.from_dict(analysis, ledger=self)
                for analysis in self.data.get("project analyses", [])
            ]
        return self._project_analyses_cache

    @property
    def _all_events(self):
        if self._events_cache is None:
            self._events_cache = [
                Event(**self.events[name], ledger=self) for name in self.events.keys()
            ]
        return self._events_cache

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

    def __init__(self, engine=None, location=None):
        """
        Initialize the database ledger.

        Parameters
        ----------
        engine : str, optional
            Database engine ('tinydb', 'sqlalchemy', 'mongodb').
            Defaults to the value in the config.
        location : str, optional
            Explicit database location/URL, overriding the config. Lets a
            caller select a specific project's database without mutating
            the process-wide config (e.g. when multiple projects are in
            play in the same process).
        """
        if engine is None:
            engine = config.get("ledger", "engine")

        if engine == "tinydb":
            # `location` may arrive as a bare path (direct construction) or
            # as a `sqlite:///`-prefixed URL (Ledger.create()'s dispatcher
            # URL-ifies bare paths for every non-yaml engine, tinydb
            # included, since that's what AsimovSQLDatabase needs). TinyDB
            # itself just wants a plain path either way.
            tinydb_path = location
            if tinydb_path and tinydb_path.startswith("sqlite:///"):
                tinydb_path = tinydb_path[len("sqlite:///"):]
            self.db = asimov.database.AsimovTinyDatabase(database_path=tinydb_path)
        elif engine in {"sqlalchemy", "sqlite", "postgresql", "mysql"}:
            self.db = asimov.database.AsimovSQLDatabase(database_url=location)
        else:
            # Default to SQL database
            self.db = asimov.database.AsimovSQLDatabase(database_url=location)

        self._events_cache = None
        self._project_analyses_cache = None
        self._data_cache = None

    def __deepcopy__(self, memo):
        # Ledgers are shared singletons; deep-copying one would try to duplicate
        # the underlying database engine (which contains unpicklable module state).
        memo[id(self)] = self
        return self

    @property
    def data(self):
        """
        The ledger-wide configuration dict (compatible with YAMLLedger.data).

        Loaded from the database on first access and cached, so callers
        that do ``update(ledger.data, document)`` followed by
        ``ledger.save()`` (as ``kind: configuration`` blueprints do) mutate
        and persist the same object rather than a throwaway copy. The
        cache can go stale relative to what another process has since
        persisted; ``save()`` merges rather than overwrites for exactly
        that reason, and refreshes this cache to the merged result.
        """
        if self._data_cache is None:
            self._data_cache = self.db.get_config() or {"project": {}, "pipelines": {}}
        return self._data_cache

    @classmethod
    def create(cls, name=None, engine=None, location=None):
        """
        Create a new database ledger.

        Parameters
        ----------
        name : str, optional
            Project name. Seeded into ``ledger.data["project"]["name"]``,
            matching what YAMLLedger.create() does - several read paths
            (`asimov monitor`, `asimov report`) expect it to be there from
            project creation onward, not only once a `kind: configuration`
            blueprint happens to set it.
        engine : str, optional
            Database engine to use.
        location : str, optional
            Explicit database URL, overriding the config. See
            ``DatabaseLedger.__init__``.

        Returns
        -------
        DatabaseLedger
            Initialized ledger instance.
        """
        ledger = cls(engine=engine, location=location)
        ledger.db._create()
        if name is not None:
            ledger.data["project"]["name"] = name
            ledger.save()
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
            if isinstance(self.db, asimov.database.AsimovSQLDatabase):
                data = self._prepare_sql_event_data(data)
            id_number = self.db.insert("event", data)
        elif isinstance(payload, Production):
            data = payload.to_dict(event=False)
            if isinstance(self.db, asimov.database.AsimovSQLDatabase):
                if "event" not in data and hasattr(payload, "event"):
                    data["event"] = payload.event.name
                data = self._prepare_sql_production_data(data)
            id_number = self.db.insert("production", data)
        elif isinstance(payload, ProjectAnalysis):
            data = payload.to_dict()
            if isinstance(self.db, asimov.database.AsimovSQLDatabase):
                data = self._prepare_sql_project_analysis_data(data)
            id_number = self.db.insert("project_analysis", data)
        else:
            raise ValueError(f"Unknown payload type: {type(payload)}")

        # Cheap and conservative: any insert could change what events() or
        # project_analyses() should return, so drop both caches rather than
        # trying to reason about which one this particular payload affects.
        self._invalidate_events_cache()
        self._invalidate_project_analyses_cache()

        return id_number

    @staticmethod
    def _normalize_nested_analysis_dict(data):
        if (
            isinstance(data, dict)
            and len(data) == 1
            and isinstance(next(iter(data.values())), dict)
        ):
            name, payload = next(iter(data.items()))
            normalized = dict(payload)
            normalized.setdefault("name", name)
            return normalized
        return dict(data)

    # Keys that are Python objects and must not be written to the database as JSON.
    _DB_EXCLUDED_META_KEYS = {"ledger", "pipelines"}

    def _prepare_sql_event_data(self, data):
        data = dict(data)
        meta = {}
        if isinstance(data.get("meta"), dict):
            for k, v in data["meta"].items():
                if k not in self._DB_EXCLUDED_META_KEYS:
                    meta[k] = v
        for key, value in data.items():
            if key not in {"name", "repository", "working_directory", "working directory",
                           "meta", "productions"} | self._DB_EXCLUDED_META_KEYS:
                meta[key] = value
        return {
            "name": data.get("name"),
            "repository": data.get("repository"),
            "working_directory": data.get("working_directory", data.get("working directory")),
            "meta": meta,
        }

    def _prepare_sql_production_data(self, data):
        data = self._normalize_nested_analysis_dict(data)
        meta = {}
        if isinstance(data.get("meta"), dict):
            for k, v in data["meta"].items():
                if k not in self._DB_EXCLUDED_META_KEYS:
                    meta[k] = v
        for key, value in data.items():
            if key not in {"name", "event", "event_name", "pipeline", "status", "comment",
                           "meta"} | self._DB_EXCLUDED_META_KEYS:
                meta[key] = value
        return {
            "name": data.get("name"),
            "event_name": data.get("event_name", data.get("event")),
            "pipeline": data.get("pipeline"),
            "status": data.get("status"),
            "comment": data.get("comment"),
            "meta": meta,
        }

    def _prepare_sql_project_analysis_data(self, data):
        data = self._normalize_nested_analysis_dict(data)
        meta = {}
        if isinstance(data.get("meta"), dict):
            for k, v in data["meta"].items():
                if k not in self._DB_EXCLUDED_META_KEYS:
                    meta[k] = v
        for key, value in data.items():
            if key not in {"name", "pipeline", "status", "comment",
                           "meta"} | self._DB_EXCLUDED_META_KEYS:
                meta[key] = value
        return {
            "name": data.get("name"),
            "pipeline": data.get("pipeline"),
            "status": data.get("status"),
            "comment": data.get("comment"),
            "meta": meta,
        }

    @property
    def events(self):
        """
        Return all of the events in the ledger.

        Cached: reconstructing every event (each with its own productions,
        dependency graph, and pipeline objects) is expensive, and this
        property gets read repeatedly within a single command (e.g. the
        monitor loop, report generation). Invalidated by any write via
        _insert/update_event/delete_event.

        Returns
        -------
        list of Event
            All events.
        """
        if self._events_cache is None:
            self._events_cache = [
                self._event_from_dict(event_dict) for event_dict in self.db.query("event")
            ]
        return self._events_cache

    def _event_from_dict(self, event_dict):
        kwargs = dict(event_dict)
        kwargs.pop("ledger", None)
        event = Event(**kwargs, ledger=self)

        # Load productions from the separate productions table.
        for prod_dict in self.db.query("production", "event_name", event.name):
            ledger_backup = event.meta.pop("ledger", None)
            try:
                production = Production.from_dict(prod_dict, event, ledger=self)
                if production.name not in [p.name for p in event.productions]:
                    event.add_production(production)
            except Exception as e:
                import logging as _logging
                _logging.getLogger(__name__).warning(
                    "Skipped loading production %r for event %r: %s",
                    prod_dict.get("name"), event.name, e
                )
            finally:
                if ledger_backup is not None:
                    event.meta["ledger"] = ledger_backup

        event.update_graph()
        return event

    @property
    def project_analyses(self):
        """
        Return all project analyses in the ledger.

        Cached; see the `events` property docstring for why. Invalidated
        by any write via _insert/update_analysis_in_project_analysis.

        Returns
        -------
        list of ProjectAnalysis
            All project analyses.
        """
        from asimov.analysis import ProjectAnalysis

        if self._project_analyses_cache is None:
            self._project_analyses_cache = [
                ProjectAnalysis.from_dict(analysis, ledger=self)
                for analysis in self.db.query("project_analysis")
            ]
        return self._project_analyses_cache

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
            return [self._event_from_dict(event_dict)]
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
            event_obj = self.get_event(event)[0]
        else:
            event_obj = None

        # Convert to Production objects
        productions = []
        for prod_dict in production_dicts:
            production_event = event_obj
            if production_event is None and "event" in prod_dict:
                production_event = self.get_event(prod_dict["event"])[0]
            productions.append(Production.from_dict(prod_dict, production_event, ledger=self))

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
        Update an event in the ledger, inserting it if it does not exist yet.

        Parameters
        ----------
        event : Event
            The event to update.
        """
        if isinstance(self.db, asimov.database.AsimovSQLDatabase):
            event_data = self._prepare_sql_event_data(event.to_dict(productions=False))
            try:
                self.db.update_event(event.name, event_data)
            except ValueError:
                self.db.insert_event(event_data)

            for production in event.productions:
                prod_data = self._prepare_sql_production_data(
                    production.to_dict(event=False)
                )
                prod_data["event_name"] = event.name
                try:
                    self.db.update_production(event.name, production.name, prod_data)
                except ValueError:
                    self.db.insert_production(prod_data)
        else:
            raise NotImplementedError("Update not implemented for TinyDB backend")
        self._invalidate_events_cache()

    def update_analysis_in_project_analysis(self, analysis):
        """
        Update a project analysis in the ledger.

        Parameters
        ----------
        analysis : ProjectAnalysis
            The analysis to update.
        """
        if isinstance(self.db, asimov.database.AsimovSQLDatabase):
            data = self._prepare_sql_project_analysis_data(analysis.to_dict())
            data["status"] = analysis.status
            try:
                self.db.update_project_analysis(analysis.name, data)
            except ValueError:
                self.db.insert_project_analysis(data)
        else:
            raise NotImplementedError("Update not implemented for TinyDB backend")
        self._invalidate_project_analyses_cache()

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
        self._invalidate_events_cache()

    def save(self):
        """
        Save changes to the ledger.

        Event/production/project-analysis writes are committed immediately
        in their own transactions, so this only needs to flush the
        ledger-wide configuration dict (``self.data``) — the one thing a
        caller can mutate in memory (via ``update(ledger.data, ...)``)
        without going through a dedicated write method.

        Merges into the currently-persisted config rather than overwriting
        it wholesale: this ledger instance may be long-lived (e.g. the
        `asimov monitor` loop, which calls save() after every analysis it
        touches) and its cached ``self.data`` can be stale relative to
        config another process wrote in the meantime. An overwrite would
        silently erase that; a merge only risks a conflict on keys this
        instance itself changed. After merging, the cache is refreshed to
        the true persisted state, so it doesn't keep drifting further out
        of date across repeated save() calls in the same process.
        """
        if self._data_cache is not None:
            self._data_cache = self.db.merge_config(self._data_cache)
