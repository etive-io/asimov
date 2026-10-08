"""
Tools for adding data from JSON and YAML files.
Inspired by the kubectl apply approach from kubernetes.
"""

import json
import os
import re
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import click
import requests
import yaml

from asimov import LOGGER_LEVEL, logger
from asimov.context import current_context
from asimov.audit import PROJECT, append_audit, new_record
from asimov.preview import changed_paths, current_plan, is_dry_run, preview, recording
from asimov.principal import current_principal
import asimov.event
from asimov.analysis import ProjectAnalysis
from asimov.ledger import Ledger
from asimov.utils import update
from asimov.strategies import (
    StrategyContext,
    StrategyError,
    expand_strategy,
    is_plugin_strategy,
    plugin_info,
    read_group,
    write_group,
)
from copy import deepcopy
from datetime import datetime
import sys

if sys.version_info < (3, 10):
    from importlib_metadata import entry_points
else:
    from importlib.metadata import entry_points


logger = logger.getChild("cli").getChild("apply")
logger.setLevel(LOGGER_LEVEL)


#: The key under which an analysis records who requested it.
REQUESTED_BY = "requested by"


def _audited(ledger, kind, target, content, outcome="added", diff=None):
    """
    Record that a document was applied.

    Call it inside ``ledger.transaction()``, in the same block as the change,
    so the record and the change are stored together or not at all.

    In a dry run nothing is recorded: the change which would have been made,
    and the audit record which would have been written for it, go into the
    plan instead.
    """
    record = new_record("apply", kind, target, content=content, outcome=outcome)
    if is_dry_run():
        current_plan().add_change(record, diff)
        return
    stored = append_audit(ledger, record)
    if current_plan() is not None:
        current_plan().add_change(stored, diff)


# The colours messages are given, which say what they are about.
_RED = "\x1b[31m"
_YELLOW = "\x1b[33m"


def _say(message):
    """
    Tell the user something about what is being applied.

    In a dry run nothing is said: a document which would be refused, or left
    out of a bundle, is noted in the plan (messages in red and yellow, as
    ``click.style`` makes them), and the rest, which says what was done,
    would be untrue. When a record is being kept of what is applied, the same
    are noted in it, and the message is still said.
    """
    plan = current_plan()
    if plan is not None:
        if _RED in message:
            plan.refuse(click.unstyle(message).lstrip("● ").strip(), "refused")
        elif _YELLOW in message:
            plan.refuse(click.unstyle(message).lstrip("● ").strip(), "skipped")
    if not is_dry_run():
        click.echo(message)


def _event_snapshot(ledger, name):
    """What is stored for an event, less what is not event-level, for comparing."""
    if getattr(ledger, "db", None) is None:
        data = deepcopy(ledger.events[name])
    else:
        data = deepcopy(ledger.get_event(name)[0].meta)
    for key in ("name", "productions", "working directory", "repository", "ledger"):
        data.pop(key, None)
    return data


def _event_diff(before, ledger, name):
    """What changed for an event, in a dry run (``before`` is ``None`` otherwise)."""
    return None if before is None else changed_paths(before, _event_snapshot(ledger, name))


def _requested_by():
    """
    Who is requesting what is being applied now, as data for the ledger.

    Always the current principal, never anything the blueprint says: a
    blueprint is content from the requester, and must not be able to name
    someone else, since this is what accounting and review rules rely on.
    """
    return current_principal().to_dict()


def get_ledger():
    """
    Get the current ledger instance.

    Reloads the ledger to ensure we have the latest state,
    preventing issues where the ledger is cached at import time.

    If called from inside a ``with project:`` block, returns
    ``project.ledger`` instead of constructing a fresh ``Ledger``, since
    only ``project.ledger`` is saved when that block exits -- mutations
    made via an independently constructed ledger would otherwise be
    silently discarded.

    Returns
    -------
    Ledger
        The current ledger instance.
    """
    from asimov.context import get_active_context

    active = get_active_context()
    if active is not None:
        return active.ledger

    from asimov import config
    if config.get("ledger", "engine") == "yamlfile":
        from asimov.ledger import YAMLLedger
        return YAMLLedger(config.get("ledger", "location"))
    else:
        from asimov import current_ledger
        return current_ledger


