"""
Convert a project ledger between the YAML and SQL backends.

The conversion works on the plain dictionaries that each backend stores, not
on ``Event``/``Production`` objects, so it never touches repositories, working
directories, or pipelines. The source ledger is only ever read. The
destination is written in full, read back, and compared with the source before
the migration is reported as successful.
"""

import copy
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List

import yaml

import asimov
from asimov.database import AsimovSQLDatabase
from asimov.ledger import DatabaseLedger, YAMLLedger

YAML_ENGINE = "yamlfile"
SQL_ENGINES = {"sqlalchemy", "sqlite", "postgresql", "mysql"}


class MigrationError(Exception):
    """Raised when a ledger cannot be migrated."""


@dataclass
class LedgerContents:
    """
    Backend-neutral snapshot of a ledger.

    Attributes
    ----------
    config : dict
        Everything stored at the top level of the ledger apart from events and
        project analyses (project name, pipeline settings, defaults, ...).
    events : list of dict
        Flat event dictionaries, without their productions.
    productions : dict
        Maps an event name to a list of flat production dictionaries, each of
        which carries its own ``name``.
    project_analyses : list of dict
        Flat project analysis dictionaries.
    """

    config: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    productions: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    project_analyses: List[Dict[str, Any]] = field(default_factory=list)

    def counts(self):
        return {
            "events": len(self.events),
            "productions": sum(len(p) for p in self.productions.values()),
            "project analyses": len(self.project_analyses),
        }


@dataclass
class MigrationReport:
    """The outcome of a migration."""

    counts: Dict[str, int]
    destination: str
    verified: bool
    dry_run: bool = False


def ledger_kind(engine):
    """Return ``"yaml"`` or ``"sql"`` for a configured ledger engine name."""
    if engine == YAML_ENGINE:
        return "yaml"
    if engine in SQL_ENGINES:
        return "sql"
    raise MigrationError(
        f"Ledger engine {engine!r} cannot be migrated; "
        f"supported engines are {YAML_ENGINE!r} and {sorted(SQL_ENGINES)}."
    )


def _database_url(location):
    if "://" in location:
        return location
    return f"sqlite:///{os.path.abspath(location)}"


def _sqlite_path(location):
    """The file behind a SQLite location, or None for any other database."""
    if "://" not in location:
        return os.path.abspath(location)
    if location.startswith("sqlite:///"):
        return os.path.abspath(location[len("sqlite:///"):])
    return None


def _flatten_production(production, event_name=None):
    """Turn ``{name: {...}}`` or a flat production into a flat dictionary."""
    production = DatabaseLedger._normalize_nested_analysis_dict(production)
    production = copy.deepcopy(production)
    production.pop("event", None)
    production.pop("event_name", None)
    if "name" not in production:
        raise MigrationError(f"A production of {event_name!r} has no name.")
    return production


def _contents_from_yaml_data(data, events):
    """Build ``LedgerContents`` from YAML-style event and ledger dictionaries."""
    config = copy.deepcopy(data)
    config.pop("events", None)
    analyses = config.pop("project analyses", None) or []

    contents = LedgerContents(config=config)
    for event in events:
        event = copy.deepcopy(event)
        name = event.get("name")
        if not name:
            raise MigrationError("The ledger contains an event with no name.")
        productions = event.pop("productions", None) or []
        contents.events.append(event)
        contents.productions[name] = [_flatten_production(p, name) for p in productions]
    contents.project_analyses = [
        _flatten_production(a, "project analyses") for a in analyses
    ]
    return contents


def read_yaml_ledger(location, merge_defaults=True):
    """
    Read a YAML ledger into ``LedgerContents``.

    With ``merge_defaults`` the project-level defaults in the file are merged
    into each event, as `YAMLLedger` does when it loads the ledger. SQL
    ledgers don't apply those defaults themselves, so they need to be stored
    on the events when migrating to SQL.
    """
    if not os.path.isfile(location):
        raise MigrationError(f"No YAML ledger found at {location}.")
    try:
        if merge_defaults:
            ledger = YAMLLedger(location=location)
            return _contents_from_yaml_data(ledger.data, ledger.events.values())
        with open(location, "r") as ledger_file:
            data = yaml.safe_load(ledger_file) or {}
        return _contents_from_yaml_data(data, data.get("events") or [])
    except (KeyError, TypeError, AttributeError, yaml.YAMLError) as exc:
        raise MigrationError(
            f"{location} doesn't look like an asimov YAML ledger: {exc!r}"
        ) from exc