def _raw_production_names(ledger, event_name):
    """Return the set of production names for an event from raw ledger data.

    Reads directly from ``ledger.events`` (a plain dict) or, for the database
    ledger, from the stored rows, rather than constructing a full ``Event``
    object, avoiding expensive git and Production initialisation just to
    obtain a set of strings.
    """
    names = set()
    db = getattr(ledger, "db", None)
    if db is not None:
        # The database ledger: read the persisted rows directly. Loading the
        # event would skip any analysis which fails to load, and collapse
        # duplicates, so its names could be handed out a second time.
        return {row["name"] for row in db.query("production", "event_name", event_name)}
    events = ledger.events
    for prod in events.get(event_name, {}).get("productions", []):
        if isinstance(prod, dict) and len(prod) == 1:
            names.add(next(iter(prod)))
        elif isinstance(prod, dict) and "name" in prod:
            names.add(prod["name"])
    return names


def next_available_name(name, existing_names):
    """Return the next available analysis name, incrementing a numeric suffix if needed.

    If ``name`` is not already taken, it is returned unchanged.  Otherwise the
    trailing ``-N`` suffix (if present) is stripped to find the stem, and the
    lowest integer >= 2 that produces a free name is appended.

    Examples
    --------
    >>> next_available_name("bilby-IMRPhenomXPHM", {"bilby-IMRPhenomXPHM"})
    'bilby-IMRPhenomXPHM-2'
    >>> next_available_name("bilby-IMRPhenomXPHM-2", {"bilby-IMRPhenomXPHM-2"})
    'bilby-IMRPhenomXPHM-3'
    """
    if name not in existing_names:
        return name
    match = re.match(r"^(.*)-(\d+)$", name)
    stem, n = (match.group(1), int(match.group(2))) if match else (name, 1)
    n += 1
    while f"{stem}-{n}" in existing_names:
        n += 1
    return f"{stem}-{n}"


# Analyses in these states have not yet used the event settings, so an event
# update with update_unstarted=True lets them inherit the new values.
UNSTARTED_STATES = {"ready", "wait"}


def _refresh_inherited(analysis_meta, old_event, new_event):
    """
    Give an analysis the new event values for every setting it merely
    inherited (i.e. still equal to the old event value), leaving any setting
    the analysis overrides untouched.
    """
    for key, value in new_event.items():
        current = analysis_meta.get(key)
        if isinstance(value, dict) and isinstance(current, dict):
            _refresh_inherited(current, old_event.get(key) or {}, value)
        elif key not in analysis_meta or current == old_event.get(key):
            analysis_meta[key] = deepcopy(value)


def _update_event_in_database_ledger(ledger, event_obj, update_unstarted=False):
    """
    Merge a new event definition into an existing event in a database ledger.

    The analyses attached to the event are never removed. Event-level
    settings which are about to be changed are frozen into each analysis
    (unless the analysis already sets them) so that existing analyses keep
    the configuration they were created with, and the previous event
    settings are kept in the ledger history. If update_unstarted is set,
    analyses which have not yet started are left to inherit the new values.
    """
    existing = ledger.get_event(event_obj.name)[0]
    old_event = deepcopy(existing.meta)
    for key in ["name", "productions", "working directory", "repository", "ledger"]:
        old_event.pop(key, None)

    new_meta = deepcopy(event_obj.meta)
    new_meta.pop("ledger", None)

    for production in existing.productions:
        if update_unstarted and str(production.status).lower() in UNSTARTED_STATES:
            _refresh_inherited(production.meta, old_event, new_meta)
            continue
        merged = update(deepcopy(old_event), production.meta)
        production.meta.clear()
        production.meta.update(merged)

    history = ledger.data.setdefault("history", {})
    event_history = history.setdefault(event_obj.name, {})
    version = f"version-{len(event_history) + 1}"
    event_history[version] = old_event
    event_history[version]["date changed"] = datetime.now().isoformat()

    update(existing.meta, new_meta)
    ledger.update_event(existing)
    ledger.save()


class _StrategyGroup:
    """The documents which one plugin strategy made from one blueprint."""

    def __init__(self, identifier, total):
        self.identifier = identifier
        self.total = total
        #: How many of them already existed, and so were left as they were.
        self.skipped = 0

    def skip(self, description):
        """Note that a document was left alone, because the strategy made it before."""
        logger.info(f"{description} already exists; it was made by this strategy, so it is left as it is")
        self.skipped += 1

    def summary(self):
        return (
            click.style("●", fg="yellow")
            + f" {self.skipped} of {self.total} documents of '{self.identifier}' already existed"
            + " (made by this strategy) and were left as they are"
        )


def _record_group(ledger, identifier, record, outcome):
    """Store the record of a group, and audit it (or, in a dry run, plan it)."""
    with ledger.transaction():
        write_group(ledger, identifier, record)
        ledger.save()
        _audited(
            ledger,
            "strategygroup",
            f"{PROJECT}/{identifier}",
            record,
            outcome=outcome,
        )


def _expand_strategies(documents, ledger, event):
    """
    Expand the plugin strategies in the documents of a blueprint.

    Yields the documents which are to be applied, each with the
    :class:`_StrategyGroup` it came from, or ``None`` if it is not from a
    strategy. A document with a plugin strategy is replaced by what the
    strategy makes of it, which can be documents of other kinds than its own
    (a subject, and the analyses which are in it). A matrix strategy is not
    expanded here: that is done when the analysis is applied.

    Everything a strategy returns is checked before the first of it is yielded,
    including that each analysis is for a subject which exists, or which the
    strategy makes before it, so a mistake applies nothing from that blueprint.

    Parameters
    ----------
    documents : iterable of dict
        The documents of the blueprint.
    ledger : Ledger
        The project's.
    event : str, optional
        The subject which the analyses are for, if the command was given one.
    """
    for document in documents:
        if not (
            str(document.get("kind", "")).lower() == "analysis"
            and is_plugin_strategy(document.get("strategy"))
        ):
            yield document, None
            continue

        blueprint_event = document.get("event")
        known_event = event or blueprint_event
        strategy_type = document["strategy"]["type"]
        identifier = document.get("name")

        # A group is named by its blueprint, and the name is unique in the
        # project: it is how the group is found again (to add to it, or to
        # change it), so a second blueprint of that name is not another group.
        previous = read_group(ledger, identifier) if isinstance(identifier, str) else None
        if previous is not None and previous.get("type") != strategy_type:
            raise StrategyError(
                f"'{identifier}' is already the name of a group made by the "
                f"'{previous.get('type')}' strategy. Group names are unique in the project: "
                "use another name for this one."
            )

        emitted = expand_strategy(
            deepcopy(document),
            StrategyContext(ledger=ledger, event=known_event, group=previous),
        )

        # Which subject each analysis is for. One which names none is for the
        # subject of the command, or of the blueprint, or that which the user
        # is asked for (once, for all of them). The command's subject replaces
        # one which the strategy only copied from the blueprint.
        default_event = known_event
        for emitted_document in emitted:
            if emitted_document["kind"] != "analysis":
                continue
            own = emitted_document.get("event")
            if event and own in (None, blueprint_event):
                emitted_document["event"] = event
            elif own is None:
                if default_event is None:
                    count = sum(1 for d in emitted if d["kind"] == "analysis" and "event" not in d)
                    default_event = str(
                        click.prompt(
                            f"Which event should these {count} analyses be applied to?"
                            if count > 1
                            else "Which event should these be applied to?"
                        )
                    )
                emitted_document["event"] = default_event

        if (
            previous is not None
            and previous.get("event")
            and default_event
            and previous["event"] != default_event
        ):
            raise StrategyError(
                f"The group '{identifier}' is for the subject '{previous['event']}', and this "
                f"blueprint is for '{default_event}'. Group names are unique in the project: "
                f"apply it to '{previous['event']}' again, or use another name."
            )

        preexisting = set(StrategyContext(ledger=ledger).subjects())
        existing = set(preexisting)
        for emitted_document in emitted:
            kind = emitted_document["kind"]
            if kind in ("event", "subject"):
                existing.add(emitted_document["name"])
            elif kind == "analysis" and emitted_document["event"] not in existing:
                raise StrategyError(
                    f"The strategy '{document['strategy']['type']}' made the analysis "
                    f"'{emitted_document['name']}' for the subject '{emitted_document['event']}', "
                    "which does not exist and is not made before it by the strategy."
                )

        # The subjects this group made: those it made before, and those it makes
        # now. One which is already there was not made by the group.
        made = sorted(
            set((previous or {}).get("subjects", []))
            | {
                d["name"]
                for d in emitted
                if d["kind"] in ("event", "subject") and d["name"] not in preexisting
            }
        )
        record = {
            "type": strategy_type,
            "blueprint": {k: v for k, v in document.items() if k != "kind"},
            "event": default_event,
            "subjects": made,
            "plugin": (previous or {}).get("plugin") or plugin_info(strategy_type),
        }
        if previous is not None and "last extended with" in previous:
            record["last extended with"] = previous["last extended with"]
        if previous is None:
            _record_group(ledger, identifier, record, "added")
        elif {k: v for k, v in previous.items()} != record:
            _record_group(ledger, identifier, record, "updated")

        group = _StrategyGroup(identifier, len(emitted))
        for emitted_document in emitted:
            yield emitted_document, group
        if group.skipped:
            _say(group.summary())

        # Documents added to a group which was made before are an extension of
        # it, perhaps by a different version of the package.
        if previous is not None and group.total > group.skipped:
            record["last extended with"] = plugin_info(strategy_type)
            _record_group(ledger, identifier, record, "updated")