def read_sql_ledger(location):
    """Read a SQL ledger into ``LedgerContents``."""
    path = _sqlite_path(location)
    if path is not None and not os.path.isfile(path):
        # Connecting to a missing SQLite file would silently create it.
        raise MigrationError(f"No SQL ledger found at {path}.")
    db = AsimovSQLDatabase(database_url=_database_url(location))
    try:
        contents = LedgerContents(config=db.get_config() or {})
        contents.events = db.query("event")
        for event in contents.events:
            contents.productions[event["name"]] = []
        for production in db.query("production"):
            contents.productions.setdefault(production["event"], []).append(
                _flatten_production(production)
            )
        contents.project_analyses = db.query("project_analysis")
    finally:
        db.engine.dispose()
    return contents


def write_yaml_ledger(contents, location):
    """Write ``contents`` to a new YAML ledger. Refuses to overwrite a file."""
    if os.path.exists(location):
        raise MigrationError(f"{location} already exists; not overwriting it.")

    data = copy.deepcopy(contents.config)
    data["events"] = []
    for event in contents.events:
        event = {k: v for k, v in copy.deepcopy(event).items() if v is not None}
        event["productions"] = [
            {production["name"]: copy.deepcopy(production)}
            for production in contents.productions.get(event["name"], [])
        ]
        data["events"].append(event)
    data["project analyses"] = copy.deepcopy(contents.project_analyses)

    os.makedirs(os.path.dirname(os.path.abspath(location)), exist_ok=True)
    tmp = location + "_tmp"
    with open(tmp, "w") as ledger_file:
        ledger_file.write(yaml.dump(data, default_flow_style=False))
    os.replace(tmp, location)


def write_sql_ledger(contents, location):
    """
    Write ``contents`` into a SQL ledger, which must not contain anything yet.
    """
    path = _sqlite_path(location)
    if path is not None and os.path.exists(path):
        raise MigrationError(f"{path} already exists; not overwriting it.")
    if path is not None:
        os.makedirs(os.path.dirname(path), exist_ok=True)

    db = AsimovSQLDatabase(database_url=_database_url(location))
    try:
        if (
            db.get_config()
            or db.query("event")
            or db.query("production")
            or db.query("project_analysis")
        ):
            raise MigrationError(f"The database at {location} is not empty.")

        if contents.config:
            db.save_config(copy.deepcopy(contents.config))

        for event in contents.events:
            name = event["name"]
            try:
                db.insert_event(DatabaseLedger._prepare_sql_event_data(event))
                for production in contents.productions.get(name, []):
                    row = dict(production, event_name=name)
                    db.insert_production(DatabaseLedger._prepare_sql_production_data(row))
            except Exception as exc:
                raise MigrationError(f"Could not write event {name!r}: {exc}") from exc

        for analysis in contents.project_analyses:
            try:
                db.insert_project_analysis(
                    DatabaseLedger._prepare_sql_project_analysis_data(analysis)
                )
            except Exception as exc:
                name = analysis.get("name")
                raise MigrationError(
                    f"Could not write project analysis {name!r}: {exc}"
                ) from exc
    finally:
        db.engine.dispose()


def _normalise(contents):
    """
    Reduce ``LedgerContents`` to a form that can be compared across backends.

    The backends differ in how they spell absent values (a missing key, ``None``
    or an empty comment) and in how they name the working directory, none of
    which is a real difference between ledgers.
    """

    def clean(record, analysis=False):
        record = {k: v for k, v in record.items() if v is not None}
        if analysis:
            # The SQL schema fills in a missing status.
            record.setdefault("status", "ready")
        if "working_directory" in record:
            record.setdefault("working directory", record.pop("working_directory"))
        if record.get("comment") == "":
            record.pop("comment")
        return record

    events = {}
    for event in contents.events:
        event = clean(event)
        event["productions"] = {
            p["name"]: clean(p, analysis=True) for p in contents.productions.get(event["name"], [])
        }
        events[event["name"]] = event
    return {
        "config": contents.config,
        "events": events,
        "project analyses": {a["name"]: clean(a, analysis=True) for a in contents.project_analyses},
    }