def apply_page(file, event=None, ledger=None, update_page=False, name=None, iterate=False, update_unstarted=False, dry_run=False):
    """
    Apply the documents in a blueprint to the project.

    Parameters
    ----------
    file : str
        The blueprint: a path, or a URL.
    event : str, optional
        The event which analyses in the blueprint should be applied to.
    ledger : Ledger, optional
        The ledger to apply to. Defaults to the active project's.
    update_page : bool
        Update what already exists rather than add new records.
    name, iterate, update_unstarted
        See ``asimov apply --help``.
    dry_run : bool
        Don't apply anything: work out what would be applied, and return it.

    Returns
    -------
    asimov.preview.ApplyPlan
        The changes made, in order, and what was refused, each change in the
        form of the audit record which was written for it. With ``dry_run``,
        the changes which would be made instead, each in the form of the audit
        record which applying it would add: nothing is written to the ledger,
        to the audit log, to disk (no directories are made and nothing is
        cloned), or sent to telemetry sinks.
    """
    if update_unstarted:
        update_page = True
    # Get ledger if not provided
    if ledger is None:
        ledger = get_ledger()

    if current_plan() is None:
        # The outermost call: keep a record of what happens, and make it a
        # preview if that was asked for.
        with (preview(ledger) if dry_run else recording()) as plan:
            apply_page(
                file,
                event=event,
                ledger=ledger,
                update_page=update_page,
                name=name,
                iterate=iterate,
                update_unstarted=update_unstarted,
            )
        return plan

    if file.startswith("http://") or file.startswith("https://"):
        r = requests.get(file)
        if r.status_code == 200:
            data = r.text
            logger.info(f"Downloaded {file}")
        else:
            raise ValueError(f"Could not download this file: {file}")
    else:
        with open(file, "r") as apply_file:
            data = apply_file.read()

    quick_parse = yaml.safe_load_all(
        data
    )  # Load as a dictionary so we can identify the object type it contains

    # Events loaded for applying analyses, by name. Loading an event builds every
    # analysis in it, so doing that once per analysis made applying a large
    # blueprint quadratic in the number of analyses. Each analysis which is added
    # is also added to its cached event, so the next one is built against the same
    # state a reload would give. Any other kind of document may change an event,
    # so it empties the cache.
    loaded_events = {}

    for document, group in _expand_strategies(quick_parse, ledger, event):
        if document["kind"] != "analysis":
            loaded_events.clear()
        doc_kind = {"subject": "event"}.get(
            str(document["kind"]).lower(), str(document["kind"]).lower()
        )
        if document["kind"] in ("event", "subject"):
            logger.info("Found an event")
            document.pop("kind")
            event_obj = asimov.event.Event.from_yaml(yaml.dump(document))

            # Check if the event is in the ledger already. ledger.events is a
            # plain dict for the YAML ledger, so that is cheap. For the database
            # ledger it builds every event, and every analysis in them, so ask
            # for just this event's row instead: doing the former for each event
            # in a blueprint made applying many subjects quadratic.
            database = getattr(ledger, "db", None)
            if database is None:
                event_exists = event_obj.name in ledger.events
            else:
                event_exists = len(database.query("event", "name", event_obj.name)) > 0

            if event_exists and group is not None:
                # Made by the strategy before; applying it again leaves it be.
                group.skip(f"The subject {event_obj.name}")
                continue

            if event_exists and update_page is True and database is not None:
                before = _event_snapshot(ledger, event_obj.name) if is_dry_run() else None
                with ledger.transaction():
                    _update_event_in_database_ledger(
                        ledger, event_obj, update_unstarted=update_unstarted
                    )
                    _audited(
                        ledger,
                        doc_kind,
                        event_obj.name,
                        document,
                        outcome="updated",
                        diff=_event_diff(before, ledger, event_obj.name),
                    )
                _say(
                    click.style("●", fg="green") + f" Successfully updated {event_obj.name}"
                )

            elif event_exists and update_page is True:
                before = _event_snapshot(ledger, event_obj.name) if is_dry_run() else None
                old_event = deepcopy(ledger.events[event_obj.name])
                for key in ["name", "productions", "working directory", "repository", "ledger"]:
                    old_event.pop(key, None)
                analyses = []
                for prod in ledger.events[event_obj.name].get("productions", []):
                    prod_name = None
                    prod_data = None

                    if isinstance(prod, dict) and len(prod) == 1:
                        prod_name, prod_data = next(iter(prod.items()))
                    elif isinstance(prod, dict):
                        prod_name = prod.get("name")
                        if prod_name:
                            prod_data = {k: v for k, v in prod.items() if k != "name"}
                        else:
                            prod_data = prod

                    if prod_data is None:
                        prod_data = {}

                    status = str(prod_data.get("status", "")).lower()
                    if update_unstarted and status in UNSTARTED_STATES:
                        merged = prod_data
                    else:
                        merged = update(prod_data, old_event, inplace=False)

                    if prod_name:
                        analyses.append({prod_name: merged})
                    else:
                        analyses.append(merged)

                # Add the old version to the history
                if "history" not in ledger.data:
                    ledger.data["history"] = {}
                history = ledger.data["history"].get(event_obj.name, {})
                version = f"version-{len(history)+1}"
                history[version] = old_event
                history[version]["date changed"] = datetime.now()

                ledger.data["history"][event_obj.name] = history
                update(ledger.events[event_obj.name], event_obj.meta)
                ledger.events[event_obj.name]["productions"] = analyses
                ledger.events[event_obj.name].pop("ledger", None)
                with ledger.transaction():
                    ledger.save()
                    _audited(
                        ledger,
                        doc_kind,
                        event_obj.name,
                        document,
                        outcome="updated",
                        diff=_event_diff(before, ledger, event_obj.name),
                    )

                _say(
                    click.style("●", fg="green") + f" Successfully updated {event_obj.name}"
                )

            elif not event_exists and update_page is False:
                with ledger.transaction():
                    ledger.update_event(event_obj)
                    _audited(ledger, doc_kind, event_obj.name, document)
                _say(
                    click.style("●", fg="green") + f" Successfully added {event_obj.name}"
                )
                logger.info(f"Added {event_obj.name} to project")

            elif not event_exists and update_page is True:
                _say(
                    click.style("●", fg="red")
                    + f" {event_obj.name} cannot be updated as there is no record of it in the project."
                )
            else:
                _say(
                    click.style("●", fg="red")
                    + f" {event_obj.name} already exists in this project."
                )

        elif document["kind"] == "analysis":
            logger.info("Found an analysis")
            document.pop("kind")

            if group is not None:
                # Made by a plugin strategy, which has already been expanded,
                # and has said which subject this is for.
                expanded_documents = [document]
                event_s = document["event"]
            else:
                # Expand a matrix strategy if present.
                expanded_documents = expand_strategy(document)

                # Determine event once for all expanded analyses
                if event:
                    event_s = event
                else:
                    if "event" in document:
                        event_s = document["event"]
                    else:
                        num_analyses = len(expanded_documents)
                        if num_analyses > 1:
                            prompt = f"Which event should these {num_analyses} analyses be applied to?"
                        else:
                            prompt = "Which event should these be applied to?"
                        event_s = str(click.prompt(prompt))

            # Resolve name overrides before constructing the Event object.
            # Reading from the raw ledger dict is cheap; get_event() is expensive
            # (it instantiates Production objects and runs git/graph operations).
            if name is not None or iterate:
                existing_names = _raw_production_names(ledger, event_s)
            for expanded_doc in expanded_documents:
                effective_name, effective_iterate = name, iterate
                if group is not None:
                    # The names are what make applying it again safe, so
                    # they are not changed, and one which was made before
                    # is left as it is.
                    if name is not None or iterate:
                        logger.warning(
                            "--name and --iterate do not apply to the analyses of a strategy; "
                            f"{expanded_doc['name']} keeps its name"
                        )
                    effective_name, effective_iterate = None, False
                    if expanded_doc["name"] in _raw_production_names(ledger, event_s):
                        group.skip(f"The analysis {event_s}/{expanded_doc['name']}")
                        continue
                if effective_name is not None:
                    expanded_doc["name"] = effective_name
                elif effective_iterate:
                    expanded_doc["name"] = next_available_name(expanded_doc["name"], existing_names)
                    # Keep existing_names current so consecutive iterations in a
                    # strategy expansion don't collide with each other.
                    existing_names.add(expanded_doc["name"])

                try:
                    if event_s not in loaded_events:
                        loaded_events[event_s] = ledger.get_event(event_s)[0]
                    event_obj = loaded_events[event_s]
                except KeyError as e:
                    _say(
                        click.style("●", fg="red")
                        + f" Could not apply a production, couldn't find the event {event_s}"
                    )
                    logger.exception(e)
                    continue
                expanded_doc[REQUESTED_BY] = _requested_by()
                production = asimov.event.Production.from_dict(
                    parameters=expanded_doc, subject=event_obj, ledger=ledger
                )
                try:
                    with ledger.transaction():
                        ledger.add_analysis(production, event=event_obj)
                        _audited(
                            ledger,
                            doc_kind,
                            f"{event_obj.name}/{production.name}",
                            expanded_doc,
                        )
                    # The YAML ledger adds it to the event itself; the database
                    # ledger only stores it.
                    if not event_obj.productions or event_obj.productions[-1] is not production:
                        event_obj.add_production(production)
                    _say(
                        click.style("●", fg="green")
                        + f" Successfully applied {production.name} to {event_obj.name}"
                    )
                    logger.info(f"Added {production.name} to {event_obj.name}")
                except ValueError as e:
                    _say(
                        click.style("●", fg="red")
                        + f" Could not apply {production.name} to {event_obj.name} as "
                        + "an analysis already exists with this name"
                    )
                    logger.exception(e)

        elif document["kind"].lower() == "postprocessing":
            # Handle a project analysis
            logger.info("Found a postprocessing description")
            document.pop("kind")
            if event:
                event_s = event

            if event:
                try:
                    event_obj = ledger.get_event(event_s)[0]
                    level = event_obj
                except KeyError as e:
                    _say(
                        click.style("●", fg="red")
                        + f" Could not apply postprocessing, couldn't find the event {event}"
                    )
                    logger.exception(e)
            else:
                level = ledger
            try:
                if document["name"] in level.data.get("postprocessing stages", {}):
                    _say(
                        click.style("●", fg="red")
                        + f" Could not apply postprocessing, as {document['name']} is already in the ledger."
                    )
                    logger.error(
                        f" Could not apply postprocessing, as {document['name']} is already in the ledger."
                    )
                else:
                    if "postprocessing stages" not in level.data:
                        level.data["postprocessing stages"] = {}
                    if isinstance(level, asimov.event.Event):
                        level.meta["postprocessing stages"][document["name"]] = document
                    elif isinstance(level, Ledger):
                        level.data["postprocessing stages"][document["name"]] = document
                        level.name = "the project"
                    with ledger.transaction():
                        ledger.save()
                        _audited(
                            ledger,
                            doc_kind,
                            level.name if isinstance(level, asimov.event.Event) else PROJECT,
                            document,
                        )
                    _say(
                        click.style("●", fg="green")
                        + f" Successfully added {document['name']} to {level.name}."
                    )
                    logger.info(f"Added {document['name']}")
            except ValueError as e:
                _say(
                    click.style("●", fg="red")
                    + f" Could not apply {document['name']} to project as "
                    + "a post-process already exists with this name"
                )
                logger.exception(e)

        elif document["kind"].lower() == "projectanalysis":
            # Handle a project analysis
            logger.info("Found a project analysis")
            document.pop("kind")
            document[REQUESTED_BY] = _requested_by()
            analysis = ProjectAnalysis.from_dict(document, ledger=ledger)

            try:
                with ledger.transaction():
                    ledger.add_analysis(analysis)
                    _audited(ledger, doc_kind, f"{PROJECT}/{analysis.name}", document)
                _say(
                    click.style("●", fg="green")
                    + f" Successfully added {analysis.name} to this project."
                )
                ledger.save()
                logger.info(f"Added {analysis.name}")
            except ValueError as e:
                if group is not None:
                    group.skip(f"The project analysis {analysis.name}")
                else:
                    _say(
                        click.style("●", fg="red")
                        + f" Could not apply {analysis.name} to project as "
                        + "an analysis already exists with this name"
                    )
                logger.exception(e)

        elif document["kind"].lower() == "analysisbundle":
            # Handle analysis bundle - a collection of analysis references
            logger.info("Found an analysis bundle")
            bundle_name = document.get("name", "unnamed bundle")
            analyses_refs = document.get("analyses", [])

            if not event:
                _say(
                    click.style("●", fg="red")
                    + f" Analysis bundle '{bundle_name}' requires an event to be specified with -e"
                )
                logger.error(f"Analysis bundle '{bundle_name}' requires an event to be specified")
                continue

            try:
                event_obj = ledger.get_event(event)[0]
            except KeyError as e:
                _say(
                    click.style("●", fg="red")
                    + f" Could not apply bundle '{bundle_name}', couldn't find the event {event}"
                )
                logger.exception(e)
                continue

            _say(
                click.style("●", fg="cyan")
                + f" Applying bundle '{bundle_name}' ({len(analyses_refs)} analyses) to {event_obj.name}"
            )

            # Resolve and apply each analysis in the bundle
            for analysis_ref in analyses_refs:
                # Analysis ref can be:
                # - A string: "bayeswave-psd" (references file stem)
                # - A dict: {"name": "...", ...} (inline definition)

                if isinstance(analysis_ref, str):
                    # Reference by file stem - need to find and load the file
                    analysis_file_name = f"{analysis_ref}.yaml"

                    # Try to find the file in common locations
                    search_paths = [
                        Path(current_context().root),  # The project directory
                        Path(current_context().root) / "analyses",  # Local analyses dir
                    ]

                    # Also check ASIMOV_DATA_PATH if set
                    if "ASIMOV_DATA_PATH" in os.environ:
                        data_path = Path(os.environ["ASIMOV_DATA_PATH"])
                        search_paths.append(data_path / "analyses")

                    # Check default asimov-data location
                    home = Path.home()
                    search_paths.append(home / ".asimov" / "gwdata" / "asimov-data" / "analyses")

                    analysis_file = None
                    for search_path in search_paths:
                        candidate = search_path / analysis_file_name
                        # Ensure the resolved path is within the expected search path
                        try:
                            candidate = candidate.resolve()
                            search_path_resolved = search_path.resolve()
                            if candidate.is_relative_to(search_path_resolved) and candidate.exists():
                                analysis_file = candidate
                                break
                        except (ValueError, OSError):
                            # Skip if path resolution fails or is invalid
                            continue

                    if not analysis_file:
                        _say(
                            click.style("  ●", fg="yellow")
                            + f" Could not find analysis file '{analysis_file_name}', skipping"
                        )
                        logger.warning(f"Could not find analysis file '{analysis_file_name}'")
                        continue

                    # Load and apply the analysis file
                    with open(analysis_file, "r") as f:
                        analysis_content = f.read()

                    # Parse the analysis file (might be multi-document)
                    for analysis_doc in yaml.safe_load_all(analysis_content):
                        if analysis_doc and analysis_doc.get("kind") == "analysis":
                            analysis_doc[REQUESTED_BY] = _requested_by()
                            try:
                                production = asimov.event.Production.from_dict(
                                    parameters=analysis_doc, subject=event_obj, ledger=ledger
                                )
                                with ledger.transaction():
                                    ledger.add_analysis(production, event=event_obj)
                                    _audited(
                                        ledger,
                                        "analysis",
                                        f"{event_obj.name}/{production.name}",
                                        analysis_doc,
                                    )
                                _say(
                                    click.style("  ●", fg="green")
                                    + f" Applied {production.name} from {analysis_ref}"
                                )
                            except ValueError as e:
                                _say(
                                    click.style("  ●", fg="yellow")
                                    + f" {analysis_doc.get('name', 'analysis')} from {analysis_ref} already exists, skipping"
                                )
                                logger.warning(f"Analysis {analysis_doc.get('name', 'analysis')} already exists: {e}")

                elif isinstance(analysis_ref, dict):
                    # Inline analysis definition
                    analysis_ref[REQUESTED_BY] = _requested_by()
                    try:
                        production = asimov.event.Production.from_dict(
                            parameters=analysis_ref, subject=event_obj, ledger=ledger
                        )
                        with ledger.transaction():
                            ledger.add_analysis(production, event=event_obj)
                            _audited(
                                ledger,
                                "analysis",
                                f"{event_obj.name}/{production.name}",
                                analysis_ref,
                            )
                        _say(
                            click.style("  ●", fg="green")
                            + f" Applied {production.name} (inline)"
                        )
                    except ValueError as e:
                        _say(
                            click.style("  ●", fg="yellow")
                            + f" {analysis_ref.get('name', 'analysis')} already exists, skipping"
                        )
                        logger.warning(f"Analysis {analysis_ref.get('name', 'analysis')} already exists: {e}")

            _say(
                click.style("●", fg="green")
                + f" Successfully applied bundle '{bundle_name}' to {event_obj.name}"
            )

        elif document["kind"] == "configuration":
            logger.info("Found configurations")
            document.pop("kind")
            with ledger.transaction():
                before = deepcopy(ledger.data) if is_dry_run() else None
                update(ledger.data, document)
                ledger.save()
                _audited(
                    ledger,
                    doc_kind,
                    PROJECT,
                    document,
                    diff=None if before is None else changed_paths(before, ledger.data),
                )
            _say(
                click.style("●", fg="green")
                + " Successfully applied a configuration update"
            )


def apply_via_plugin(event, hookname, **kwargs):
    discovered_hooks = entry_points(group="asimov.hooks.applicator")
    current_ledger = get_ledger()
    for hook in discovered_hooks:
        if hook.name in hookname:
            hook.load()(current_ledger).run(event)
            click.echo(click.style("●", fg="green") + f"{event} has been applied.")

            break
    else:
        click.echo(
            click.style("●", fg="red") + f"No hook found matching {hookname}. "
            f"Installed hooks are {', '.join(discovered_hooks.names)}"
        )


@click.command()
@click.option("--file", "-f", help="Location of the file containing the ledger items.")
@click.option(
    "--event",
    "-e",
    help="The event which the ledger items should be applied to (e.g. for analyses)",
    default=None,
)
@click.option(
    "--plugin", "-p", help="The plugin to use to apply this data", default=None
)
@click.option(
    "--update",
    "-U",
    is_flag=True,
    show_default=True,
    default=False,
    help="Update the project with this blueprint rather than adding a new record.",
)
@click.option(
    "--update-unstarted",
    is_flag=True,
    default=False,
    help="Update the event (implies --update), and let analyses which have not yet "
    "started inherit the new event settings. Analyses which have started or "
    "finished keep the settings they were created with.",
)
@click.option(
    "--name",
    "-n",
    default=None,
    help="Override the analysis name specified in the blueprint.",
)
@click.option(
    "--iterate",
    "-I",
    is_flag=True,
    default=False,
    help="Automatically increment the analysis name suffix to avoid a name conflict.",
)
@click.option(
    "--dry-run",
    "dry_run",
    is_flag=True,
    default=False,
    help="Show what would change, and what would be refused, without changing anything.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="How --dry-run reports what would change.",
)
def apply(file, event, plugin, update, update_unstarted, name, iterate, dry_run, output_format):
    from asimov import setup_file_logging
    if dry_run and plugin:
        raise click.UsageError("--dry-run can't be used with --plugin.")
    if output_format != "text" and not dry_run:
        raise click.UsageError("--format is for --dry-run.")
    current_ledger = get_ledger()
    if not dry_run:
        setup_file_logging()
    if plugin:
        apply_via_plugin(event, hookname=plugin)
    elif file:
        plan = apply_page(
            file,
            event,
            ledger=current_ledger,
            update_page=update,
            name=name,
            iterate=iterate,
            update_unstarted=update_unstarted,
            dry_run=dry_run,
        )
        if dry_run:
            if output_format == "json":
                click.echo(json.dumps(plan.to_dict(), indent=2, default=str))
            else:
                click.echo("\n".join(plan.render()))