def _diff(a, b, path="") -> Iterator[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b), key=str):
            here = f"{path}/{key}"
            if key not in a:
                yield f"{here}: only in the destination"
            elif key not in b:
                yield f"{here}: missing from the destination"
            else:
                yield from _diff(a[key], b[key], here)
    elif isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            yield f"{path}: {len(a)} items in the source, {len(b)} in the destination"
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                yield from _diff(x, y, f"{path}[{i}]")
    elif a != b:
        yield f"{path}: {a!r} in the source, {b!r} in the destination"


def differences(source, destination):
    """List the differences between two ``LedgerContents``; empty if equivalent."""
    return list(_diff(_normalise(source), _normalise(destination)))


def _read(kind, location, **kwargs):
    reader = read_yaml_ledger if kind == "yaml" else read_sql_ledger
    return reader(location, **kwargs)


def _with_yaml_header(contents):
    """Add the sections a YAML ledger always has, if the source lacked them."""
    contents = copy.deepcopy(contents)
    contents.config.setdefault("asimov", {}).setdefault("version", asimov.__version__)
    contents.config.setdefault("project", {})
    return contents


def _write_and_verify(contents, dest_kind, location):
    """Write ``contents`` to ``location`` and check that it reads back the same."""
    if dest_kind == "yaml":
        contents = _with_yaml_header(contents)
        write_yaml_ledger(contents, location)
        # Read the file as it is stored, without merging defaults into events.
        written = read_yaml_ledger(location, merge_defaults=False)
    else:
        write_sql_ledger(contents, location)
        written = read_sql_ledger(location)

    problems = differences(contents, written)
    if problems:
        shown = "\n  ".join(problems[:20])
        more = f"\n  ... and {len(problems) - 20} more" if len(problems) > 20 else ""
        raise MigrationError(
            "The migrated ledger does not match the original:\n  " + shown + more
        )


def _remove(location):
    path = _sqlite_path(location) or location
    if os.path.exists(path):
        os.remove(path)


def migrate_ledger(
    source_engine, source_location, dest_engine, dest_location, dry_run=False
):
    """
    Copy a ledger from one backend to another.

    The source is left untouched. If the destination cannot be written, or does
    not read back identically, it is removed again and a `MigrationError` is
    raised.

    Parameters
    ----------
    source_engine, dest_engine : str
        Ledger engine names: ``yamlfile`` or one of the SQL engines.
    source_location, dest_location : str
        File paths or, for SQL ledgers, database URLs.
    dry_run : bool
        Do the whole migration into a temporary file and discard it, so that
        problems are found without creating anything. Destinations that
        aren't a local file (e.g. PostgreSQL) can only be checked for being
        readable and convertible, not written.

    Returns
    -------
    MigrationReport
    """
    source_kind = ledger_kind(source_engine)
    dest_kind = ledger_kind(dest_engine)
    if source_kind == dest_kind:
        raise MigrationError(
            f"The source and destination are both {source_kind.upper()} ledgers; "
            "there is nothing to convert."
        )

    contents = _read(source_kind, source_location)

    local = dest_kind == "yaml" or _sqlite_path(dest_location) is not None
    if dry_run:
        verified = False
        if local:
            scratch = tempfile.mkdtemp(prefix="asimov-migrate-")
            try:
                _write_and_verify(
                    contents,
                    dest_kind,
                    os.path.join(scratch, os.path.basename(dest_location) or "ledger"),
                )
                verified = True
            finally:
                shutil.rmtree(scratch, ignore_errors=True)
        return MigrationReport(contents.counts(), dest_location, verified, dry_run=True)

    location = dest_location if dest_kind == "yaml" else _database_url(dest_location)
    # Check this before writing: the cleanup below must only ever remove a
    # file that this migration created.
    if local and os.path.exists(_sqlite_path(location) or location):
        raise MigrationError(f"{dest_location} already exists; not overwriting it.")
    try:
        _write_and_verify(contents, dest_kind, location)
    except BaseException:
        # Don't leave a half-written ledger behind that looks like a real one.
        if local:
            _remove(location)
        raise
    return MigrationReport(contents.counts(), dest_location, verified=True)
